# backend/tests/test_preferences.py
"""Серверные настройки интерфейса пользователя (2.13).

GET /api/preferences — настройки текущего пользователя (по ресурсам);
PUT /api/preferences/{resource} — сохранение (upsert). Изоляция между
пользователями: каждый видит/меняет только свои настройки.
"""

import json

from fastapi.testclient import TestClient

from app import app
from auth import create_access_token
from models import UserRole


def _headers(user):
    token = create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def test_save_and_get_preferences(db, user_factory):
    alice = user_factory("prefalice", UserRole.admin)
    bob = user_factory("prefbob", UserRole.operator)
    client = TestClient(app)

    h_alice = _headers(alice)
    h_bob = _headers(bob)

    # Поначалу настроек нет.
    resp = client.get("/api/preferences", headers=h_alice)
    assert resp.status_code == 200
    assert resp.json() == []

    # Сохранение настроек раздела (upsert) и получение.
    payload = {
        "columns": {"order": ["a", "b"], "hidden": [], "widths": {"a": 120}},
        "sorters": [{"field": "accrual_date", "order": "desc"}],
        "pageSize": 25,
    }
    resp = client.put("/api/preferences/payments", headers=h_alice, json=payload)
    assert resp.status_code == 200
    assert resp.json()["resource"] == "payments"

    # Повторное сохранение того же раздела — обновление, а не дубль.
    payload["pageSize"] = 50
    resp = client.put("/api/preferences/payments", headers=h_alice, json=payload)
    assert resp.status_code == 200

    resp = client.get("/api/preferences", headers=h_alice)
    assert resp.status_code == 200
    prefs = {p["resource"]: p["data"] for p in resp.json()}
    assert set(prefs.keys()) == {"payments"}
    assert prefs["payments"]["pageSize"] == 50

    # Разные разделы одного пользователя.
    client.put("/api/preferences/accounts", headers=h_alice, json={"pageSize": 10})

    resp = client.get("/api/preferences", headers=h_alice)
    prefs = {p["resource"]: p["data"] for p in resp.json()}
    assert set(prefs.keys()) == {"payments", "accounts"}

    # Второй пользователь своих настроек не видит (изоляция).
    resp = client.get("/api/preferences", headers=h_bob)
    assert resp.status_code == 200
    assert resp.json() == []

    # Мусорные payload отклоняются.
    resp = client.put("/api/preferences/payments", headers=h_alice, json=[1, 2, 3])
    assert resp.status_code == 422
