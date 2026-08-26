# tests/test_auth.py

"""Тесты аутентификации и ролевого доступа."""

import pytest
from fastapi import HTTPException

from auth import (
    create_access_token,
    decode_access_token,
    get_current_user,
    hash_password,
    has_level,
    require_roles,
    verify_password,
)
from models import UserRole


def test_hash_verify_password():
    h = hash_password("s3cret")
    assert h.startswith("260000$")
    assert verify_password("s3cret", h) is True
    assert verify_password("wrong", h) is False


def test_create_and_decode_token(db, user_factory):
    u = user_factory("tok", UserRole.cashier)
    token = create_access_token(u)
    payload = decode_access_token(token)
    assert payload["sub"] == str(u.id)
    assert payload["role"] == "cashier"


def test_login_success_and_bad_password(db, user_factory):
    import app as A

    u = user_factory("log", UserRole.admin, password="pw")
    res = A.login({"username": u.username, "password": "pw"}, db)
    assert res["token_type"] == "bearer"
    assert res["user"]["role"] == "admin"
    assert res["user"]["role_name"] == "Администратор"

    with pytest.raises(HTTPException) as exc:
        A.login({"username": u.username, "password": "wrong"}, db)
    assert exc.value.status_code == 401


def test_me_requires_valid_token(db, user_factory):
    import app as A
    from fastapi.security import HTTPAuthorizationCredentials

    u = user_factory("me", UserRole.cashier)
    token = create_access_token(u)
    current = get_current_user(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), db
    )
    assert current.id == u.id
    assert current.role == UserRole.cashier

    # отсутствие токена -> 401
    with pytest.raises(HTTPException) as exc:
        get_current_user(None, db)
    assert exc.value.status_code == 401


def test_role_hierarchy():
    assert has_level(__user(UserRole.resident), UserRole.resident) is True
    assert has_level(__user(UserRole.cashier), UserRole.operator) is False
    assert has_level(__user(UserRole.operator), UserRole.cashier) is True
    assert has_level(__user(UserRole.admin), UserRole.operator) is True


def test_require_roles_allows_admin_denies_lower(db, user_factory):
    from fastapi.security import HTTPAuthorizationCredentials

    cashier = user_factory("rr", UserRole.cashier)
    admin = user_factory("ra", UserRole.admin)

    dep = require_roles("admin")
    # admin допускается
    current_admin = get_current_user(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=create_access_token(admin)), db
    )
    assert dep(current_admin).id == admin.id
    # cashier — нет (его роль не admin)
    current_cash = get_current_user(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=create_access_token(cashier)), db
    )
    with pytest.raises(HTTPException) as exc:
        dep(current_cash)
    assert exc.value.status_code == 403


def __user(role: UserRole):
    """Хелпер для создания User-объекта без БД (для тестов иерархии)."""
    from models import User

    u = User(username="x", password_hash="", role=role, is_active=True)
    u.id = 1
    return u
