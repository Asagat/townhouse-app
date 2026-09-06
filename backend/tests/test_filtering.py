# backend/tests/test_filtering.py
"""Общий механизм серверной фильтрации списков (Б10).

Проверяем generic GET /api/{resource} с параметрами вида
`<field>[_{like|ne|gte|lte}]=<value>` (формат @refinedev/simple-rest):
  - contains (full_name_like) по тексту;
  - диапазоны (gte/lte) по числовому полю;
  - неразрешимые/неприменимые параметры молча игнорируются (200, без ошибки).
"""

from fastapi.testclient import TestClient

from app import app
from auth import create_access_token
from models import UserRole


def _headers(admin):
    token = create_access_token(admin)
    return {"Authorization": f"Bearer {token}"}


def test_filter_owners_contains(db, user_factory, account_factory):
    admin = user_factory("filadmin", UserRole.admin)
    a1 = account_factory("bfil1")
    a2 = account_factory("bfil2")
    client = TestClient(app)
    h = _headers(admin)

    # Подстрока, общая для двух созданных контрагентов.
    resp = client.get("/api/owners?_start=0&_end=50&full_name_like=bfil", headers=h)
    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "2"

    # Только один из них.
    resp = client.get("/api/owners?_start=0&_end=50&full_name_like=bfil1", headers=h)
    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "1"
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == a1["owner_id"]
    assert "bfil1" in body[0]["full_name"]

    # Точное равенство (eq).
    resp = client.get("/api/owners?_start=0&_end=50&full_name=bfil1 T", headers=h)
    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "1"


def test_filter_apartments_numeric_range(db, user_factory, account_factory):
    admin = user_factory("filrange", UserRole.admin)
    account_factory("brng1")
    account_factory("brng2")
    client = TestClient(app)
    h = _headers(admin)

    # Квартиры создаются со square=1 — обе попадают в «>= 1».
    resp = client.get("/api/apartments?_start=0&_end=100&square_gte=1", headers=h)
    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "2"

    # «<= 0» — пусто.
    resp = client.get("/api/apartments?_start=0&_end=100&square_lte=0", headers=h)
    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "0"


def test_filter_unknown_and_bad_params_ignored(db, user_factory, account_factory):
    admin = user_factory("filign", UserRole.admin)
    account_factory("bign1")
    account_factory("bign2")
    client = TestClient(app)
    h = _headers(admin)

    # Несуществующее поле и нечисловое значение для числового поля — молча игнорируются.
    resp = client.get(
        "/api/owners?_start=0&_end=50&no_such_field_like=x&square_gte=abc",
        headers=h,
    )
    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "2"
