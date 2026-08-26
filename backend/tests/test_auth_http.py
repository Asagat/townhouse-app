# tests/test_auth_http.py

"""HTTP-тесты аутентификации и ролевого доступа (через TestClient)."""

import pytest
from fastapi.testclient import TestClient

from app import app
from auth import hash_password
from models import User, UserRole
from sqlalchemy import text


@pytest.fixture()
def client(db):
    return TestClient(app)


@pytest.fixture()
def seed_users(db):
    ids = []
    for uname, role in [
        ("http_admin", UserRole.admin),
        ("http_cash", UserRole.cashier),
        ("http_oper", UserRole.operator),
    ]:
        u = User(username=uname, password_hash=hash_password("pass"), full_name=uname, role=role, is_active=True)
        db.add(u)
        db.commit()
        db.refresh(u)
        ids.append(u.id)
    yield {u: uname for uname in ("http_admin", "http_cash", "http_oper")}
    if ids:
        db.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": ids})
        db.commit()


def _token(client, username, password="pass"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(client, username):
    return {"Authorization": f"Bearer {_token(client, username)}"}


def test_unauthorized_access_denied(client):
    assert client.get("/api/owners?_start=0&_end=10").status_code == 401


def test_login_bad_credentials(client):
    r = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    assert r.status_code == 401


def test_admin_can_create_user(client, db, seed_users):
    h = _auth(client, "http_admin")
    r = client.post("/api/auth/users", headers=h, json={"username": "made_by_admin", "password": "p", "role": "controller"})
    assert r.status_code == 201 and r.json()["role"] == "controller"
    db.execute(text("DELETE FROM users WHERE username='made_by_admin'"))
    db.commit()


def test_cashier_permissions(client, seed_users):
    h = _auth(client, "http_cash")
    assert client.get("/api/owners?_start=0&_end=10", headers=h).status_code == 200  # чтение учёта
    assert client.delete("/api/owners/1", headers=h).status_code == 403            # удаление запрещено
    assert client.post("/api/auth/users", headers=h, json={"username": "nx", "password": "p", "role": "cashier"}).status_code == 403
    assert client.patch("/api/tariffs/4", headers=h, json={"price": 51}).status_code == 403  # настройки


def test_operator_cannot_change_settings(client, seed_users):
    h = _auth(client, "http_oper")
    assert client.patch("/api/tariffs/4", headers=h, json={"price": 51}).status_code == 403
    assert client.post("/api/auth/users", headers=h, json={"username": "nx", "password": "p", "role": "cashier"}).status_code == 403
    assert client.get("/api/meter_readings?_start=0&_end=10", headers=h).status_code == 200


def test_admin_list_and_update_user(client, db, seed_users):
    h = _auth(client, "http_admin")
    # список пользователей
    r = client.get("/api/auth/users", headers=h)
    assert r.status_code == 200
    users = r.json()
    cash = next(u for u in users if u["username"] == "http_cash")
    # смена роли кассира на оператора
    r = client.patch(f"/api/auth/users/{cash['id']}", headers=h, json={"role": "operator"})
    assert r.status_code == 200 and r.json()["role"] == "operator"
    # смена пароля
    r = client.patch(f"/api/auth/users/{cash['id']}", headers=h, json={"password": "newpass1"})
    assert r.status_code == 200
    # вход под новым паролем
    assert _token(client, "http_cash", "newpass1")


def test_admin_cannot_deactivate_or_remove_self(client, seed_users):
    h = _auth(client, "http_admin")
    adm = client.get("/api/auth/users", headers=h).json()
    adm_id = next(u for u in adm if u["username"] == "http_admin")["id"]
    assert client.patch(f"/api/auth/users/{adm_id}", headers=h, json={"is_active": False}).status_code == 403
    assert client.delete(f"/api/auth/users/{adm_id}", headers=h).status_code == 403


def test_admin_delete_user(client, db, seed_users):
    h = _auth(client, "http_admin")
    # создадим пользователя и удалим его
    r = client.post("/api/auth/users", headers=h, json={"username": "to_delete", "password": "pw123456", "role": "cashier"})
    assert r.status_code == 201
    uid = r.json()["id"]
    assert client.delete(f"/api/auth/users/{uid}", headers=h).status_code == 204
    assert client.get("/api/auth/users", headers=h).status_code == 200
