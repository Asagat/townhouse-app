# tests/conftest.py

"""
Настройка pytest для бэкенда.

Тесты работают против реальной БД PostgreSQL (см. backend/database.py), используя
ОТДЕЛЬНЫЕ сущности с уникальными метками (owner.first_name == маркер теста), которые
всегда удаляются после прохождения теста. Подходить к БД без изолированной схемы
нельзя назвать идеальным, но для проекта без Alembic/тестовой схемы это единственный
прагматичный вариант: тесты идемпотентны и не оставляют следов.

Запуск из каталога backend:  python -m pytest tests/ -q
Для корректного импорта модулей (модели используют неявные относительные импорты)
тесты добавляют каталог backend в sys.path.
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from database import SessionLocal  # noqa: E402
from models import (  # noqa: E402
    Account,
    Apartment,
    CashPoint,
    Counterparty,
    Transaction,
    TransactionTypeEnum,
    User,
    UserRole,
)
from sqlalchemy import text  # noqa: E402
from auth import hash_password  # noqa: E402


# Префикс имён для видов услуг, которые создают тесты (см. test_accrual_formulas,
# test_writeoffs). Такие услуги после каждого теста автоматически удаляются
# фикстурой `_cleanup_test_services`, чтобы не засорять справочник.
TEST_SERVICE_PREFIX = "__test_"


@pytest.fixture(autouse=True)
def _cleanup_test_services():
    """После каждого теста удаляет тестовые виды услуг (по префиксу) и их
    зависимости (тарифы, счётчики, показания), чтобы не засорять справочник."""
    yield
    session = SessionLocal()
    try:
        prefix = TEST_SERVICE_PREFIX + "%"
        svc_ids = [r[0] for r in session.execute(
            text("SELECT id FROM services_type WHERE services_type LIKE :p"), {"p": prefix}
        ).fetchall()]
        for sid in svc_ids:
            session.execute(text("DELETE FROM tariffs WHERE services_type_id = :s"), {"s": sid})
            meter_ids = [r[0] for r in session.execute(
                text("SELECT id FROM meters WHERE services_type_id = :s"), {"s": sid}
            ).fetchall()]
            for mid in meter_ids:
                session.execute(text("DELETE FROM meter_readings WHERE meter_id = :x"), {"x": mid})
            session.execute(text("DELETE FROM meters WHERE services_type_id = :s"), {"s": sid})
        session.execute(text("DELETE FROM services_type WHERE services_type LIKE :p"), {"p": prefix})
        session.commit()
    except Exception:
        # Не даём ошибке очистки замаскировать результат самого теста.
        session.rollback()
    finally:
        session.close()


@pytest.fixture()
def db():
    """Сессия БД. Каждый тест получает свежую сессию."""
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def user_factory(db):
    """Фабрика создания пользователя с автоочисткой."""
    created_ids: list[int] = []

    def _make(marker: str, role: UserRole, password: str = "pass123"):
        u = User(
            username=f"{marker}-user",
            password_hash=hash_password(password),
            full_name=marker,
            role=role,
            is_active=True,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        created_ids.append(u.id)
        return u

    yield _make

    if created_ids:
        db.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": created_ids})
        db.commit()


@pytest.fixture()
def account_factory(db):
    """
    Фабрика создания лицевого счёта с уникальной меткой и автоочисткой.

    Возвращает функцию, которая создаёт owner/apartment/account/cash_point и
    возвращает dict с ключами: account_id, owner_id, apartment_id, cash_point_id.
    Все созданные сущности гарантированно удаляются по завершении теста.
    """
    created: list[dict] = []

    def _make(marker: str):
        own = Counterparty(full_name=f"{marker} T", first_name=marker, last_name="O")
        db.add(own)
        db.flush()
        apt = Apartment(
            apartment_number=_next_apartment_number(db),
            address=marker,
            square=1,
            owner_id=own.id,
        )
        db.add(apt)
        db.flush()
        acc = Account(
            account_number=f"{marker}-ACCT",
            account_name=marker,
            is_active=True,
            apartment_id=apt.id,
        )
        db.add(acc)
        db.flush()
        cp = CashPoint(name=f"{marker}-CP")
        db.add(cp)
        db.flush()
        db.commit()
        record = {
            "account_id": acc.id,
            "owner_id": own.id,
            "apartment_id": apt.id,
            "cash_point_id": cp.id,
        }
        created.append(record)
        return record

    yield _make

    # Очистка: удаляем в правильном порядке (обратном связям).
    for rec in created:
        account_id = rec["account_id"]
        db.execute(text("DELETE FROM cash_register WHERE account_id = :a"), {"a": account_id})
        db.execute(text("DELETE FROM accounts_register WHERE account_id = :a"), {"a": account_id})
        db.execute(text("DELETE FROM accruals_register WHERE account_id = :a"), {"a": account_id})
        db.execute(text("DELETE FROM transactions WHERE account_id = :a"), {"a": account_id})
        db.execute(text("DELETE FROM accounts WHERE id = :a"), {"a": account_id})
        # Показания/счётчики могут быть созданы в тесте; FK к apartments в БД RESTRICT.
        db.execute(text("DELETE FROM meter_readings WHERE apartment_id = :apt"), {"apt": rec["apartment_id"]})
        db.execute(text("DELETE FROM meters WHERE apartment_id = :apt"), {"apt": rec["apartment_id"]})
        db.execute(text("DELETE FROM apartments WHERE id = :a"), {"a": rec["apartment_id"]})
        db.execute(text("DELETE FROM owners WHERE id = :a"), {"a": rec["owner_id"]})
        db.execute(text("DELETE FROM cash_points WHERE id = :a"), {"a": rec["cash_point_id"]})
    # Удаляем тестовые документы начислений, не привязанные к реальным данным.
    db.execute(text("DELETE FROM accrual_documents WHERE title = 'test accruals'"))
    db.commit()


def _next_apartment_number(db) -> int:
    """Возвращает уникальный номер квартиры, не конфликтующий с существующими."""
    max_val = db.execute(text("SELECT COALESCE(MAX(apartment_number), 0) FROM apartments")).scalar()
    return int(max_val or 0) + 100000  # заведомо выше реальных
