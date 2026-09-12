# backend/tests/test_tariff_status.py
"""Статус тарифа «Действующий/Архивный» и правила единой ленты по срокам (2.18).

Признака разовости (is_oneoff) больше нет: у одного вида услуги «Действующим»
остаётся последний созданный тариф; предыдущие «Действующие» того же вида
помечаются «Архивными». Закрытый тариф-период (с valid_to) обязан иметь
«Примечание» и не может пересекаться по срокам с другим «Действующим» тарифом
периода того же вида услуги.

Дополнительно (12.09.2026) запрещён «двойник»: открытая ставка и закрытый тариф-период
одной услуги с одной датой начала и одной ценой (@see `test_open_tariff_twin_is_rejected`).
"""

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


def test_create_open_tariff_archives_previous_of_service(db, user_factory):
    """Открытый тариф одного вида услуги вытесняет предыдущие «Действующие» того
    же вида (единая лента: статус теперь считается по виду услуги без разряда)."""
    admin = user_factory("tfstatus", UserRole.admin)
    svc_id = _make_service(db, "__test_СтатусЛента")
    db.commit()
    client = TestClient(app)
    h = _headers(admin)

    def create(price, valid_from, comment=None, valid_to=None):
        payload = {
            "services_type_id": svc_id,
            "price": price,
            "valid_from": valid_from,
        }
        if valid_to is not None:
            payload["valid_to"] = valid_to
            if comment is None:
                comment = "причина периода"
        if comment is not None:
            payload["comment"] = comment
        resp = client.post("/api/tariffs", headers=h, json=payload)
        assert resp.status_code == 201, resp.text
        return resp.json()

    def get_status(tariff_id: int) -> str:
        resp = client.get(f"/api/tariffs/{tariff_id}", headers=h)
        assert resp.status_code == 200, resp.text
        return resp.json()["status"]

    # Открытые ставки одного вида услуги: новая вытесняет предыдущую.
    t1 = create(100, "2026-01-01")
    assert t1["status"] == "active"
    t2 = create(200, "2026-06-01")
    assert t2["status"] == "active"
    assert get_status(t1["id"]) == "archived"

    # Любой следующий тариф того же вида (в т.ч. закрытый период) вытесняет
    # прежнего «Действующего» — признака разовости больше нет.
    t3 = create(300, "2026-07-01", comment="замена месяца июль", valid_to="2026-07-31")
    assert get_status(t3["id"]) == "active"
    assert get_status(t2["id"]) == "archived"


def test_period_tariff_rules_comment_and_overlap(db, user_factory):
    """Закрытый тариф-период: обязательное «Примечание» и запрет пересечения сроков
    c другим «Действующим» тарифом периода того же вида услуги."""
    admin = user_factory("tsrules", UserRole.admin)
    svc_id = _make_service(db, "__test_ПериодПравила")
    db.commit()
    client = TestClient(app)
    h = _headers(admin)

    def post(price, valid_from, valid_to, comment=None):
        payload = {
            "services_type_id": svc_id,
            "price": price,
            "valid_from": valid_from,
            "valid_to": valid_to,
        }
        if comment is not None:
            payload["comment"] = comment
        return client.post("/api/tariffs", headers=h, json=payload)

    # Закрытый тариф периода без «Примечания» — отклоняем.
    r = post(5000, "2026-03-01", "2026-03-31")
    assert r.status_code == 422, r.text

    # Закрытый тариф периода с примечанием — создаётся.
    r = post(5000, "2026-03-01", "2026-03-31", comment="замена ставки март, детская площадка")
    assert r.status_code == 201, r.text
    march = r.json()
    assert march["status"] == "active"

    # Пересекающийся с ним по срокам тариф периода (март) — запрещён: оператор
    # должен оформить ставку периода единой записью с итоговой суммой.
    r = post(2000, "2026-03-15", "2026-03-31", comment="второй март")
    assert r.status_code == 422, r.text
    assert "единой записью" in r.json()["detail"]

    # Непересекающийся тариф периода (июнь) — допустим.
    r = post(9000, "2026-06-01", "2026-06-30", comment="июнь")
    assert r.status_code == 201, r.text

    # Открытая (без valid_to) ставка той же услуги не требует примечания и не
    # пересекается по срокам с закрытыми периодами — допустимa.
    payload = {
        "services_type_id": svc_id,
        "price": 100,
        "valid_from": "2026-01-01",
    }
    r = client.post("/api/tariffs", headers=h, json=payload)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "active"


def test_open_tariff_twin_is_rejected(db, user_factory):
    """Запрет «двойника»: открытая ставка и закрытый период с одной датой и ценой.

    Реальный дефект (конверсия 2.18): у «Фонда развития» одновременно существовали
    открытая база 148 850 с 01.04.2026 и закрытый период 148 850 на апрель 2026 —
    открытая запись «перекрывала» период и подставлялась в начисления следующих
    месяцев (`resolve_tariff_for_accrual_period` поле `status` не читает).
    """
    admin = user_factory("tftwin", UserRole.admin)
    svc_id = _make_service(db, "__test_ДвойникПериода")
    db.commit()
    client = TestClient(app)
    h = _headers(admin)

    def create(price, valid_from, valid_to=None, comment=None):
        payload = {"services_type_id": svc_id, "price": price, "valid_from": valid_from}
        if valid_to is not None:
            payload["valid_to"] = valid_to
            payload["comment"] = comment or "разовый период"
        return client.post("/api/tariffs", headers=h, json=payload)

    # Закрытый период на май 2026 — создаётся.
    r = create(4000, "2026-05-01", "2026-05-31", comment="разовый сбор май")
    assert r.status_code == 201, r.text

    # Открытый «двойник» (та же услуга/дата/цена) — запрещён.
    r = create(4000, "2026-05-01")
    assert r.status_code == 422, r.text
    assert "уже есть" in r.json()["detail"]

    # Открытая ставка с той же датой, но другой ценой — допустима (месяц отличается).
    r = create(2000, "2026-05-01")
    assert r.status_code == 201, r.text

    # И обратная сторона: закрытый период, дублирующий открытую базу, — тоже 422.
    r = create(2000, "2026-05-01", "2026-05-31", comment="дубль базы")
    assert r.status_code == 422, r.text
    assert "уже есть" in r.json()["detail"]
