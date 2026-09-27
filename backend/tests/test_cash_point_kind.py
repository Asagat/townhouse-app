# tests/test_cash_point_kind.py

"""Задача 2.15: тип «Касса/Счёт» — валидация операции и раздельные итоги отчёта."""

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException

from models import (
    AnalyticArticle,
    AnalyticKind,
    CashPoint,
    CashPointKind,
    Counterparty,
    Transaction,
    TransactionTypeEnum,
)
from services import resolve_transaction_values
from routers.reports import build_cash_register_report


def _income_article(db) -> AnalyticArticle:
    art = db.query(AnalyticArticle).filter(AnalyticArticle.kind == AnalyticKind.income).first()
    if art is None:
        art = AnalyticArticle(name="__test_income", kind=AnalyticKind.income)
        db.add(art)
        db.commit()
        db.refresh(art)
    return art


def _contractor(db) -> Counterparty:
    """Свежий тестовый контрагент.

    Раньше возвращался первый попавшийся контрагент, а при пустом справочнике
    создавался `__test_ctr`, который затем НЕ удалялся. На изолированной БД такой
    «хвост» переползал в следующие тесты и ломал подсчёт в test_filtering
    (владельцев оказывалось на одного больше). Теперь контрагента всегда создаёт
    и удаляет сам тест.
    """
    ctr = Counterparty(full_name="__test_ctr", first_name="__test")
    db.add(ctr)
    db.commit()
    db.refresh(ctr)
    return ctr


def test_transaction_type_must_match_cash_point_kind(db):
    art = _income_article(db)
    ctr = _contractor(db)
    cp_cash = CashPoint(name="__test_cp_cash", kind=CashPointKind.cash)
    cp_bank = CashPoint(name="__test_cp_bank", kind=CashPointKind.bank)
    db.add_all([cp_cash, cp_bank])
    db.commit()
    try:
        base = {"amount": "100", "article_id": art.id, "contractor_id": ctr.id}

        # Касса + «Приход в кассу» — ок.
        vals = resolve_transaction_values(
            db, {**base, "cash_point_id": cp_cash.id, "transaction_type": "Приход в кассу"}
        )
        assert vals["cash_point_id"] == cp_cash.id

        # Касса + «Приход в банк» — несоответствие типа.
        with pytest.raises(HTTPException) as e:
            resolve_transaction_values(
                db, {**base, "cash_point_id": cp_cash.id, "transaction_type": "Приход в банк"}
            )
        assert e.value.status_code == 422

        # Счёт + «Приход в банк» — ок.
        resolve_transaction_values(
            db, {**base, "cash_point_id": cp_bank.id, "transaction_type": "Приход в банк"}
        )

        # Несуществующая касса/счёт — 422.
        with pytest.raises(HTTPException):
            resolve_transaction_values(
                db, {**base, "cash_point_id": 999999, "transaction_type": "Приход в кассу"}
            )
    finally:
        db.delete(cp_cash)
        db.delete(cp_bank)
        db.delete(ctr)
        db.commit()


def test_cash_report_totals_by_kind(db, account_factory):
    rec = account_factory("cpkind")
    bank = CashPoint(name="__test_bank_report", kind=CashPointKind.bank)
    db.add(bank)
    db.commit()

    t1 = Transaction(
        account_id=rec["account_id"], cash_point_id=rec["cash_point_id"],
        transaction_type=TransactionTypeEnum.in_cash, amount=Decimal("1000"),
        transaction_date=datetime(2016, 11, 1, 9, 0),
    )
    t2 = Transaction(
        account_id=None, cash_point_id=bank.id,
        transaction_type=TransactionTypeEnum.in_bank, amount=Decimal("300"),
        transaction_date=datetime(2016, 11, 1, 9, 0),
    )
    db.add_all([t1, t2])
    db.commit()
    try:
        # Отчёт только по банковскому счёту.
        out = build_cash_register_report(db, None, None, cash_point_id=bank.id)
        assert out["totals_by_kind"]["bank"]["income"] == 300.0
        assert out["totals_by_kind"]["cash"]["income"] == 0.0
        assert out["cash_points"][0]["kind"] == "Счёт"
        assert out["cash_points"][0]["kind_code"] == "bank"

        # Отчёт только по кассе.
        out_cash = build_cash_register_report(db, None, None, cash_point_id=rec["cash_point_id"])
        assert out_cash["cash_points"][0]["kind"] == "Касса"
        assert out_cash["totals_by_kind"]["cash"]["income"] == 1000.0
    finally:
        db.delete(t1)
        db.delete(t2)
        db.delete(bank)
        db.commit()
