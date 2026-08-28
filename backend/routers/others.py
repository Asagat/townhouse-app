# backend/routers/others.py
"""Прочие специальные эндпоинты (ЭТАП 3 роадмапа).

Вынесен из `app.py`: отчёт по лицевому счёту (`accounts/{id}/statement`) вместе
с его helpers (`build_account_statement`, `_current_account_balance`).
Логика сохранена без изменений.
"""

from auth import get_current_user
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from models import Account, User
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
