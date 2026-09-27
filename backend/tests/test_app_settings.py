# tests/test_app_settings.py

"""Б3: глобальные настройки (префикс л/с) и авто-генерация номера лицевого счёта."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import app
from auth import hash_password
from models import Apartment, Counterparty, User, UserRole


@pytest.fixture()
def client(db):
    return TestClient(app)


@pytest.fixture()
def seed(db):
    users = []
    for uname, role in [("set_admin", UserRole.admin), ("set_oper", UserRole.operator)]:
        u = User(username=uname, password_hash=hash_password("pass"), full_name=uname, role=role, is_active=True)
        db.add(u)
        db.commit()
        db.refresh(u)
        users.append(u.id)

    own = Counterparty(full_name="__test_set_own", first_name="__test")
    db.add(own)
    db.flush()
    apt = Apartment(apartment_number=999777, address="__test", square=1, owner_id=own.id)
    db.add(apt)
    db.commit()
    db.refresh(apt)

    created_accounts: list[int] = []
    yield {"owner_id": own.id, "apartment_id": apt.id, "account_ids": created_accounts}

    # Возвращаем настройку по умолчанию и чистим созданное.
    db.execute(text("DELETE FROM app_settings WHERE key = 'account_number_prefix'"))
    for acc_id in created_accounts:
        db.execute(text("DELETE FROM accounts WHERE id = :i"), {"i": acc_id})
    db.execute(text("DELETE FROM apartments WHERE id = :i"), {"i": apt.id})
    db.execute(text("DELETE FROM counterparties WHERE id = :i"), {"i": own.id})
    if users:
        db.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": users})
    db.commit()


def _auth(client, username):
    r = client.post("/api/auth/login", json={"username": username, "password": "pass"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_settings_and_generated_account_number(client, db, seed):
    admin = _auth(client, "set_admin")

    # По умолчанию префикс «LS-».
    r = client.get("/api/auth/settings", headers=admin)
    assert r.status_code == 200
    assert r.json()["settings"]["account_number_prefix"] == "LS-"

    # Меняем префикс.
    r = client.put("/api/auth/settings", headers=admin, json={"settings": {"account_number_prefix": "TST-"}})
    assert r.status_code == 200
    assert r.json()["settings"]["account_number_prefix"] == "TST-"

    # Пустой префикс недопустим.
    assert client.put(
        "/api/auth/settings", headers=admin, json={"settings": {"account_number_prefix": "  "}}
    ).status_code == 422

    # Создаём счёт без номера — генерируется «префикс + номер квартиры».
    r = client.post(
        "/api/accounts",
        headers=admin,
        json={"apartment_id": seed["apartment_id"], "account_name": "Тест"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    seed["account_ids"].append(body["id"])
    assert body["account_number"] == "TST-999777"

    # Оператор к настройкам доступа не имеет.
    assert client.get("/api/auth/settings", headers=_auth(client, "set_oper")).status_code == 403
