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
    """Создаёт вид услуги с типом тарифа и тариф к нему (самодостаточно).

    Ед. изм. задаётся на услуге (09.2026), в тарифе не хранится.
    """
    ttype = _tariff_type(db, tariff_type_name)
    svc = ServiceType(services_type=name, priority=0, tariff_type_id=ttype.id)
    db.add(svc)
    db.flush()
    t = Tariff(services_type_id=svc.id,
               price=price, valid_from=date(2000, 1, 2))
    db.add(t)
    db.flush()
    return svc, t


def test_fixed_tariff(db, account_factory):
    rec = account_factory("fix")
    svc, _ = _make_service_with_tariff(db, "__test_Фикс", "Фиксированный", 2000)
    db.commit()
    acc = db.get(Account, rec["account_id"])
    result = A.calculate_accrual_for_account_service(db, acc, db.get(ServiceType, svc.id), date(2099, 12, 31))
    assert result is not None
    assert result["amount"] == 2000.0  # фикс. = тариф, без показаний/площади


def test_square_tariff(db, account_factory):
    rec = account_factory("sq")
    db.execute(text("UPDATE apartments SET square=300 WHERE id=:id"), {"id": rec["apartment_id"]})
    db.commit()
    svc, _ = _make_service_with_tariff(db, "__test_Площадь", "По площади", 10)
    db.commit()
    acc = db.get(Account, rec["account_id"])
    result = A.calculate_accrual_for_account_service(db, acc, db.get(ServiceType, svc.id), date(2099, 12, 31))
    assert result is not None
    assert result["amount"] == 10.0 * 300.0  # тариф × площадь


def test_meter_tariff_uses_consumption(db, account_factory):
    rec = account_factory("met")
    apt = db.get(Apartment, rec["apartment_id"])
    svc, _ = _make_service_with_tariff(db, "__test_Счётчик", "По счетчику", 10)
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


def test_period_tariff_covering_month_takes_priority_over_open(db, account_factory):
    """ 2.18: закрытый тариф-период услуги действует на тот месяц, который он
    покрывает своими valid_from..valid_to, и подменяет открытую базовую ставку
    ровно в этом месяце; в соседние месяцы начисляется открытая база. (Признака
    разовости больше нет — ставка = запись «ставка + срок».)"""
    rec = account_factory("rper")
    ttype = _tariff_type(db, "Фиксированный")
    svc = ServiceType(services_type="__test_ПериодЗамена", priority=0, tariff_type_id=ttype.id)
    db.add(svc)
    db.flush()

    # Открытая база услуги (регулярная ставка, valid_to = NULL).
    regular = Tariff(services_type_id=svc.id,
                     price=100, valid_from=date(2000, 1, 1))
    db.add(regular)
    # Закрытый тариф-период той же услуги на апрель 2018 (замена ставки месяца).
    period = Tariff(services_type_id=svc.id,
                    price=5000, valid_from=date(2018, 4, 1), valid_to=date(2018, 4, 30))
    db.add(period)
    db.flush()
    db.commit()
    acc = db.get(Account, rec["account_id"])

    # Месяц, покрытый закрытым тарифом периода (апрель 2018) — начисляем по нему.
    svc_obj = db.get(ServiceType, svc.id)
    in_month = A.calculate_accrual_for_account_service(db, acc, svc_obj, date(2018, 4, 30))
    assert in_month is not None
    assert in_month["tariff_id"] == period.id  # выбран закрытый периода, не открытая база
    assert in_month["amount"] == 5000.0

    # Соседние месяцы без закрытого периода (май 2018, январь 2019) — открытая база.
    for d in (date(2018, 5, 31), date(2019, 1, 31)):
        other_month = A.calculate_accrual_for_account_service(db, acc, svc_obj, d)
        assert other_month is not None
        assert other_month["tariff_id"] == regular.id  # вернулась открытая база
        assert other_month["amount"] == 100.0
