# tests/test_sorting.py

"""Тесты общего решения серверной сортировки по вложенным полям (роадмап 1.5).

Проверяют, что декларативно описанный путь по relationship (owner.full_name) генерирует
коррелированный подзапрос и что API корректно сортирует по нему, а не просто молча
возвращает данные в исходном порядке (чего раньше добивался фоллбек hasattr).
"""

from models import (
    AnalyticArticle,
    AnalyticKind,
    CashPoint,
    Transaction,
    TransactionTypeEnum,
)
from services import set_transaction_title

import pytest
from fastapi.testclient import TestClient
from app import app


@pytest.fixture()
def client():
    return TestClient(app)

def test_nested_sort_by_owner_full_name(client, db, account_factory):
    """Сортировка transactions по owner.full_name (3-hop путь через account.apartment.owner)."""
    rec_b = account_factory("zzzz_sort")   # owner.full_name = "zzzz_sort T"
    rec_a = account_factory("aaaa_sort")   # owner.full_name = "aaaa_sort T"
    db.flush()

    article = db.query(AnalyticArticle).filter(AnalyticArticle.kind == AnalyticKind.income).first()
    assert article is not None
    cp = db.get(CashPoint, rec_a["cash_point_id"]) or db.query(CashPoint).first()

    tx_a = Transaction(
        account_id=rec_a["account_id"],
        cash_point_id=cp.id,
        article_id=article.id,
        transaction_type=TransactionTypeEnum.in_cash,
        amount=100,
    )
    tx_b = Transaction(
        account_id=rec_b["account_id"],
        cash_point_id=cp.id,
        article_id=article.id,
        transaction_type=TransactionTypeEnum.in_cash,
        amount=200,
    )
    db.add_all([tx_a, tx_b])
    db.flush()
    set_transaction_title(db, tx_a)
    set_transaction_title(db, tx_b)
    db.commit()

    # Авторизация: админ (создаём/берём существующего).
    from models import User, UserRole
    from auth import create_access_token, hash_password
    created_admin = None
    admin = db.query(User).filter(User.role == UserRole.admin).first()
    if admin is None:
        admin = User(username="__sort_admin", password_hash=hash_password("p"), full_name="Sort Admin", role=UserRole.admin, is_active=True)
        db.add(admin); db.commit(); db.refresh(admin)
        created_admin = admin
    try:
        headers = {"Authorization": f"Bearer {create_access_token(admin)}"}

        r = client.get(
            "/api/transactions",
            params={"_sort": "owner.full_name", "_order": "asc", "_start": 0, "_end": 20},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        ids_in_order = [row["id"] for row in data]
        # Оба созданных прихода должны присутствовать и быть упорядочены: aaaa_sort раньше zzzz_sort.
        assert tx_a.id in ids_in_order and tx_b.id in ids_in_order
        assert ids_in_order.index(tx_a.id) < ids_in_order.index(tx_b.id)
    finally:
        if created_admin is not None:
            db.delete(created_admin)
            db.commit()


def test_direct_column_sort_still_works(client, db, account_factory):
    """Прямой столбец (amount) сортируется по-прежнему."""
    rec = account_factory("colsort")
    db.flush()
    article = db.query(AnalyticArticle).filter(AnalyticArticle.kind == AnalyticKind.income).first()
    cp = db.get(CashPoint, rec["cash_point_id"]) or db.query(CashPoint).first()

    tx_hi = Transaction(account_id=rec["account_id"], cash_point_id=cp.id, article_id=article.id,
                        transaction_type=TransactionTypeEnum.in_cash, amount=999)
    tx_lo = Transaction(account_id=rec["account_id"], cash_point_id=cp.id, article_id=article.id,
                        transaction_type=TransactionTypeEnum.in_cash, amount=1)
    db.add_all([tx_hi, tx_lo])
    db.flush()
    set_transaction_title(db, tx_hi)
    set_transaction_title(db, tx_lo)
    db.commit()

    from models import User, UserRole
    from auth import create_access_token, hash_password
    created_admin = None
    admin = db.query(User).filter(User.role == UserRole.admin).first()
    if admin is None:
        admin = User(username="__sort_admin2", password_hash=hash_password("p"), role=UserRole.admin, is_active=True)
        db.add(admin); db.commit(); db.refresh(admin)
        created_admin = admin
    try:
        headers = {"Authorization": f"Bearer {create_access_token(admin)}"}

        r = client.get("/api/transactions", params={"_sort": "amount", "_order": "asc", "_start": 0, "_end": 50}, headers=headers)
        assert r.status_code == 200
        data = r.json()
        ids = [row["id"] for row in data]
        # Обе созданные суммы присутствуют и упорядочены по возрастанию (1 перед 999).
        assert tx_lo.id in ids and tx_hi.id in ids
        assert ids.index(tx_lo.id) < ids.index(tx_hi.id)
        assert data[0]["amount"] <= data[-1]["amount"]
    finally:
        if created_admin is not None:
            db.delete(created_admin)
            db.commit()
