# tests/test_role_permissions.py

"""Задача 2.6: настраиваемая матрица прав (role_permissions).

Проверяет эндпоинты `/api/auth/permissions*`: чтение своей матрицы, правку админом,
немедленный эффект на доступ, фиксацию admin/resident, «запертые» действия и сброс.
В конце каждый тест восстанавливает дефолтную (засеянную) матрицу.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import app
from auth import hash_password
from models import User, UserRole
from permissions import PERMISSION_CATALOG, ROLES, default_permissions


@pytest.fixture()
def client(db):
    return TestClient(app)


@pytest.fixture()
def seed_users(db):
    ids = []
    for uname, role in [
        ("perm_admin", UserRole.admin),
        ("perm_cash", UserRole.cashier),
    ]:
        u = User(
            username=uname, password_hash=hash_password("pass"),
            full_name=uname, role=role, is_active=True,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        ids.append(u.id)
    yield
    _restore_defaults(db)
    if ids:
        db.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": ids})
        db.commit()


def _restore_defaults(db) -> None:
    """Возвращает матрицу к засеянной дефолтной (тесты правят общую dev-БД)."""
    db.execute(text("DELETE FROM role_permissions"))
    perms = default_permissions()
    rows = []
    for role in ROLES:
        for entry in PERMISSION_CATALOG:
            p = perms[role][entry["key"]]
            rows.append({
                "role": role, "resource": entry["key"],
                "menu": p["menu"], "read": p["read"], "create": p["create"],
                "edit": p["edit"], "delete": p["delete"],
            })
    db.execute(
        text(
            "INSERT INTO role_permissions "
            "(role, resource, menu, can_read, can_create, can_edit, can_delete) "
            "VALUES (:role, :resource, :menu, :read, :create, :edit, :delete)"
        ),
        rows,
    )
    db.commit()


def _auth(client, username, password="pass"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_me_returns_effective_permissions(client, seed_users):
    h = _auth(client, "perm_cash")
    r = client.get("/api/auth/permissions/me", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["role"] == "cashier"
    # «Чтение» справочника есть (форма нуждается), но пункт меню — нет (две оси).
    assert data["keys"]["analytic_articles"]["read"] is True
    assert data["keys"]["analytic_articles"]["menu"] is False
    assert data["keys"]["owners"]["menu"] is True


def test_admin_matrix_and_toggle(client, db, seed_users):
    h = _auth(client, "perm_admin")
    r = client.get("/api/auth/permissions", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert "catalog" in body and "roles" in body and "matrix" in body

    # Снимаем у кассира чтение «Контрагентов».
    r = client.put(
        "/api/auth/permissions",
        headers=h,
        json={"items": [{
            "role": "cashier", "resource": "owners",
            "menu": False, "read": False, "create": False, "edit": False, "delete": False,
        }]},
    )
    assert r.status_code == 200 and r.json()["updated"] == 1

    cash = _auth(client, "perm_cash")
    assert client.get("/api/owners?_start=0&_end=10", headers=cash).status_code == 403
    me = client.get("/api/auth/permissions/me", headers=cash).json()
    assert me["keys"]["owners"]["read"] is False
    assert me["keys"]["owners"]["menu"] is False


def test_reset_restores_defaults(client, seed_users):
    h = _auth(client, "perm_admin")
    client.put(
        "/api/auth/permissions",
        headers=h,
        json={"items": [{
            "role": "cashier", "resource": "owners",
            "menu": False, "read": False, "create": False, "edit": False, "delete": False,
        }]},
    )
    cash = _auth(client, "perm_cash")
    assert client.get("/api/owners?_start=0&_end=10", headers=cash).status_code == 403

    r = client.post("/api/auth/permissions/reset", headers=h)
    assert r.status_code == 200 and r.json()["deleted"] >= 1
    assert client.get("/api/owners?_start=0&_end=10", headers=cash).status_code == 200


def test_admin_role_is_fixed(client, db, seed_users):
    h = _auth(client, "perm_admin")
    r = client.put(
        "/api/auth/permissions",
        headers=h,
        json={"items": [{
            "role": "admin", "resource": "owners",
            "menu": False, "read": False, "create": False, "edit": False, "delete": False,
        }]},
    )
    # Строка для фиксированной роли игнорируется.
    assert r.status_code == 200 and r.json()["updated"] == 0
    assert client.get("/api/owners?_start=0&_end=10", headers=h).status_code == 200


def test_locked_actions_are_clamped(client, db, seed_users):
    h = _auth(client, "perm_admin")
    # Пытаемся разрешить создание «Типов тарифов» кассиру — ресурс «заперт».
    r = client.put(
        "/api/auth/permissions",
        headers=h,
        json={"items": [{
            "role": "cashier", "resource": "tariff_types",
            "menu": False, "read": True, "create": True, "edit": True, "delete": True,
        }]},
    )
    assert r.status_code == 200 and r.json()["updated"] == 1
    row = db.execute(
        text("SELECT can_create, can_edit, can_delete FROM role_permissions "
             "WHERE role='cashier' AND resource='tariff_types'")
    ).first()
    assert tuple(row) == (False, False, False)
