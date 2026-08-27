"""
Инициализация СИСТЕМНЫХ справочников (идемпотентно).

Запускается ПОСЛЕ bootstrap_db.py (создание схемы) и ПЕРЕД первым запуском
приложения на новом окружении (локально или на VPS). Создаёт справочники,
которые раньше заводились вручную в БД:

  - типы тарифов: «По счетчику», «Фиксированный», «По площади» (зашиты логикой,
    неизменяемы) — см. app.calculate_accrual_for_account_service;
  - типовые виды услуг (с приоритетом списания);
  - дефолтные тарифы для услуг (если у услуги тарифа ещё нет).

Скрипт идемпотентен: ничего не перезаписывает, только создаёт отсутствующее.
Безопасен и на уже существующей БД (там просто ничего не создаст повторно).

Запуск из каталога backend:
    python init_data.py
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Гарантируем UTF-8 для stdout (кириллица в логах на любом окружении).
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from database import SessionLocal  # noqa: E402
from models import ServiceType, Tariff, TariffType  # noqa: E402


# Типы тарифов (системные, имена зашиты в логику расчёта — не менять).
_TARIFF_TYPES = ["По счетчику", "Фиксированный", "По площади", "На человека"]

# Услуги по умолчанию: (название, приоритет списания). Ниже — вариант по умолчанию.
_SERVICES = [
    ("Электричество", 1),
    ("Холодная вода", 2),
    ("Охрана", 3),
    ("Обслуживание ТП", 4),
    ("Фонд развития", 5),
]

# Дефолтные тарифы: (название_услуги, имя_типа, цена). Создаются, только если
# у услуги вообще нет ни одного тарифа.
_DEFAULT_TARIFFS = [
    ("Электричество", "По счетчику", 50.00),
    ("Холодная вода", "По счетчику", 5.00),
    ("Охрана", "Фиксированный", 2000.00),
    ("Фонд развития", "Фиксированный", 5000.00),
    ("Обслуживание ТП", "По площади", 10.00),
]


def _ensure_tariff_types(db) -> dict[str, TariffType]:
    """Создаёт недостающие типы тарифов, возвращает {имя: объект}."""
    result: dict[str, TariffType] = {}
    for name in _TARIFF_TYPES:
        tt = db.query(TariffType).filter(TariffType.name == name).first()
        if not tt:
            tt = TariffType(name=name)
            db.add(tt)
            db.flush()
            print(f"  + тип тарифа: {name}")
        result[name] = tt
    return result


def _ensure_services(db) -> dict[str, ServiceType]:
    """Создаёт недостающие услуги по умолчанию, возвращает {название: объект}."""
    result: dict[str, ServiceType] = {}
    for sname, prio in _SERVICES:
        svc = db.query(ServiceType).filter(ServiceType.services_type == sname).first()
        if not svc:
            svc = ServiceType(services_type=sname, priority=prio)
            db.add(svc)
            db.flush()
            print(f"  + услуга: {sname} (приоритет {prio})")
        result[sname] = svc
    return result


def _ensure_tariffs(db, services: dict[str, ServiceType], tariff_types: dict[str, TariffType]) -> None:
    """Создаёт дефолтные тарифы, если у услуги тарифов ещё нет."""
    for sname, ttype_name, price in _DEFAULT_TARIFFS:
        svc = services.get(sname)
        if svc is None:
            continue
        has_tariff = db.query(Tariff).filter(Tariff.services_type_id == svc.id).count() > 0
        if has_tariff:
            continue
        tt = tariff_types[ttype_name]
        db.add(Tariff(
            services_type_id=svc.id,
            tariff_type_id=tt.id,
            price=price,
            valid_from=date(2000, 1, 2),  # до всех реальных периодов — чтобы не мешать
        ))
        print(f"  + тариф: {sname} ({ttype_name}) = {price}")


def main() -> None:
    db = SessionLocal()
    try:
        print("Инициализация системных справочников:")
        tariff_types = _ensure_tariff_types(db)
        services = _ensure_services(db)
        _ensure_tariffs(db, services, tariff_types)
        db.commit()
        print("Готово.")
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"Ошибка: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
