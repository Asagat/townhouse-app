"""
seed_demo_data.py — генерация ДЕМОНСТРАЦИОННЫХ данных (документы + регистры).

Назначение: наполнить ЧИСТУЮ (демо-)БД правдоподобным набором данных, чтобы
показать систему целиком — лицевые счёта, показания, начисления, квитанции,
кассу и производные регистры. Данные вымышленные; суммы/ставки взяты похожими
на реальные (сняты с боевой БД как ориентир).

Что создаётся (в порядке, как это делает приложение — «документ → регистр»):
  1. справочники (идемпотентно): типы тарифов, 6 видов услуг с приоритетами и
     типами, касса, статьи аналитики;
  2. тарифы услуг (ставки похожи на реальные: э/э 40 ₸/кВт·ч, фиксированные — см. SERVICES);
  3. собственники → квартиры → лицевые счёта → счётчики (только «По счетчику»);
  4. показания: базовый замер ДО демо-периода + по одному за каждый демо-месяц
     (потребление = разность показаний — так считает `calculate_accrual_for_account_service`);
  5. документы начислений (по одному на месяц) и строки `accruals_register`;
  6. документы «Приход/Расход» и строки `cash_register` (жительские оплаты + расходы кассы);
  7. пересборка производного `accounts_register` штатным `rebuild_accounts_register`
     (детерминированное распределение денег по услугам по приоритету);
  8. квитанции по каждому счёту за каждый месяц (`generate_receipt_document`);
  9. контроль: `check_register_integrity` по всем л/с + контрольные суммы.

БЕЗОПАСНОСТЬ
  - по умолчанию — сухой прогон (ничего не пишет в БД);
  - запись только с `--apply`;
  - `--apply` отказывается работать, если в целевой БД уже есть бизнес-данные
    (контрагенты/квартиры/счета/счётчики/документы/регистры) — чтобы случайно не
    смешать демо с реальными данными. Для повторного прогона на ЗАВЕДОМО
    демонстрационной БД есть `--wipe` (удаляет бизнес-данные перед генерацией).
  - скрипт печатает целевую БД (пароль маскируется) до любых изменений.

Запуск из каталога backend (на демо-БД, например DATABASE_URL=...townhouse_demo):
    python migrations/seed_demo_data.py                          # план (dry-run)
    python migrations/seed_demo_data.py --apply                  # создать данные
    python migrations/seed_demo_data.py --apply --wipe           # пересоздать с нуля
    python migrations/seed_demo_data.py --apply --residents      # + ЛК-пользователи

Опции: --months N (по умолчанию 3), --apartments N (10), --end ГГГГ-ММ
(последний демо-месяц; по умолчанию — последний завершённый), --seed N,
--no-payments, --residents.
"""

import argparse
import calendar
import os
import random
import re
import sys
from datetime import date, datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from database import SessionLocal, SQLALCHEMY_DATABASE_URL  # noqa: E402
from models import (  # noqa: E402
    AccrualDocument,
    Account,
    AnalyticArticle,
    AnalyticKind,
    Apartment,
    CashPoint,
    Counterparty,
    Meter,
    MeterReading,
    MeterReadingDocument,
    ServiceType,
    Tariff,
    TariffType,
    Transaction,
    TransactionTypeEnum,
    User,
    UserRole,
)
from auth import hash_password  # noqa: E402
from services import (  # noqa: E402
    audit_document_create,
    build_accrual_register_items,
    build_meter_reading_document_title,
    default_accrual_document_title,
    set_transaction_title,
)
from writeoffs import check_register_integrity, rebuild_accounts_register  # noqa: E402


# --- ПАРАМЕТРЫ ДЕМО-ДАННЫХ -------------------------------------------------

DEFAULT_APARTMENTS = 10
DEFAULT_MONTHS = 3
DEFAULT_SEED = 20260915

STREET = "ул. Демонстрационная"
HOUSE = "д. 1/10"
BASE_URL_MASK = "***"

# Канонические виды услуг и ставки — «похоже на реальные» (ориентир — боевая БД):
# (название, приоритет списания, тип тарифа, ед. изм., ставка ₸).
SERVICES = [
    ("Электроэнергия", 1, "По счетчику", "кВт*ч", Decimal("40.00")),
    ("Охрана", 2, "Фиксированный", "В месяц", Decimal("14760.00")),
    ("Охрана - электроэнергия", 3, "Фиксированный", "В месяц", Decimal("1000.00")),
    ("Обслуживание ТП", 4, "Фиксированный", "В месяц", Decimal("4000.00")),
    ("Вывоз мусора", 5, "Фиксированный", "В месяц", Decimal("3000.00")),
    ("Фонд развития", 6, "Фиксированный", "В месяц", Decimal("2000.00")),
]
METER_SERVICE = "Электроэнергия"  # единственная услуга «По счетчику»

# 10 вымышленных собственников (казахстанские ФИО).
# (ФИО полностью, имя, фамилия, отчество).
OWNERS = [
    ("Мыркынбаева Мыркынбая", "Мыркынбая", "Мыркынбаева", None),
    ("Абдуллаев Ерлан Серикович", "Ерлан", "Абдуллаев", "Серикович"),
    ("Нурпеисова Айгуль Маратовна", "Айгуль", "Нурпеисова", "Маратовна"),
    ("Смагулов Данияр Аскарович", "Данияр", "Смагулов", "Аскарович"),
    ("Оспанова Жанар Бекзатовна", "Жанар", "Оспанова", "Бекзатовна"),
    ("Жумабаев Тимур Нурланович", "Тимур", "Жумабаев", "Нурланович"),
    ("Ибраева Сауле Кайратовна", "Сауле", "Ибраева", "Кайратовна"),
    ("Касымов Асхат Ерболович", "Асхат", "Касымов", "Ерболович"),
    ("Бектурова Динара Сериковна", "Динара", "Бектурова", "Сериковна"),
    ("Ахметов Нурлан Маратович", "Нурлан", "Ахметов", "Маратович"),
]

# Жительские оплаты: доля от начисления месяца по порядку квартиры (0 = должник).
PAY_FRACTIONS = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.5, 0.0, 1.0]

# Расходы кассы за месяц: (статья, сумма ₸).
EXPENSES = [
    ("Заработная плата персонала", Decimal("620000.00")),
    ("Вывоз мусора и утилизация", Decimal("45000.00")),
    ("Материалы и инвентарь", Decimal("38000.00")),
]
INCOME_ARTICLE = "Поступления от жителей"

# Расходы кассы идут без привязки к квартире — учёт общий (account_id = NULL).
EXPENSE_DAY = 25
PAYMENT_DAY = 15

# Демо-БД не должна содержать реальных данных — проверяем эти таблицы.
BUSINESS_TABLES = [
    "counterparties", "apartments", "accounts", "meters",
    "meter_reading_documents", "meter_readings",
    "accrual_documents", "accruals_register",
    "receipt_documents", "receipt_items",
    "transactions", "cash_register", "accounts_register",
    "writeoff_documents", "writeoff_items",
]
# Удаление бизнес-данных (порядок: производные → первичные → справочные владельцы).
WIPE_ORDER = [
    "accounts_register", "cash_register",
    "receipt_items", "receipt_documents",
    "writeoff_items", "writeoff_documents",
    "accruals_register", "accrual_documents",
    "meter_readings", "meter_reading_documents",
    "transactions", "meters", "accounts",
    "apartments", "counterparties", "tariffs",
]

RESIDENT_PASSWORD = "demo12345"


# --- МЕЛКИЕ ПОМОЩНИКИ ------------------------------------------------------

def month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def month_seq(end_year: int, end_month: int, count: int) -> list[tuple[int, int]]:
    """Последовательность (год, месяц) длиной count, заканчивающаяся end."""
    out: list[tuple[int, int]] = []
    y, m = end_year, end_month
    for _ in range(count):
        out.append((y, m))
        y, m = prev_month(y, m)
    return list(reversed(out))


def account_opens_late(index: int, apartments: int, months_count: int) -> bool:
    """Последний л/с открывается со ВТОРОГО демо-месяца (демонстрация учёта opened_at)."""
    return index == apartments - 1 and months_count > 1


def month_label(year: int, month: int) -> str:
    names = [
        "январь", "февраль", "март", "апрель", "май", "июнь",
        "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
    ]
    return f"{names[month - 1]} {year}"


def masked_db_url() -> str:
    """DATABASE_URL с замаскированным паролем (безопасно печатать)."""
    return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:" + BASE_URL_MASK + "@", SQLALCHEMY_DATABASE_URL)


def apartment_address(number: int) -> str:
    return f"{STREET}, {HOUSE}, кв. {number}"


def phone_for(index: int) -> str:
    return f"777{6000000 + index * 11111:07d}"


# --- ПЛАН (чистая функция — для dry-run) -----------------------------------

def build_plan(args) -> dict:
    months = month_seq(args.end_year, args.end_month, args.months)
    apartments = min(args.apartments, len(OWNERS))
    accrual_rows = 0
    for pos, _period in enumerate(months):
        # в первом месяце последний счёт ещё не открыт (демонстрация opened_at)
        late = account_opens_late(apartments - 1, apartments, len(months)) and pos == 0
        accrual_rows += (apartments - (1 if late else 0)) * len(SERVICES)
    payments = 0
    if not args.no_payments:
        for idx in range(apartments):
            fraction = PAY_FRACTIONS[idx] if idx < len(PAY_FRACTIONS) else 0.0
            if fraction <= 0:
                continue
            # счёт, открытый со второго месяца, платит только со второго месяца
            months_active = len(months) - (1 if account_opens_late(idx, apartments, len(months)) else 0)
            payments += months_active
    expenses = 0 if args.no_payments else len(EXPENSES) * len(months)
    return {
        "months": months,
        "apartments": apartments,
        "owners": apartments,
        "services": len(SERVICES),
        "accrual_documents": len(months),
        "accrual_rows": accrual_rows,
        # показания: базовый замер + по одному на месяц
        "reading_documents": len(months) + 1,
        "readings": apartments * (len(months) + 1),
        "payments": payments,
        "expenses": expenses,
        "receipts": accrual_rows // len(SERVICES) if SERVICES else 0,
        "residents": apartments if args.residents else 0,
    }


def print_plan(plan: dict, args) -> None:
    print("=" * 70)
    print(" Демо-данные: план генерации")
    print("=" * 70)
    print(f" Целевая БД        : {masked_db_url()}")
    print(f" Период            : {month_label(*plan['months'][0])} … {month_label(*plan['months'][-1])}"
          f"  ({len(plan['months'])} мес.)")
    print(f" Собственники/кв./ЛС: {plan['owners']}")
    print(f" Видов услуг       : {plan['services']}")
    print(f" Документы начислений: {plan['accrual_documents']} (строк регистра: {plan['accrual_rows']})")
    print(f" Документы показаний: {plan['reading_documents']} (замеров: {plan['readings']})")
    print(f" Приход/Расход     : приходов {plan['payments']}, расходов {plan['expenses']}"
          + ("  (отключено)" if args.no_payments else ""))
    print(f" Квитанций         : {plan['receipts']}")
    if plan["residents"]:
        print(f" Пользователи ЛК   : {plan['residents']} (пароль «{RESIDENT_PASSWORD}»)")
    print("=" * 70)


# --- СПРАВОЧНИКИ (идемпотентно) --------------------------------------------

def ensure_reference(db, user_id: int | None) -> dict:
    """Гарантирует типы тарифов, услуги, кассу и статьи аналитики. Возвращает контекст."""
    tariff_types: dict[str, TariffType] = {}
    for name in ["По счетчику", "Фиксированный", "По площади", "На человека"]:
        tt = db.query(TariffType).filter(TariffType.name == name).first()
        if tt is None:
            tt = TariffType(name=name)
            db.add(tt)
            db.flush()
            print(f"   + тип тарифа: {name}")
        tariff_types[name] = tt

    services: dict[str, ServiceType] = {}
    for name, priority, type_name, unit, _price in SERVICES:
        svc = db.query(ServiceType).filter(ServiceType.services_type == name).first()
        if svc is None:
            svc = ServiceType(
                services_type=name,
                priority=priority,
                tariff_type_id=tariff_types[type_name].id,
                unit=unit,
            )
            db.add(svc)
            db.flush()
            print(f"   + вид услуги: {name} (приоритет {priority}, тип «{type_name}»)")
        services[name] = svc

    cash_point = db.query(CashPoint).order_by(CashPoint.id).first()
    if cash_point is None:
        cash_point = CashPoint(name="Касса")
        db.add(cash_point)
        db.flush()
        print("   + касса: Касса")

    articles: dict[str, AnalyticArticle] = {}
    article_specs = (
        [(INCOME_ARTICLE, AnalyticKind.income)]
        + [(name, AnalyticKind.expense) for name, _ in EXPENSES]
    )
    for name, kind in article_specs:
        art = db.query(AnalyticArticle).filter(
            AnalyticArticle.name == name, AnalyticArticle.kind == kind
        ).first()
        if art is None:
            art = AnalyticArticle(name=name, kind=kind, is_active=True)
            db.add(art)
            db.flush()
            print(f"   + статья аналитики: {name}")
        articles[name] = art

    return {
        "tariff_types": tariff_types,
        "services": services,
        "cash_point": cash_point,
        "articles": articles,
    }


def ensure_tariffs(db, ctx: dict, first_day: date) -> None:
    """Ставки услуг: у службы должна быть действующая (открытая) ставка нужного размера."""
    for name, _priority, _type_name, _unit, price in SERVICES:
        svc = ctx["services"][name]
        open_tariff = (
            db.query(Tariff)
            .filter(Tariff.services_type_id == svc.id, Tariff.valid_to.is_(None))
            .order_by(Tariff.valid_from.desc())
            .first()
        )
        if open_tariff is None:
            db.add(Tariff(
                services_type_id=svc.id,
                price=price,
                valid_from=first_day,
                status="active",
                comment="Ставка демо-данных",
            ))
            print(f"   + тариф: {name} = {price} ₸ (с {first_day:%d.%m.%Y})")
        else:
            if Decimal(str(open_tariff.price)) != price or open_tariff.status != "active":
                open_tariff.price = price
                open_tariff.status = "active"
                open_tariff.comment = "Ставка демо-данных"
                print(f"   ~ тариф обновлён: {name} = {price} ₸")
            else:
                print(f"   = тариф уже на месте: {name} = {price} ₸")
    db.flush()


# --- БИЗНЕС-ДАННЫЕ ---------------------------------------------------------

def create_owners(db, ctx: dict, plan: dict, rng: random.Random) -> list[dict]:
    """Собственники → квартиры → лицевые счёта → счётчики."""
    months = plan["months"]
    first_day = month_start(*months[0])
    second_day = month_start(*months[1]) if len(months) > 1 else first_day
    electricity = ctx["services"][METER_SERVICE]

    records: list[dict] = []
    for idx in range(plan["apartments"]):
        full_name, first_name, last_name, middle_name = OWNERS[idx]
        number = idx + 1

        owner = Counterparty(
            full_name=full_name,
            first_name=first_name,
            last_name=last_name,
            middle_name=middle_name,
            phone=phone_for(idx),
            is_active=True,
        )
        db.add(owner)
        db.flush()

        apartment = Apartment(
            owner_id=owner.id,
            apartment_number=number,
            address=apartment_address(number),
            square=Decimal(rng.choice([110, 120, 128, 135, 142, 150, 160])),
        )
        db.add(apartment)
        db.flush()

        # Последний счёт открыт со второго демо-месяца — демонстрирует учёт opened_at
        # (в первом месяце он не попадает в месячное начисление).
        opened_at = second_day if account_opens_late(idx, plan["apartments"], len(months)) else first_day

        account = Account(
            apartment_id=apartment.id,
            account_number=f"LS-{number:04d}",
            account_name=f"Лицевой счёт кв. {number}",
            is_active=True,
            opened_at=opened_at,
        )
        db.add(account)
        db.flush()

        meter = Meter(
            services_type_id=electricity.id,
            apartment_id=apartment.id,
            serial_number=f"M-{number:02d}-1",
            installed_at=first_day,
        )
        db.add(meter)
        db.flush()

        records.append({
            "index": idx,
            "number": number,
            "owner_id": owner.id,
            "apartment_id": apartment.id,
            "account_id": account.id,
            "meter_id": meter.id,
            "start_reading": Decimal(rng.randint(1000, 5000)),
        })
    print(f"   + собственников: {len(records)}, квартир/ЛС: {len(records)}, счётчиков: {len(records)}")
    return records


def create_readings(db, ctx: dict, plan: dict, records: list[dict],
                    rng: random.Random, user_id: int | None) -> list[dict]:
    """Показания: базовый замер до демо-периода + по одному на каждый месяц."""
    electricity = ctx["services"][METER_SERVICE]
    base_year, base_month = prev_month(*plan["months"][0])
    periods = [(base_year, base_month)] + list(plan["months"])

    values: dict[int, Decimal] = {rec["account_id"]: rec["start_reading"] for rec in records}
    rows_written = 0

    for pos, (year, month) in enumerate(periods):
        reading_date = month_start(year, month)
        document = MeterReadingDocument(
            title=build_meter_reading_document_title(reading_date, electricity.services_type),
            reading_date=reading_date,
            services_type_id=electricity.id,
        )
        audit_document_create(document, user_id, "демонстрационные данные")
        db.add(document)
        db.flush()

        for rec in records:
            if pos > 0:
                # потребление месяца (кВт·ч) — правдоподобный диапазон
                values[rec["account_id"]] += Decimal(rng.randint(150, 600))
            db.add(MeterReading(
                document_id=document.id,
                apartment_id=rec["apartment_id"],
                meter_id=rec["meter_id"],
                services_type_id=electricity.id,
                reading=values[rec["account_id"]],
                reading_date=reading_date,
            ))
            rows_written += 1
    db.flush()
    print(f"   + документов показаний: {len(periods)}, замеров: {rows_written}")
    return periods


def create_accruals(db, ctx: dict, plan: dict, records: list[dict],
                    user_id: int | None) -> dict:
    """Документы начислений (по одному на месяц) + строки accruals_register."""
    service_list = list(ctx["services"].values())
    pairs = {(rec["account_id"], svc.id) for rec in records for svc in service_list}

    accrued: dict[tuple[int, tuple[int, int]], Decimal] = {}
    documents = 0
    rows_total = 0

    for year, month in plan["months"]:
        period_end = month_end(year, month)
        document = AccrualDocument(
            accrual_date=period_end,
            title=default_accrual_document_title(period_end),
            doc_kind="monthly",
        )
        audit_document_create(document, user_id, "демонстрационные данные")
        db.add(document)
        db.flush()

        items = build_accrual_register_items(db, document, period_end, period_end, pairs)
        if not items:
            db.delete(document)
            db.flush()
            continue

        db.add_all(items)
        db.flush()
        documents += 1
        rows_total += len(items)
        for item in items:
            key = (item.account_id, (year, month))
            accrued[key] = accrued.get(key, Decimal("0")) + Decimal(str(item.amount))

    db.flush()
    print(f"   + документов начислений: {documents}, строк регистра: {rows_total}")
    return accrued


def create_cash(db, ctx: dict, plan: dict, records: list[dict],
                accrued: dict, user_id: int | None) -> tuple[int, int]:
    """Документы «Приход/Расход»: жительские оплаты + расходы кассы.

    Пишем через ORM, поэтому событие `transaction_after_insert` само наполнит
    `cash_register` (см. models.py). Распределение по долгам делает последующая
    пересборка `accounts_register`.
    """
    cash_point = ctx["cash_point"]
    income_article = ctx["articles"][INCOME_ARTICLE]
    payments = 0
    expenses = 0

    for year, month in plan["months"]:
        # --- оплаты жителей
        for rec in records:
            fraction = PAY_FRACTIONS[rec["index"]] if rec["index"] < len(PAY_FRACTIONS) else 0.0
            if fraction <= 0:
                continue
            charged = accrued.get((rec["account_id"], (year, month)))
            if not charged:
                continue
            amount = (charged * Decimal(str(fraction))).quantize(Decimal("0.01"))
            if amount <= 0:
                continue
            tx = Transaction(
                transaction_date=datetime(year, month, PAYMENT_DAY, 12, 0),
                account_id=rec["account_id"],
                cash_point_id=cash_point.id,
                article_id=income_article.id,
                contractor_id=rec["owner_id"],
                transaction_type=TransactionTypeEnum.in_cash,
                amount=amount,
                notes=f"Оплата за {month_label(year, month)}",
                created_by=user_id,
                change_description="демонстрационные данные",
            )
            db.add(tx)
            db.flush()
            set_transaction_title(db, tx)
            payments += 1

        # --- расходы кассы (без привязки к квартире)
        for article_name, amount in EXPENSES:
            tx = Transaction(
                transaction_date=datetime(year, month, EXPENSE_DAY, 12, 0),
                account_id=None,
                cash_point_id=cash_point.id,
                article_id=ctx["articles"][article_name].id,
                contractor_id=None,
                transaction_type=TransactionTypeEnum.out_cash,
                amount=amount,
                notes=f"{article_name} за {month_label(year, month)}",
                created_by=user_id,
                change_description="демонстрационные данные",
            )
            db.add(tx)
            db.flush()
            set_transaction_title(db, tx)
            expenses += 1

    db.flush()
    print(f"   + приходов (оплат жителей): {payments}, расходов кассы: {expenses}")
    return payments, expenses


def create_receipts(db, plan: dict, records: list[dict], user_id: int | None) -> int:
    """Квитанции по каждому счёту за каждый месяц с начислениями."""
    from routers.receipts import generate_receipt_document

    created = 0
    for year, month in plan["months"]:
        for rec in records:
            account = db.get(Account, rec["account_id"])
            exists = db.execute(text(
                "SELECT 1 FROM receipt_documents WHERE account_id = :a "
                "AND period_year = :y AND period_month = :m LIMIT 1"
            ), {"a": account.id, "y": year, "m": month}).first()
            if exists:
                continue
            receipt = generate_receipt_document(db, account, year, month, user_id=user_id)
            if receipt is not None:
                created += 1
    db.flush()
    print(f"   + квитанций: {created}")
    return created


def create_residents(db, records: list[dict]) -> int:
    """Демо-пользователи ЛК жителя (роль resident, привязка к счёту)."""
    created = 0
    for rec in records:
        username = f"demo{rec['number']:03d}"
        if db.query(User).filter(User.username == username).first():
            continue
        full_name = OWNERS[rec["index"]][0]
        db.add(User(
            username=username,
            password_hash=hash_password(RESIDENT_PASSWORD),
            full_name=full_name,
            role=UserRole.resident,
            account_id=rec["account_id"],
            is_active=True,
        ))
        created += 1
    db.flush()
    print(f"   + пользователей ЛК: {created} (логины demo001…demo{len(records):03d}, "
          f"пароль «{RESIDENT_PASSWORD}»)")
    return created


# --- ЗАЩИТА, ОЧИСТКА, КОНТРОЛЬ --------------------------------------------

def existing_business_rows(db) -> dict[str, int]:
    found: dict[str, int] = {}
    for table in BUSINESS_TABLES:
        count = db.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0
        if count:
            found[table] = int(count)
    return found


def wipe_business_data(db) -> None:
    print("   Удаляю бизнес-данные целевой БД (--wipe)…")
    for table in WIPE_ORDER:
        db.execute(text(f"DELETE FROM {table}"))
    # В БД у enum-полей (native_enum=False) хранятся ИМЕНА членов (resident, admin…),
    # а не .value (там русские подписи) — иначе фильтр не совпадёт ни с чем.
    db.execute(text("DELETE FROM users WHERE role = :r"), {"r": UserRole.resident.name})
    db.flush()


def pick_user_id(db) -> int | None:
    """Кто будет «автором» демо-документов (аудит): admin, иначе operator, иначе None."""
    for role in (UserRole.admin, UserRole.operator):
        row = db.execute(text(
            "SELECT id FROM users WHERE role = :r ORDER BY id LIMIT 1"
        ), {"r": role.name}).first()
        if row:
            return int(row[0])
    return None


def run_controls(db, records: list[dict]) -> bool:
    print("-" * 70)
    print(" Контроль после генерации")
    inconsistent = []
    for rec in records:
        result = check_register_integrity(db, rec["account_id"])
        if not result["consistent"]:
            inconsistent.append((rec, result))

    accruals_sum = db.execute(text("SELECT coalesce(sum(amount), 0) FROM accruals_register")).scalar()
    cash_income = db.execute(text("SELECT coalesce(sum(income), 0) FROM cash_register")).scalar()
    cash_expense = db.execute(text("SELECT coalesce(sum(expense), 0) FROM cash_register")).scalar()
    settled = db.execute(text("SELECT coalesce(sum(expense), 0) FROM accounts_register")).scalar()
    debt = db.execute(text(
        "SELECT coalesce(sum(income - expense), 0) FROM accounts_register"
    )).scalar()

    print(f"   л/с проверено           : {len(records)}")
    print(f"   из них согласованных    : {len(records) - len(inconsistent)}")
    print(f"   Σ начислений            : {accruals_sum:,.2f} ₸")
    print(f"   Σ приход кассы          : {cash_income:,.2f} ₸")
    print(f"   Σ расход кассы          : {cash_expense:,.2f} ₸")
    print(f"   Σ погашено долга (услуги): {settled:,.2f} ₸")
    print(f"   Долг по дому (сальдо)   : {debt:,.2f} ₸")
    for rec, result in inconsistent:
        print(f"   ! кв.{rec['number']}: расхождение {result}")
    if inconsistent:
        print("   ВНИМАНИЕ: целостность не сошлась — проверьте данные.")
        return False
    print("   Все лицевые счёта согласованы (check_register_integrity).")
    return True


# --- MAIN ------------------------------------------------------------------

def parse_args(argv: list[str]) -> argparse.Namespace:
    today = date.today()
    default_year, default_month = prev_month(today.year, today.month)
    parser = argparse.ArgumentParser(
        description="Генерация демонстрационных данных (документы + регистры).",
    )
    parser.add_argument("--apply", action="store_true", help="записать данные в БД (иначе dry-run)")
    parser.add_argument("--wipe", action="store_true", help="удалить бизнес-данные перед генерацией")
    parser.add_argument("--months", type=int, default=DEFAULT_MONTHS, help="сколько месяцев (по умолчанию 3)")
    parser.add_argument("--apartments", type=int, default=DEFAULT_APARTMENTS, help="сколько квартир/ЛС (по умолчанию 10)")
    parser.add_argument("--end", default=f"{default_year:04d}-{default_month:02d}",
                        help="последний демо-месяц в формате ГГГГ-ММ (по умолчанию — последний завершённый)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="зерно генератора (воспроизводимость)")
    parser.add_argument("--no-payments", action="store_true", help="не создавать «Приход/Расход»")
    parser.add_argument("--residents", action="store_true", help="создать демо-пользователей ЛК жителя")
    args = parser.parse_args(argv)

    if args.months < 1:
        parser.error("--months должен быть >= 1")
    if args.apartments < 1 or args.apartments > len(OWNERS):
        parser.error(f"--apartments должен быть от 1 до {len(OWNERS)} (столько заготовлено собственников)")
    if not re.fullmatch(r"\d{4}-\d{2}", args.end):
        parser.error("--end задаётся как ГГГГ-ММ")
    args.end_year, args.end_month = int(args.end[:4]), int(args.end[5:7])
    if not 1 <= args.end_month <= 12:
        parser.error("--end: месяц от 01 до 12")
    if (args.end_year, args.end_month) > (today.year, today.month):
        parser.error("--end не может быть в будущем")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    plan = build_plan(args)
    print_plan(plan, args)

    if not args.apply:
        print("\ndry-run: в БД ничего не записано. Для генерации добавьте --apply.")
        return 0

    db = SessionLocal()
    try:
        print(f"▶ Целевая БД: {masked_db_url()}")
        found = existing_business_rows(db)
        if found and not args.wipe:
            print("✖ В целевой БД уже есть бизнес-данные:")
            for table, count in sorted(found.items()):
                print(f"    {table}: {count}")
            print("  Демо-данные создаются только в ПУСТУЮ БД (чтобы не смешать с реальными).")
            print("  Если это заведомо демонстрационная БД — запустите с ключом --wipe.")
            return 2

        user_id = pick_user_id(db)
        print(f"▶ Пользователь для аудита: {user_id if user_id is not None else 'нет (поля останутся пустыми)'}")

        if args.wipe:
            wipe_business_data(db)

        rng = random.Random(args.seed)
        print("▶ Справочники (идемпотентно)")
        ctx = ensure_reference(db, user_id)
        ensure_tariffs(db, ctx, month_start(*plan["months"][0]))

        print("▶ Контрагенты, квартиры, лицевые счёта, счётчики")
        records = create_owners(db, ctx, plan, rng)

        print("▶ Показания")
        create_readings(db, ctx, plan, records, rng, user_id)

        print("▶ Начисления")
        accrued = create_accruals(db, ctx, plan, records, user_id)

        if not args.no_payments:
            print("▶ Приход/Расход (касса)")
            create_cash(db, ctx, plan, records, accrued, user_id)

        print("▶ Пересборка регистра взаиморасчётов (accounts_register)")
        rebuild_accounts_register(db, [rec["account_id"] for rec in records])

        print("▶ Квитанции")
        create_receipts(db, plan, records, user_id)

        if args.residents:
            print("▶ Пользователи ЛК жителя")
            create_residents(db, records)

        db.commit()

        ok = run_controls(db, records)
        print("-" * 70)
        print("✅ Демо-данные созданы." if ok else "⚠️  Демо-данные созданы, но контроль не сошёлся.")
        return 0 if ok else 3
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"✖ Ошибка: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
