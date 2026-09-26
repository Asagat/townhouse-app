# backend/tests/test_receipts_bulk_delete.py
"""Массовое удаление квитанций: за месяц, за весь год и по выделенным id.

Эндпоинты:
  - `DELETE /api/receipt_documents/bulk_delete?year&month` — месяц;
  - `DELETE /api/receipt_documents/bulk_delete?year` — весь год (все месяцы);
  - `POST  /api/receipt_documents/bulk_delete {"ids": [...]}` — выделенные строки.

Тест использует «пустые» годы (1999/2000), реальные данные не затрагиваются;
созданные квитанции удаляются в конце.
"""

from fastapi.testclient import TestClient
from sqlalchemy import text

from app import app
from auth import create_access_token
from models import ReceiptDocument, UserRole


def _headers(admin):
    return {"Authorization": f"Bearer {create_access_token(admin)}"}


def _receipt(db, account_id: int, year: int, month: int) -> int:
    """Создаёт квитанцию-шапку и возвращает её id (обычное число)."""
    rec = ReceiptDocument(
        account_id=account_id,
        period_year=year,
        period_month=month,
        apartment_number=1,
        owner_name="Тест Тест",
        total_amount=0,
        debt=0,
        overpayment=0,
        payable_amount=0,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return int(rec.id)


def _exists(db, receipt_id: int) -> bool:
    """Есть ли квитанция в БД (по SQL — минуя identity map сессии)."""
    db.expire_all()
    return (
        db.execute(
            text("SELECT count(*) FROM receipt_documents WHERE id = :i"), {"i": receipt_id}
        ).scalar()
        == 1
    )


def test_bulk_delete_by_ids(db, user_factory, account_factory):
    admin = user_factory("rdelids", UserRole.admin)
    acc = account_factory("rdelids")
    client = TestClient(app)

    rid = _receipt(db, acc["account_id"], 1999, 7)
    resp = client.post(
        "/api/receipt_documents/bulk_delete",
        headers=_headers(admin),
        json={"ids": [rid]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] == 1
    assert not _exists(db, rid)


def test_bulk_delete_by_month_then_whole_year(db, user_factory, account_factory):
    admin = user_factory("rdelper", UserRole.admin)
    acc = account_factory("rdelper")
    client = TestClient(app)
    h = _headers(admin)

    jan = _receipt(db, acc["account_id"], 1999, 1)
    feb = _receipt(db, acc["account_id"], 1999, 2)
    other_year = _receipt(db, acc["account_id"], 2000, 1)

    # 1) За конкретный месяц (январь 1999) — удаляется только он.
    resp = client.delete("/api/receipt_documents/bulk_delete?year=1999&month=1", headers=h)
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] == 1
    assert not _exists(db, jan)
    assert _exists(db, feb)
    assert _exists(db, other_year)

    # 2) За весь 1999 год (без month) — февраль; 2000-й не затрагивается.
    resp = client.delete("/api/receipt_documents/bulk_delete?year=1999", headers=h)
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] == 1
    assert not _exists(db, feb)
    assert _exists(db, other_year)

    # Убираем квитанции за 2000 (иначе автоочистка счёта упрётся в FK RESTRICT).
    resp = client.delete("/api/receipt_documents/bulk_delete?year=2000", headers=h)
    assert resp.status_code == 200, resp.text
    assert not _exists(db, other_year)


def test_bulk_delete_requires_year(db, user_factory):
    admin = user_factory("rdelnone", UserRole.admin)
    client = TestClient(app)
    resp = client.delete("/api/receipt_documents/bulk_delete", headers=_headers(admin))
    assert resp.status_code == 422
