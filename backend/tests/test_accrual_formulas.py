# tests/test_accrual_formulas.py

"""Тесты формул начислений по типу тарифа:

  - «Фиксированный» : amount = тариф (без счётчика/площади);
  - «По площади»    : amount = тариф × площадь квартиры;
  - «По счетчику»   : amount = тариф × потребление (текущее − предыдущее показание).

Тесты самодостаточны: создают собственные виды услуг и тарифы, поэтому не зависят
от наличия/ID услуг и типов тарифов в справочнике.
"""

from datetime import date

from sqlalchemy import text

import app as A
from models import Account, Apartment, Meter, MeterReading, ServiceType, Tariff, TariffType


def _tariff_type(db, name: str) -> TariffType:
    """Тип тарифа (по имени). Служебные имена зашиты в расчёт («По площади»,
    «Фиксированный», «По счетчику»). Переиспользует существующий, если есть."""
    tt = db.query(TariffType).filter(TariffType.name == name).first()
    if tt:
        return tt
    tt = TariffType(name=name)
    db.add(tt)
    db.flush()
    return tt


def _make_service_with_tariff(db, name: str, tariff_type_name: str, price):
    """Создаёт вид услуги и тариф к нему (самодостаточно, без привязки к ID)."""
    svc = ServiceType(services_type=name, priority=0)
    db.add(svc)
    db.flush()
    ttype = _tariff_type(db, tariff_type_name)
    t = Tariff(services_type_id=svc.id, tariff_type_id=ttype.id,
               price=price, valid_from=date(2000, 1, 2), unit="u")
    db.add(t)
    db.flush()
    return svc, t


def test_fixed_tariff(db, account_factory):
    rec = account_factory("fix")
    svc, _ = _make_service_with_tariff(db, "тест Фикс", "Фиксированный", 2000)
    db.commit()
    acc = db.get(Account, rec["account_id"])
    result = A.calculate_accrual_for_account_service(db, acc, db.get(ServiceType, svc.id), date(2099, 12, 31))
    assert result is not None
    assert result["amount"] == 2000.0  # фикс. = тариф, без показаний/площади


def test_square_tariff(db, account_factory):
    rec = account_factory("sq")
    db.execute(text("UPDATE apartments SET square=300 WHERE id=:id"), {"id": rec["apartment_id"]})
    db.commit()
    svc, _ = _make_service_with_tariff(db, "тест Площадь", "По площади", 10)
    db.commit()
    acc = db.get(Account, rec["account_id"])
    result = A.calculate_accrual_for_account_service(db, acc, db.get(ServiceType, svc.id), date(2099, 12, 31))
    assert result is not None
    assert result["amount"] == 10.0 * 300.0  # тариф × площадь


def test_meter_tariff_uses_consumption(db, account_factory):
    rec = account_factory("met")
    apt = db.get(Apartment, rec["apartment_id"])
    svc, _ = _make_service_with_tariff(db, "тест Счётчик", "По счетчику", 10)
    db.commit()
    meter = Meter(services_type_id=svc.id, apartment_id=apt.id,
                  serial_number=f"TM-{svc.id}-{rec['account_id']}")
    db.add(meter)
    db.flush()
    db.add(MeterReading(document_id=None, apartment_id=apt.id, meter_id=meter.id,
                        services_type_id=svc.id, reading=40, reading_date=date(2099, 1, 1)))
    db.add(MeterReading(document_id=None, apartment_id=apt.id, meter_id=meter.id,
                        services_type_id=svc.id, reading=100, reading_date=date(2099, 2, 1)))
    db.commit()
    acc = db.get(Account, rec["account_id"])
    result = A.calculate_accrual_for_account_service(db, acc, db.get(ServiceType, svc.id), date(2099, 12, 31))
    assert result is not None
    assert result["consumption"] == 60.0
    assert result["amount"] == 10.0 * 60.0  # тариф × потребление
