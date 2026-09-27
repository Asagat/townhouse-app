# tests/test_resident_contacts_password.py

"""Блок ЛК: смена пароля (Б9) и контактные данные жителя (Б2)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import app
from auth import hash_password
from models import Account, Apartment, Counterparty, User, UserRole


@pytest.fixture()
def client(db):
    return TestClient(app)


@pytest.fixture()
def resident(db):
    own = Counterparty(full_name="__test_Рез Конт", first_name="__test_Рез", phone="+70000000000")
    db.add(own)
    db.flush()
    apt = Apartment(apartment_number=999001, address="__test", square=1, owner_id=own.id)
    db.add(apt)
    db.flush()
    acc = Account(account_number="__test_res_acct", account_name="__test", is_active=True, apartment_id=apt.id)
    db.add(acc)
    db.flush()
    u = User(
        username="__test_res_user",
        password_hash=hash_password("oldpass"),
        full_name="__test_Рез",
        role=UserRole.resident,
        is_active=True,
        account_id=acc.id,
        must_change_password=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    yield {"user_id": u.id, "owner_id": own.id, "account_id": acc.id, "apartment_id": apt.id}
    db.execute(text("DELETE FROM users WHERE id = :i"), {"i": u.id})
    db.execute(text("DELETE FROM accounts WHERE id = :i"), {"i": acc.id})
    db.execute(text("DELETE FROM apartments WHERE id = :i"), {"i": apt.id})
    db.execute(text("DELETE FROM counterparties WHERE id = :i"), {"i": own.id})
    db.commit()


def _auth(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_change_password_flow(client, resident):
    h = _auth(client, "__test_res_user", "oldpass")

    # Неверный текущий пароль.
    assert client.post(
        "/api/auth/change-password", headers=h,
        json={"current_password": "bad", "new_password": "newpass1"},
    ).status_code == 400

    # Слишком короткий новый.
    assert client.post(
        "/api/auth/change-password", headers=h,
        json={"current_password": "oldpass", "new_password": "123"},
    ).status_code == 422

    # Успешная смена — флаг снимается.
    r = client.post(
        "/api/auth/change-password", headers=h,
        json={"current_password": "oldpass", "new_password": "newpass1"},
    )
    assert r.status_code == 200
    me = client.get("/api/auth/me", headers=h).json()
    assert me["must_change_password"] is False

    # Вход с новым паролем работает.
    _auth(client, "__test_res_user", "newpass1")


def test_resident_contacts_edit(client, resident):
    h = _auth(client, "__test_res_user", "oldpass")

    r = client.get("/api/me/contacts", headers=h)
    assert r.status_code == 200
    assert r.json()["login"] == "__test_res_user"  # логин — только чтение

    r = client.patch(
        "/api/me/contacts", headers=h,
        json={
            "full_name": "Новое ФИО",
            "phone": "+7 777 000 00 00",
            "email": "x@y.z",
            "contact_info": "telegram",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["full_name"] == "Новое ФИО"
    assert body["email"] == "x@y.z"
    assert body["contact_info"] == "telegram"
    assert body["login"] == "__test_res_user"

    # Пустое ФИО недопустимо.
    assert client.patch("/api/me/contacts", headers=h, json={"full_name": "  "}).status_code == 422
