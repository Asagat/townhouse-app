# backend/routers/dashboard.py
"""Дашборд главной страницы (задача 2.19 роадмапа).

Информационная сводка по дому «на сейчас», БЕЗ параметров и срезов (углубление —
в существующие отчёты). Все метрики согласованы с «источником истины» — денежными
регистрами и повторяют формулу/смысл уже готовых отчётов:

  - потоки за последние 30 дней (по operation_date строк регистров):
      Начислено   = Σ income  в accounts_register (записи с видом услуги);
      Внесено     = Σ income  в cash_register (реально поступившие деньги);
      Списано     = Σ expense в accounts_register (по услугам) = погашение долга
                    (совпадает с суммарной «Оплачено» отчётов);
      Расходы     = Σ expense в cash_register = выбытие денег из кассы (по статьям).

  - состояния (кумулятивно, на сегодня), чтобы совпадали с отчётами «на сейчас»:
      Долг        = Σ по активным л/с max(0, начислено − погашено) — та же формула,
                    что `build_debtors_report.total_debt`;
      Остаток     = Σ (income − expense) по cash_register — то, что даёт
                    «Остаток на конец» отчёта по кассе.
"""

import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from models import User


router = APIRouter(prefix="/api")

# Окно «последние 30 дней» для потоков.
WINDOW_DAYS = 30


def _fmt(v) -> float:
    return float(round(Decimal(str(v or 0)), 2))


def _pad_month(ym: int):
    """Год/месяц из «плоского» номера (год*12+месяц-1)."""
    y, zero = divmod(ym, 12)
    return y, zero + 1


def _window_bounds():
    """(from_dt, to_dt) окна потоков: последние 30 дней по operation_date."""
    to_dt = datetime.now()
    from_dt = to_dt - timedelta(days=WINDOW_DAYS)
    return from_dt, to_dt


def build_house_metrics(db: Session) -> dict:
    """Одно состояние и денежное движение за последние 30 дней по всем записям."""
    from_dt, to_dt = _window_bounds()

    # --- Потоки за окно 30 дней (по фактической дате строки в регистре) ---
    # Начислено / Списано(погашение долга) — accounts_register по услугам.
    accrual_row = db.execute(
        text("""
            SELECT
                COALESCE(SUM(CASE WHEN operation_date >= :f AND operation_date <= :t THEN income END),0) AS accrued,
                COALESCE(SUM(CASE WHEN operation_date >= :f AND operation_date <= :t THEN expense END),0) AS paid
            FROM accounts_register
            WHERE services_type_id IS NOT NULL
        """),
        {"f": from_dt, "t": to_dt},
    ).first()
    accrued_window = _fmt(accrual_row[0])
    written_off_window = _fmt(accrual_row[1])  # погашение долга за окно

    # Внесено в кассу (приход денег) за окно.
    received = _fmt(
        db.execute(
            text("SELECT COALESCE(SUM(income),0) FROM cash_register "
                 "WHERE operation_date >= :f AND operation_date <= :t"),
            {"f": from_dt, "t": to_dt},
        ).scalar()
    )

    # --- Состояния на сейчас (кумулятивно, вся история) ---
    # Остаток денежных средств = Σ(income − expense) по всем строкам кассового регистра.
    cash_balance = _fmt(
        db.execute(
            text("SELECT COALESCE(SUM(income - expense),0) FROM cash_register")
        ).scalar()
    )

    debt_info = _house_debt(db)
    return {
        "metrics": {
            "accrued": accrued_window,
            "received": received,
            "written_off": written_off_window,
            "debt": debt_info["total_debt"],
            "cash_balance": cash_balance,
            "debtors_count": debt_info["count"],
        },
    }


def _account_net(db: Session):
    """Итоговая нетто-сводка по каждому активному л/с: accrued/paid за всю историю.

    Возвращает список dict: account_id, account_number, apartment_number, owner_name,
    accrued, paid, debt (= max(0, accrued−paid)). Фильтр accounts.is_active — как в
    отчёте должников (в расчёт только текущие л/с).
    """
    rows = db.execute(
        text("""
        SELECT a.id AS account_id,
               a.account_number,
               ap.apartment_number,
               o.full_name AS owner_name,
               COALESCE(SUM(CASE WHEN ar.services_type_id IS NOT NULL THEN ar.income END),0) AS accrued,
               COALESCE(SUM(CASE WHEN ar.services_type_id IS NOT NULL THEN ar.expense END),0) AS paid
        FROM accounts a
        LEFT JOIN apartments ap ON ap.id = a.apartment_id
        LEFT JOIN counterparties o ON o.id = ap.owner_id
        LEFT JOIN accounts_register ar ON ar.account_id = a.id
        WHERE a.is_active = TRUE
        GROUP BY a.id, a.account_number, ap.apartment_number, o.full_name
        ORDER BY a.account_number
        """)
    ).fetchall()

    net = []
    for r in rows:
        accrued = _fmt(r[4])
        paid = _fmt(r[5])
        debt = max(0.0, accrued - paid)
        net.append({
            "account_id": int(r[0]),
            "account_number": r[1],
            "apartment_number": r[2],
            "owner_name": r[3],
            "accrued": accrued,
            "paid": paid,
            "debt": debt,
        })
    return net


def _house_debt(db: Session) -> dict:
    """Суммарный долг по активным л/с (формула отчёта должников) и число должников."""
    net = _account_net(db)
    debtors = [n for n in net if n["debt"] > 0]
    return {
        "count": len(debtors),
        "total_debt": round(sum(n["debt"] for n in debtors), 2),
    }


def build_top_debtors(db: Session, limit: int = 5) -> list[dict]:
    """Краткий топ должников по величине долга (для блока «Должники»)."""
    net = _account_net(db)
    debtors = sorted([n for n in net if n["debt"] > 0], key=lambda x: -x["debt"])
    return debtors[:limit]


def build_debt_dynamics(db: Session, months: int = 12) -> list[dict]:
    """Динамика долга по месяцам: долг «на конец» каждого из последних `months` месяцев.

    Долг на конец месяца = Σ по активным л/с max(0, начислено − погашено), где
    начислено/погашено — кумулятивно по всей истории счёта до конца этого месяца.
    Возвращает список по возрастанию периодов YYYY-MM → {"month", "debt", "label"}.
    """
    # Помесячные суммы по каждому л/с (вся история) — строим кумулятив в памяти.
    rows = db.execute(
        text("""
            SELECT ar.account_id,
                   date_trunc('month', ar.operation_date)::date AS m,
                   COALESCE(SUM(CASE WHEN ar.services_type_id IS NOT NULL THEN ar.income END),0) AS inc,
                   COALESCE(SUM(CASE WHEN ar.services_type_id IS NOT NULL THEN ar.expense END),0) AS exp
            FROM accounts_register ar
            JOIN accounts a ON a.id = ar.account_id
            WHERE ar.services_type_id IS NOT NULL AND a.is_active = TRUE
            GROUP BY ar.account_id, 2
            ORDER BY ar.account_id, 2
        """)
    ).fetchall()

    # Кумулятив по счёту: последовательность (month_idx, cum_inc, cum_exp).
    run: dict[int, list[tuple[int, float, float]]] = {}
    for r in rows:
        acc_id = int(r[0])
        idx = r[1].year * 12 + (r[1].month - 1)
        inc = _fmt(r[2])
        exp = _fmt(r[3])
        bucket = run.setdefault(acc_id, [])
        prev_inc = bucket[-1][1] if bucket else 0.0
        prev_exp = bucket[-1][2] if bucket else 0.0
        bucket.append((idx, prev_inc + inc, prev_exp + exp))

    # Последние `months` месяцев, включая текущий.
    today = date.today()
    cur_idx = today.year * 12 + (today.month - 1)
    dynamics = []
    for k in range(months - 1, -1, -1):
        idx = cur_idx - k
        y, m = _pad_month(idx)
        total = 0.0
        for bucket in run.values():
            # точка «на конец месяца» = последний кумулятивный вклад с month_idx <= idx
            point = None
            for item in bucket:
                if item[0] <= idx:
                    point = item
                else:
                    break
            if point is not None:
                total += max(0.0, point[1] - point[2])
        dynamics.append({
            "month": f"{y:04d}-{m:02d}",
            "debt": round(total, 2),
            "label": f"{_month_name(m)} {y}",
        })
    return dynamics


def _month_name(month: int) -> str:
    return ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"][month - 1]


def build_expenses(pool: Session) -> dict:
    """Расходы по кассе за последние 30 дней: итог и разбивка по статьям расходов.

    Переиспользует источник отчёта по расходам (`cash_register.expense > 0`).
    """
    from_dt, to_dt = _window_bounds()
    rows = pool.execute(
        text("""
            SELECT aa.name AS article_name,
                   COALESCE(SUM(cr.expense),0) AS exp
            FROM cash_register cr
            LEFT JOIN transactions t ON t.id = cr.transaction_id
            LEFT JOIN analytic_articles aa ON aa.id = t.article_id
            WHERE cr.expense > 0 AND cr.operation_date >= :f AND cr.operation_date <= :t
            GROUP BY aa.name ORDER BY 2 DESC
        """),
        {"f": from_dt, "t": to_dt},
    ).fetchall()
    articles = [{"name": r[0] or "Без статьи", "expense": _fmt(r[1])} for r in rows]
    total = round(sum(a["expense"] for a in articles), 2)
    return {"total": total, "articles": articles, "count": len(articles)}


@router.get("/dashboard")
def dashboard(
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("admin", "operator", "cashier", "auditor")),
):
    """Дашборд главной страницы — информационная сводка по дому «на сейчас»."""
    metrics = build_house_metrics(db)
    debtors = build_top_debtors(db, limit=5)
    dynamics = build_debt_dynamics(db, months=12)
    expenses = build_expenses(db)
    return {
        "metrics": metrics["metrics"],
        "top_debtors": debtors,
        "debt_dynamics": dynamics,
        "expenses": expenses,
        "window_days": WINDOW_DAYS,
    }
