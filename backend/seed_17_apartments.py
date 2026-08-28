"""
Наполнение справочников тестовыми данными на 17 квартир (идемпотентно).

Создаёт (только если ещё нет / не переводит в нужное состояние):
  - 17 владельцев с казахскими ФИО и казахстанскими телефонами;
  - 17 квартир (номера 101..117);
  - 17 лицевых счетов (LS-000101..LS-000117);
  - кассы «Касса» и «Счёт в Каспи»;
  - счётчики на каждую квартиру для услуг со счётчиком из справочника;
  - показания счётчиков за ТЕКУЩИЙ месяц для всех услуг со счётчиком;
  - пользователей на все роли (пароль fth123).

Услуги, типы тарифов и тарифы ожидаются заранее созданными скриптом
`init_data.py` (запускается при развёртывании до первого старта).

Скрипт ИДЕМПОТЕНТЕН: повторный запуск ничего не ломает и не дублирует —
проверяется существование по уникальным ключам (номер квартиры, номер счёта,
серийный номер счётчика, телефон владельца, чтение по квартире/услуге/дате,
username пользователя). Дампа БД нет, поэтому данные генерируются
детерминированно по номеру квартиры.

Запуск из каталога backend:
    python seed_17_apartments.py
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from database import SessionLocal  # noqa: E402
from auth import hash_password  # noqa: E402
from sqlalchemy import text  # noqa: E402
from models import (  # noqa: E402
    Account,
    Apartment,
    CashPoint,
    Meter,
    MeterReading,
    MeterReadingDocument,
    Owner,
    ServiceType,
    User,
    UserRole,
)

# Количество квартир для наполнения.
NUM_APARTMENTS = 17

# Первый номер квартиры и лицевого счёта.
FIRST_APT_NUM = 1

# Адрес комплекса (квартирная нумерация отдельным полем apartment_number).
BASE_ADDRESS = "Алматы, ул. Цветочная 1/8"

# Площади квартир: диапазон 265..340 м², прогрессия по номеру квартиры.
AREA_MIN = 265.0
AREA_MAX = 340.0

# Услуги, по которым заводятся счётчики и показания (тип тарифа «По счетчику», задан в init_data).
METER_SERVICES = ["Электричество", "Холодная вода"]

# Названия месяцев для автогенерации названия документа показаний (синхронно с app.py).
MONTH_NAMES_RU = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]

# Пароль для всех тестовых пользователей.
TEST_USER_PASSWORD = "fth123"

# Пользователи на все роли: (username, role)
USERS_BY_ROLE = [
    ("admin", UserRole.admin),
    ("operator", UserRole.operator),
    ("cashier", UserRole.cashier),
    ("controller", UserRole.controller),
    ("resident", UserRole.resident),
]


def _owner_for_apt(idx: int) -> dict:
    """Детерминированные казахские ФИО и KZ-телефон по индексу квартиры (0..NUM-1)."""
    surnames = ["Ахметов", "Омаров", "Сулейменов", "Нуртас", "Искаков", "Бекенов",
                "Жумабаев", "Тлеубердиев", "Сатпаев", "Калмурзаев", "Айтхожин",
                "Досмухамбетов", "Ермеков", "Серикбаев", "Нурахметов", "Тажибаев",
                "Баймуратов"]
    names = ["Айдар", "Дамир", "Ерлан", "Марат", "Нурлан", "Серик",
             "Тимур", "Асхат", "Бауыржан", "Галым", "Жандос", "Канат",
             "Мейрамбек", "Нуржан", "Руслан", "Самат", "Талгат"]
    last_name = surnames[idx % len(surnames)]
    first_name = names[idx % len(names)]
    # Казахстанские мобильные коды операторов (Kcell, Beeline/Activ, Tele2/Altel, IZI).
    kz_codes = [701, 702, 705, 707, 708, 710, 775, 776, 777, 778]
    code = kz_codes[(idx + 3) % len(kz_codes)]
    return {
        "last_name": last_name,
        "first_name": first_name,
        "middle_name": "",
        "full_name": f"{last_name} {first_name}".strip(),
        "phone": f"+7 ({code}) {100 + idx * 13:03d}-{1000 + idx * 37:04d}",
        "email": f"s{idx + 1}@mail.kz",
        "contact_info": f"Владелец квартиры {FIRST_APT_NUM + idx}",
    }


def _create_owner(db, idx: int) -> Owner:
    data = _owner_for_apt(idx)
    existing = db.query(Owner).filter(Owner.phone == data["phone"]).first()
    if existing:
        # Синхронизируем ФИО у уже существующего владельца (самовосстановление при
        # изменении списков имён/фамилий в генераторе), телефон — неизменный ключ.
        if existing.full_name != data["full_name"]:
            print(f"  ~ владелец {existing.full_name} -> {data['full_name']}")
            existing.full_name = data["full_name"]
            existing.first_name = data["first_name"]
            existing.last_name = data["last_name"]
            existing.middle_name = data["middle_name"] or None
        return existing

    owner = Owner(
        full_name=data["full_name"],
        first_name=data["first_name"],
        last_name=data["last_name"],
        middle_name=data["middle_name"] or None,
        phone=data["phone"],
        email=data["email"],
        contact_info=data["contact_info"],
        is_active=True,
    )
    db.add(owner)
    db.flush()
    print(f"  + владелец: {owner.full_name} ({owner.phone})")
    return owner


def _create_apartment(db, idx: int, owner: Owner) -> Apartment:
    apt_num = FIRST_APT_NUM + idx
    existing = db.query(Apartment).filter(Apartment.apartment_number == apt_num).first()
    if existing:
        # Квартира может существовать от прошлых прогонов/старых данных —
        # перепривязываем к нужному (актуальному) владельцу.
        if existing.owner_id != owner.id:
            old_owner = existing.owner
            print(f"  ~ кв.{apt_num}: собственник {old_owner.full_name if old_owner else '?'} -> {owner.full_name}")
            existing.owner_id = owner.id
            db.flush()  # фиксируем перепривязку до чистки осиротевших владельцев
        return existing

    # Единый адрес комплекса; квартиры нумеруются 1..NUM.
    area_step = (AREA_MAX - AREA_MIN) / (NUM_APARTMENTS - 1)
    apt = Apartment(
        owner_id=owner.id,
        apartment_number=apt_num,
        square=round(AREA_MIN + idx * area_step, 1),
        address=f"{BASE_ADDRESS}, кв. {apt_num}",
    )
    db.add(apt)
    db.flush()
    print(f"  + квартира №{apt.apartment_number}: {apt.address} ({apt.square} м²)")
    return apt


def _cleanup_orphan_owners(db) -> None:
    """Удаляет владельцев, у которых не осталось квартир (после перепривязки)."""
    orphans = db.query(Owner).filter(~Owner.apartments.any()).all()
    for o in orphans:
        print(f"  - удалён осиротевший владелец: {o.full_name}")
        db.delete(o)


def _create_account(db, idx: int, apartment: Apartment) -> Account:
    account_number = f"FTH-{FIRST_APT_NUM + idx:03d}"
    existing = db.query(Account).filter(Account.account_number == account_number).first()
    if existing:
        return existing

    account = Account(
        apartment_id=apartment.id,
        account_number=account_number,
        account_name=f"Лицевой счёт кв. {apartment.apartment_number}",
        is_active=True,
    )
    db.add(account)
    db.flush()
    print(f"  + лицевой счёт: {account.account_number} — {account.account_name}")
    return account


def _ensure_cash_points(db) -> None:
    """Приводит кассы к нужным именам: «Касса» и «Счёт в Каспи» (идемпотентно)."""
    desired = ["Касса", "Счёт в Каспи"]
    existing = db.query(CashPoint).order_by(CashPoint.id.asc()).all()

    # Первое прохождение: переименовать существующие в первые несовпавшие нужные имена.
    for cp in existing:
        if cp.name in desired:
            continue
        # Берём первый из желаемых, чьё имя ещё не занято ни одной кассой.
        for target in desired:
            taken = any(c.name == target for c in existing)
            if not taken:
                print(f"  ~ касса '{cp.name}' переименована в '{target}'")
                cp.name = target
                break
        else:
            # Все желаемые имена заняты иных касс — деактивируем лишнюю, чтобы не путать.
            cp.is_active = False
            print(f"  ~ касса '{cp.name}' деактивирована (лишняя)")

    # Второе прохождение: создаём недостающие кассы с нужными именами.
    names_now = [c.name for c in db.query(CashPoint).all()]
    for name in desired:
        if name not in names_now:
            db.add(CashPoint(name=name, is_active=True))
            db.flush()
            print(f"  + касса: {name}")


def _ensure_meters(db, apartment: Apartment, services: list[ServiceType]) -> None:
    """Для каждой «счётчиковой» услуги создаёт счётчик на квартиру (если нет)."""
    for svc in services:
        has_meter = (
            db.query(Meter)
            .filter(
                Meter.apartment_id == apartment.id,
                Meter.services_type_id == svc.id,
            )
            .first()
        )
        if has_meter:
            continue
        serial = f"{svc.services_type[0]}-{apartment.apartment_number}-{svc.id}"
        meter = Meter(
            serial_number=serial,
            apartment_id=apartment.id,
            services_type_id=svc.id,
            installed_at=date(2023, 1, 15),
        )
        db.add(meter)
        db.flush()
        print(f"  + счётчик: {serial} ({svc.services_type})")


def _ensure_meter_readings(db, services: list[ServiceType]) -> None:
    """
    Генерирует показания и документы показаний за ТЕКУЩИЙ месяц для каждой
    «счётчиковой» услуги. Идемпотентно: документ пропускается, если на этот
    месяц/услугу уже есть; запись показания — если уже создана для квартиры/услуги/даты.
    """
    today = date.today()
    reading_date = date(today.year, today.month, 1)
    month_label = MONTH_NAMES_RU[today.month - 1]
    title = f"Показания за {month_label} {today.year}"

    for svc in services:
        # Документ показаний по услуге на текущий месяц.
        existing_doc = (
            db.query(MeterReadingDocument)
            .filter(
                MeterReadingDocument.services_type_id == svc.id,
                MeterReadingDocument.reading_date == reading_date,
            )
            .first()
        )
        if existing_doc:
            document = existing_doc
            print(f"  ~ документ показаний уже есть: {existing_doc.title} ({svc.services_type})")
        else:
            document = MeterReadingDocument(
                title=title,
                reading_date=reading_date,
                services_type_id=svc.id,
            )
            db.add(document)
            db.flush()
            print(f"  + документ показаний: {title} ({svc.services_type})")

        # Показания по квартирам, у которых есть счётчик на эту услугу.
        meters = (
            db.query(Meter)
            .filter(
                Meter.services_type_id == svc.id,
                Meter.apartment_id.isnot(None),
            )
            .order_by(Meter.apartment_id.asc())
            .all()
        )
        for meter in meters:
            apt_num = meter.apartment.apartment_number if meter.apartment else meter.apartment_id
            existing_reading = (
                db.query(MeterReading)
                .filter(
                    MeterReading.apartment_id == meter.apartment_id,
                    MeterReading.services_type_id == svc.id,
                    MeterReading.reading_date == reading_date,
                )
                .first()
            )
            if existing_reading:
                continue
            # Нарастающее детерминированное показание; эл. — сотни, вода — десятки.
            base = apt_num * (37 if svc.services_type == "Электричество" else 9)
            value = base + today.month * (5 if svc.services_type == "Электричество" else 1)
            reading = MeterReading(
                document_id=document.id,
                apartment_id=meter.apartment_id,
                meter_id=meter.id,
                services_type_id=svc.id,
                reading=value,
                reading_date=reading_date,
            )
            db.add(reading)
            print(f"  + показание: кв.{apt_num} {svc.services_type} = {value} (за {month_label})")


def _ensure_users(db, resident_account_id: int | None = None) -> None:
    """Создаёт/обновляет пользователей на все роли с паролем fth123 (идемпотентно).

    Роль resident дополнительно привязывается к лицевому счёту (`account_id`) —
    нужен для Личного кабинета (ЛК) жителя.
    """
    for username, role in USERS_BY_ROLE:
        user = db.query(User).filter(User.username == username).first()
        password_hash = hash_password(TEST_USER_PASSWORD)
        if user:
            # Обновляем пароль и роль, чтобы соответствовать тестовым данным.
            user.password_hash = password_hash
            user.role = role
            user.is_active = True
            if not user.full_name:
                user.full_name = f"Тестовый {role.value}"
            if role == UserRole.resident and resident_account_id is not None:
                user.account_id = resident_account_id
            print(f"  ~ пользователь '{username}' обновлён (роль '{role.value}')")
        else:
            db.add(User(
                username=username,
                password_hash=password_hash,
                full_name=f"Тестовый {role.value}",
                role=role,
                is_active=True,
                account_id=resident_account_id if role == UserRole.resident else None,
            ))
            print(f"  + пользователь '{username}' (роль '{role.value}')")


def _reset_test_data(db) -> None:
    """Полная очистка тестовых таблиц и сброс автоинкремента ID на 1.

    Вызывается с флагом --reset. Удаляет тестовые данные в порядке зависимостей
    и сбрасывает последовательности PostgreSQL, чтобы новые ID начинались с 1
    (например, справочник «Контрагенты»/owners). Кассы, услуги, тарифы, типы
    тарифов и пользователи не трогаются.
    """
    print("Сброс тестовых данных (--reset):")
    # Порядок важен: дети удаляются раньше родителей (FK RESTRICT).
    order = [
        (MeterReading.__tablename__, "показания"),
        (MeterReadingDocument.__tablename__, "документы показаний"),
        (Meter.__tablename__, "счётчики"),
        (Account.__tablename__, "лицевые счета"),
        (Apartment.__tablename__, "квартиры"),
        (Owner.__tablename__, "контрагенты (владельцы)"),
    ]
    for table, label in order:
        db.execute(text(f"DELETE FROM \"{table}\""))
        print(f"  - очищена таблица: {table} ({label})")

    # Сброс автоинкремента (PostgreSQL: таблица_имя_id_seq) на 1.
    for table, _ in order:
        db.execute(text(f"ALTER SEQUENCE \"{table}_id_seq\" RESTART WITH 1"))
    print("  - последовательности ID сброшены (начнутся с 1)")


def _parse_args() -> bool:
    """Возвращает True, если запрошена полная пересборка (--reset)."""
    import argparse
    parser = argparse.ArgumentParser(description="Наполнение тестовыми данными на 17 квартир")
    parser.add_argument(
        "--reset", action="store_true",
        help="Полная очистка тестовых таблиц и сброс ID на 1 перед наполнением",
    )
    return parser.parse_args().reset


def main() -> None:
    reset = _parse_args()
    db = SessionLocal()
    try:
        services = (
            db.query(ServiceType).filter(ServiceType.services_type.in_(METER_SERVICES)).all()
        )
        if not services:
            print("⚠️  Услуги со счётчиком не найдены. Сначала запустите: python init_data.py")
            db.close()
            sys.exit(1)

        if reset:
            _reset_test_data(db)

        print(f"Наполнение тестовыми данными на {NUM_APARTMENTS} квартир:")
        _ensure_cash_points(db)
        for idx in range(NUM_APARTMENTS):
            owner = _create_owner(db, idx)
            apartment = _create_apartment(db, idx, owner)
            _create_account(db, idx, apartment)
            _ensure_meters(db, apartment, services)

        _cleanup_orphan_owners(db)
        _ensure_meter_readings(db, services)
        # Привязываем resident к лицевому счёту первой квартиры (для ЛК).
        first_account = db.query(Account).filter(Account.account_number == f"FTH-{FIRST_APT_NUM:03d}").first()
        _ensure_users(db, resident_account_id=first_account.id if first_account else None)

        db.commit()
        print("Готово. Справочники, показания и пользователи наполнены.")
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"Ошибка: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
