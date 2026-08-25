# backend/app.py

import calendar
import enum
import json
import logging
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from database import engine, get_db
from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from models import (
    Account,
    AccountsRegister,
    AccrualsRegister,
    AccrualDocument,
    Apartment,
    CashPoint,
    Meter,
    MeterReading,
    MeterReadingDocument,
    Owner,
    ServiceType,
    Tariff,
    TariffType,
    Transaction,
    TransactionTypeEnum,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, asc, text

# Инициализация основного приложения
app = FastAPI(title="Townhouse ERP System")
logger = logging.getLogger(__name__)

# --- НАСТРОЙКА CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)

# --- НАСТРОЙКА API РОУТЕРА ---
api_router = APIRouter(prefix="/api")


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ СЕРИАЛИЗАЦИИ ---

def make_serializer(fields: list[str]):
    def serialize(item: Any) -> dict:
        result = {}
        for field in fields:
            val = getattr(item, field, None)
            if isinstance(val, (datetime, date)):
                result[field] = val.isoformat()
            elif isinstance(val, Decimal):
                result[field] = float(val)
            else:
                result[field] = val
        result["id"] = getattr(item, "id", None)
        return result
    return serialize


def apartment_serializer(item: Apartment) -> dict:
    owner = item.owner
    return {
        "id": item.id,
        "owner_id": item.owner_id,
        "apartment_number": item.apartment_number,
        "address": item.address,
        "square": float(item.square) if item.square is not None else 0.0,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "owner": {
            "id": owner.id,
            "full_name": owner.full_name,
            "phone": owner.phone,
        } if owner else None
    }


def account_serializer(item: Account) -> dict:
    apartment = item.apartment
    return {
        "id": item.id,
        "apartment_id": item.apartment_id,
        "account_number": item.account_number,
        "account_name": item.account_name,
        "is_active": item.is_active,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "apartment": {
            "id": apartment.id,
            "apartment_number": apartment.apartment_number,
            "address": apartment.address,
        } if apartment else None
    }


def cash_point_serializer(item: CashPoint) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "is_active": item.is_active,
    }


def transaction_serializer(item: Transaction) -> dict:
    account = item.account
    cash_point = item.cash_point

    result = {
        "id": item.id,
        "transaction_date": item.transaction_date.isoformat() if item.transaction_date else None,
        "account_id": item.account_id,
        "cash_point_id": item.cash_point_id,
        "transaction_type": item.transaction_type.value if hasattr(item.transaction_type, "value") else item.transaction_type,
        "amount": float(item.amount) if item.amount is not None else 0.0,
        "notes": item.notes,
    }

    if account and account.apartment:
        result["apartment_id"] = account.apartment.id
    else:
        result["apartment_id"] = None

    if account:
        result["account"] = {
            "id": account.id,
            "account_number": account.account_number,
            "account_name": account.account_name,
        }
        if account.apartment:
            result["apartment"] = {
                "id": account.apartment.id,
                "apartment_number": account.apartment.apartment_number,
                "address": account.apartment.address,
            }
            if account.apartment.owner:
                result["owner"] = {
                    "id": account.apartment.owner.id,
                    "full_name": account.apartment.owner.full_name,
                    "phone": account.apartment.owner.phone,
                }
            else:
                result["owner"] = None
        else:
            result["apartment"] = None
            result["owner"] = None
    else:
        result["account"] = None
        result["apartment"] = None
        result["owner"] = None

    if cash_point:
        result["cash_point"] = {
            "id": cash_point.id,
            "name": cash_point.name,
        }
    else:
        result["cash_point"] = None

    return result


def tariff_serializer(item: Tariff) -> dict:
    st = item.services_type
    tt = item.tariff_type
    return {
        "id": item.id,
        "services_type_id": item.services_type_id,
        "tariff_type_id": item.tariff_type_id,
        "price": float(item.price) if item.price is not None else 0.0,
        "valid_from": item.valid_from.isoformat() if item.valid_from else None,
        "unit": item.unit,
        "services_type": {"id": st.id, "services_type": st.services_type} if st else None,
        "tariff_type": {"id": tt.id, "name": tt.name} if tt else None,
    }


def meter_serializer(item: Meter) -> dict:
    apartment = item.apartment
    services_type = item.services_type
    return {
        "id": item.id,
        "services_type_id": item.services_type_id,
        "apartment_id": item.apartment_id,
        "serial_number": item.serial_number,
        "installed_at": item.installed_at.isoformat() if item.installed_at else None,
        "apartment": {
            "id": apartment.id,
            "apartment_number": apartment.apartment_number,
            "address": apartment.address,
        } if apartment else None,
        "services_type": {
            "id": services_type.id,
            "services_type": services_type.services_type,
        } if services_type else None,
    }


def meter_reading_document_serializer(item: MeterReadingDocument) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "reading_date": item.reading_date.isoformat() if item.reading_date else None,
        "services_type_id": item.services_type_id,
        "services_type": {
            "id": item.services_type.id,
            "services_type": item.services_type.services_type,
        } if item.services_type else None,
        "readings_count": len(item.readings) if item.readings else 0,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def meter_reading_serializer(item: MeterReading) -> dict:
    meter = item.meter
    services_type = item.services_type
    apartment = item.apartment or (meter.apartment if meter else None)
    document = item.document

    result = {
        "id": item.id,
        "document_id": item.document_id,
        "meter_id": item.meter_id,
        "services_type_id": item.services_type_id,
        "reading": float(item.reading) if item.reading is not None else 0.0,
        "reading_date": item.reading_date.isoformat() if item.reading_date else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }

    if apartment:
        result["apartment_id"] = apartment.id
    else:
        result["apartment_id"] = None

    if meter:
        result["meter"] = {
            "id": meter.id,
            "serial_number": meter.serial_number,
        }
    else:
        result["meter"] = None

    if services_type:
        result["services_type"] = {
            "id": services_type.id,
            "services_type": services_type.services_type,
        }
    else:
        result["services_type"] = None

    if apartment:
        result["apartment"] = {
            "id": apartment.id,
            "apartment_number": apartment.apartment_number,
            "address": apartment.address,
        }
    else:
        result["apartment"] = None

    if document:
        result["document"] = {
            "id": document.id,
            "title": document.title,
        }
    else:
        result["document"] = None

    return result


def accruals_register_serializer(item: AccrualsRegister) -> dict:
    result = {
        "id": item.id,
        "accrual_document_id": item.accrual_document_id,
        "accrual_date": item.accrual_date.isoformat() if item.accrual_date else None,
        "account_id": item.account_id,
        "tariff_id": item.tariff_id,
        "services_type_id": item.services_type_id,
        "current_reading_id": item.current_reading_id,
        "past_reading_value": float(item.past_reading_value) if item.past_reading_value is not None else None,
        "current_reading_value": float(item.current_reading_value) if item.current_reading_value is not None else None,
        "consumption": float(item.consumption) if item.consumption is not None else 0.0,
        "amount": float(item.amount) if item.amount is not None else 0.0,
    }

    if item.account:
        result["account"] = {
            "id": item.account.id,
            "account_number": item.account.account_number,
            "account_name": item.account.account_name,
        }
    else:
        result["account"] = None

    if item.services_type:
        result["services_type"] = {
            "id": item.services_type.id,
            "services_type": item.services_type.services_type,
        }
    else:
        result["services_type"] = None

    if item.tariff:
        result["tariff"] = {
            "id": item.tariff.id,
            "price": float(item.tariff.price) if item.tariff.price else 0,
            "unit": item.tariff.unit,
        }
    else:
        result["tariff"] = None

    return result


def accrual_document_serializer(item: AccrualDocument) -> dict:
    return {
        "id": item.id,
        "accrual_date": item.accrual_date.isoformat() if item.accrual_date else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "accruals_count": len(item.accruals) if item.accruals else 0,
        "total_amount": sum(float(a.amount) for a in item.accruals) if item.accruals else 0.0,
    }


def accounts_register_serializer(item: AccountsRegister) -> dict:
    result = {
        "id": item.id,
        "operation_date": item.operation_date.isoformat() if item.operation_date else None,
        "account_id": item.account_id,
        "transaction_id": item.transaction_id,
        "accrual_id": item.accrual_id,
        "income": float(item.income) if item.income is not None else 0.0,
        "expense": float(item.expense) if item.expense is not None else 0.0,
        "balance_after": float(item.balance_after) if item.balance_after is not None else 0.0,
    }

    if item.account:
        result["account"] = {
            "id": item.account.id,
            "account_number": item.account.account_number,
            "account_name": item.account.account_name,
        }
    else:
        result["account"] = None

    return result


SERIALIZERS = {
    Owner: make_serializer([
        "full_name", "first_name", "last_name", "middle_name",
        "phone", "email", "contact_info", "is_active"
    ]),
    Apartment: apartment_serializer,
    Account: account_serializer,
    CashPoint: cash_point_serializer,
    Transaction: transaction_serializer,
    ServiceType: make_serializer(["services_type"]),
    TariffType: make_serializer(["name"]),
    Tariff: tariff_serializer,
    Meter: meter_serializer,
    MeterReading: meter_reading_serializer,
    MeterReadingDocument: meter_reading_document_serializer,
    AccrualsRegister: accruals_register_serializer,
    AccountsRegister: accounts_register_serializer,
    AccrualDocument: accrual_document_serializer,
}

MODEL_MAP = {
    "owners": Owner,
    "apartments": Apartment,
    "accounts": Account,
    "cash_points": CashPoint,
    "transactions": Transaction,
    "payments": Transaction,
    "services_type": ServiceType,
    "tariff_types": TariffType,
    "tariffs": Tariff,
    "meters": Meter,
    "meter_readings": MeterReading,
    "meter_reading_documents": MeterReadingDocument,
    "accruals_register": AccrualsRegister,
    "accounts_register": AccountsRegister,
    "accrual_documents": AccrualDocument,
}


# --- МЕТАДАННЫЕ О ПОЛЯХ (для динамической формы на фронтенде) ---
FIELD_CONFIG: dict[str, list[dict[str, Any]]] = {
    "owners": [
        {"name": "full_name", "label": "ФИО (полное)", "type": "string", "required": True},
        {"name": "first_name", "label": "Имя", "type": "string", "required": True},
        {"name": "last_name", "label": "Фамилия", "type": "string"},
        {"name": "middle_name", "label": "Отчество", "type": "string"},
        {"name": "phone", "label": "Телефон", "type": "string"},
        {"name": "email", "label": "Email", "type": "string"},
        {"name": "contact_info", "label": "Доп. контакты", "type": "text"},
        {"name": "is_active", "label": "Активен", "type": "boolean"},
    ],
    "apartments": [
        {"name": "apartment_number", "label": "№ квартиры", "type": "integer", "required": True},
        {"name": "address", "label": "Адрес", "type": "string", "required": True},
        {"name": "square", "label": "Площадь, м²", "type": "decimal"},
        {
            "name": "owner_id",
            "label": "Собственник",
            "type": "reference",
            "reference": "owners",
            "required": True,
        },
    ],
    "accounts": [
        {"name": "account_number", "label": "№ счёта", "type": "string", "required": True},
        {"name": "account_name", "label": "Наименование", "type": "string", "required": True},
        {"name": "is_active", "label": "Активен", "type": "boolean"},
        {
            "name": "apartment_id",
            "label": "Квартира",
            "type": "reference",
            "reference": "apartments",
            "required": True,
        },
    ],
    "cash_points": [
        {"name": "name", "label": "Наименование", "type": "string", "required": True},
        {"name": "is_active", "label": "Активна", "type": "boolean"},
    ],
    "transactions": [
        {
            "name": "apartment_id",
            "label": "Квартира",
            "type": "reference",
            "reference": "apartments",
            "required": True,
        },
        {
            "name": "cash_point_id",
            "label": "Касса/Счёт",
            "type": "reference",
            "reference": "cash_points",
            "required": True,
        },
        {
            "name": "transaction_type",
            "label": "Тип операции",
            "type": "enum",
            "enum_class": TransactionTypeEnum,
            "required": True,
        },
        {"name": "amount", "label": "Сумма", "type": "decimal", "required": True},
        {"name": "notes", "label": "Примечание", "type": "string"},
    ],
    "payments": [
        {
            "name": "apartment_id",
            "label": "Квартира",
            "type": "reference",
            "reference": "apartments",
            "required": True,
        },
        {
            "name": "cash_point_id",
            "label": "Касса/Счёт",
            "type": "reference",
            "reference": "cash_points",
            "required": True,
        },
        {
            "name": "transaction_type",
            "label": "Тип операции",
            "type": "enum",
            "enum_class": TransactionTypeEnum,
            "required": True,
        },
        {"name": "amount", "label": "Сумма", "type": "decimal", "required": True},
        {"name": "notes", "label": "Примечание", "type": "string"},
    ],
    "service_types": [
        {"name": "services_type", "label": "Вид услуги", "type": "string", "required": True},
    ],
    "services_type": [
        {"name": "services_type", "label": "Вид услуги", "type": "string", "required": True},
    ],
    "tariff_types": [
        {"name": "name", "label": "Наименование", "type": "string", "required": True},
    ],
    "tariffs": [
        {
            "name": "services_type_id",
            "label": "Вид услуги",
            "type": "reference",
            "reference": "services_type",
            "required": True,
        },
        {
            "name": "tariff_type_id",
            "label": "Тип тарифа",
            "type": "reference",
            "reference": "tariff_types",
            "required": True,
        },
        {"name": "price", "label": "Цена", "type": "decimal", "required": True},
        {"name": "unit", "label": "Ед. изм.", "type": "string"},
        {"name": "valid_from", "label": "Действует с", "type": "date", "required": True},
    ],
    "meters": [
        {"name": "serial_number", "label": "Серийный номер", "type": "string", "required": True},
        {
            "name": "apartment_id",
            "label": "Квартира",
            "type": "reference",
            "reference": "apartments",
            "required": True,
        },
        {
            "name": "services_type_id",
            "label": "Вид услуги",
            "type": "reference",
            "reference": "services_type",
            "required": True,
        },
        {"name": "installed_at", "label": "Дата установки", "type": "date"},
    ],
    "meter_readings": [
        {
            "name": "apartment_id",
            "label": "Квартира",
            "type": "reference",
            "reference": "apartments",
            "required": True,
        },
        {
            "name": "services_type_id",
            "label": "Вид услуги",
            "type": "reference",
            "reference": "services_type",
            "required": True,
        },
        {"name": "reading", "label": "Показание", "type": "decimal", "required": True},
        {
            "name": "reading_date",
            "label": "Дата показания",
            "type": "date",
            "required": True,
            "default": "today",
        },
    ],
    "meter_reading_documents": [
        {"name": "id", "label": "ID документа", "type": "integer", "required": False},
        {"name": "title", "label": "Название", "type": "string", "required": True},
        {
            "name": "reading_date",
            "label": "Дата показаний",
            "type": "date",
            "required": True,
            "default": "today",
        },
        {
            "name": "services_type_id",
            "label": "Вид услуги",
            "type": "reference",
            "reference": "services_type",
            "required": True,
        },
        {"name": "readings_count", "label": "Количество записей", "type": "integer", "required": False},
        {"name": "created_at", "label": "Дата создания", "type": "datetime", "required": False},
    ],
    "accruals_register": [
        {"name": "accrual_date", "label": "Дата начисления", "type": "date", "required": True},
        {
            "name": "account_id",
            "label": "Лицевой счёт",
            "type": "reference",
            "reference": "accounts",
            "required": True,
        },
        {
            "name": "services_type_id",
            "label": "Вид услуги",
            "type": "reference",
            "reference": "services_type",
            "required": True,
        },
        {"name": "past_reading_value", "label": "Показание прошлое", "type": "decimal"},
        {"name": "current_reading_value", "label": "Показание текущее", "type": "decimal"},
        {"name": "consumption", "label": "Потребление", "type": "decimal", "required": True},
        {"name": "amount", "label": "Сумма", "type": "decimal", "required": True},
    ],
    "accounts_register": [
        {
            "name": "account_id",
            "label": "Лицевой счёт",
            "type": "reference",
            "reference": "accounts",
            "required": True,
        },
        {"name": "income", "label": "Приход", "type": "decimal"},
        {"name": "expense", "label": "Расход", "type": "decimal"},
        {"name": "balance_after", "label": "Баланс после", "type": "decimal"},
    ],
    "accrual_documents": [
        {"name": "id", "label": "ID документа", "type": "integer", "required": False},
        {"name": "accrual_date", "label": "Дата начисления", "type": "date", "required": True},
        {"name": "created_at", "label": "Дата создания", "type": "datetime", "required": False},
        {"name": "accruals_count", "label": "Количество записей", "type": "integer", "required": False},
        {"name": "total_amount", "label": "Общая сумма", "type": "decimal", "required": False},
    ],
}


# --- КАСТОМНЫЕ БИЛДЕРЫ ДЛЯ СОЗДАНИЯ/ОБНОВЛЕНИЯ ЗАПИСЕЙ ---

def coerce_field_value(raw_value: Any, field: dict[str, Any]) -> Any:
    if raw_value is None or raw_value == "":
        return None

    field_type = field["type"]

    try:
        if field_type in ("reference", "integer"):
            return int(raw_value)
        if field_type == "decimal":
            return Decimal(str(raw_value))
        if field_type == "boolean":
            return bool(raw_value)
        if field_type == "date":
            return (
                datetime.strptime(raw_value, "%Y-%m-%d").date()
                if isinstance(raw_value, str)
                else raw_value
            )
        if field_type == "datetime":
            return (
                datetime.fromisoformat(raw_value)
                if isinstance(raw_value, str)
                else raw_value
            )
    except (ValueError, InvalidOperation) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Некорректное значение поля '{field['label']}': {raw_value}",
        ) from exc

    if field_type == "enum":
        enum_cls = field["enum_class"]
        for member in enum_cls:
            if member.value == raw_value or member.name == raw_value:
                return member
        raise HTTPException(
            status_code=422,
            detail=f"Недопустимое значение поля '{field['label']}': {raw_value}",
        )

    return raw_value


def resolve_transaction_values(
    db: Session, payload: dict[str, Any], exclude_id: int | None = None
) -> dict[str, Any]:
    apartment_id = payload.get("apartment_id")
    cash_point_id = payload.get("cash_point_id")
    transaction_type = payload.get("transaction_type")
    amount = payload.get("amount")
    notes = payload.get("notes")

    if apartment_id in (None, ""):
        raise HTTPException(status_code=422, detail="Укажите квартиру")
    if cash_point_id in (None, ""):
        raise HTTPException(status_code=422, detail="Поле 'Касса/Счёт' обязательно")
    if transaction_type in (None, ""):
        raise HTTPException(status_code=422, detail="Поле 'Тип операции' обязательно")
    if amount in (None, ""):
        raise HTTPException(status_code=422, detail="Поле 'Сумма' обязательно")

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

    return {
        "account_id": account.id,
        "cash_point_id": int(cash_point_id),
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

    return {
        "apartment_id": int(apartment_id),
        "meter_id": meter.id,
        "services_type_id": int(services_type_id),
        "reading": coerced_reading,
        "reading_date": coerced_date,
    }


CUSTOM_VALUE_BUILDERS: dict[str, Any] = {
    "meter_readings": resolve_meter_reading_values,
    "transactions": resolve_transaction_values,
    "payments": resolve_transaction_values,
}


# --- ФУНКЦИЯ РАСЧЕТА НАЧИСЛЕНИЙ ---

def calculate_accruals_preview(db: Session, year: int, month: int) -> list[dict[str, Any]]:
    period_end = date(year, month, calendar.monthrange(year, month)[1])

    accounts = db.query(Account).filter(Account.is_active == True).all()
    service_types = db.query(ServiceType).all()

    rows = []
    row_number = 1

    for account in accounts:
        apartment = account.apartment
        if not apartment:
            continue

        for service_type in service_types:
            tariff = db.query(Tariff).filter(
                Tariff.services_type_id == service_type.id,
                Tariff.valid_from <= period_end
            ).order_by(Tariff.valid_from.desc()).first()

            if not tariff:
                continue

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

            tariff_type = db.query(TariffType).filter(TariffType.id == tariff.tariff_type_id).first()
            tariff_type_name = tariff_type.name if tariff_type else ""

            if tariff_type_name == "Постоянный":
                amount = float(tariff.price)
            else:
                amount = consumption * float(tariff.price)

            if consumption > 0 or tariff_type_name == "Постоянный":
                rows.append({
                    "row_number": row_number,
                    "account_id": account.id,
                    "account_id_label": f"№ {apartment.apartment_number} — {apartment.address}",
                    "services_type_id": service_type.id,
                    "services_type_id_label": service_type.services_type,
                    "tariff_id": tariff.id,
                    "tariff_id_label": f"{float(tariff.price)} ₸",
                    "past_reading_value": past_reading,
                    "current_reading_value": current_reading,
                    "consumption": consumption,
                    "amount": amount
                })
                row_number += 1

    return rows


# --- ЭНДПОИНТ МЕТАДАННЫХ РЕСУРСОВ ---
# ВАЖНО: должен быть ПЕРВЫМ среди универсальных эндпоинтов!
@api_router.get("/meta/{resource}")
def get_resource_meta(resource: str):
    if resource not in MODEL_MAP:
        raise HTTPException(status_code=404, detail="Resource not found")

    fields = FIELD_CONFIG.get(resource, [])
    result = []
    for field in fields:
        item = {
            "name": field["name"],
            "label": field["label"],
            "type": field["type"],
            "required": field.get("required", False),
        }
        if field.get("reference"):
            item["reference"] = field["reference"]
        if field.get("enum_class"):
            item["choices"] = [
                {"value": member.value, "label": member.value}
                for member in field["enum_class"]
            ]
        if "default" in field:
            item["default"] = field["default"]
        result.append(item)

    return {"fields": result}


# --- ЭНДПОИНТЫ ДЛЯ ДОКУМЕНТОВ НАЧИСЛЕНИЙ ---

@api_router.post("/accrual_documents", status_code=201)
def create_accrual_document(
    payload: dict[str, Any],
    db: Session = Depends(get_db)
):
    accrual_date = payload.get("accrual_date")
    if not accrual_date:
        raise HTTPException(status_code=422, detail="Укажите дату начисления")

    document = AccrualDocument(
        accrual_date=datetime.strptime(accrual_date, "%Y-%m-%d").date()
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    return accrual_document_serializer(document)


@api_router.get("/accrual_documents/{document_id}")
def get_accrual_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    document = db.query(AccrualDocument).filter(AccrualDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")
    return accrual_document_serializer(document)


@api_router.patch("/accrual_documents/{document_id}")
def update_accrual_document(
    document_id: int,
    payload: dict[str, Any],
    db: Session = Depends(get_db)
):
    document = db.query(AccrualDocument).filter(AccrualDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")

    if "accrual_date" in payload:
        document.accrual_date = datetime.strptime(payload["accrual_date"], "%Y-%m-%d").date()

    db.commit()
    db.refresh(document)
    return accrual_document_serializer(document)


@api_router.delete("/accrual_documents/{document_id}", status_code=204)
def delete_accrual_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    document = db.query(AccrualDocument).filter(AccrualDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")

    db.delete(document)
    db.commit()
    return Response(status_code=204)


# --- ЭНДПОИНТЫ ДЛЯ ДОКУМЕНТОВ ПОКАЗАНИЙ (массовый ввод) ---

@api_router.post("/meter_readings/bulk", status_code=201)
def bulk_create_readings(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """Массовое создание показаний с документом-шапкой"""
    title = payload.get("title")
    reading_date = payload.get("reading_date")
    services_type_id = payload.get("services_type_id")
    readings_data = payload.get("readings") or payload.get("entries") or []

    if not title or not reading_date or not services_type_id:
        raise HTTPException(status_code=422, detail="Заполните название, дату и вид услуги")
    if not readings_data:
        raise HTTPException(status_code=422, detail="Добавьте хотя бы одно показание")

    parsed_date = (
        datetime.strptime(reading_date, "%Y-%m-%d").date()
        if isinstance(reading_date, str)
        else reading_date
    )

    document = MeterReadingDocument(
        title=title,
        reading_date=parsed_date,
        services_type_id=int(services_type_id),
    )
    db.add(document)
    db.flush()

    created_readings = []
    row_errors = []
    for row in readings_data:
        apartment_id = row.get("apartment_id")
        reading_value = row.get("reading")
        meter_id = row.get("meter_id")

        if apartment_id in (None, "") or reading_value in (None, ""):
            continue

        apartment = db.query(Apartment).filter(Apartment.id == int(apartment_id)).first()
        if not apartment:
            row_errors.append({"apartment_id": apartment_id, "detail": "Квартира не найдена"})
            continue

        if not meter_id:
            meter = (
                db.query(Meter)
                .filter(
                    Meter.apartment_id == int(apartment_id),
                    Meter.services_type_id == int(services_type_id),
                )
                .order_by(Meter.installed_at.desc().nullslast(), Meter.id.desc())
                .first()
            )
            meter_id = meter.id if meter else None

        meter_reading = MeterReading(
            document_id=document.id,
            apartment_id=int(apartment_id),
            services_type_id=int(services_type_id),
            reading=Decimal(str(reading_value)),
            reading_date=parsed_date,
            meter_id=meter_id,
        )
        db.add(meter_reading)
        created_readings.append(meter_reading)

    if not created_readings:
        db.rollback()
        raise HTTPException(status_code=422, detail="Нет корректных строк для сохранения")

    db.commit()
    db.refresh(document)

    return {
        "document": meter_reading_document_serializer(document),
        "created": [{"id": r.id, "apartment_id": r.apartment_id} for r in created_readings],
        "errors": row_errors,
    }


@api_router.get("/meter_reading_documents/{document_id}/readings")
def get_document_readings(
    document_id: int,
    db: Session = Depends(get_db)
):
    document = db.query(MeterReadingDocument).filter(MeterReadingDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")

    readings = db.query(MeterReading).filter(MeterReading.document_id == document_id).all()

    return {
        "document": meter_reading_document_serializer(document),
        "readings": [meter_reading_serializer(r) for r in readings],
    }


# --- ЭНДПОИНТЫ ДЛЯ НАЧИСЛЕНИЙ ---

@api_router.get("/accruals_register/calculate")
async def calculate_accruals(
    year: int,
    month: int,
    db: Session = Depends(get_db),
):
    if month < 1 or month > 12:
        raise HTTPException(status_code=422, detail="Некорректный месяц")

    rows = calculate_accruals_preview(db, year, month)
    return {"rows": rows}


@api_router.post("/accruals_register/generate", status_code=201)
async def generate_accruals(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    year = payload.get("year")
    month = payload.get("month")
    document_id = payload.get("document_id")
    rows = payload.get("rows") or []

    if year in (None, "") or month in (None, ""):
        raise HTTPException(status_code=422, detail="Укажите месяц и год начисления")
    if not document_id:
        raise HTTPException(status_code=422, detail="Укажите ID документа начислений")
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=422, detail="Нет строк для начисления")

    year = int(year)
    month = int(month)
    if month < 1 or month > 12:
        raise HTTPException(status_code=422, detail="Некорректный месяц")

    accrual_date = date(year, month, calendar.monthrange(year, month)[1])

    document = db.query(AccrualDocument).filter(AccrualDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail=f"Документ начислений с ID {document_id} не найден")

    items = []
    for row in rows:
        account_id = row.get("account_id")
        services_type_id = row.get("services_type_id")
        tariff_id = row.get("tariff_id")
        amount = row.get("amount")
        consumption = row.get("consumption")

        if account_id in (None, "") or services_type_id in (None, "") or tariff_id in (None, ""):
            continue
        if amount in (None, ""):
            continue

        past_reading = row.get("past_reading_value")
        current_reading = row.get("current_reading_value")

        items.append(
            AccrualsRegister(
                accrual_document_id=int(document_id),
                accrual_date=accrual_date,
                account_id=int(account_id),
                services_type_id=int(services_type_id),
                tariff_id=int(tariff_id),
                past_reading_value=Decimal(str(past_reading)) if past_reading is not None else None,
                current_reading_value=Decimal(str(current_reading)) if current_reading is not None else None,
                consumption=Decimal(str(consumption)) if consumption is not None else Decimal("0"),
                amount=Decimal(str(amount)) if amount is not None else Decimal("0"),
            )
        )

    if not items:
        raise HTTPException(status_code=422, detail="Нет корректных строк для начисления")

    db.add_all(items)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Нарушение целостности данных при сохранении начислений: {str(exc)}",
        ) from exc

    try:
        for item in items:
            last_balance_result = db.execute(
                text("SELECT balance_after FROM accounts_register WHERE account_id = :account_id ORDER BY operation_date DESC, id DESC LIMIT 1"),
                {"account_id": item.account_id}
            ).scalar()

            previous_balance = last_balance_result if last_balance_result is not None else 0
            previous_balance = float(previous_balance)

            expense = float(item.amount)
            income = 0.0
            new_balance = previous_balance - expense

            db.execute(
                text("""
                    INSERT INTO accounts_register (
                        operation_date,
                        account_id,
                        accrual_id,
                        income,
                        expense,
                        balance_after
                    ) VALUES (
                        :operation_date,
                        :account_id,
                        :accrual_id,
                        :income,
                        :expense,
                        :balance_after
                    )
                """),
                {
                    "operation_date": datetime.now(),
                    "account_id": item.account_id,
                    "accrual_id": item.id,
                    "income": income,
                    "expense": expense,
                    "balance_after": new_balance
                }
            )

        db.commit()

    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Не удалось создать записи в регистре взаиморасчетов: {str(exc)}",
        ) from exc

    serializer = SERIALIZERS.get(AccrualsRegister)
    created_rows = [serializer(item) for item in items]

    return {"created": created_rows}


# --- УНИВЕРСАЛЬНЫЕ CRUD ЭНДПОИНТЫ ---
# ВАЖНО: должны быть ПОСЛЕ эндпоинтов /meta, /accrual_documents, /accruals_register, /meter_readings/bulk

@api_router.get("/{resource}")
def get_list(
    resource: str,
    _start: int = 0,
    _end: int = 10,
    _sort: str | None = None,
    _order: str | None = None,
    db: Session = Depends(get_db)
):
    if resource not in MODEL_MAP:
        raise HTTPException(status_code=404, detail="Resource not found")

    model = MODEL_MAP[resource]
    query = db.query(model)

    if resource == "accounts_register":
        query = query.options(
            joinedload(AccountsRegister.account)
        )
    elif resource == "accruals_register":
        query = query.options(
            joinedload(AccrualsRegister.account),
            joinedload(AccrualsRegister.services_type),
            joinedload(AccrualsRegister.tariff)
        )
    elif resource == "accrual_documents":
        query = query.options(
            joinedload(AccrualDocument.accruals)
        )
    elif resource in ["transactions", "payments"]:
        query = query.options(
            joinedload(Transaction.account)
            .joinedload(Account.apartment)
            .joinedload(Apartment.owner),
            joinedload(Transaction.cash_point)
        )
    elif resource == "meter_reading_documents":
        query = query.options(
            joinedload(MeterReadingDocument.services_type),
            joinedload(MeterReadingDocument.readings),
        )
    elif resource == "meter_readings":
        query = query.options(
            joinedload(MeterReading.meter),
            joinedload(MeterReading.apartment),
            joinedload(MeterReading.services_type),
            joinedload(MeterReading.document),
        )

    if _sort:
        order_func = desc if (_order or "").lower() == "desc" else asc
        if hasattr(model, _sort):
            query = query.order_by(order_func(getattr(model, _sort)))
        elif hasattr(model, "id"):
            query = query.order_by(order_func(model.id))

    total_count = query.count()
    items = query.offset(_start).limit(_end - _start).all()

    serializer = SERIALIZERS.get(model)
    if serializer:
        serialized_data = [serializer(item) for item in items]
    else:
        serialized_data = [{"id": getattr(i, "id", None)} for i in items]

    return Response(
        content=json.dumps(serialized_data, default=str, ensure_ascii=False),
        media_type="application/json",
        headers={"X-Total-Count": str(total_count)}
    )


@api_router.get("/{resource}/{item_id}")
async def get_resource_item(
    resource: str,
    item_id: int,
    db: Session = Depends(get_db)
):
    model = MODEL_MAP.get(resource)
    if not model:
        raise HTTPException(status_code=404, detail="Resource not found")

    if resource == "accounts_register":
        item = db.query(model).options(
            joinedload(AccountsRegister.account)
        ).filter(model.id == item_id).first()
    elif resource == "accruals_register":
        item = db.query(model).options(
            joinedload(AccrualsRegister.account),
            joinedload(AccrualsRegister.services_type),
            joinedload(AccrualsRegister.tariff)
        ).filter(model.id == item_id).first()
    elif resource == "accrual_documents":
        item = db.query(model).options(
            joinedload(AccrualDocument.accruals)
        ).filter(model.id == item_id).first()
    elif resource in ["transactions", "payments"]:
        item = db.query(model).options(
            joinedload(Transaction.account)
            .joinedload(Account.apartment)
            .joinedload(Apartment.owner),
            joinedload(Transaction.cash_point)
        ).filter(model.id == item_id).first()
    elif resource == "meter_reading_documents":
        item = db.query(model).options(
            joinedload(MeterReadingDocument.services_type),
            joinedload(MeterReadingDocument.readings),
        ).filter(model.id == item_id).first()
    elif resource == "meter_readings":
        item = db.query(model).options(
            joinedload(MeterReading.meter),
            joinedload(MeterReading.apartment),
            joinedload(MeterReading.services_type),
            joinedload(MeterReading.document),
        ).filter(model.id == item_id).first()
    else:
        item = db.get(model, item_id)

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    serializer = SERIALIZERS.get(model)
    if serializer:
        row = serializer(item)
    else:
        row = {"id": item.id}

    return row


@api_router.post("/{resource}", status_code=201)
async def create_resource_item(
    resource: str, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)
):
    if resource in ["accounts_register"]:
        raise HTTPException(
            status_code=403,
            detail=f"Создание записей в '{resource}' запрещено."
        )

    model = MODEL_MAP.get(resource)
    fields = FIELD_CONFIG.get(resource)
    if not model or fields is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    builder = CUSTOM_VALUE_BUILDERS.get(resource)
    if builder:
        values = builder(db, payload)
    else:
        values = {}
        for field in fields:
            name = field["name"]
            if name in payload:
                values[name] = coerce_field_value(payload[name], field)
            elif field.get("required"):
                raise HTTPException(
                    status_code=422, detail=f"Поле '{field['label']}' обязательно"
                )

    item = model(**values)
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Нарушение целостности данных (проверьте связанные записи)",
        ) from exc
    db.refresh(item)

    serializer = SERIALIZERS.get(model)
    row = serializer(item) if serializer else {"id": item.id}
    return row


@api_router.patch("/{resource}/{item_id}")
async def update_resource_item(
    resource: str,
    item_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    if resource in ["accounts_register"]:
        raise HTTPException(
            status_code=403,
            detail=f"Обновление записей в '{resource}' запрещено."
        )

    model = MODEL_MAP.get(resource)
    fields = FIELD_CONFIG.get(resource)
    if not model or fields is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    item = db.get(model, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    builder = CUSTOM_VALUE_BUILDERS.get(resource)
    if builder:
        values = builder(db, payload, item_id)
        for name, value in values.items():
            setattr(item, name, value)
    else:
        field_by_name = {field["name"]: field for field in fields}
        for name, raw_value in payload.items():
            field = field_by_name.get(name)
            if not field:
                continue
            setattr(item, name, coerce_field_value(raw_value, field))

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Нарушение целостности данных (проверьте связанные записи)",
        ) from exc
    db.refresh(item)

    serializer = SERIALIZERS.get(model)
    row = serializer(item) if serializer else {"id": item.id}
    return row


@api_router.delete("/{resource}/{item_id}", status_code=204)
async def delete_resource_item(
    resource: str, item_id: int, db: Session = Depends(get_db)
):
    if resource in ["accounts_register"]:
        raise HTTPException(
            status_code=403,
            detail=f"Удаление записей из '{resource}' запрещено."
        )

    model = MODEL_MAP.get(resource)
    if not model:
        raise HTTPException(status_code=404, detail="Resource not found")

    item = db.get(model, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    db.delete(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Не удалось удалить: запись используется в других таблицах",
        ) from exc

    return Response(status_code=204)


app.include_router(api_router)
