# tests/test_accrual_formulas.py

"""Тесты формул начислений по типу тарифа:

  - «Фиксированный» : amount = тариф (без счётчика/площади);
  - «По площади»    : amount = тариф × площадь квартиры;
  - «По счетчику»   : amount = тариф × потребление (текущее − предыдущее показание).
"""

from datetime import date, timedelta

from sqlalchemy import text

import app as A
from models import Account, Apartment, Meter, MeterReading, ServiceType, Tariff


def _make_tariff(db, service_id, tariff_type_id, price):
    # Дата строго больше любой существующей для услуги, чтобы наш тариф был выбран расчётом.
    latest = db.execute(
        text("SELECT COALESCE(MAX(valid_from), '2000-01-01') FROM tariffs WHERE services_type_id = :s"),
        {"s": service_id},
    ).scalar()
    vf = (latest or date(2000, 1, 1)) + timedelta(days=1)
    t = Tariff(services_type_id=service_id, tariff_type_id=tariff_type_id,
               price=price, valid_from=vf, unit="u")
    db.add(t)
    db.flush()
    return t


def test_fixed_tariff(db, account_factory):
    rec = account_factory("fix")
    _make_tariff(db, 5, 2, 2000)  # услуга 5, тип «Фиксированный»
    db.commit()
    acc = db.get(Account, rec["account_id"])
    result = A.calculate_accrual_for_account_service(db, acc, db.get(ServiceType, 5), date(2099, 12, 31))
    assert result is not None
    assert result["amount"] == 2000.0  # фикс. = тариф, без показаний/площади


def test_square_tariff(db, account_factory):
    rec = account_factory("sq")
    db.execute(text("UPDATE apartments SET square=300 WHERE id=:id"), {"id": rec["apartment_id"]})
    db.commit()
    _make_tariff(db, 6, 3, 10)  # услуга 6, тип «По площади», price=10
    db.commit()
    acc = db.get(Account, rec["account_id"])
    result = A.calculate_accrual_for_account_service(db, acc, db.get(ServiceType, 6), date(2099, 12, 31))
    assert result is not None
    assert result["amount"] == 10.0 * 300.0  # тариф × площадь


def test_meter_tariff_uses_consumption(db, account_factory):
    rec = account_factory("met")
    apt = db.get(Apartment, rec["apartment_id"])
    meter = Meter(services_type_id=7, apartment_id=apt.id, serial_number=f"TM-{rec['account_id']}")
    db.add(meter)
    db.flush()
    db.add(MeterReading(document_id=None, apartment_id=apt.id, meter_id=meter.id,
                        services_type_id=7, reading=40, reading_date=date(2099, 1, 1)))
    db.add(MeterReading(document_id=None, apartment_id=apt.id, meter_id=meter.id,
                        services_type_id=7, reading=100, reading_date=date(2099, 2, 1)))
    db.commit()
    _make_tariff(db, 7, 1, 10)  # услуга 7, тип «По счетчику», price=10
    db.commit()
    acc = db.get(Account, rec["account_id"])
    result = A.calculate_accrual_for_account_service(db, acc, db.get(ServiceType, 7), date(2099, 12, 31))
    assert result is not None
    assert result["consumption"] == 60.0
    assert result["amount"] == 10.0 * 60.0  # тариф × потребление
