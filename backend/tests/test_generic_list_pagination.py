# tests/test_generic_list_pagination.py

"""Generic-список: запрос БЕЗ параметров пагинации должен отдавать ВЕСЬ список.

Регрессия: в `GET /api/{resource}` был скрытый дефолт `_end = 10`, поэтому запросы
без `_start/_end` молча обрезались до 10 строк. Именно так шлёт Refine при
`pagination: { mode: "off" }` (и прямые fetch-и справочников в выпадающие списки):
в форме массового ввода показаний и в просмотре/редактировании документа показаний
было видно 10 квартир из 17, в выписке по счёту — 10 счетов из 17.

Тесты работают против реальной БД; создаваемые сущности удаляются фикстурой
`account_factory`. Проверки не зависят от абсолютного числа строк — сравнивают
размер ответа с `X-Total-Count`.
"""

import pytest
from fastapi.testclient import TestClient

from app import app
from models import UserRole


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def admin_headers(client, user_factory):
    user_factory("pagination_admin", UserRole.admin)
    r = client.post(
        "/api/auth/login",
        json={"username": "pagination_admin-user", "password": "pass123"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_list_without_pagination_returns_all_rows(client, account_factory, admin_headers):
    # Заведомо больше 10 квартир — иначе прежняя обрезка была бы незаметна.
    for i in range(12):
        account_factory(f"pagtest{i}")

    full = client.get("/api/apartments", headers=admin_headers)
    assert full.status_code == 200, full.text
    total = int(full.headers["X-Total-Count"])
    assert total >= 12
    assert len(full.json()) == total, (
        "без _start/_end должен возвращаться весь список, а не первые 10 строк"
    )

    # Явная пагинация продолжает работать, а X-Total-Count — про весь список.
    page = client.get(
        "/api/apartments", headers=admin_headers, params={"_start": 0, "_end": 2}
    )
    assert page.status_code == 200
    assert len(page.json()) == 2
    assert page.headers["X-Total-Count"] == full.headers["X-Total-Count"]


def test_reference_select_style_fetch_returns_all(client, account_factory, admin_headers):
    """Так ReferenceSelect тянет справочник: только `_end` (без `_start`)."""
    for i in range(12):
        account_factory(f"refsel{i}")

    r = client.get("/api/apartments", headers=admin_headers, params={"_end": 100000})
    assert r.status_code == 200, r.text
    assert len(r.json()) == int(r.headers["X-Total-Count"])
