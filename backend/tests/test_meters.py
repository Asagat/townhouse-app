# tests/test_meters.py
"""П. 2.7 роадмапа: счётчик можно заводить только к услуге с тарифом «По счетчику».

Проверяются чистые функции из services.py (service_supports_meter /
validate_meter_service_type); HTTP-слой generic CRUD вызывает их на create/update
ресурса meters (см. app.py).
"""

import pytest
from datetime import date
from fastapi import HTTPException

from models import ServiceType, Tariff, TariffType
from services import (
    METER_TARIFF_TYPE_NAME,
    service_supports_meter,
    validate_meter_service_type,
)


def _meter_tariff_type(db) -> TariffType:
    """Системный тип тарифа «По счетчику» (init_data); если отсутствует — создаёт."""
    tt = db.query(TariffType).filter(TariffType.name == METER_TARIFF_TYPE_NAME).first()
    if tt is None:
        tt = TariffType(name=METER_TARIFF_TYPE_NAME)
        db.add(tt)
        db.flush()
    return tt


def _make_service(db, name: str, meter_tariff_type: TariffType | None) -> ServiceType:
    """Создаёт услугу (удаляется авто-фикстурой conftest по префиксу __test_)."""
    svc = ServiceType(services_type=name, priority=0)
    db.add(svc)
    db.flush()
    if meter_tariff_type is not None:
        db.add(
            Tariff(
                services_type_id=svc.id,
                tariff_type_id=meter_tariff_type.id,
                price=10.00,
                valid_from=date(2020, 1, 1),
            )
        )
        db.flush()
    return svc


def test_service_supports_meter_detects_tariff(db):
    meter_tt = _meter_tariff_type(db)
    ok_svc = _make_service(db, "__test_meter_ok", meter_tt)
    plain_svc = _make_service(db, "__test_meter_plain", None)
    db.commit()

    assert service_supports_meter(db, ok_svc.id) is True
    assert service_supports_meter(db, plain_svc.id) is False
    assert service_supports_meter(db, None) is False
    assert service_supports_meter(db, "") is False


def test_validate_meter_service_type_rejects_unsupported(db):
    meter_tt = _meter_tariff_type(db)
    ok_svc = _make_service(db, "__test_meter_ok2", meter_tt)
    plain_svc = _make_service(db, "__test_meter_plain2", None)
    db.commit()

    # Допустимая услуга — исключений нет.
    validate_meter_service_type(db, ok_svc.id)

    # Услуга без тарифа «По счетчику» — 422 с понятным текстом.
    with pytest.raises(HTTPException) as exc_info:
        validate_meter_service_type(db, plain_svc.id)
    assert exc_info.value.status_code == 422
    assert METER_TARIFF_TYPE_NAME in exc_info.value.detail

    # Несуществующая услуга / пустое значение — 422.
    with pytest.raises(HTTPException) as exc_info:
        validate_meter_service_type(db, 999_999_999)
    assert exc_info.value.status_code == 422
    with pytest.raises(HTTPException):
        validate_meter_service_type(db, None)
