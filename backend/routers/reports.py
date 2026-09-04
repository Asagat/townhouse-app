# backend/routers/reports.py
"""Отчёты (п. 2.11 роадмапа).

Первый реализованный отчёт — «Отчёт по кассе»: движение денег по кассам/счетам
за период (остаток на начало, приход, расход, остаток на конец) из `cash_register`
с разбивкой по документам «Приход/Расход».

Данные берутся напрямую из регистра денежных средств (`cash_register`) —
единственного источника движения денег, поэтому отчёт всегда согласован с
фактическим учётом (без пересчёта среза).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from models import User


router = APIRouter(prefix="/api")


def _fmt(v) -> float:
    return float(round(Decimal(str(v or 0)), 2))


def build_cash_register_report(
    db: Session,
    from_date: str | None,
    to_date: str | None,
    cash_point_id: int | None = None,
) -> dict:
    """
    Отчёт по кассе за период.

    - Период: даты 'YYYY-MM-DD'. Если не заданы — берём за всё время.
    - Начальный остаток по кассе — баланс последней записи ДО начала периода.
    - Приход/расход за период — суммы income/expense из cash_register.
    - Конечный остаток = начальный + приход - расход.
    - Опционально фильтр по кассе (cash_point_id).
    """
    from_hour = _parse_day(from_date, True)
    to_hour = _parse_day(to_date, False)
    if from_hour and to_hour and from_hour > to_hour:
        raise HTTPException(status_code=422, detail="Дата начала позже даты конца")

    # Список касс (всех, или одной выбранной).
    if cash_point_id:
        points = db.execute(
            text("SELECT id, name, is_active FROM cash_points WHERE id = :id"),
            {"id": cash_point_id},
        ).fetchall()
        if not points:
            raise HTTPException(status_code=404, detail="Касса не найдена")
    else:
        points = db.execute(
            text("SELECT id, name, is_active FROM cash_points ORDER BY id"),
        ).fetchall()

    # Начальные остатки по кассам (баланс последней записи ДО начала периода).
    opening: dict[int, float] = {p.id: 0.0 for p in points}
    if from_hour is not None:
        for p in points:
            row = db.execute(
                text("""
                    SELECT cr.balance_after
                    FROM cash_register cr
                    JOIN transactions t ON t.id = cr.transaction_id
                    WHERE t.cash_point_id = :cp AND cr.operation_date < :start
                    ORDER BY cr.operation_date DESC, cr.id DESC
                    LIMIT 1
                """),
                {"cp": p.id, "start": from_hour},
            ).first()
            opening[p.id] = _fmt(row[0]) if row and row[0] is not None else 0.0

    # Движение за период по кассам + детализация по документам.
    movements: list[dict] = []
    per_cp: dict[int, dict] = {
        p.id: {"income": 0.0, "expense": 0.0} for p in points
    }

    for p in points:
        where = ["t.cash_point_id = :cp"]
        params: dict[str, Any] = {"cp": p.id, "start": from_hour, "end": to_hour}
        if from_hour is not None:
            where.append("cr.operation_date >= :start")
        if to_hour is not None:
            where.append("cr.operation_date <= :end")
        rows = db.execute(
            text(f"""
                SELECT cr.id, cr.operation_date, cr.income, cr.expense,
                       t.title, t.id AS transaction_id,
                       a.account_number, a.account_name,
                       aa.name AS article_name,
                       o.full_name AS contractor_name
                FROM cash_register cr
                JOIN transactions t ON t.id = cr.transaction_id
                LEFT JOIN accounts a ON a.id = cr.account_id
                LEFT JOIN analytic_articles aa ON aa.id = t.article_id
                LEFT JOIN counterparties o ON o.id = t.contractor_id
                WHERE {' AND '.join(where)}
                ORDER BY cr.operation_date ASC, cr.id ASC
            """),
            params,
        ).fetchall()

        for r in rows:
            income = _fmt(r[2])
            expense = _fmt(r[3])
            per_cp[p.id]["income"] += income
            per_cp[p.id]["expense"] += expense
            movements.append(
                {
                    "cash_point_id": p.id,
                    "cash_point_name": p.name,
                    "operation_date": r[1].isoformat() if r[1] else None,
                    "document_title": r[4],
                    "transaction_id": r[5],
                    "account_number": r[6],
                    "account_name": r[7],
                    "article_name": r[8],
                    "contractor_name": r[9],
                    "income": income,
                    "expense": expense,
                    "amount": income if income else -expense,
                }
            )

    # Итоговая сводка по кассам и общие суммы.
    cash_points: list[dict] = []
    totals = {"opening": 0.0, "income": 0.0, "expense": 0.0, "closing": 0.0}
    for p in points:
        inc = per_cp[p.id]["income"]
        exp = per_cp[p.id]["expense"]
        closing = opening[p.id] + inc - exp
        cash_points.append(
            {
                "cash_point_id": p.id,
                "cash_point_name": p.name,
                "is_active": bool(p.is_active),
                "opening": round(opening[p.id], 2),
                "income": round(inc, 2),
                "expense": round(exp, 2),
                "closing": round(closing, 2),
            }
        )
        totals["opening"] += opening[p.id]
        totals["income"] += inc
        totals["expense"] += exp
        totals["closing"] += closing

    movements.sort(key=lambda x: (x["operation_date"] or "", x["transaction_id"] or 0))

    return {
        "period": {"from": from_date, "to": to_date},
        "totals": {k: round(v, 2) for k, v in totals.items()},
        "cash_points": cash_points,
        "movements": movements,
    }


def _parse_day(value: str | None, is_start: bool):
    """Парсит дату в datetime границу периода (начало/конец суток) или None."""
    if not value:
        return None
    try:
        day = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="Некорректная дата (YYYY-MM-DD)")
    return day.replace(hour=0 if is_start else 23, minute=0 if is_start else 59,
                       second=0 if is_start else 59)


@router.get("/reports/cash_register")
def cash_register_report(
    from_date: str | None = Query(None, description="Начало периода YYYY-MM-DD"),
    to_date: str | None = Query(None, description="Конец периода YYYY-MM-DD"),
    cash_point_id: int | None = Query(None, description="Фильтр по кассе"),
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("admin", "operator", "cashier")),
):
    """Отчёт по кассе: движение денег по кассам/счетам за период.

    Доступен только бухгалтерским ролям (admin/operator/cashier); resident/контролёр — нет.
    """
    return build_cash_register_report(db, from_date, to_date, cash_point_id)


def build_expense_report(
    db: Session,
    from_date: str | None,
    to_date: str | None,
    cash_point_id: int | None = None,
) -> dict:
    """Отчёт по расходам за период.

    - Берётся только расходная часть движения кассы (cash_register.expense > 0) за период;
    - агрегируется ИТОГ расходов и разбивка ПО СТАТЬЯМ расходов (analytic_articles kind='expense');
    - детализация по документам-расходам (movements) — сетка, аналогичная кассир отчёту,
      но только по расходной стороне;
    - опционально фильтр по кассе (cash_point_id).
    """
    from_hour = _parse_day(from_date, True)
    to_hour = _parse_day(to_date, False)
    if from_hour and to_hour and from_hour > to_hour:
        raise HTTPException(status_code=422, detail="Дата начала позже даты конца")

    where = ["cr.expense > 0"]
    params: dict[str, Any] = {"start": from_hour, "end": to_hour, "cp": cash_point_id}
    if from_hour is not None:
        where.append("cr.operation_date >= :start")
    if to_hour is not None:
        where.append("cr.operation_date <= :end")
    if cash_point_id:
        where.append("t.cash_point_id = :cp")

    rows = db.execute(
        text(f"""
            SELECT cr.operation_date, cr.income, cr.expense,
                   t.cash_point_id,
                   t.title, t.id AS transaction_id,
                   COALESCE(a.account_number,'') AS account_number,
                   aa.name AS article_name,
                   o.full_name AS contractor_name
            FROM cash_register cr
            JOIN transactions t ON t.id = cr.transaction_id
            LEFT JOIN accounts a ON a.id = cr.account_id
            LEFT JOIN analytic_articles aa ON aa.id = t.article_id
            LEFT JOIN counterparties o ON o.id = t.contractor_id
            WHERE {' AND '.join(where)}
            ORDER BY cr.operation_date ASC, cr.id ASC
        """),
        params,
    ).fetchall()

    movements: list[dict] = []
    by_article: dict[str, float] = {}
    grand_total = 0.0
    for r in rows:
        exp = _fmt(r[2])
        grand_total += exp
        art_name = r[7]
        by_article[art_name or "Без статьи"] = by_article.get(art_name or "Без статьи", 0.0) + exp
        movements.append(
            {
                "cash_point_id": r[3],
                "transaction_id": r[5],
                "operation_date": r[0].isoformat() if r[0] else None,
                "document_title": r[4],
                "article_name": art_name,
                "contractor_name": r[8],
                "account_number": r[6] or None,
                "amount": round(exp, 2),
            }
        )

    articles = [
        {"name": k, "expense": round(v, 2)}
        for k, v in sorted(by_article.items(), key=lambda kv: -kv[1])
    ]
    movements.sort(key=lambda x: (x["operation_date"] or "", x["transaction_id"] or 0))

    return {
        "period": {"from": from_date, "to": to_date},
        "total_expense": round(grand_total, 2),
        "articles": articles,
        "movements": movements,
        "count": len(movements),
    }


@router.get("/reports/expenses")
def expense_report(
    from_date: str | None = Query(None, description="Начало периода YYYY-MM-DD"),
    to_date: str | None = Query(None, description="Конец периода YYYY-MM-DD"),
    cash_point_id: int | None = Query(None, description="Фильтр по кассе"),
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("admin", "operator", "cashier")),
):
    """Отчёт по расходам: расход кассы за период (итог, по статьям, детализация)."""
    return build_expense_report(db, from_date, to_date, cash_point_id)


# --- Отчёт по должникам ---


def _account_balance_metrics(db: Session, account_id: int) -> dict:
    """Метрики баланса по л/с: начислено/списано по услугам, внесено, долг/переплата.

    Согласовано с build_account_statement: долг = начислено − списано (>=0),
    переплата = внесено − списано (>=0).
    """
    def _one(q: str) -> float:
        return float(db.execute(text(q), {"a": account_id}).scalar() or 0.0)

    accrued = _one(
        "SELECT COALESCE(SUM(income),0) FROM accounts_register "
        "WHERE account_id=:a AND services_type_id IS NOT NULL"
    )
    paid = _one(
        "SELECT COALESCE(SUM(expense),0) FROM accounts_register "
        "WHERE account_id=:a AND services_type_id IS NOT NULL"
    )
    available = _one(
        "SELECT COALESCE(SUM(income - expense),0) FROM cash_register WHERE account_id=:a"
    )
    debt = max(0.0, accrued - paid)
    overpayment = max(0.0, available - paid)
    return {
        "accrued": round(accrued, 2),
        "paid": round(paid, 2),
        "available": round(available, 2),
        "debt": round(debt, 2),
        "overpayment": round(overpayment, 2),
    }


def build_debtors_report(db: Session, min_amount: float = 0.0) -> dict:
    """Список должников: активные л/с с положительным долгом, по убыванию долга."""
    accounts = db.execute(text(
        "SELECT a.id, a.account_number, a.account_name, ap.apartment_number AS kv, "
        "       ap.address, o.full_name AS owner FROM accounts a "
        "LEFT JOIN apartments ap ON ap.id = a.apartment_id "
        "LEFT JOIN counterparties o ON o.id = ap.owner_id "
        "WHERE a.is_active ORDER BY a.account_number"
    )).fetchall()

    rows = []
    for acc in accounts:
        m = _account_balance_metrics(db, int(acc[0]))
        if m["debt"] > min_amount:
            rows.append({
                "account_id": int(acc[0]),
                "account_number": acc[1],
                "account_name": acc[2],
                "apartment_number": acc[3],
                "address": acc[4],
                "owner_name": acc[5],
                "accrued": m["accrued"],
                "paid": m["paid"],
                "debt": m["debt"],
                "overpayment": m["overpayment"],
            })
    rows.sort(key=lambda r: -r["debt"])
    total_debt = round(sum(r["debt"] for r in rows), 2)
    return {"rows": rows, "total_debt": total_debt, "count": len(rows)}


@router.get("/reports/debtors")
def debtors_report(
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("admin", "operator", "cashier")),
):
    """Отчёт по должникам: активные л/с с долгом, по убыванию."""
    return build_debtors_report(db)


# --- Выписка по лицевому счёту ---


def build_statement_report(db: Session, account_id: int, from_date: str | None = None,
                           to_date: str | None = None) -> dict:
    """Выписка по л/с: помесячно — начислено, списано (по услугам), остаток на конец."""
    acc = db.execute(text(
        "SELECT a.id, a.account_number, a.account_name, ap.apartment_number AS kv, "
        "       o.full_name AS owner FROM accounts a "
        "LEFT JOIN apartments ap ON ap.id = a.apartment_id "
        "LEFT JOIN counterparties o ON o.id = ap.owner_id "
        "WHERE a.id = :id"), {"id": account_id}).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Лицевой счёт не найден")

    from_hour = _parse_day(from_date, True)
    to_hour = _parse_day(to_date, False)
    if from_hour and to_hour and from_hour > to_hour:
        raise HTTPException(status_code=422, detail="Дата начала позже даты конца")

    # Месяцы с движением по счёту (публикуем по датам строк взаиморасчётов).
    rows = db.execute(
        text("""
            SELECT date_trunc('month', operation_date)::date AS m
            FROM accounts_register WHERE account_id = :a
            GROUP BY 1 ORDER BY 1
        """),
        {"a": account_id},
    ).fetchall()

    months = []
    for (m,) in rows:
        if from_hour is not None and m < from_hour.date():
            continue
        if to_hour is not None and m > to_hour.date():
            break
        months.append(m)

    monthly = []
    prev_month_end = None
    for m in months:
        import calendar as _cal
        end = datetime(m.year, m.month, _cal.monthrange(m.year, m.month)[1], 23, 59, 59)
        params = {"a": account_id, "start": m, "end": end}
        accrued = float(db.execute(
            text("SELECT COALESCE(SUM(income),0) FROM accounts_register "
                 "WHERE account_id=:a AND services_type_id IS NOT NULL "
                 "AND operation_date>=:start AND operation_date<=:end"), params).scalar() or 0.0)
        paid = float(db.execute(
            text("SELECT COALESCE(SUM(expense),0) FROM accounts_register "
                 "WHERE account_id=:a AND services_type_id IS NOT NULL "
                 "AND operation_date>=:start AND operation_date<=:end"), params).scalar() or 0.0)
        closing = float(db.execute(
            text("SELECT balance_after FROM accounts_register WHERE account_id=:a "
                 "ORDER BY operation_date DESC, id DESC LIMIT 1"), {"a": account_id}).scalar() or 0.0)
        monthly.append({
            "period": m.strftime("%Y-%m"),
            "accrued": round(accrued, 2),
            "paid": round(paid, 2),
            "closing": round(closing, 2),
        })

    return {
        "account": {
            "id": account_id,
            "account_number": acc[1],
            "account_name": acc[2],
            "apartment_number": acc[3],
            "owner_name": acc[4],
        },
        "monthly": monthly,
        "closing": round(monthly[-1]["closing"], 2) if monthly else 0.0,
    }


@router.get("/reports/statement")
def statement_report(
    account_id: int = Query(..., description="ID лицевого счёта"),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("admin", "operator", "cashier")),
):
    """Выписка по лицевому счёту: помесячно начислено/списано/остаток."""
    return build_statement_report(db, account_id, from_date, to_date)
