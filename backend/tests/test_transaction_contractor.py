# backend/tests/test_transaction_contractor.py
"""Контрагент в документах «Приход/Расход» и зеркале регистра кассы.

Регрессия: `resolve_transaction_values` собирал поля вручную и НЕ переносил
`contractor_id`, из-за чего при вводе через приложение контрагент терялся и в
документе (`transactions`), и в зеркальной строке `cash_register`.
"""

from fastapi.testclient import TestClient

from app import app
from auth import create_access_token
from models import AnalyticArticle, AnalyticKind, CashRegister, Counterparty, Transaction, UserRole


def _headers(admin):
    return {"Authorization": f"Bearer {create_access_token(admin)}"}


def _income_article(db):
    article = db.query(AnalyticArticle).filter(AnalyticArticle.kind == AnalyticKind.income).first()
    assert article is not None, "в справочнике должна быть хотя бы одна статья «Доход»"
    return article


def test_create_payment_saves_contractor_in_document_and_register(
    db, user_factory, account_factory
):
    admin = user_factory("ctradmin", UserRole.admin)
    rec = account_factory("ctr1")
    article = _income_article(db)
    client = TestClient(app)

    resp = client.post(
        "/api/payments",
        headers=_headers(admin),
        json={
            "apartment_id": rec["apartment_id"],
            "cash_point_id": rec["cash_point_id"],
            "article_id": article.id,
            "contractor_id": rec["owner_id"],
            "transaction_type": "in_cash",
            "amount": 1234.56,
            "transaction_date": "2026-09-10T10:00:00",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["contractor_id"] == rec["owner_id"]
    assert body["contractor_name"]

    # Документ «Приход/Расход» хранит контрагента.
    tx = db.get(Transaction, body["id"])
    db.refresh(tx)
    assert tx.contractor_id == rec["owner_id"]

    # Зеркальная строка регистра кассы тоже получила контрагента.
    cash = db.query(CashRegister).filter(CashRegister.transaction_id == tx.id).first()
    assert cash is not None
    assert cash.contractor_id == rec["owner_id"]


def test_create_payment_without_contractor_rejected(db, user_factory, account_factory):
    """Контрагент обязателен (как в field_config) — без него документ не создаётся."""
    admin = user_factory("ctradmin2", UserRole.admin)
    rec = account_factory("ctr2")
    article = _income_article(db)
    client = TestClient(app)

    resp = client.post(
        "/api/payments",
        headers=_headers(admin),
        json={
            "apartment_id": rec["apartment_id"],
            "cash_point_id": rec["cash_point_id"],
            "article_id": article.id,
            "transaction_type": "in_cash",
            "amount": 100,
            "transaction_date": "2026-09-10T10:00:00",
        },
    )
    assert resp.status_code == 422
    assert "Контрагент" in resp.json()["detail"]


def test_update_payment_replaces_contractor_in_register(db, user_factory, account_factory):
    admin = user_factory("ctradmin3", UserRole.admin)
    rec = account_factory("ctr3")
    other = account_factory("ctr4")
    article = _income_article(db)
    client = TestClient(app)

    created = client.post(
        "/api/payments",
        headers=_headers(admin),
        json={
            "apartment_id": rec["apartment_id"],
            "cash_point_id": rec["cash_point_id"],
            "article_id": article.id,
            "contractor_id": rec["owner_id"],
            "transaction_type": "in_cash",
            "amount": 500,
            "transaction_date": "2026-09-10T10:00:00",
        },
    )
    assert created.status_code == 201, created.text
    tx_id = created.json()["id"]

    updated = client.patch(
        f"/api/payments/{tx_id}",
        headers=_headers(admin),
        json={
            "apartment_id": rec["apartment_id"],
            "cash_point_id": rec["cash_point_id"],
            "article_id": article.id,
            "contractor_id": other["owner_id"],
            "transaction_type": "in_cash",
            "amount": 500,
            "transaction_date": "2026-09-10T10:00:00",
        },
    )
    assert updated.status_code == 200, updated.text

    cash = db.query(CashRegister).filter(CashRegister.transaction_id == tx_id).first()
    db.refresh(cash)
    assert cash.contractor_id == other["owner_id"]
    assert db.get(Counterparty, cash.contractor_id) is not None
