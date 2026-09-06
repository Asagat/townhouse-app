# backend/tests/test_tariff_status.py
"""Статус тарифа «Действующий/Архивный».

При создании нового тарифа предыдущие «Действующие» той же группы
(вид услуги + признак разовости) помечаются «Архивными», новый становится
«Действующим». Регулярные и разовые тарифы одной услуги независимы
(разовый спец-сбор не вытесняет регулярную ставку и наоборот).
"""

from datetime import date

from fastapi.testclient import TestClient

from app import app
from auth import create_access_token
from models import ServiceType, TariffType, UserRole


def _headers(admin):
    token = create_access_token(admin)
    return {"Authorization": f"Bearer {token}"}


def _make_service(db, name: str) -> int:
    tt = db.query(TariffType).filter(TariffType.name == "Фиксированный").first()
    if tt is None:
        tt = TariffType(name="Фиксированный")
        db.add(tt)
        db.flush()
    svc = ServiceType(services_type=name, priority=0, tariff_type_id=tt.id)
    db.add(svc)
    db.flush()
    return svc.id


def test_create_tariff_archives_previous_in_group(db, user_factory):
    admin = user_factory("tfstatus", UserRole.admin)
    svc_id = _make_service(db, "__test_Статус")
    db.commit()
    client = TestClient(app)
    h = _headers(admin)

    def create(price, valid_from, oneoff=False):
        resp = client.post(
            "/api/tariffs",
            headers=h,
            json={
                "services_type_id": svc_id,
                "price": price,
                "valid_from": valid_from,
                "is_oneoff": oneoff,
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    def get_status(tariff_id: int) -> str:
        resp = client.get(f"/api/tariffs/{tariff_id}", headers=h)
        assert resp.status_code == 200, resp.text
        return resp.json()["status"]

    # Регулярные тарифы одной услуги: новый вытесняет предыдущий.
    t1 = create(100, "2026-01-01")
    assert t1["status"] == "active"
    t2 = create(200, "2026-06-01")
    assert t2["status"] == "active"
    assert get_status(t1["id"]) == "archived"

    # Разовый тариф той же услуги не трогает регулярные (и наоборот).
    one1 = create(5000, "2026-02-01", oneoff=True)
    assert one1["status"] == "active"
    assert get_status(t2["id"]) == "active"

    # Второй разовый тариф архивирует первый разовый (внутри своей группы).
    one2 = create(6000, "2026-09-01", oneoff=True)
    assert one2["status"] == "active"
    assert get_status(one1["id"]) == "archived"
    assert get_status(t2["id"]) == "active"
