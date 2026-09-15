# tests/test_period_duplicate_guard.py

"""Защита «от дурака»: повторная генерация документов за один период.

Месячное начисление и квитанции за период создаются НЕ идемпотентно
(`generate_receipt_document` не проверяет существующую квитанцию, а
`generate_accruals` каждый вызов создаёт новый `AccrualDocument`). Поэтому эндпоинты
обязаны отказать (409) с понятным сообщением, если за период уже есть аналогичный
документ, и НЕ создавать новые документы/строки.

Используются «свободные» периоды 1999 года — история проекта начинается с 2017-10,
таких документов в БД заведомо нет (тесты идемпотентны и не трогают реальные данные).
"""

import calendar
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import app
from models import AccrualDocument, ReceiptDocument, UserRole

GUARD_MESSAGE = "уже имеется аналогичный документ"

# Периоды 1999 года: заведомо вне реальных данных проекта.
MONTHLY_DOC_PERIOD = (1999, 1)      # сюда кладём «занятый» месячный документ начислений
FREE_ACCRUAL_PERIOD = (1999, 2)     # свободный период для начислений
RECEIPTS_TAKEN_PERIOD = (1999, 1)   # сюда кладём «занятые» квитанции
RECEIPTS_FREE_PERIOD = (1999, 3)    # свободный период для квитанций


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def operator_headers(client, user_factory):
    """Заголовки авторизации оператора (проходит и require_roles, и require_write_access)."""
    user_factory("guard_operator", UserRole.operator)
    r = client.post(
        "/api/auth/login",
        json={"username": "guard_operator-user", "password": "pass123"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _monthly_doc_count(db, year: int, month: int) -> int:
    start, end = _month_bounds(year, month)
    return db.execute(
        text(
            "SELECT count(*) FROM accrual_documents WHERE doc_kind = 'monthly' "
            "AND accrual_date >= :s AND accrual_date <= :e"
        ),
        {"s": start, "e": end},
    ).scalar()


def _receipt_count(db, year: int, month: int) -> int:
    return db.execute(
        text(
            "SELECT count(*) FROM receipt_documents "
            "WHERE period_year = :y AND period_month = :m"
        ),
        {"y": year, "m": month},
    ).scalar()


def _purge_accrual_period(db, year: int, month: int) -> None:
    """Аварийная уборка периода начислений (если тест оставил следы)."""
    start, end = _month_bounds(year, month)
    db.execute(
        text(
            "DELETE FROM accruals_register WHERE accrual_date >= :s AND accrual_date <= :e"
        ),
        {"s": start, "e": end},
    )
    db.execute(
        text(
            "DELETE FROM accrual_documents WHERE accrual_date >= :s AND accrual_date <= :e"
        ),
        {"s": start, "e": end},
    )
    db.commit()


def _purge_receipts_period(db, year: int, month: int) -> None:
    """Аварийная уборка квитанций периода (если тест оставил следы)."""
    db.execute(
        text(
            "DELETE FROM receipt_items WHERE receipt_id IN ("
            " SELECT id FROM receipt_documents WHERE period_year = :y AND period_month = :m)"
        ),
        {"y": year, "m": month},
    )
    db.execute(
        text(
            "DELETE FROM receipt_documents WHERE period_year = :y AND period_month = :m"
        ),
        {"y": year, "m": month},
    )
    db.commit()


def test_accruals_generate_blocked_when_monthly_document_exists(client, db, operator_headers):
    year, month = MONTHLY_DOC_PERIOD
    _, month_end = _month_bounds(year, month)

    doc = AccrualDocument(
        accrual_date=month_end, title="__test_guard_monthly", doc_kind="monthly"
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    try:
        before = _monthly_doc_count(db, year, month)
        r = client.post(
            "/api/accruals_register/generate",
            headers=operator_headers,
            json={
                "year": year,
                "month": month,
                "selections": [{"account_id": 1, "services_type_id": 1}],
            },
        )
        assert r.status_code == 409, r.text
        assert GUARD_MESSAGE in r.json()["detail"]
        # Документ не создан: в периоде по-прежнему столько же месячных документов.
        assert _monthly_doc_count(db, year, month) == before
    finally:
        _purge_accrual_period(db, year, month)


def test_accruals_generate_not_blocked_without_document(client, db, operator_headers):
    """Без месячного документа за период защита не срабатывает (отказ другой причины)."""
    year, month = FREE_ACCRUAL_PERIOD
    try:
        # Несуществующий вид услуги -> строк не будет (422), но это НЕ отказ «дубль».
        r = client.post(
            "/api/accruals_register/generate",
            headers=operator_headers,
            json={
                "year": year,
                "month": month,
                "selections": [{"account_id": 1, "services_type_id": 999999}],
            },
        )
        assert r.status_code != 409, r.text
        assert _monthly_doc_count(db, year, month) == 0
    finally:
        _purge_accrual_period(db, year, month)


def test_accruals_offset_by_one_month_not_blocked(client, db, operator_headers):
    """Документ соседнего месяца не блокирует генерацию (границы периода соблюдены)."""
    taken_year, taken_month = MONTHLY_DOC_PERIOD
    _, month_end = _month_bounds(taken_year, taken_month)
    db.add(
        AccrualDocument(
            accrual_date=month_end, title="__test_guard_neighbor", doc_kind="monthly"
        )
    )
    db.commit()

    year, month = FREE_ACCRUAL_PERIOD
    try:
        r = client.post(
            "/api/accruals_register/generate",
            headers=operator_headers,
            json={
                "year": year,
                "month": month,
                "selections": [{"account_id": 1, "services_type_id": 999999}],
            },
        )
        assert r.status_code != 409, r.text
    finally:
        _purge_accrual_period(db, taken_year, taken_month)
        _purge_accrual_period(db, year, month)


def test_receipts_generate_blocked_when_receipts_exist(client, db, account_factory, operator_headers):
    year, month = RECEIPTS_TAKEN_PERIOD
    # Счёт создаём сами (не полагаемся на наличие данных: CI-БД — только справочники).
    account_id = account_factory("dupguard")["account_id"]

    receipt = ReceiptDocument(
        account_id=account_id, period_year=year, period_month=month
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)

    try:
        before = _receipt_count(db, year, month)
        r = client.post(
            "/api/receipt_documents/generate",
            headers=operator_headers,
            json={"year": year, "month": month},
        )
        assert r.status_code == 409, r.text
        assert GUARD_MESSAGE in r.json()["detail"]
        # Новые квитанции не созданы.
        assert _receipt_count(db, year, month) == before
    finally:
        _purge_receipts_period(db, year, month)


def test_receipts_generate_not_blocked_for_empty_period(client, db, operator_headers):
    """Пустой период: защита не мешает штатному пути (нет начислений -> квитанций нет)."""
    year, month = RECEIPTS_FREE_PERIOD
    try:
        r = client.post(
            "/api/receipt_documents/generate",
            headers=operator_headers,
            json={"year": year, "month": month},
        )
        assert r.status_code == 201, r.text
        assert r.json()["created"] == []
        assert _receipt_count(db, year, month) == 0
    finally:
        _purge_receipts_period(db, year, month)
