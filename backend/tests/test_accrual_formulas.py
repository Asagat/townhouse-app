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


def test_oneoff_on_period_takes_priority_over_regular(db, account_factory):
    """ 2.18: разовый тариф услуги действует на месяц своего valid_from
    и подменяет регулярный ровно в этом месяце; в соседние месяцы начисляется
    регулярный. (Раньше разовый вовсе исключался из месячного расчёта — поэтому
    спец-сбор «уходил в долг»: показывался регулярный тариф.)"""
    rec = account_factory("rof")
    ttype = _tariff_type(db, "Фиксированный")
    svc = ServiceType(services_type="__test_Однораз", priority=0, tariff_type_id=ttype.id)
    db.add(svc)
    db.flush()

    # Регулярный тариф услуги (обычная месячная ставка).
    regular = Tariff(services_type_id=svc.id,
                     price=100, valid_from=date(2000, 1, 1), is_oneoff=False)
    db.add(regular)
    # Разовый тариф той же услуги на апрель 2018 (замена ставки месяца).
    oneoff = Tariff(services_type_id=svc.id,
                    price=5000, valid_from=date(2018, 4, 15), is_oneoff=True)
    db.add(oneoff)
    db.flush()
    db.commit()
    acc = db.get(Account, rec["account_id"])

    # Месяц, на который задан разовый (апрель 2018) — начисляем по разовому.
    svc_obj = db.get(ServiceType, svc.id)
    in_month = A.calculate_accrual_for_account_service(db, acc, svc_obj, date(2018, 4, 30))
    assert in_month is not None
    assert in_month["tariff_id"] == oneoff.id   # выбран разовый, не регулярный
    assert in_month["amount"] == 5000.0
    assert in_month["tariff_is_oneoff"] is True

    # Соседний месяц без разового (май 2018) — снова регулярный тариф.
    other_month = A.calculate_accrual_for_account_service(db, acc, svc_obj, date(2018, 5, 31))
    assert other_month is not None
    assert other_month["tariff_id"] == regular.id  # регулярный вернулся
    assert other_month["amount"] == 100.0
    assert other_month["tariff_is_oneoff"] is False

    # Разовый на будущую дату из другого месяца не «перехватывает» позже идущие
    # месяцы (даже если valid_from ещё не наступил для начисляемого месяца).
    jan_2019 = A.calculate_accrual_for_account_service(db, acc, svc_obj, date(2019, 1, 31))
    assert jan_2019 is not None
    assert jan_2019["tariff_id"] == regular.id
    assert jan_2019["amount"] == 100.0
