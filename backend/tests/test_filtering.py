# backend/tests/test_filtering.py
"""Общий механизм серверной фильтрации списков (Б10).

Проверяем generic GET /api/{resource} с параметрами вида
`<field>[_{like|ne|gte|lte}]=<value>` (формат @refinedev/simple-rest):
  - contains (full_name_like) по тексту;
  - диапазоны (gte/lte) по числовому полю;
  - неразрешимые/неприменимые параметры молча игнорируются (200, без ошибки).
"""

from datetime import datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app import app
from auth import create_access_token
from models import Transaction, TransactionTypeEnum, UserRole


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


def test_filter_nested_contains_and_eq(db, user_factory, account_factory):
    """Фильтры по вложенным полям (путь по relationship): contains и eq.

    Раньше падало с 500: для path-дескрипторов тип уже извлечён из столбца,
    а классификатор повторно обращался к `.type` (AttributeError).
    """
    admin = user_factory("filnest", UserRole.admin)
    account_factory("bnest1")
    account_factory("bnest2")
    client = TestClient(app)
    h = _headers(admin)

    # contains по вложенному полю (Квартиры -> Собственник.full_name).
    resp = client.get("/api/apartments?_start=0&_end=50&owner.full_name_like=bnest", headers=h)
    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "2"

    # eq по вложенному полю (Квартиры -> Собственник.full_name, полное имя).
    resp = client.get("/api/apartments?_start=0&_end=50&owner.full_name=bnest1 T", headers=h)
    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "1"

    # contains по вложенному полю на регистре начислений (л/с -> номер счёта).
    resp = client.get(
        "/api/accruals_register?_start=0&_end=50&account.account_number_like=bnest",
        headers=h,
    )
    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "0"


# Фильтр по enum-колонке (transaction_type): значение — имя члена PG-enum.
def test_filter_transactions_by_enum(db, user_factory, account_factory):
    admin = user_factory("filenum", UserRole.admin)
    a = account_factory("benum1")
    b = account_factory("benum2")
    for acc, tt_name in ((a, "in_cash"), (b, "out_cash")):
        db.add(Transaction(
            account_id=acc["account_id"],
            cash_point_id=acc["cash_point_id"],
            transaction_type=TransactionTypeEnum[tt_name],
            amount=Decimal("100"),
            transaction_date=datetime(2026, 9, 1, 10, 0),
        ))
    db.commit()
    client = TestClient(app)
    h = _headers(admin)

    resp = client.get("/api/payments?_start=0&_end=50&transaction_type=in_cash", headers=h)
    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "1"

    resp = client.get("/api/payments?_start=0&_end=50&transaction_type=out_cash", headers=h)
    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "1"


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
