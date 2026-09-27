# tests/test_apartment_residents.py

"""Б8: сведения о жильцах и тариф «На человека»."""

from datetime import date

from sqlalchemy import text

import app as A
from models import (
    Account,
    ApartmentResident,
    ResidentRole,
    ServiceType,
    Tariff,
    TariffType,
)


def _tariff_type(db, name: str) -> TariffType:
    tt = db.query(TariffType).filter(TariffType.name == name).first()
    if tt:
        return tt
    tt = TariffType(name=name)
    db.add(tt)
    db.flush()
    return tt


def _make_service_with_tariff(db, name: str, tariff_type_name: str, price):
    ttype = _tariff_type(db, tariff_type_name)
    svc = ServiceType(services_type=name, priority=0, tariff_type_id=ttype.id)
    db.add(svc)
    db.flush()
    db.add(Tariff(services_type_id=svc.id, price=price, valid_from=date(2000, 1, 2)))
    db.flush()
    return svc


def test_per_person_tariff(db, account_factory):
    rec = account_factory("perperson")
    svc = _make_service_with_tariff(db, "__test_Человек", "На человека", 10)
    db.commit()

    db.add_all(
        [
            ApartmentResident(apartment_id=rec["apartment_id"], full_name="А", role=ResidentRole.tenant),
            ApartmentResident(apartment_id=rec["apartment_id"], full_name="Б", role=ResidentRole.owner),
            # Выбыл задолго до периода.
            ApartmentResident(
                apartment_id=rec["apartment_id"], full_name="В",
                role=ResidentRole.tenant, date_to=date(2000, 1, 1),
            ),
            # Ещё не проживает на дату начисления.
            ApartmentResident(
                apartment_id=rec["apartment_id"], full_name="Г",
                role=ResidentRole.tenant, date_from=date(2099, 1, 1),
            ),
        ]
    )
    db.commit()
    try:
        acc = db.get(Account, rec["account_id"])
        result = A.calculate_accrual_for_account_service(
            db, acc, db.get(ServiceType, svc.id), date(2026, 6, 30)
        )
        assert result is not None
        assert result["amount"] == 20.0  # тариф 10 × 2 активных жильца
        assert "2 чел." in result["tariff_id_label"]
    finally:
        db.execute(
            text("DELETE FROM apartment_residents WHERE apartment_id = :a"),
            {"a": rec["apartment_id"]},
        )
        db.commit()
