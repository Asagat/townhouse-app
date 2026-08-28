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
                       aa.code AS article_code, aa.name AS article_name
                FROM cash_register cr
                JOIN transactions t ON t.id = cr.transaction_id
                LEFT JOIN accounts a ON a.id = cr.account_id
                LEFT JOIN analytic_articles aa ON aa.id = t.article_id
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
                    "article_code": r[8],
                    "article_name": r[9],
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
