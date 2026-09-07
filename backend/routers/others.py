# backend/routers/others.py
"""Прочие специальные эндпоинты (ЭТАП 3 роадмапа).

Вынесен из `app.py`: отчёт по лицевому счёту (`accounts/{id}/statement`) вместе
с его helpers (`build_account_statement`, `_current_account_balance`).
Логика сохранена без изменений.
"""

import io
from datetime import datetime

from auth import get_current_user
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

import statement_pdf as spdf
from models import Account, User, UserRole
from services import _service_name


router = APIRouter(prefix="/api")


def _current_account_balance(db: Session, account_id: int) -> float:
    """Текущий баланс лицевого счёта — последняя запись accounts_register.

    По конвенции («КОНВЕНЦИЯ ЗНАКОВ» в models.py) это долг по услугам:
    = SUM(income) - SUM(expense) по accounts_register. Положительный = долг;
    переплата (деньги сверх распределённых) тут не отражается — см.
    _account_debt_overpayment в отчёте.
    """
    value = db.execute(
        text("SELECT balance_after FROM accounts_register WHERE account_id = :account_id "
             "ORDER BY operation_date DESC, id DESC LIMIT 1"),
        {"account_id": account_id},
    ).scalar()
    return float(value) if value is not None else 0.0


def build_account_statement(db: Session, account_id: int) -> dict:
    """
    Сводка по лицевому счёту для отчёта / личного кабинета.

    Метрики считаются НЕПОСРЕДСТВЕННО из регистров (а не по-знаковому balance_after),
    поэтому корректны при целевой конвенции знаков (income = начислено, expense = списано):

      - начислено по услугам  = Σ income записей accounts_register с видом услуги;
      - оплачено по услугам   = Σ expense записей accounts_register с видом услуги
                                 (это же и есть строки «списание»);
      - внесено на счёт       = Σ(income - expense) из cash_register;
      - долг по услуге        = начислено - оплачено;
      - переплата (аванс)     = внесено - оплачено (>=0) — свободные деньги сверх
                                 распределённых по услугам.
    """
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise KeyError(account_id)

    # Свод по услугам из регистра взаиморасчётов.
    svc_rows = db.execute(
        text("""
            SELECT services_type_id,
                   COALESCE(SUM(income), 0)  AS accrued,
                   COALESCE(SUM(expense), 0) AS paid
            FROM accounts_register
            WHERE account_id = :a AND services_type_id IS NOT NULL
            GROUP BY services_type_id
            ORDER BY MIN(id)
        """),
        {"a": account_id},
    ).fetchall()

    services = []
    accrued_total = 0.0
    paid_total = 0.0
    for row in svc_rows:
        svc_id = row[0]
        accrued = float(row[1] or 0.0)
        paid = float(row[2] or 0.0)
        debt = max(0.0, accrued - paid)
        accrued_total += accrued
        paid_total += paid
        services.append(
            {
                "services_type_id": svc_id,
                "service_name": _service_name(db, svc_id),
                "accrued": round(accrued, 2),
                "paid": round(paid, 2),
                "debt": round(debt, 2),
            }
        )

    services.sort(key=lambda s: (s["service_name"] or ""))

    # Внесено (доступно) из регистра денежных средств.
    available = db.execute(
        text("SELECT COALESCE(SUM(income - expense), 0) FROM cash_register WHERE account_id = :a"),
        {"a": account_id},
    ).scalar()
    available = float(available or 0.0)

    debt_total = max(0.0, accrued_total - paid_total)
    overpayment = max(0.0, available - paid_total)
    balance = _current_account_balance(db, account_id)

    apartment = account.apartment
    owner = apartment.owner if apartment else None

    return {
        "account": {
            "id": account.id,
            "account_number": account.account_number,
            "account_name": account.account_name,
        },
        "apartment": (
            {
                "id": apartment.id,
                "apartment_number": apartment.apartment_number,
                "address": apartment.address,
            }
            if apartment
            else None
        ),
        "owner": (
            {
                "id": owner.id,
                "full_name": owner.full_name,
                "phone": owner.phone,
            }
            if owner
            else None
        ),
        "metrics": {
            "accrued_total": round(accrued_total, 2),
            "paid_total": round(paid_total, 2),
            "available": round(available, 2),
            "debt_total": round(debt_total, 2),
            "overpayment": round(overpayment, 2),
            "balance": round(balance, 2),
        },
        "services": services,
    }


@router.get("/accounts/{account_id}/statement")
def get_account_statement(
    account_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Отчёт по лицевому счёту: начислено / оплачено / долг по услугам, внесено / переплата.

    Админ/оператор/кассир/контролёр — любой счёт. Для роли resident доступен
    только собственный счёт (привязка users.account_id).
    """
    _ensure_can_view_account(db, user, account_id)
    try:
        return build_account_statement(db, account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Лицевой счёт не найден")


def _parse_period_bound(value: str | None, is_start: bool):
    """Парсит границу периода YYYY-MM-DD в datetime (начало/конец суток)."""
    if not value:
        return None
    try:
        d = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="Некорректная дата (YYYY-MM-DD)")
    if is_start:
        return d.replace(hour=0, minute=0, second=0, microsecond=0)
    return d.replace(hour=23, minute=59, second=59, microsecond=999999)


def _period_label(from_date: str | None, to_date: str | None) -> str:
    if from_date and to_date:
        return f"с {from_date[8:10]}.{from_date[5:7]}.{from_date[:4]} по {to_date[8:10]}.{to_date[5:7]}.{to_date[:4]}"
    if from_date:
        return f"с {from_date[8:10]}.{from_date[5:7]}.{from_date[:4]}"
    if to_date:
        return f"по {to_date[8:10]}.{to_date[5:7]}.{to_date[:4]}"
    return "за всё время"


def build_account_movements(db: Session, account_id: int,
                            from_date: str | None = None,
                            to_date: str | None = None) -> dict:
    """Движения по лицевому счёту за период (источник — accounts_register).

    Каждая строка регистра взаиморасчётов классифицируется:
      - income>0 (accrual_id)  — «Начисление»;
      - expense>0 с writeoff_id — «Списание задолженностей»;
      - expense>0 с transaction — «Оплата» (распределение внесённых денег).
    Сумма отображается с точки зрения счёта: начисление «+», оплата/списание «−».
    """
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Лицевой счёт не найден")

    frm = _parse_period_bound(from_date, True)
    to = _parse_period_bound(to_date, False)
    if frm and to and frm > to:
        raise HTTPException(status_code=422, detail="Дата начала позже даты конца")

    params: dict = {"a": account_id}
    period_sql = ""
    if frm is not None:
        period_sql += " AND ar.operation_date >= :frm"
        params["frm"] = frm
    if to is not None:
        period_sql += " AND ar.operation_date <= :to"
        params["to"] = to

    rows = db.execute(text(
        "SELECT ar.operation_date, ar.services_type_id,"
        "       COALESCE(ar.income,0) AS inc, COALESCE(ar.expense,0) AS exp,"
        "       ar.balance_after, ar.accrual_id, ar.transaction_id, ar.writeoff_id,"
        "       st.services_type AS service, tx.title AS tx_title, wo.title AS wo_title "
        "FROM accounts_register ar "
        "LEFT JOIN services_type st ON st.id = ar.services_type_id "
        "LEFT JOIN transactions tx ON tx.id = ar.transaction_id "
        "LEFT JOIN writeoff_documents wo ON wo.id = ar.writeoff_id "
        "WHERE ar.account_id = :a" + period_sql + " "
        "ORDER BY ar.operation_date, ar.id"
    ), params).fetchall()

    movements = []
    for r in rows:
        m = r._mapping
        inc = float(m["inc"] or 0.0)
        exp = float(m["exp"] or 0.0)
        service = m["service"] or "—"
        writeoff_id = m["writeoff_id"]
        if inc > 0:
            kind, kind_label, amount = "accrual", "Начисление", inc
        elif exp > 0 and writeoff_id:
            kind, kind_label, amount = "writeoff", "Списание", -exp
        else:
            kind, kind_label, amount = "payment", "Оплата", -exp
        movements.append({
            "date": m["operation_date"].strftime("%Y-%m-%d") if m["operation_date"] else None,
            "kind": kind,
            "kind_label": kind_label,
            "service": service,
            "amount": round(amount, 2),
            "balance_after": round(float(m["balance_after"] or 0.0), 2),
            "document": (m["tx_title"] or m["wo_title"]) or None,
        })

    apartment = account.apartment
    owner = apartment.owner if apartment else None

    # --- Сводка за период (для блока «Движения»: Начислено/Внесено/Списано/Долг). ---
    def _sum_sql(expr: str, table: str, extra: str = "") -> float:
        sql = (f"SELECT COALESCE(SUM({expr}),0) FROM {table} "
               f"WHERE account_id = :a{extra}")
        p: dict = {"a": account_id}
        if frm is not None:
            p["frm"] = frm
        if to is not None:
            p["to"] = to
        return float(db.execute(text(sql), p).scalar() or 0.0)

    period_extra = ""
    if frm is not None:
        period_extra += " AND operation_date >= :frm"
    if to is not None:
        period_extra += " AND operation_date <= :to"
    accrued = _sum_sql(
        "income", "accounts_register",
        " AND services_type_id IS NOT NULL" + period_extra)
    paid = _sum_sql(
        "expense", "accounts_register",
        " AND services_type_id IS NOT NULL" + period_extra)
    available = _sum_sql("income - expense", "cash_register", period_extra)

    # Долг на конец периода — накопленное (начислено − списано) до конца периода.
    hist_extra = ""
    hist_params: dict = {"a": account_id}
    if to is not None:
        hist_extra = " AND operation_date <= :to"
        hist_params["to"] = to
    hist_accrued = float(db.execute(text(
        "SELECT COALESCE(SUM(income),0) FROM accounts_register "
        "WHERE account_id = :a AND services_type_id IS NOT NULL" + hist_extra),
        hist_params).scalar() or 0.0)
    hist_paid = float(db.execute(text(
        "SELECT COALESCE(SUM(expense),0) FROM accounts_register "
        "WHERE account_id = :a AND services_type_id IS NOT NULL" + hist_extra),
        hist_params).scalar() or 0.0)

    return {
        "account": {
            "id": account.id,
            "account_number": account.account_number,
            "account_name": account.account_name,
            "apartment_number": apartment.apartment_number if apartment else None,
            "owner_name": owner.full_name if owner else None,
        },
        "metrics": {
            "accrued": round(accrued, 2),
            "paid": round(paid, 2),
            "available": round(available, 2),
            "debt": round(max(0.0, hist_accrued - hist_paid), 2),
        },
        "movements": movements,
        "closing": round(float(movements[-1]["balance_after"]), 2) if movements else 0.0,
    }


@router.get("/me/movements")
def get_my_movements(
    from_date: str | None = None,
    to_date: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Движения по своему лицевому счёту (ЛК жителя)."""
    account_id = _get_user_account(db, user)
    return build_account_movements(db, account_id, from_date, to_date)


@router.get("/accounts/{account_id}/movements")
def get_account_movements(
    account_id: int,
    from_date: str | None = None,
    to_date: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Движения по лицевому счёту (для ролей с доступом; resident — только свой)."""
    _ensure_can_view_account(db, user, account_id)
    return build_account_movements(db, account_id, from_date, to_date)


@router.get("/me/statement/pdf")
def get_my_statement_pdf(
    from_date: str | None = None,
    to_date: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """PDF выписки-движений по своему лицевому счёту (ЛК жителя)."""
    account_id = _get_user_account(db, user)
    data = build_account_movements(db, account_id, from_date, to_date)
    pdf = spdf.build_movements_pdf(
        data["account"], data["movements"], closing=data["closing"],
        period_label=_period_label(from_date, to_date),
    )
    filename = f"statement_{account_id}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )


@router.get("/accounts/{account_id}/statement/pdf")
def get_account_statement_pdf(
    account_id: int,
    from_date: str | None = None,
    to_date: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """PDF выписки-движений по лицевому счёту (админ/оператор/…; resident — только свой)."""
    _ensure_can_view_account(db, user, account_id)
    data = build_account_movements(db, account_id, from_date, to_date)
    pdf = spdf.build_movements_pdf(
        data["account"], data["movements"], closing=data["closing"],
        period_label=_period_label(from_date, to_date),
    )
    filename = f"statement_{account_id}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )


def _ensure_can_view_account(db: Session, user: User, account_id: int) -> None:
    """resident видит только свой счёт; прочие роли не ограничиваются."""
    if user is not None and getattr(user, "role", None) is not None and user.role.name == "resident":
        own = getattr(user, "account_id", None)
        if not own or int(own) != int(account_id):
            raise HTTPException(status_code=403, detail="Нет доступа к этому лицевому счёту")


def _get_user_account(db: Session, user: User) -> int:
    """Возвращает account_id текущего пользователя (для ЛК).

    Если у пользователя не задан account_id — 404 (нет привязки к счёту)."""
    account_id = getattr(user, "account_id", None)
    if not account_id:
        raise HTTPException(
            status_code=404,
            detail="Лицевой счёт не привязан к пользователю",
        )
    return int(account_id)


@router.get("/me/statement")
def get_my_statement(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Сводка по собственному лицевому счёту текущего пользователя (ЛК жителя).

    Счёт берётся из привязки users.account_id — жителю не нужно знать свой id.
    """
    account_id = _get_user_account(db, user)
    try:
        return build_account_statement(db, account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Лицевой счёт не найден")


@router.get("/me/house_expenses")
def get_my_house_expenses(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Расходы ТСЖ по кассе — агрегированная сводка для ЛК жителя.

    Разбивка по статьям расходов и общая сумма из того же источника, что
    «Отчёт по расходам» (cash_register). Показываем за ВСЁ время (накопление),
    чтобы житель всегда видел, куда потрачены средства; персональные операции/
    контрагенты жителю не отдаются (только статьи и итог).
    """
    rows = db.execute(
        text("""
            SELECT COALESCE(aa.name, 'Без статьи') AS name, COALESCE(SUM(cr.expense), 0) AS total
            FROM cash_register cr
            JOIN transactions t ON t.id = cr.transaction_id
            LEFT JOIN analytic_articles aa ON aa.id = t.article_id
            WHERE cr.expense > 0
            GROUP BY name
            ORDER BY total DESC, name
        """),
    ).fetchall()
    articles = [{"name": r[0], "expense": round(float(r[1]), 2)} for r in rows]
    return {
        "articles": articles,
        "total": round(sum(a["expense"] for a in articles), 2),
    }


@router.get("/creators")
def list_creators(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Пользователи для фильтра «Автор» в журналах документов.

    Жители исключены — документы они не создают. Значение фильтра (и колонка
    «Автор») — full_name, а если ФИО не заполнено — логин (см. serializers._creator_name).
    """
    users = (
        db.query(User)
        .filter(User.role != UserRole.resident)
        .order_by(User.full_name.asc(), User.username.asc())
        .all()
    )
    return [
        {"id": u.id, "username": u.username, "full_name": u.full_name} for u in users
    ]
