# backend/services.py
"""Чистые сервисные функции начислений и транзакций.

Вынесены из `app.py` (ЭТАП 2 роадмапа). Это НЕ роутеры — только бизнес-логика
(расчёт начислений, построение реестров, нормализация значений транзакций/показаний
счётчиков и авто-названий транзакций). `app.py` импортирует их обратно.
"""

import calendar
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from field_config import coerce_field_value
from models import (
    Account,
    AccrualsRegister,
    AccrualDocument,
    AnalyticArticle,
    AnalyticKind,
    Meter,
    MeterReading,
    ServiceType,
    Tariff,
    TariffType,
    Transaction,
    TransactionTypeEnum,
    recalculate_account_balance,
)


def audit_document_create(item: Any, user_id: int | None, description: str | None = None) -> None:
    """Проставляет метаданные автора при создании документа (п. 2.9).

    Работает только если у объекта есть соответствующие аудит-поля.
    """
    if hasattr(item, "created_by"):
        item.created_by = user_id
    if hasattr(item, "updated_by"):
        item.updated_by = user_id
    if hasattr(item, "change_description") and description:
        item.change_description = description


def audit_document_update(item: Any, user_id: int | None, description: str | None = None) -> None:
    """Обновляет метаданные автора при изменении документа (п. 2.9).
    `updated_at` обновляется на уровне СУБД (onupdate)."""
    if hasattr(item, "updated_by"):
        item.updated_by = user_id
    if hasattr(item, "change_description") and description:
        item.change_description = description


def resolve_transaction_values(
    db: Session, payload: dict[str, Any], exclude_id: int | None = None
) -> dict[str, Any]:
    apartment_id = payload.get("apartment_id")
    cash_point_id = payload.get("cash_point_id")
    transaction_type = payload.get("transaction_type")
    amount = payload.get("amount")
    notes = payload.get("notes")
    transaction_date = payload.get("transaction_date")
    article_id = payload.get("article_id")

    if cash_point_id in (None, ""):
        raise HTTPException(status_code=422, detail="Поле 'Касса/Счёт' обязательно")
    if transaction_type in (None, ""):
        raise HTTPException(status_code=422, detail="Поле 'Тип операции' обязательно")
    if amount in (None, ""):
        raise HTTPException(status_code=422, detail="Поле 'Сумма' обязательно")
    if article_id in (None, ""):
        raise HTTPException(status_code=422, detail="Поле 'Аналитика' обязательно")

    # Квартира/л/с НЕ обязательны: если не указаны — операция идёт в общий денежный
    # регистр без привязки к лицевому счёту (account_id = NULL), но с аналитикой.
    account_id = None
    if apartment_id not in (None, ""):
        account = (
            db.query(Account)
            .filter(Account.apartment_id == int(apartment_id))
            .order_by(Account.created_at.desc(), Account.id.desc())
            .first()
        )
        if not account:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Не найден лицевой счёт для указанной квартиры. "
                    "Сначала зарегистрируйте лицевой счёт в разделе «Лицевые счета»."
                ),
            )
        account_id = account.id

    values = {
        "account_id": account_id,
        "cash_point_id": int(cash_point_id),
        "article_id": int(article_id) if article_id not in (None, "") else None,
        "transaction_type": coerce_field_value(
            transaction_type,
            {
                "type": "enum",
                "label": "Тип операции",
                "enum_class": TransactionTypeEnum,
            },
        ),
        "amount": coerce_field_value(amount, {"type": "decimal", "label": "Сумма"}),
        "notes": notes,
    }

    # Аналитика: статья должна соответствовать типу операции (доход↔приход, расход↔расход).
    if values.get("article_id") is not None:
        article = db.get(AnalyticArticle, values["article_id"])
        if article is None:
            raise HTTPException(status_code=422, detail="Статья аналитики не найдена")
        tx_kind = values["transaction_type"]
        is_income = tx_kind in (TransactionTypeEnum.in_cash, TransactionTypeEnum.in_bank)
        expected = AnalyticKind.income if is_income else AnalyticKind.expense
        if article.kind != expected:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Статья аналитики «{article.name}» не соответствует типу операции "
                    f"(получен тип «{getattr(tx_kind, 'name', tx_kind)}»): "
                    "для прихода укажите статью «Доход», для расхода — «Расход»"
                ),
            )

    # Дата операции не может быть в будущем (1.10 роадмапа).
    if transaction_date not in (None, ""):
        coerced_dt = coerce_field_value(
            transaction_date, {"type": "datetime", "label": "Дата операции"}
        )
        validate_date_not_future(
            coerced_dt.date() if hasattr(coerced_dt, "date") else coerced_dt,
            "Дата операции",
        )
        values["transaction_date"] = coerced_dt

    return values


def build_transaction_title(transaction: Transaction) -> str:
    """
    Формирует название документа «Приход/Расход» по формуле:
    «Тип операции + №(ID) + дата операции», например «Приход в кассу №17 от 24.08.2026».
    """
    type_label = (
        transaction.transaction_type.value
        if hasattr(transaction.transaction_type, "value")
        else str(transaction.transaction_type)
    )
    date_label = ""
    if transaction.transaction_date:
        date_label = transaction.transaction_date.strftime("%d.%m.%Y")
    return f"{type_label} №{transaction.id} от {date_label}".strip()


def set_transaction_title(db: Session, transaction: Transaction) -> None:
    """Вычисляет и сохраняет название транзакции по формуле (обновляет строку)."""
    new_title = build_transaction_title(transaction)
    if transaction.title != new_title:
        transaction.title = new_title
        db.add(transaction)
        db.flush()


def validate_reading_not_decreased(
    db: Session,
    meter_id: int | None,
    reading,
    reading_date: date,
    exclude_id: int | None = None,
) -> None:
    """Проверяет, что показание счётчика не меньше предыдущего (счётчики нарастающие).

    Сравнивается с последним показанием того же счётчика с датой <= новой даты
    (при редактировании текущая запись исключается через exclude_id). При
    уменьшении бросает HTTPException(422) с понятным сообщением.
    """
    if meter_id in (None, ""):
        return
    query = db.query(MeterReading).filter(
        MeterReading.meter_id == int(meter_id),
        MeterReading.reading_date <= reading_date,
    )
    if exclude_id is not None:
        query = query.filter(MeterReading.id != int(exclude_id))
    prev = query.order_by(MeterReading.reading_date.desc(), MeterReading.id.desc()).first()
    if prev is None:
        return
    cur = Decimal(str(reading))
    prev_val = Decimal(str(prev.reading))
    if cur < prev_val:
        # Явно указываем квартиру, чтобы в массовом вводе было видно, по какой
        # строке ошибка (даже если фронтенд не подсветит её отдельно).
        apt_label = ""
        meter = db.get(Meter, int(meter_id))
        apt = meter.apartment if meter else None
        if apt is not None:
            apt_label = f"Квартира №{apt.apartment_number}: "
        raise HTTPException(
            status_code=422,
            detail=(
                f"{apt_label}текущее показание ({cur}) меньше предыдущего ({prev_val}) "
                f"от {prev.reading_date.strftime('%d.%m.%Y')}"
            ),
        )


# --- АВТО-НАЗВАНИЯ ДОКУМЕНТОВ И ПРОВЕРКИ ДАТ (роадмап 1.9 / 1.10) ---

MONTH_NAMES_RU = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]


def default_accrual_document_title(accrual_date: date) -> str:
    """Авто-название документа начислений: «Начисление за август 2026»."""
    return f"Начисление за {MONTH_NAMES_RU[accrual_date.month - 1]} {accrual_date.year}"


def build_meter_reading_document_title(reading_date: date, services_type_name: str | None) -> str:
    """Авто-название документа показаний: «Показания за август 2026 — Электричество»."""
    month_label = MONTH_NAMES_RU[reading_date.month - 1]
    suffix = f" — {services_type_name}" if services_type_name else ""
    return f"Показания за {month_label} {reading_date.year}{suffix}"


def build_writeoff_document_title(writeoff_id: int, writeoff_date: date | None = None) -> str:
    """Авто-название документа списания (роадмап 1.9): «Списание задолженностей №5 от 27.08.2026»."""
    date_label = writeoff_date.strftime("%d.%m.%Y") if writeoff_date else ""
    return f"Списание задолженностей №{writeoff_id}{(' от ' + date_label) if date_label else ''}".strip()


def validate_date_not_future(value: date, label: str) -> None:
    """Проверка «дата не в будущем» (1.10 роадмапа)."""
    if value > date.today():
        raise HTTPException(status_code=422, detail=f"{label} не может быть в будущем")


def resolve_meter_reading_document_values(
    db: Session, payload: dict[str, Any], exclude_id: int | None = None
) -> dict[str, Any]:
    """Создание документа показаний через generic API.

    Название генерируется автоматически (1.9 роадмапа) — введённое пользователем
    значение игнорируется; дата не может быть в будущем (1.10).
    """
    reading_date = payload.get("reading_date") or date.today().isoformat()
    services_type_id = payload.get("services_type_id")
    if services_type_id in (None, ""):
        raise HTTPException(status_code=422, detail="Укажите вид услуги")
    coerced_date = coerce_field_value(
        reading_date, {"type": "date", "label": "Дата показаний"}
    )
    validate_date_not_future(coerced_date, "Дата показаний")
    svc = db.get(ServiceType, int(services_type_id))
    title = build_meter_reading_document_title(
        coerced_date, svc.services_type if svc else None
    )
    return {
        "title": title,
        "reading_date": coerced_date,
        "services_type_id": int(services_type_id),
    }


def resolve_meter_reading_values(
    db: Session, payload: dict[str, Any], exclude_id: int | None = None
) -> dict[str, Any]:
    apartment_id = payload.get("apartment_id")
    services_type_id = payload.get("services_type_id")
    reading = payload.get("reading")
    reading_date = payload.get("reading_date")

    if apartment_id in (None, "") or services_type_id in (None, ""):
        raise HTTPException(
            status_code=422, detail="Укажите квартиру и вид услуги"
        )
    if reading in (None, ""):
        raise HTTPException(status_code=422, detail="Поле 'Показание' обязательно")

    meter = (
        db.query(Meter)
        .filter(
            Meter.apartment_id == int(apartment_id),
            Meter.services_type_id == int(services_type_id),
        )
        .order_by(Meter.installed_at.desc().nullslast(), Meter.id.desc())
        .first()
    )
    if not meter:
        raise HTTPException(
            status_code=422,
            detail=(
                "Не найден счётчик для указанной квартиры и вида услуги. "
                "Сначала зарегистрируйте счётчик в разделе «Счетчики»."
            ),
        )

    coerced_reading = coerce_field_value(
        reading, {"type": "decimal", "label": "Показание"}
    )
    coerced_date = coerce_field_value(
        reading_date or date.today().isoformat(),
        {"type": "date", "label": "Дата показания"},
    )

    # Дата показания не может быть в будущем (1.10 роадмапа).
    validate_date_not_future(coerced_date, "Дата показания")

    # Показания счётчиков нарастающие: текущее не может быть меньше предыдущего.
    validate_reading_not_decreased(db, meter.id, coerced_reading, coerced_date, exclude_id=exclude_id)

    return {
        "apartment_id": int(apartment_id),
        "meter_id": meter.id,
        "services_type_id": int(services_type_id),
        "reading": coerced_reading,
        "reading_date": coerced_date,
    }


# --- ФУНКЦИЯ РАСЧЕТА НАЧИСЛЕНИЙ ---

def calculate_accrual_for_account_service(
    db: Session, account: Account, service_type: ServiceType, period_end: date
) -> dict[str, Any] | None:
    """
    Рассчитывает начисление для одной пары (лицевой счёт, вид услуги) на конец периода.
    Возвращает None, если начислить нечего (нет тарифа или нулевое потребление для непостоянного тарифа).
    Эта функция — единственный источник истины для расчёта: используется и для превью,
    и при фактическом сохранении в регистр, чтобы клиент не мог подделать сумму/показания.
    """
    apartment = account.apartment
    if not apartment:
        return None

    tariff = db.query(Tariff).filter(
        Tariff.services_type_id == service_type.id,
        Tariff.valid_from <= period_end
    ).order_by(Tariff.valid_from.desc()).first()

    if not tariff:
        return None

    meter = db.query(Meter).filter(
        Meter.apartment_id == apartment.id,
        Meter.services_type_id == service_type.id
    ).first()

    past_reading = None
    current_reading = None
    consumption = 0

    if meter:
        current_reading_obj = db.query(MeterReading).filter(
            MeterReading.meter_id == meter.id,
            MeterReading.reading_date <= period_end
        ).order_by(MeterReading.reading_date.desc()).first()

        if current_reading_obj:
            current_reading = float(current_reading_obj.reading)

            past_reading_obj = db.query(MeterReading).filter(
                MeterReading.meter_id == meter.id,
                MeterReading.reading_date < current_reading_obj.reading_date,
                MeterReading.id != current_reading_obj.id
            ).order_by(MeterReading.reading_date.desc()).first()

            if past_reading_obj:
                past_reading = float(past_reading_obj.reading)
            else:
                past_reading = 0

            consumption = current_reading - past_reading

    # Определяем тип тарифа (служебный справочник — защищён от изменений):
    #  - «По счетчику»   : сумма = тариф × (текущее − предыдущее показание)
    #  - «Фиксированный» : сумма = тариф (не зависит от счётчика/площади)
    #  - «По площади»    : сумма = тариф × площадь квартиры
    tariff_type = db.query(TariffType).filter(TariffType.id == tariff.tariff_type_id).first()
    tariff_type_name = tariff_type.name if tariff_type else ""

    if tariff_type_name == "По площади":
        square = float(apartment.square or 0.0)
        amount = float(tariff.price) * square
        return {
            "account_id": account.id,
            "account_id_label": f"№ {apartment.apartment_number} — {apartment.address}",
            "services_type_id": service_type.id,
            "services_type_id_label": service_type.services_type,
            "tariff_id": tariff.id,
            "tariff_id_label": f"{float(tariff.price)} ₸ × {square} м²",
            "past_reading_value": past_reading,
            "current_reading_value": current_reading,
            "consumption": consumption,
            "amount": amount,
        }

    # «Фиксированный» — всегда начисляется, от показаний/площади не зависит.
    if tariff_type_name == "Фиксированный":
        amount = float(tariff.price)
        return {
            "account_id": account.id,
            "account_id_label": f"№ {apartment.apartment_number} — {apartment.address}",
            "services_type_id": service_type.id,
            "services_type_id_label": service_type.services_type,
            "tariff_id": tariff.id,
            "tariff_id_label": f"{float(tariff.price)} ₸",
            "past_reading_value": past_reading,
            "current_reading_value": current_reading,
            "consumption": consumption,
            "amount": amount,
        }

    # «По счетчику» (и любой иной тип по умолчанию) — по потреблению.
    if consumption <= 0:
        return None
    amount = float(tariff.price) * consumption
    return {
        "account_id": account.id,
        "account_id_label": f"№ {apartment.apartment_number} — {apartment.address}",
        "services_type_id": service_type.id,
        "services_type_id_label": service_type.services_type,
        "tariff_id": tariff.id,
        "tariff_id_label": f"{float(tariff.price)} ₸ × {consumption}",
        "past_reading_value": past_reading,
        "current_reading_value": current_reading,
        "consumption": consumption,
        "amount": amount,
    }


def build_accrual_register_items(
    db: Session,
    document: AccrualDocument,
    period_end: date,
    accrual_date: date,
    requested_pairs: set[tuple[int, int]],
) -> list[AccrualsRegister]:
    """
    Строит список строк AccrualsRegister для выбранных пар (account_id, services_type_id),
    пересчитывая каждую на сервере. Используется и при создании,
    и при редактировании документа начислений.
    """
    items = []
    for account_id, services_type_id in requested_pairs:
        account = db.query(Account).filter(Account.id == account_id, Account.is_active == True).first()
        service_type = db.query(ServiceType).filter(ServiceType.id == services_type_id).first()
        if not account or not service_type:
            continue

        calculated = calculate_accrual_for_account_service(db, account, service_type, period_end)
        if calculated is None:
            continue

        items.append(
            AccrualsRegister(
                accrual_document_id=document.id,
                accrual_date=accrual_date,
                account_id=calculated["account_id"],
                services_type_id=calculated["services_type_id"],
                tariff_id=calculated["tariff_id"],
                past_reading_value=Decimal(str(calculated["past_reading_value"])) if calculated["past_reading_value"] is not None else None,
                current_reading_value=Decimal(str(calculated["current_reading_value"])) if calculated["current_reading_value"] is not None else None,
                consumption=Decimal(str(calculated["consumption"])),
                amount=Decimal(str(calculated["amount"])),
            )
        )

    return items


def create_accounts_register_entries_for_accruals(db: Session, items: list[AccrualsRegister]) -> None:
    """
    Создаёт записи в регистре взаиморасчётов для каждой строки начисления,
    затем полностью пересчитывает балансы затронутых аккаунтов.

    Конвенция знаков: начисление записывается в income (долг жителя растёт),
    списание/оплата — в expense (долг падает). balance_after = SUM(income)-SUM(expense),
    положительный = долг, отрицательный = переплата (см. «КОНВЕНЦИЯ ЗНАКОВ» в models.py).
    """
    affected_accounts: set[int] = set()
    for item in items:
        db.execute(
            text("""
                INSERT INTO accounts_register (
                    operation_date,
                    account_id,
                    accrual_id,
                    services_type_id,
                    income,
                    expense,
                    balance_after
                ) VALUES (
                    :operation_date,
                    :account_id,
                    :accrual_id,
                    :services_type_id,
                    :income,
                    :expense,
                    :balance_after
                )
            """),
            {
                "operation_date": datetime.now(),
                "account_id": item.account_id,
                "accrual_id": item.id,
                "services_type_id": item.services_type_id,
                "income": float(item.amount),
                "expense": 0.0,
                "balance_after": 0.0,
            },
        )
        affected_accounts.add(item.account_id)

    for account_id in affected_accounts:
        recalculate_account_balance(db, account_id)


# --- ОБЩИЕ ХЕЛПЕРЫ (используются router-модулями квитанций и отчёта по счёту) ---

# Название услуги «фонд развития» — сюда «садится» общий долг/переплата счёта в квитанции.
FUND_SERVICE_FALLBACK = "Фонд развития"


def _service_name(db: Session, services_type_id) -> str:
    """Название вида услуги; для пустого/отсутствующего вида — «Фонд развития»."""
    if services_type_id is None:
        return FUND_SERVICE_FALLBACK
    st = db.get(ServiceType, services_type_id)
    return st.services_type if st else str(services_type_id)


def calculate_accruals_preview(db: Session, year: int, month: int) -> list[dict[str, Any]]:
    period_end = date(year, month, calendar.monthrange(year, month)[1])

    accounts = db.query(Account).filter(Account.is_active == True).all()
    service_types = db.query(ServiceType).all()

    rows = []
    row_number = 1

    for account in accounts:
        for service_type in service_types:
            row = calculate_accrual_for_account_service(db, account, service_type, period_end)
            if row is None:
                continue
            row["row_number"] = row_number
            rows.append(row)
            row_number += 1

    return rows
