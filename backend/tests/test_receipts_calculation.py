# backend/tests/test_receipts_calculation.py
"""Расчёт долга/переплаты в квитанции: приходы текущего месяца учитываются.

Регрессия: «долг» брался как состояние регистра НА НАЧАЛО месяца
(`operation_date < 1-е число`), поэтому платежи, сделанные в этом же месяце, не
уменьшали «К оплате» — квитанция, сформированная после оплат, задваивала уплаченное.

Новая модель (сохраняет формулу «К оплате = Сумма + Долг − Переплата»):
  - «К оплате»  = фактический долг счёта (баланс регистра взаиморасчётов);
  - «Долг»      = задолженность за прошлые периоды (без начислений этого месяца);
  - «Переплата» = уже внесённое в счёт месяца сверх прошлого долга (или аванс).
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text

from app import create_accounts_register_entries_for_accruals
from models import (
    Account,
    AccrualDocument,
    AccrualsRegister,
    ServiceType,
    Tariff,
    TariffType,
    Transaction,
    TransactionTypeEnum,
)
from routers.receipts import generate_receipt_document
from writeoffs import calculate_write_offs


def _svc_with_tariff(db, name: str):
    """Тестовый вид услуги (префикс `__test_` — автоочистка) со своим тарифом."""
    tt = db.query(TariffType).filter(TariffType.name == "Фиксированный").first()
    svc = ServiceType(services_type=name, priority=0, tariff_type_id=tt.id)
    db.add(svc)
    db.flush()
    tariff = Tariff(services_type_id=svc.id, price=Decimal("1"), valid_from=date(2000, 1, 1))
    db.add(tariff)
    db.flush()
    return svc, tariff


def _accrual(db, account_id: int, svc_id: int, tariff_id: int, amount, year: int, month: int):
    """Начисление реальным путём: документ → accruals_register → accounts_register."""
    doc = AccrualDocument(
        accrual_date=date(year, month, 1), title="test accruals"
    )
    db.add(doc)
    db.flush()
    ar = AccrualsRegister(
        accrual_document_id=doc.id,
        accrual_date=doc.accrual_date,
        account_id=account_id,
        tariff_id=tariff_id,
        services_type_id=svc_id,
        consumption=0,
        amount=amount,
    )
    db.add(ar)
    db.flush()
    create_accounts_register_entries_for_accruals(db, [ar])
    db.commit()


def _payment(db, account_id: int, cash_point_id: int, amount, day: int = 10) -> None:
    tx = Transaction(
        account_id=account_id,
        cash_point_id=cash_point_id,
        transaction_type=TransactionTypeEnum.in_cash,
        amount=amount,
        transaction_date=datetime(2026, 9, day, 10, 0),
    )
    db.add(tx)
    db.commit()


def _drop_receipts(db, account_id: int) -> None:
    """Убирает квитанции теста (иначе автоочистка счёта упрётся в FK RESTRICT)."""
    db.execute(text("DELETE FROM receipt_documents WHERE account_id = :a"), {"a": account_id})
    db.commit()


def test_receipt_payable_accounts_for_payment_in_the_same_month(db, account_factory):
    rec = account_factory("rcptpay")
    svc, tariff = _svc_with_tariff(db, "__test_Квитанция1")
    try:
        _accrual(db, rec["account_id"], svc.id, tariff.id, Decimal("10000"), 2026, 9)
        _payment(db, rec["account_id"], rec["cash_point_id"], Decimal("4000"))
        calculate_write_offs(db, [rec["account_id"]])
        db.commit()

        acc = db.get(Account, rec["account_id"])
        receipt = generate_receipt_document(db, acc, 2026, 9)
        db.commit()

        assert receipt is not None
        assert float(receipt.total_amount) == 10000.0
        # К оплате — фактический долг (10000 − 4000), а не «сумма + долг на начало».
        assert float(receipt.payable_amount) == 6000.0
        assert float(receipt.debt) == 0.0
        # Уже внесённое в счёт месяца показано в «Переплате»: 10000 + 0 − 6000.
        assert float(receipt.overpayment) == 4000.0

        # Сумма строк квитанции сходится с «К оплате».
        rows_sum = db.execute(
            text("SELECT COALESCE(SUM(payable),0) FROM receipt_items WHERE receipt_id = :r"),
            {"r": receipt.id},
        ).scalar()
        assert float(rows_sum) == 6000.0
    finally:
        _drop_receipts(db, rec["account_id"])


def test_receipt_payable_without_payments_is_charges_plus_prior_debt(db, account_factory):
    """Без приходов поведение прежнее: «К оплате» = долг прошлых месяцев + начисления."""
    rec = account_factory("rcptdebt")
    svc, tariff = _svc_with_tariff(db, "__test_Квитанция2")
    try:
        _accrual(db, rec["account_id"], svc.id, tariff.id, Decimal("10000"), 2026, 8)
        _accrual(db, rec["account_id"], svc.id, tariff.id, Decimal("5000"), 2026, 9)

        acc = db.get(Account, rec["account_id"])
        receipt = generate_receipt_document(db, acc, 2026, 9)
        db.commit()

        assert receipt is not None
        assert float(receipt.total_amount) == 5000.0
        assert float(receipt.debt) == 10000.0  # долг за август
        assert float(receipt.overpayment) == 0.0
        assert float(receipt.payable_amount) == 15000.0
    finally:
        _drop_receipts(db, rec["account_id"])
