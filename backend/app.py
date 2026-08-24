# --- app.py ---
import calendar
import enum
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
    Apartment,
    CashPoint,
    Meter,
    MeterReading,
    Owner,
    ServiceType,
    Tariff,
    TariffType,
    Transaction,
    TransactionTypeEnum,
)
from sqladmin import Admin, ModelView
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, asc

# Инициализация основного приложения
app = FastAPI(title="Townhouse ERP System")

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

# --- ЗАЩИЩЕННЫЕ РЕСУРСЫ (только для чтения) ---
PROTECTED_RESOURCES = ["accounts_register"]


@api_router.get("/")
def api_index():
    return {"status": "API is Online"}


MODEL_MAP = {
    "owners": Owner,
    "apartments": Apartment,
    "accounts": Account,
    "cash_points": CashPoint,
    "transactions": Transaction,
    "payments": Transaction,
    "accruals_register": AccrualsRegister,
    "accounts_register": AccountsRegister,
    "service_types": ServiceType,
    "tariff_types": TariffType,
    "tariffs": Tariff,
    "meters": Meter,
    "meter_readings": MeterReading,
}


def default_serializer(item) -> dict:
    name_val = (
        getattr(item, "full_name", None)
        or getattr(item, "number", None)
        or getattr(item, "name", None)
        or "—"
    )
    return {"id": item.id, "full_name": name_val, "phone": getattr(item, "phone", "—")}


def make_serializer(fields: list[str]):
    def serializer(item) -> dict:
        result: dict = {"id": item.id}
        for field in fields:
            value = getattr(item, field, None)
            if isinstance(value, Decimal):
                value = float(value)
            elif isinstance(value, (datetime, date)):
                value = value.isoformat()
            elif isinstance(value, enum.Enum):
                value = value.value
            result[field] = value
        return result
    return serializer


def apartment_serializer(item: Apartment) -> dict:
    result = {
        "id": item.id,
        "apartment_number": item.apartment_number,
        "address": item.address,
        "square": float(item.square) if item.square else None,
        "owner_id": item.owner_id,
    }
    if item.owner:
        result["owner"] = {
            "id": item.owner.id,
            "full_name": item.owner.full_name,
            "phone": item.owner.phone,
        }
    else:
        result["owner"] = None
    return result

def meter_serializer(item: Meter) -> dict:
    apartment = item.apartment
    services_type = item.services_type

    result = {
        "id": item.id,
        "serial_number": item.serial_number,
        "apartment_id": item.apartment_id,
        "services_type_id": item.services_type_id,
        "installed_at": item.installed_at.isoformat() if item.installed_at else None,
    }

    if apartment:
        result["apartment"] = {
            "id": apartment.id,
            "apartment_number": apartment.apartment_number,
            "address": apartment.address,
        }
    else:
        result["apartment"] = None

    if services_type:
        result["services_type"] = {
            "id": services_type.id,
            "services_type": services_type.services_type,
        }
    else:
        result["services_type"] = None

    return result


def account_serializer(item: Account) -> dict:
    result = {
        "id": item.id,
        "account_number": item.account_number,
        "account_name": item.account_name,
        "is_active": item.is_active,
        "apartment_id": item.apartment_id,
    }
    if item.apartment:
        result["apartment"] = {
            "id": item.apartment.id,
            "apartment_number": item.apartment.apartment_number,
            "address": item.apartment.address,
            "square": float(item.apartment.square) if item.apartment.square else None,
        }
    else:
        result["apartment"] = None
    return result


def meter_reading_serializer(item: MeterReading) -> dict:
    meter = item.meter
    services_type = item.services_type
    apartment = meter.apartment if meter else None

    result = {
        "id": item.id,
        "reading": float(item.reading) if item.reading is not None else None,
        "reading_date": item.reading_date.isoformat() if item.reading_date else None,
        "meter_id": item.meter_id,
    }

    if apartment:
        result["apartment"] = {
            "id": apartment.id,
            "apartment_number": apartment.apartment_number,
            "address": apartment.address,
        }
    else:
        result["apartment"] = None

    if services_type:
        result["services_type"] = {
            "id": services_type.id,
            "services_type": services_type.services_type,
        }
    else:
        result["services_type"] = None

    if meter:
        result["meter"] = {
            "id": meter.id,
            "serial_number": meter.serial_number,
        }
    else:
        result["meter"] = None

    result["meter_label"] = meter.serial_number if meter else None
    result["apartment_id"] = meter.apartment_id if meter else None
    result["services_type_id"] = item.services_type_id

    return result


def transaction_serializer(item: Transaction) -> dict:
    account = item.account
    result = {
        "id": item.id,
        "amount": float(item.amount) if item.amount is not None else None,
        "transaction_type": item.transaction_type.value if item.transaction_type else None,
        "transaction_date": item.transaction_date.isoformat() if item.transaction_date else None,
        "account_id": item.account_id,
        "cash_point_id": item.cash_point_id,
        "notes": item.notes,
    }

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
        else:
            result["apartment"] = None
    else:
        result["account"] = None
        result["apartment"] = None

    if item.cash_point:
        result["cash_point"] = {
            "id": item.cash_point.id,
            "name": item.cash_point.name,
        }
    else:
        result["cash_point"] = None

    result["account_label"] = account.account_number if account else None
    result["apartment_id"] = account.apartment_id if account else None

    return result


def accruals_register_serializer(item: AccrualsRegister) -> dict:
    account = item.account
    services_type = item.services_type

    result = {
        "id": item.id,
        "accrual_date": item.accrual_date.isoformat() if item.accrual_date else None,
        "account_id": item.account_id,
        "tariff_id": item.tariff_id,
        "services_type_id": item.services_type_id,
        "past_reading_value": float(item.past_reading_value) if item.past_reading_value is not None else None,
        "current_reading_value": float(item.current_reading_value) if item.current_reading_value is not None else None,
        "consumption": float(item.consumption) if item.consumption is not None else 0.0,
        "amount": float(item.amount) if item.amount is not None else 0.0,
    }

    if account:
        result["account"] = {
            "id": account.id,
            "account_number": account.account_number,
            "account_name": account.account_name,
        }
    else:
        result["account"] = None

    if services_type:
        result["services_type"] = {
            "id": services_type.id,
            "services_type": services_type.services_type,
        }
    else:
        result["services_type"] = None

    return result


def accounts_register_serializer(item: AccountsRegister) -> dict:
    account = item.account
    result = {
        "id": item.id,
        "operation_date": item.operation_date.isoformat() if item.operation_date else None,
        "account_id": item.account_id,
        "income": float(item.income) if item.income is not None else 0.0,
        "expense": float(item.expense) if item.expense is not None else 0.0,
        "balance_after": float(item.balance_after) if item.balance_after is not None else 0.0,
    }

    if account:
        result["account"] = {
            "id": account.id,
            "account_number": account.account_number,
            "account_name": account.account_name,
        }
        result["account_label"] = f"{account.account_number} ({account.account_name})"
    else:
        result["account"] = None
        result["account_label"] = None

    return result


def tariff_serializer(item: Tariff) -> dict:
    services_type = item.services_type
    tariff_type = item.tariff_type

    result = {
        "id": item.id,
        "services_type_id": item.services_type_id,
        "tariff_type_id": item.tariff_type_id,
        "price": float(item.price) if item.price is not None else 0.0,
        "unit": item.unit,
        "valid_from": item.valid_from.isoformat() if item.valid_from else None,
    }

    if services_type:
        result["services_type"] = {
            "id": services_type.id,
            "services_type": services_type.services_type,
        }
        result["services_type_id_label"] = services_type.services_type
    else:
        result["services_type"] = None
        result["services_type_id_label"] = None

    if tariff_type:
        result["tariff_type"] = {
            "id": tariff_type.id,
            "name": tariff_type.name,
        }
        result["tariff_type_id_label"] = tariff_type.name
    else:
        result["tariff_type"] = None
        result["tariff_type_id_label"] = None

    return result


SERIALIZERS = {
    Owner: make_serializer(
        [
            "full_name",
            "first_name",
            "last_name",
            "middle_name",
            "phone",
            "email",
            "contact_info",
            "is_active",
        ]
    ),
    Apartment: apartment_serializer,
    Account: account_serializer,
    CashPoint: make_serializer(["name", "is_active"]),
    Transaction: transaction_serializer,
    ServiceType: make_serializer(["services_type"]),
    TariffType: make_serializer(["name"]),
    Tariff: tariff_serializer,
    Meter: meter_serializer,
    MeterReading: meter_reading_serializer,
    AccrualsRegister: accruals_register_serializer,
    AccountsRegister: accounts_register_serializer,
}


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
    "service_types": [
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
            "reference": "service_types",
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
            "reference": "service_types",
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
            "reference": "service_types",
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
            "name": "tariff_id",
            "label": "Тариф",
            "type": "reference",
            "reference": "tariffs",
            "required": True,
        },
        {
            "name": "services_type_id",
            "label": "Вид услуги",
            "type": "reference",
            "reference": "service_types",
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
}
FIELD_CONFIG["payments"] = FIELD_CONFIG["transactions"]


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


REFERENCE_LABEL_BUILDERS: dict[str, Any] = {
    "owners": lambda row: row.get("full_name") or f"#{row['id']}",
    "apartments": lambda row: f"№ {row.get('apartment_number')} — {row.get('owner', {}).get('full_name') or 'Без собственника'}",
    "accounts": lambda row: f"{row.get('account_number')} ({row.get('account_name')})",
    "cash_points": lambda row: row.get("name") or f"#{row['id']}",
    "service_types": lambda row: row.get("services_type") or f"#{row['id']}",
    "tariff_types": lambda row: row.get("name") or f"#{row['id']}",
    "tariffs": lambda row: f"{row.get('price')} ₸" + (f" / {row['unit']}" if row.get("unit") else ""),
    "meters": lambda row: row.get("serial_number") or f"#{row['id']}",
}


def enrich_with_reference_labels(
    db: Session, resource: str, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not rows:
        return rows

    reference_fields = [
        field for field in FIELD_CONFIG.get(resource, []) if field["type"] == "reference"
    ]
    if not reference_fields:
        return rows

    for field in reference_fields:
        field_name = field["name"]
        target_resource = field["reference"]
        target_model = MODEL_MAP.get(target_resource)
        if not target_model:
            continue

        ids = {row.get(field_name) for row in rows if row.get(field_name) is not None}
        if not ids:
            continue

        target_serializer = SERIALIZERS.get(target_model, default_serializer)
        target_items = db.query(target_model).filter(target_model.id.in_(ids)).all()
        label_builder = REFERENCE_LABEL_BUILDERS.get(
            target_resource,
            lambda row: row.get("full_name") or row.get("name") or f"#{row['id']}",
        )
        labels_by_id = {
            item.id: label_builder(target_serializer(item)) for item in target_items
        }

        label_key = f"{field_name}_label"
        for row in rows:
            fk_value = row.get(field_name)
            row[label_key] = labels_by_id.get(fk_value) if fk_value is not None else None

    return rows


def get_previous_reading(
    db: Session,
    meter_id: int,
    reading_date_value: date,
    exclude_id: int | None = None,
) -> MeterReading | None:
    query = db.query(MeterReading).filter(
        MeterReading.meter_id == meter_id,
        MeterReading.reading_date <= reading_date_value,
    )
    if exclude_id is not None:
        query = query.filter(MeterReading.id != exclude_id)
    return query.order_by(
        MeterReading.reading_date.desc(), MeterReading.id.desc()
    ).first()


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

    previous = get_previous_reading(db, meter.id, coerced_date, exclude_id)
    if previous is not None and coerced_reading < previous.reading:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Показание ({coerced_reading}) меньше предыдущего "
                f"({previous.reading} от {previous.reading_date.strftime('%d.%m.%Y')}). "
                "Проверьте введённое значение."
            ),
        )

    return {
        "meter_id": meter.id,
        "services_type_id": int(services_type_id),
        "reading": coerced_reading,
        "reading_date": coerced_date,
    }


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


CUSTOM_VALUE_BUILDERS: dict[str, Any] = {
    "meter_readings": resolve_meter_reading_values,
    "transactions": resolve_transaction_values,
    "payments": resolve_transaction_values,
}


CONSTANT_TARIFF_TYPE_NAME = "Постоянный"
VARIABLE_TARIFF_TYPE_NAME = "Переменный"


def quantize_amount(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_accruals_preview(db: Session, period_year: int, period_month: int) -> list[dict[str, Any]]:
    period_end = date(period_year, period_month, calendar.monthrange(period_year, period_month)[1])

    service_types = db.query(ServiceType).order_by(ServiceType.id).all()
    accounts = (
        db.query(Account)
        .filter(Account.is_active.is_(True))
        .order_by(Account.id)
        .all()
    )

    rows: list[dict[str, Any]] = []
    row_number = 1

    for service_type in service_types:
        tariff = (
            db.query(Tariff)
            .filter(
                Tariff.services_type_id == service_type.id,
                Tariff.valid_from <= period_end,
            )
            .order_by(Tariff.valid_from.desc(), Tariff.id.desc())
            .first()
        )
        if not tariff:
            continue

        tariff_type = db.get(TariffType, tariff.tariff_type_id)
        tariff_type_name = tariff_type.name if tariff_type else ""

        for account in accounts:
            if not account.apartment_id:
                continue

            meter = (
                db.query(Meter)
                .filter(
                    Meter.apartment_id == account.apartment_id,
                    Meter.services_type_id == service_type.id,
                )
                .order_by(Meter.installed_at.desc().nullslast(), Meter.id.desc())
                .first()
            )

            past_value: Decimal | None = None
            current_value: Decimal | None = None
            consumption = Decimal("0")

            if meter:
                current_reading = (
                    db.query(MeterReading)
                    .filter(
                        MeterReading.meter_id == meter.id,
                        MeterReading.reading_date <= period_end,
                    )
                    .order_by(MeterReading.reading_date.desc(), MeterReading.id.desc())
                    .first()
                )
                if current_reading:
                    current_value = current_reading.reading
                    past_reading = (
                        db.query(MeterReading)
                        .filter(
                            MeterReading.meter_id == meter.id,
                            MeterReading.reading_date <= current_reading.reading_date,
                            MeterReading.id != current_reading.id,
                        )
                        .order_by(MeterReading.reading_date.desc(), MeterReading.id.desc())
                        .first()
                    )
                    if past_reading:
                        past_value = past_reading.reading
                    else:
                        past_value = Decimal("0")
                    consumption = current_value - past_value

            if tariff_type_name == CONSTANT_TARIFF_TYPE_NAME:
                amount = tariff.price
            elif tariff_type_name == VARIABLE_TARIFF_TYPE_NAME:
                if current_value is None:
                    continue
                amount = consumption * tariff.price
            else:
                continue

            apartment = account.apartment
            apartment_label = (
                f"№ {apartment.apartment_number} ({account.account_number})"
                if apartment
                else account.account_number
            )

            rows.append(
                {
                    "row_number": row_number,
                    "account_id": account.id,
                    "account_id_label": apartment_label,
                    "services_type_id": service_type.id,
                    "services_type_id_label": service_type.services_type,
                    "tariff_id": tariff.id,
                    "tariff_id_label": f"{tariff.price} ₸" + (f" / {tariff.unit}" if tariff.unit else ""),
                    "past_reading_value": float(past_value) if past_value is not None else None,
                    "current_reading_value": float(current_value) if current_value is not None else None,
                    "consumption": float(consumption),
                    "amount": float(quantize_amount(amount)),
                }
            )
            row_number += 1

    return rows


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
    payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)
):
    year = payload.get("year")
    month = payload.get("month")
    rows = payload.get("rows") or []

    if year in (None, "") or month in (None, ""):
        raise HTTPException(status_code=422, detail="Укажите месяц и год начисления")
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=422, detail="Нет строк для начисления")

    year = int(year)
    month = int(month)
    if month < 1 or month > 12:
        raise HTTPException(status_code=422, detail="Некорректный месяц")

    accrual_date = date(year, month, calendar.monthrange(year, month)[1])

    accrual_items = []
    register_items = []

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

        coerced_amount = coerce_field_value(amount, {"type": "decimal", "label": "Сумма"})
        if not coerced_amount or coerced_amount <= 0:
            continue

        acc_id = int(account_id)

        # 1. Создаем запись начисления
        accrual_item = AccrualsRegister(
            accrual_date=accrual_date,
            account_id=acc_id,
            services_type_id=int(services_type_id),
            tariff_id=int(tariff_id),
            past_reading_value=coerce_field_value(
                row.get("past_reading_value"), {"type": "decimal", "label": "Показание прошлое"}
            ),
            current_reading_value=coerce_field_value(
                row.get("current_reading_value"), {"type": "decimal", "label": "Показание текущее"}
            ),
            consumption=coerce_field_value(
                consumption, {"type": "decimal", "label": "Потребление"}
            ) or Decimal("0"),
            amount=coerced_amount,
        )
        accrual_items.append(accrual_item)

        # 2. Получаем последний баланс лицевого счета из регистра взаиморасчетов
        last_reg = (
            db.query(AccountsRegister)
            .filter(AccountsRegister.account_id == acc_id)
            .order_by(AccountsRegister.operation_date.desc(), AccountsRegister.id.desc())
            .first()
        )
        current_balance = last_reg.balance_after if last_reg and last_reg.balance_after is not None else Decimal("0.00")

        # Начисление увеличивает долг абонента (уменьшает баланс лицевого счета)
        new_balance = current_balance - coerced_amount

        # 3. Создаем запись во взаиморасчетах (AccountsRegister)
        register_item = AccountsRegister(
            operation_date=accrual_date,
            account_id=acc_id,
            income=Decimal("0.00"),
            expense=coerced_amount,
            balance_after=new_balance,
        )
        register_items.append(register_item)

    if not accrual_items:
        raise HTTPException(status_code=422, detail="Нет корректных строк для начисления")

    db.add_all(accrual_items)
    db.add_all(register_items)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Нарушение целостности данных при сохранении начислений и взаиморасчетов",
        ) from exc

    serializer = SERIALIZERS.get(AccrualsRegister, default_serializer)
    created_rows = [serializer(item) for item in accrual_items]
    created_rows = enrich_with_reference_labels(db, "accruals_register", created_rows)

    return {"created": created_rows}


@api_router.get("/meta/{resource}")
async def get_resource_meta(resource: str):
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


@api_router.get("/{resource}")
async def get_resource(
    resource: str,
    response: Response,
    _start: int | None = None,
    _end: int | None = None,
    _sort: str | None = None,
    _order: str | None = None,
    db: Session = Depends(get_db),
):
    model = MODEL_MAP.get(resource)
    if not model:
        raise HTTPException(status_code=404, detail="Resource not found")

    query = db.query(model)

    # Подгружаем связанные данные для конкретных ресурсов
    if resource == "apartments":
        query = query.options(joinedload(Apartment.owner))
    elif resource == "accounts":
        query = query.options(joinedload(Account.apartment))
    elif resource in ["transactions", "payments"]:
        query = query.options(
            joinedload(Transaction.account).joinedload(Account.apartment),
            joinedload(Transaction.cash_point)
        )
    elif resource == "meters":
        query = query.options(joinedload(Meter.apartment), joinedload(Meter.services_type))
    elif resource == "meter_readings":
        query = query.options(
            joinedload(MeterReading.meter).joinedload(Meter.apartment),
            joinedload(MeterReading.services_type)
        )
    elif resource == "tariffs":
        query = query.options(joinedload(Tariff.services_type), joinedload(Tariff.tariff_type))
    elif resource == "accruals_register":
        query = query.options(
            joinedload(AccrualsRegister.account),
            joinedload(AccrualsRegister.services_type)
        )
    elif resource == "accounts_register":
        query = query.options(joinedload(AccountsRegister.account))

    total = query.count()

    # --- РАСШИРЕННАЯ СЕРВЕРНАЯ СОРТИРОВКА (включая вложенные поля и _label) ---
    if _sort:
        order_func = desc if (_order or "").lower() == "desc" else asc

        sorted_applied = False

        if resource == "apartments":
            if _sort in ["owner.full_name", "owner_id_label"]:
                query = query.join(Owner, isouter=True).order_by(order_func(Owner.full_name))
                sorted_applied = True

        elif resource == "accounts":
            if _sort in ["apartment.apartment_number", "apartment_id_label"]:
                query = query.join(Apartment, isouter=True).order_by(order_func(Apartment.apartment_number))
                sorted_applied = True

        elif resource == "meters":
            if _sort in ["apartment.apartment_number", "apartment_id_label"]:
                query = query.join(Apartment, isouter=True).order_by(order_func(Apartment.apartment_number))
                sorted_applied = True
            elif _sort in ["services_type.services_type", "services_type_id_label"]:
                query = query.join(ServiceType, isouter=True).order_by(order_func(ServiceType.services_type))
                sorted_applied = True

        elif resource == "meter_readings":
            if _sort in ["apartment.apartment_number", "apartment_id_label"]:
                query = query.join(Meter, isouter=True).join(Apartment, isouter=True).order_by(order_func(Apartment.apartment_number))
                sorted_applied = True
            elif _sort in ["services_type.services_type", "services_type_id_label"]:
                query = query.join(ServiceType, isouter=True).order_by(order_func(ServiceType.services_type))
                sorted_applied = True
            elif _sort in ["meter.serial_number", "meter_label"]:
                query = query.join(Meter, isouter=True).order_by(order_func(Meter.serial_number))
                sorted_applied = True

        elif resource in ["transactions", "payments"]:
            if _sort in ["apartment.apartment_number", "apartment_id_label"]:
                query = query.join(Account, isouter=True).join(Apartment, isouter=True).order_by(order_func(Apartment.apartment_number))
                sorted_applied = True
            elif _sort in ["account.account_number", "account_label"]:
                query = query.join(Account, isouter=True).order_by(order_func(Account.account_number))
                sorted_applied = True
            elif _sort in ["cash_point.name", "cash_point_id_label"]:
                query = query.join(CashPoint, isouter=True).order_by(order_func(CashPoint.name))
                sorted_applied = True

        elif resource == "tariffs":
            if _sort in ["services_type.services_type", "services_type_id_label"]:
                query = query.join(ServiceType, isouter=True).order_by(order_func(ServiceType.services_type))
                sorted_applied = True
            elif _sort in ["tariff_type.name", "tariff_type_id_label"]:
                query = query.join(TariffType, isouter=True).order_by(order_func(TariffType.name))
                sorted_applied = True

        elif resource == "accruals_register":
            if _sort in ["account.account_number", "account_id_label"]:
                query = query.join(Account, isouter=True).order_by(order_func(Account.account_number))
                sorted_applied = True
            elif _sort in ["services_type.services_type", "services_type_id_label"]:
                query = query.join(ServiceType, isouter=True).order_by(order_func(ServiceType.services_type))
                sorted_applied = True

        elif resource == "accounts_register":
            if _sort in ["account.account_number", "account_id_label"]:
                query = query.join(Account, isouter=True).order_by(order_func(Account.account_number))
                sorted_applied = True

        if not sorted_applied and hasattr(model, _sort):
            column = getattr(model, _sort)
            query = query.order_by(order_func(column))

    if _start is not None and _end is not None:
        query = query.offset(_start).limit(max(_end - _start, 0))

    items = query.all()
    serializer = SERIALIZERS.get(model, default_serializer)
    rows = [serializer(item) for item in items]
    rows = enrich_with_reference_labels(db, resource, rows)

    response.headers["X-Total-Count"] = str(total)
    return rows


@api_router.get("/{resource}/{item_id}")
async def get_resource_item(resource: str, item_id: int, db: Session = Depends(get_db)):
    model = MODEL_MAP.get(resource)
    if not model:
        raise HTTPException(status_code=404, detail="Resource not found")

    item = db.get(model, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    serializer = SERIALIZERS.get(model, default_serializer)
    row = serializer(item)
    return enrich_with_reference_labels(db, resource, [row])[0]


@api_router.post("/meter_readings/bulk", status_code=201)
async def bulk_create_meter_readings(
    payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)
):
    services_type_id = payload.get("services_type_id")
    reading_date = payload.get("reading_date") or date.today().isoformat()
    entries = payload.get("entries") or []

    if services_type_id in (None, ""):
        raise HTTPException(status_code=422, detail="Укажите вид услуги")
    if not isinstance(entries, list) or not entries:
        raise HTTPException(
            status_code=422, detail="Нет ни одной заполненной строки с показаниями"
        )

    to_create: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for entry in entries:
        apartment_id = entry.get("apartment_id")
        reading = entry.get("reading")
        if reading in (None, ""):
            continue

        row_payload = {
            "apartment_id": apartment_id,
            "services_type_id": services_type_id,
            "reading": reading,
            "reading_date": reading_date,
        }
        try:
            values = resolve_meter_reading_values(db, row_payload)
            to_create.append(values)
        except HTTPException as exc:
            errors.append({"apartment_id": apartment_id, "detail": exc.detail})

    created_rows: list[dict[str, Any]] = []
    if to_create:
        items = [MeterReading(**values) for values in to_create]
        db.add_all(items)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="Нарушение целостности данных при сохранении показаний",
            ) from exc

        serializer = SERIALIZERS.get(MeterReading, default_serializer)
        created_rows = [serializer(item) for item in items]
        created_rows = enrich_with_reference_labels(db, "meter_readings", created_rows)

    return {"created": created_rows, "errors": errors}


@api_router.post("/{resource}", status_code=201)
async def create_resource_item(
    resource: str, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)
):
    if resource in PROTECTED_RESOURCES:
        raise HTTPException(
            status_code=403,
            detail=f"Создание записей в '{resource}' запрещено. Записи создаются автоматически."
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

    serializer = SERIALIZERS.get(model, default_serializer)
    row = serializer(item)
    return enrich_with_reference_labels(db, resource, [row])[0]


@api_router.patch("/{resource}/{item_id}")
async def update_resource_item(
    resource: str,
    item_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    if resource in PROTECTED_RESOURCES:
        raise HTTPException(
            status_code=403,
            detail=f"Обновление записей в '{resource}' запрещено. Записи обновляются автоматически."
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

    serializer = SERIALIZERS.get(model, default_serializer)
    row = serializer(item)
    return enrich_with_reference_labels(db, resource, [row])[0]


@api_router.delete("/{resource}/{item_id}", status_code=204)
async def delete_resource_item(
    resource: str, item_id: int, db: Session = Depends(get_db)
):
    if resource in PROTECTED_RESOURCES:
        raise HTTPException(
            status_code=403,
            detail=f"Удаление записей из '{resource}' запрещено. Записи удаляются автоматически при удалении транзакций."
        )

    model = MODEL_MAP.get(resource)
    if not model:
        raise HTTPException(status_code=404, detail="Resource not found")

    item = db.get(model, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if resource in ["transactions", "payments"]:
        db.query(AccountsRegister).filter(
            AccountsRegister.transaction_id == item_id
        ).delete()

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

# --- НАСТРОЙКА АДМИН-ПАНЕЛИ ---
admin = Admin(app, engine, title="Family Townhouse")

admin.templates.env.globals.update(
    {
        "gettext": lambda s: {
            "Save": "Сохранить",
            "Delete": "Удалить",
            "Add": "Добавить",
            "Edit": "Изменить",
            "Search": "Поиск",
            "Cancel": "Отмена",
            "Create": "Создать",
            "Are you sure you want to delete this item?": "Вы уверены, что хотите удалить этот элемент?",
            "Home": "Главная",
            "Actions": "Действия",
            "Apply": "Применить",
            "Reset": "Сброс",
        }.get(s, s)
    }
)


class OwnerAdmin(ModelView, model=Owner):
    category = "1. Основные"
    name_plural = "Собственники"
    column_list = ["id", "full_name", "phone"]
    icon = "fa-solid fa-user"


class ApartmentAdmin(ModelView, model=Apartment):
    category = "1. Основные"
    name_plural = "Квартиры/Дома"
    column_list = ["id", "number", "area"]
    icon = "fa-solid fa-house"


class AccountAdmin(ModelView, model=Account):
    category = "1. Основные"
    name_plural = "Лицевые счета"
    column_list = ["id", "number", "balance"]
    icon = "fa-solid fa-file-invoice-dollar"


class ServiceTypeAdmin(ModelView, model=ServiceType):
    category = "2. Справочники"
    name_plural = "Виды услуг"
    icon = "fa-solid fa-list-check"
    column_list = ["id", "services_type"]


class TariffTypeAdmin(ModelView, model=TariffType):
    category = "2. Справочники"
    name_plural = "Типы тарифов"
    icon = "fa-solid fa-tags"


class TariffAdmin(ModelView, model=Tariff):
    category = "2. Справочники"
    name_plural = "Тарифы"
    icon = "fa-solid fa-money-bill-wave"


class MeterAdmin(ModelView, model=Meter):
    category = "2. Справочники"
    name_plural = "Счетчики"
    icon = "fa-solid fa-gauge-high"


class MeterReadingAdmin(ModelView, model=MeterReading):
    category = "2. Справочники"
    name_plural = "Показания"
    icon = "fa-solid fa-pen-to-square"


class TransactionAdmin(ModelView, model=Transaction):
    category = "3. Учет"
    name_plural = "Транзакции"
    column_list = ["id", "amount", "transaction_type", "date"]
    icon = "fa-solid fa-exchange-alt"


class CashPointAdmin(ModelView, model=CashPoint):
    category = "3. Учет"
    name_plural = "Кассы/Счета"
    column_list = ["id", "name", "point_type"]
    icon = "fa-solid fa-vault"


class AccrualsRegisterAdmin(ModelView, model=AccrualsRegister):
    category = "3. Учет"
    name_plural = "Регистр начислений"
    column_list = [
        "id",
        "accrual_date",
        "past_reading_value",
        "current_reading_value",
        "amount",
    ]
    icon = "fa-solid fa-calculator"


class AccountsRegisterAdmin(ModelView, model=AccountsRegister):
    category = "3. Учет"
    name_plural = "Регистр взаиморасчетов"
    column_list = ["id", "operation_date", "income", "expense"]
    icon = "fa-solid fa-book"
    can_create = False
    can_edit = False
    can_delete = False


admin.add_view(OwnerAdmin)
admin.add_view(ApartmentAdmin)
admin.add_view(AccountAdmin)
admin.add_view(CashPointAdmin)
admin.add_view(ServiceTypeAdmin)
admin.add_view(TariffAdmin)
admin.add_view(MeterAdmin)
admin.add_view(MeterReadingAdmin)
admin.add_view(TransactionAdmin)
admin.add_view(AccrualsRegisterAdmin)
admin.add_view(AccountsRegisterAdmin)
admin.add_view(TariffTypeAdmin)


@app.get("/")
def index():
    return {"status": "Online", "admin_panel": "/admin", "api_v1": "/api"}
