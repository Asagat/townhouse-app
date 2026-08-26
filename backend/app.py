# backend/app.py

import calendar
import enum
import io
import json
import logging
import os
import zipfile
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from database import engine, get_db
from fastapi import (
    APIRouter,
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from auth import create_access_token, get_current_user, hash_password, require_roles, verify_password

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from models import (
    Account,
    AccountsRegister,
    AccrualsRegister,
    AccrualDocument,
    Apartment,
    CashPoint,
    CashRegister,
    Meter,
    MeterReading,
    MeterReadingDocument,
    Owner,
    ReceiptDocument,
    ReceiptItem,
    ServiceType,
    Tariff,
    TariffType,
    Transaction,
    TransactionTypeEnum,
    User,
    UserRole,
    recalculate_account_balance,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, asc, text

import receipt_config as rc
from writeoffs import calculate_write_offs, rebuild_accounts_register, check_register_integrity
from permissions import require_resource_access

# Инициализация основного приложения
app = FastAPI(title="Townhouse ERP System")
logger = logging.getLogger(__name__)

# --- НАСТРОЙКА CORS ---
# Разрешённые источники берутся из CORS_ORIGINS (разделитель — запятая).
# По умолчанию — прод-домен и localhost для разработки. allow_origins=["*"]
# совместно с allow_credentials=True браузерами не поддерживается, поэтому листим явно.
_DEFAULT_ORIGINS = "https://townhouse.sagacloud.kz,http://localhost:5173"
_cors_src = os.getenv("CORS_ORIGINS", _DEFAULT_ORIGINS)
_cors_origins = [o.strip() for o in _cors_src.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)

# --- НАСТРОЙКА API РОУТЕРА ---
api_router = APIRouter(prefix="/api")

# --- АУТЕНТИФИКАЦИЯ ---
# Отдельный роутер, включается РАНЬШЕ api_router, чтобы /api/auth/* не попадал
# в catch-all api_router (POST /{resource}).
auth_router = APIRouter(prefix="/api/auth")


def _user_serializer(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role.name if hasattr(user.role, "name") else str(user.role),
        "role_name": user.role.value if hasattr(user.role, "value") else str(user.role),
        "is_active": user.is_active,
    }


@auth_router.post("/login")
def login(payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    """Вход по логину/паролю. Возвращает JWT и данные пользователя."""
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    if not username or not password:
        raise HTTPException(status_code=422, detail="Укажите логин и пароль")

    user = db.query(User).filter(User.username == username).first()
    # Одинаковый ответ и при «нет пользователя», и при неверном пароле — не выдаём,
    # какой из вариантов сработал.
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    token = create_access_token(user)
    return {"access_token": token, "token_type": "bearer", "user": _user_serializer(user)}


@auth_router.get("/me")
def me(user: User = Depends(get_current_user)):
    """Текущий пользователь по токену."""
    return _user_serializer(user)


@auth_router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("admin")),
):
    """Создание пользователя (только администратор)."""
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    role_raw = payload.get("role") or "cashier"
    full_name = payload.get("full_name")

    if not username or not password:
        raise HTTPException(status_code=422, detail="Логин и пароль обязательны")
    try:
        role = UserRole[role_raw]
    except KeyError:
        raise HTTPException(status_code=422, detail="Недопустимая роль")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="Пользователь с таким логином уже существует")

    user = User(
        username=username,
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Не удалось создать пользователя") from exc
    db.refresh(user)
    return _user_serializer(user)


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ СЕРИАЛИЗАЦИИ ---

MONTH_NAMES_RU = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]


def default_accrual_document_title(accrual_date: date) -> str:
    """Авто-генерирует название документа начислений по его дате."""
    return f"Начисление за {MONTH_NAMES_RU[accrual_date.month - 1]} {accrual_date.year}"


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
    owner = apartment.owner if apartment else None
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
            "owner": {
                "id": owner.id,
                "full_name": owner.full_name,
            } if owner else None,
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
        "title": item.title,
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
        "document_title": item.accrual_document.title if item.accrual_document else None,
    }

    if item.account:
        result["account"] = {
            "id": item.account.id,
            "account_number": item.account.account_number,
            "account_name": item.account.account_name,
        }
    else:
        result["account"] = None

    apartment = item.account.apartment if item.account else None
    result["apartment"] = (
        {
            "id": apartment.id,
            "apartment_number": apartment.apartment_number,
            "address": apartment.address,
        }
        if apartment
        else None
    )

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
        "title": item.title,
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
        "services_type_id": item.services_type_id,
        "income": float(item.income) if item.income is not None else 0.0,
        "expense": float(item.expense) if item.expense is not None else 0.0,
        "balance_after": float(item.balance_after) if item.balance_after is not None else 0.0,
        "document_title": (
            item.accrual.accrual_document.title
            if item.accrual and item.accrual.accrual_document
            else (item.transaction.title if item.transaction else None)
        ),
    }

    if item.account:
        result["account"] = {
            "id": item.account.id,
            "account_number": item.account.account_number,
            "account_name": item.account.account_name,
        }
    else:
        result["account"] = None

    apartment = item.account.apartment if item.account else None
    result["apartment"] = (
        {
            "id": apartment.id,
            "apartment_number": apartment.apartment_number,
            "address": apartment.address,
        }
        if apartment
        else None
    )

    if item.services_type:
        result["services_type"] = {
            "id": item.services_type.id,
            "services_type": item.services_type.services_type,
        }
    else:
        result["services_type"] = None

    return result


def cash_register_serializer(item: CashRegister) -> dict:
    """Сериализатор регистра денежных средств."""
    result = {
        "id": item.id,
        "operation_date": item.operation_date.isoformat() if item.operation_date else None,
        "account_id": item.account_id,
        "transaction_id": item.transaction_id,
        "income": float(item.income) if item.income is not None else 0.0,
        "expense": float(item.expense) if item.expense is not None else 0.0,
        "balance_after": float(item.balance_after) if item.balance_after is not None else 0.0,
        "document_title": item.transaction.title if item.transaction else None,
    }

    if item.account:
        result["account"] = {
            "id": item.account.id,
            "account_number": item.account.account_number,
            "account_name": item.account.account_name,
        }
    else:
        result["account"] = None

    apartment = item.account.apartment if item.account else None
    result["apartment"] = (
        {
            "id": apartment.id,
            "apartment_number": apartment.apartment_number,
            "address": apartment.address,
        }
        if apartment
        else None
    )

    return result


def receipt_item_serializer(item: ReceiptItem) -> dict:
    return {
        "id": item.id,
        "receipt_id": item.receipt_id,
        "services_type_id": item.services_type_id,
        "service_name": item.service_name,
        "reading_prev": float(item.reading_prev) if item.reading_prev is not None else None,
        "reading_curr": float(item.reading_curr) if item.reading_curr is not None else None,
        "quantity": float(item.quantity) if item.quantity is not None else 0.0,
        "tariff": float(item.tariff) if item.tariff is not None else 0.0,
        "amount": float(item.amount) if item.amount is not None else 0.0,
        "debt": float(item.debt) if item.debt is not None else 0.0,
        "overpayment": float(item.overpayment) if item.overpayment is not None else 0.0,
        "payable": float(item.payable) if item.payable is not None else 0.0,
    }


def receipt_document_serializer(item: ReceiptDocument) -> dict:
    result = {
        "id": item.id,
        "account_id": item.account_id,
        "period_year": item.period_year,
        "period_month": item.period_month,
        "apartment_number": item.apartment_number,
        "address": item.address,
        "owner_name": item.owner_name,
        "account_number": item.account_number,
        "total_amount": float(item.total_amount) if item.total_amount is not None else 0.0,
        "debt": float(item.debt) if item.debt is not None else 0.0,
        "overpayment": float(item.overpayment) if item.overpayment is not None else 0.0,
        "payable_amount": float(item.payable_amount) if item.payable_amount is not None else 0.0,
        "issued_at": item.issued_at.isoformat() if item.issued_at else None,
        "items_count": len(item.items) if item.items else 0,
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
    ServiceType: make_serializer(["services_type", "priority"]),
    TariffType: make_serializer(["name"]),
    Tariff: tariff_serializer,
    Meter: meter_serializer,
    MeterReading: meter_reading_serializer,
    MeterReadingDocument: meter_reading_document_serializer,
    AccrualsRegister: accruals_register_serializer,
    AccountsRegister: accounts_register_serializer,
    CashRegister: cash_register_serializer,
    AccrualDocument: accrual_document_serializer,
    ReceiptDocument: receipt_document_serializer,
    ReceiptItem: receipt_item_serializer,
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
    "cash_register": CashRegister,
    "accrual_documents": AccrualDocument,
    "receipt_documents": ReceiptDocument,
    "receipt_items": ReceiptItem,
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
        {"name": "title", "label": "Название", "type": "string", "required": False},
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
        {"name": "transaction_date", "label": "Дата", "type": "date", "default": "today", "required": True},
        {"name": "notes", "label": "Примечание", "type": "string"},
    ],
    "payments": [
        {"name": "title", "label": "Название", "type": "string", "required": False},
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
        {"name": "transaction_date", "label": "Дата", "type": "date", "default": "today", "required": True},
        {"name": "notes", "label": "Примечание", "type": "string"},
    ],
    "service_types": [
        {"name": "services_type", "label": "Вид услуги", "type": "string", "required": True},
        {"name": "priority", "label": "Приоритет списания", "type": "integer", "required": False},
    ],
    "services_type": [
        {"name": "services_type", "label": "Вид услуги", "type": "string", "required": True},
        {"name": "priority", "label": "Приоритет списания", "type": "integer", "required": False},
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
        {
            "name": "services_type_id",
            "label": "Вид услуги",
            "type": "reference",
            "reference": "services_type",
            "required": False,
        },
        {"name": "income", "label": "Приход", "type": "decimal"},
        {"name": "expense", "label": "Расход", "type": "decimal"},
        {"name": "balance_after", "label": "Баланс после", "type": "decimal"},
    ],
    "cash_register": [
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
        {"name": "title", "label": "Название документа", "type": "string", "required": False},
        {"name": "created_at", "label": "Дата создания", "type": "datetime", "required": False},
        {"name": "accruals_count", "label": "Количество записей", "type": "integer", "required": False},
        {"name": "total_amount", "label": "Общая сумма", "type": "decimal", "required": False},
    ],
    "receipt_documents": [
        {"name": "id", "label": "№ квитанции", "type": "integer", "required": False},
        {"name": "account_id", "label": "Лицевой счёт", "type": "reference", "reference": "accounts", "required": False},
        {"name": "apartment_number", "label": "№ квартиры", "type": "integer", "required": False},
        {"name": "owner_name", "label": "Собственник", "type": "string", "required": False},
        {"name": "period_month", "label": "Месяц", "type": "integer", "required": False},
        {"name": "period_year", "label": "Год", "type": "integer", "required": False},
        {"name": "total_amount", "label": "Начислено", "type": "decimal", "required": False},
        {"name": "debt", "label": "Долг", "type": "decimal", "required": False},
        {"name": "overpayment", "label": "Переплата", "type": "decimal", "required": False},
        {"name": "payable_amount", "label": "К оплате", "type": "decimal", "required": False},
        {"name": "issued_at", "label": "Дата создания", "type": "datetime", "required": False},
        {"name": "items_count", "label": "Количество записей", "type": "integer", "required": False},
    ],
    "receipt_items": [
        {"name": "id", "label": "ID", "type": "integer", "required": False},
        {"name": "receipt_id", "label": "Квитанция", "type": "integer", "required": False},
        {"name": "service_name", "label": "Услуга", "type": "string", "required": False},
        {"name": "amount", "label": "Сумма", "type": "decimal", "required": False},
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
    transaction_date = payload.get("transaction_date")

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

    values = {
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

    # Дата операции: если передана — устанавливаем; иначе БД поставит сейчас().
    if transaction_date not in (None, ""):
        values["transaction_date"] = coerce_field_value(
            transaction_date, {"type": "datetime", "label": "Дата операции"}
        )

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

    tariff_type = db.query(TariffType).filter(TariffType.id == tariff.tariff_type_id).first()
    tariff_type_name = tariff_type.name if tariff_type else ""

    if tariff_type_name == "Постоянный":
        amount = float(tariff.price)
    else:
        amount = consumption * float(tariff.price)

    if consumption <= 0 and tariff_type_name != "Постоянный":
        return None

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

    parsed_date = datetime.strptime(accrual_date, "%Y-%m-%d").date()
    title = payload.get("title") or default_accrual_document_title(parsed_date)

    document = AccrualDocument(
        accrual_date=parsed_date,
        title=title,
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

    if "title" in payload:
        title = payload["title"]
        document.title = (
            title
            if title not in (None, "")
            else default_accrual_document_title(document.accrual_date)
        )

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

    # Каскадное удаление начислений удалит и их записи accounts_register; запоминаем
    # затронутые аккаунты, чтобы после удаления пересчитать их балансы.
    accrued_items = db.query(AccrualsRegister).filter(
        AccrualsRegister.accrual_document_id == document_id
    ).all()
    affected_accounts: set[int] = {item.account_id for item in accrued_items}

    db.delete(document)
    db.commit()

    for account_id in affected_accounts:
        recalculate_account_balance(db, account_id)
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


@api_router.put("/meter_reading_documents/{document_id}/full")
def update_meter_reading_document_full(
    document_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """
    Полностью обновляет документ показаний и пересоздаёт его строки: старые показания удаляются,
    новые создаются из присланного списка — аналогично bulk-созданию, но в режиме редактирования.
    """
    document = db.query(MeterReadingDocument).filter(MeterReadingDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")

    title = payload.get("title")
    reading_date = payload.get("reading_date")
    services_type_id = payload.get("services_type_id")
    readings_data = payload.get("readings") or []

    if not title or not reading_date or not services_type_id:
        raise HTTPException(status_code=422, detail="Заполните название, дату и вид услуги")
    if not readings_data:
        raise HTTPException(status_code=422, detail="Добавьте хотя бы одно показание")

    parsed_date = (
        datetime.strptime(reading_date, "%Y-%m-%d").date()
        if isinstance(reading_date, str)
        else reading_date
    )
    services_type_id = int(services_type_id)

    document.title = title
    document.reading_date = parsed_date
    document.services_type_id = services_type_id

    # Удаляем старые показания этого документа и создаём новые из присланного списка
    db.query(MeterReading).filter(MeterReading.document_id == document_id).delete(synchronize_session=False)
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
                    Meter.services_type_id == services_type_id,
                )
                .order_by(Meter.installed_at.desc().nullslast(), Meter.id.desc())
                .first()
            )
            meter_id = meter.id if meter else None

        meter_reading = MeterReading(
            document_id=document.id,
            apartment_id=int(apartment_id),
            services_type_id=services_type_id,
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
        "updated": [{"id": r.id, "apartment_id": r.apartment_id} for r in created_readings],
        "errors": row_errors,
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
    db: Session = Depends(get_db),
    _auth: User = Depends(require_roles("operator", "admin")),
):
    """
    Создаёт документ начислений и строки регистра за одну транзакцию.

    Важно: клиент присылает только идентификаторы выбранных строк (account_id + services_type_id),
    а не рассчитанные значения. Сумма, потребление, тариф и показания
    всегда пересчитываются на сервере на момент сохранения, чтобы исключить подмену
    данных через API и рассинхронизацию с изменившимися между превью и сохранением данными.
    """
    year = payload.get("year")
    month = payload.get("month")
    selections = payload.get("selections") or payload.get("rows") or []

    if year in (None, "") or month in (None, ""):
        raise HTTPException(status_code=422, detail="Укажите месяц и год начисления")
    if not isinstance(selections, list) or not selections:
        raise HTTPException(status_code=422, detail="Нет строк для начисления")

    year = int(year)
    month = int(month)
    if month < 1 or month > 12:
        raise HTTPException(status_code=422, detail="Некорректный месяц")

    period_end = date(year, month, calendar.monthrange(year, month)[1])

    # Собираем уникальные пары (account_id, services_type_id) из выбора клиента
    requested_pairs: set[tuple[int, int]] = set()
    for row in selections:
        account_id = row.get("account_id")
        services_type_id = row.get("services_type_id")
        if account_id in (None, "") or services_type_id in (None, ""):
            continue
        requested_pairs.add((int(account_id), int(services_type_id)))

    if not requested_pairs:
        raise HTTPException(status_code=422, detail="Нет корректных строк для начисления")

    accrual_date = date(year, month, calendar.monthrange(year, month)[1])

    # Создаём документ начислений в той же транзакции, чтобы исключить документы-сирот
    title = payload.get("title") or default_accrual_document_title(accrual_date)
    document = AccrualDocument(accrual_date=accrual_date, title=title)
    db.add(document)
    db.flush()  # получаем document.id до commit

    items = build_accrual_register_items(db, document, period_end, accrual_date, requested_pairs)

    if not items:
        db.rollback()
        raise HTTPException(status_code=422, detail="Нет корректных строк для начисления (возможно, данные успели измениться с момента расчёта превью)")

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
        create_accounts_register_entries_for_accruals(db, items)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Не удалось создать записи в регистре взаиморасчётов: {str(exc)}",
        ) from exc

    db.refresh(document)

    serializer = SERIALIZERS.get(AccrualsRegister)
    created_rows = [serializer(item) for item in items]

    return {
        "document": accrual_document_serializer(document),
        "created": created_rows,
    }


@api_router.get("/accrual_documents/{document_id}/details")
def get_accrual_document_details(
    document_id: int,
    db: Session = Depends(get_db)
):
    """Возвращает документ начислений вместе с его строками регистра, чтобы их можно было отредактировать."""
    document = db.query(AccrualDocument).filter(AccrualDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")

    accruals = db.query(AccrualsRegister).filter(AccrualsRegister.accrual_document_id == document_id).all()
    serializer = SERIALIZERS.get(AccrualsRegister)

    year = document.accrual_date.year
    month = document.accrual_date.month

    return {
        "document": accrual_document_serializer(document),
        "accruals": [serializer(item) for item in accruals],
        "year": year,
        "month": month,
        "selections": [
            {"account_id": item.account_id, "services_type_id": item.services_type_id}
            for item in accruals
        ],
    }


@api_router.put("/accrual_documents/{document_id}/full")
async def update_accrual_document_full(
    document_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """
    Полностью пересоздаёт строки регистра начислений для документа: старые строки удаляются,
    новые рассчитываются на сервере по присланным идентификаторам (account_id + services_type_id).
    Связанные записи регистра взаиморасчётов (accounts_register) также пересоздаются.
    """
    document = db.query(AccrualDocument).filter(AccrualDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")

    accrual_date_raw = payload.get("accrual_date")
    selections = payload.get("selections") or []

    if not isinstance(selections, list) or not selections:
        raise HTTPException(status_code=422, detail="Нет строк для начисления")

    requested_pairs: set[tuple[int, int]] = set()
    for row in selections:
        account_id = row.get("account_id")
        services_type_id = row.get("services_type_id")
        if account_id in (None, "") or services_type_id in (None, ""):
            continue
        requested_pairs.add((int(account_id), int(services_type_id)))

    if not requested_pairs:
        raise HTTPException(status_code=422, detail="Нет корректных строк для начисления")

    accrual_date = (
        datetime.strptime(accrual_date_raw, "%Y-%m-%d").date()
        if accrual_date_raw
        else document.accrual_date
    )
    period_end = date(accrual_date.year, accrual_date.month, calendar.monthrange(accrual_date.year, accrual_date.month)[1])

    # Удаляем старые строки регистра вместе со связанными записями взаиморасчётов
    old_items = db.query(AccrualsRegister).filter(AccrualsRegister.accrual_document_id == document_id).all()
    old_ids = [item.id for item in old_items]
    # Аккаунты, затронутые удаляемыми строками, — их балансы тоже нужно пересчитать
    affected_accounts: set[int] = {item.account_id for item in old_items}
    if old_ids:
        db.execute(text("DELETE FROM accounts_register WHERE accrual_id = ANY(:ids)"), {"ids": old_ids})
        db.query(AccrualsRegister).filter(AccrualsRegister.id.in_(old_ids)).delete(synchronize_session=False)
        db.flush()

    document.accrual_date = accrual_date

    if "title" in payload:
        title_value = payload["title"]
        document.title = (
            title_value
            if title_value not in (None, "")
            else default_accrual_document_title(accrual_date)
        )
    elif document.title in (None, ""):
        document.title = default_accrual_document_title(accrual_date)

    new_items = build_accrual_register_items(db, document, period_end, accrual_date, requested_pairs)
    if not new_items:
        db.rollback()
        raise HTTPException(status_code=422, detail="Нет корректных строк для начисления")

    db.add_all(new_items)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Нарушение целостности данных при сохранении начислений: {str(exc)}",
        ) from exc

    try:
        create_accounts_register_entries_for_accruals(db, new_items)
        # Пересчитываем балансы аккаунтов, которым начисление полностью убрали (старые строки),
        # а также новых. create_accounts_register_entries_for_accruals уже пересчитал новые, но
        # унифицированно пересчитываем все затронутые (дублирование безопасно).
        affected_accounts.update(item.account_id for item in new_items)
        for account_id in affected_accounts:
            recalculate_account_balance(db, account_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Не удалось обновить записи в регистре взаиморасчётов: {str(exc)}",
        ) from exc

    db.refresh(document)

    serializer = SERIALIZERS.get(AccrualsRegister)
    updated_rows = [serializer(item) for item in new_items]

    return {
        "document": accrual_document_serializer(document),
        "updated": updated_rows,
    }


# --- ЭНДПОИНТЫ ДЛЯ КВИТАНЦИЙ ---

FUND_SERVICE_TYPE_ID = 7  # «Фонд развития»: сюда садим общий долг/переплату счёта


FUND_SERVICE_FALLBACK = "Фонд развития"


def _current_account_balance(db: Session, account_id: int) -> float:
    """Текущий баланс лицевого счёта — последняя запись accounts_register.

    По конвенции («КОНВЕНЦИЯ ЗНАКОВ» в models.py) это долг по услугам:
    = SUM(income) - SUM(expense) по accounts_register. Положительный = долг;
    переплата (деньги сверх распределённых) тут не отражается — см.
    _account_debt_overpayment в отчёте.
    """
    value = db.execute(
        text("SELECT balance_after FROM accounts_register WHERE account_id = :account_id "
             "ORDER BY operation_date DESC, id DESC LIMIT 1"),
        {"account_id": account_id},
    ).scalar()
    return float(value) if value is not None else 0.0


def _account_debt_overpayment(db: Session, account_id: int) -> tuple[float, float]:
    """Возвращает (долг, переплата) по счёту на основе регистров.

    - долг = начислено - списано (>=0);
    - переплата = внесено на счёт - списано (>=0) — аванс сверх распределённых услуг.
    Согласовано с метриками отчёта build_account_statement (баланс/квитанции сходятся).
    """
    accrued_total = db.execute(
        text("SELECT COALESCE(SUM(income),0) FROM accounts_register WHERE account_id=:a AND services_type_id IS NOT NULL"),
        {"a": account_id},
    ).scalar()
    paid_total = db.execute(
        text("SELECT COALESCE(SUM(expense),0) FROM accounts_register WHERE account_id=:a AND services_type_id IS NOT NULL"),
        {"a": account_id},
    ).scalar()
    available = db.execute(
        text("SELECT COALESCE(SUM(income - expense),0) FROM cash_register WHERE account_id=:a"),
        {"a": account_id},
    ).scalar()
    accrued_total = float(accrued_total or 0.0)
    paid_total = float(paid_total or 0.0)
    available = float(available or 0.0)
    debt = max(0.0, accrued_total - paid_total)
    overpayment = max(0.0, available - paid_total)
    return debt, overpayment


def _service_name(db: Session, services_type_id) -> str:
    if services_type_id is None:
        return FUND_SERVICE_FALLBACK
    st = db.get(ServiceType, services_type_id)
    return st.services_type if st else str(services_type_id)


def generate_receipt_document(db: Session, account: Account, year: int, month: int) -> ReceiptDocument | None:
    """
    Формирует квитанцию для одного лицевого счёта за период.
    Возвращает None, если за период нет начислений.
    """
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])

    accruals = (
        db.query(AccrualsRegister)
        .filter(
            AccrualsRegister.account_id == account.id,
            AccrualsRegister.accrual_date >= start,
            AccrualsRegister.accrual_date <= end,
        )
        .all()
    )
    if not accruals:
        return None

    apartment = account.apartment
    owner_name = apartment.owner.full_name if apartment and apartment.owner else ""

    receipt = ReceiptDocument(
        account_id=account.id,
        period_year=year,
        period_month=month,
        apartment_number=apartment.apartment_number if apartment else None,
        address=apartment.address if apartment else None,
        owner_name=owner_name,
        account_number=account.account_number,
    )
    db.add(receipt)
    db.flush()

    # Долг и переплата счёта на основе регистров (см. «КОНВЕНЦИЯ ЗНАКОВ»):
    # долг = начислено - списано, переплата = внесено - списано (аванс).
    debt, overpayment = _account_debt_overpayment(db, account.id)

    total_amount = 0.0
    created_items: list[ReceiptItem] = []
    for acc in accruals:
        tariff = acc.tariff.price if acc.tariff else 0
        amount = float(acc.amount)
        total_amount += amount
        item = ReceiptItem(
            receipt_id=receipt.id,
            services_type_id=acc.services_type_id,
            service_name=_service_name(db, acc.services_type_id),
            reading_prev=acc.past_reading_value,
            reading_curr=acc.current_reading_value,
            quantity=acc.consumption,
            tariff=tariff,
            amount=amount,
            debt=0.0,
            overpayment=0.0,
            payable=amount,
        )
        db.add(item)
        created_items.append(item)

    # Долг/переплату садим на строку «Фонд развития» (services_type_id == FUND_SERVICE_TYPE_ID).
    # Ищем среди уже созданных строк фонда из начислений; если таковой нет — создаём отдельную.
    fund_row = next(
        (x for x in created_items if x.services_type_id == FUND_SERVICE_TYPE_ID),
        None,
    )
    if fund_row is None:
        fund_row = ReceiptItem(
            receipt_id=receipt.id,
            services_type_id=FUND_SERVICE_TYPE_ID,
            service_name=FUND_SERVICE_FALLBACK,
            reading_prev=None,
            reading_curr=None,
            quantity=1,
            tariff=0.0,
            amount=0.0,
            debt=0.0,
            overpayment=0.0,
            payable=0.0,
        )
        db.add(fund_row)
    # «Садим» общий баланс (долг ИЛИ переплата) на строку фонда: payable = amount + долг - переплата
    fund_row.debt = debt
    fund_row.overpayment = overpayment
    fund_row.payable = float(fund_row.amount or 0.0) + debt - overpayment

    receipt.total_amount = total_amount
    receipt.debt = debt
    receipt.overpayment = overpayment
    receipt.payable_amount = total_amount + debt - overpayment

    return receipt


@api_router.post("/receipt_documents/generate", status_code=201)
def generate_receipts(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """Массово формирует квитанции по всем активным лицевым счетам за период."""
    year = payload.get("year")
    month = payload.get("month")
    if year in (None, "") or month in (None, ""):
        raise HTTPException(status_code=422, detail="Укажите месяц и год")
    year = int(year)
    month = int(month)
    if month < 1 or month > 12:
        raise HTTPException(status_code=422, detail="Некорректный месяц")

    accounts = db.query(Account).filter(Account.is_active == True).all()
    created = []
    for account in accounts:
        rec = generate_receipt_document(db, account, year, month)
        if rec:
            created.append(rec)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Не удалось сохранить квитанции: {str(exc)}")

    serializer = SERIALIZERS.get(ReceiptDocument)
    rows = []
    for rec in created:
        db.refresh(rec)
        rows.append(serializer(rec) if serializer else {"id": rec.id})
    return {"year": year, "month": month, "created": rows}


@api_router.post("/write_offs/run", status_code=201)
def run_write_offs(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    _auth: User = Depends(require_roles("operator", "admin")),
):
    """
    Операция «Списание задолженностей».

    Распределяет доступные деньги каждого лицевого счёта по видам услуг
    в порядке приоритета (services_type.priority) и пишет результат
    в Регистр взаиморасчётов. Идемпотентна: существующие строки списания
    для затронутых счетов перестраиваются заново.

    Запускается: по кнопке, по регламенту (cron) или при создании
    «Приход/Расход».
    """
    raw_ids = payload.get("account_ids")
    if raw_ids is None:
        account_ids = None
    elif isinstance(raw_ids, list):
        account_ids = [int(x) for x in raw_ids]
    else:
        raise HTTPException(status_code=422, detail="Поле 'account_ids' должно быть списком или отсутствовать")

    try:
        result = calculate_write_offs(db, account_ids)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Ошибка списания задолженностей")
        raise HTTPException(status_code=409, detail=f"Не удалось выполнить списание: {str(exc)}")

    return result


@api_router.post("/maintenance/rebuild_registers", status_code=201)
def rebuild_registers(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    _auth: User = Depends(require_roles("operator", "admin")),
):
    """
    Полный пересбор производного среза (accounts_register) «с нуля» из первичных
    регистров (accruals_register + cash_register). Служебная операция для
    восстановления согласованности после импорта/правок данных и после
    «не прошедшего» списания.

    Опциональный account_ids — ограничить пересбор конкретными счетами;
    если не передан — все активные. После пересбора возвращает аудит целостности
    по затронутым счетам.
    """
    raw_ids = payload.get("account_ids")
    if raw_ids is None:
        account_ids = None
    elif isinstance(raw_ids, list):
        account_ids = [int(x) for x in raw_ids]
    else:
        raise HTTPException(status_code=422, detail="Поле 'account_ids' должно быть списком или отсутствовать")

    try:
        rebuild = rebuild_accounts_register(db, account_ids)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Ошибка пересбора регистров")
        raise HTTPException(status_code=409, detail=f"Не удалось пересобрать регистры: {str(exc)}")

    # Аудит целостности по затронутым счетам.
    audit = []
    for rec in rebuild["processed"]:
        audit.append(check_register_integrity(db, rec["account_id"]))

    return {
        "rebuilt": rebuild["processed"],
        "integrity": audit,
        "all_consistent": all(a["consistent"] for a in audit),
    }


# --- ОТЧЁТ ПО ЛИЦЕВОМУ СЧЁТУ ---


def build_account_statement(db: Session, account_id: int) -> dict:
    """
    Сводка по лицевому счёту для отчёта / личного кабинета.

    Метрики считаются НЕПОСРЕДСТВЕННО из регистров (а не по-знаковому balance_after),
    поэтому корректны при целевой конвенции знаков (income = начислено, expense = списано):

      - начислено по услугам  = Σ income записей accounts_register с видом услуги;
      - оплачено по услугам   = Σ expense записей accounts_register с видом услуги
                                 (это же и есть строки «списание»);
      - внесено на счёт       = Σ(income - expense) из cash_register;
      - долг по услуге        = начислено - оплачено;
      - переплата (аванс)     = внесено - оплачено (>=0) — свободные деньги сверх
                                 распределённых по услугам.
    """
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise KeyError(account_id)

    # Свод по услугам из регистра взаиморасчётов.
    svc_rows = db.execute(
        text("""
            SELECT services_type_id,
                   COALESCE(SUM(income), 0)  AS accrued,
                   COALESCE(SUM(expense), 0) AS paid
            FROM accounts_register
            WHERE account_id = :a AND services_type_id IS NOT NULL
            GROUP BY services_type_id
            ORDER BY MIN(id)
        """),
        {"a": account_id},
    ).fetchall()

    services = []
    accrued_total = 0.0
    paid_total = 0.0
    for row in svc_rows:
        svc_id = row[0]
        accrued = float(row[1] or 0.0)
        paid = float(row[2] or 0.0)
        debt = max(0.0, accrued - paid)
        accrued_total += accrued
        paid_total += paid
        services.append(
            {
                "services_type_id": svc_id,
                "service_name": _service_name(db, svc_id),
                "accrued": round(accrued, 2),
                "paid": round(paid, 2),
                "debt": round(debt, 2),
            }
        )

    services.sort(key=lambda s: (s["service_name"] or ""))

    # Внесено (доступно) из регистра денежных средств.
    available = db.execute(
        text("SELECT COALESCE(SUM(income - expense), 0) FROM cash_register WHERE account_id = :a"),
        {"a": account_id},
    ).scalar()
    available = float(available or 0.0)

    debt_total = max(0.0, accrued_total - paid_total)
    overpayment = max(0.0, available - paid_total)
    balance = _current_account_balance(db, account_id)

    apartment = account.apartment
    owner = apartment.owner if apartment else None

    return {
        "account": {
            "id": account.id,
            "account_number": account.account_number,
            "account_name": account.account_name,
        },
        "apartment": (
            {
                "id": apartment.id,
                "apartment_number": apartment.apartment_number,
                "address": apartment.address,
            }
            if apartment
            else None
        ),
        "owner": (
            {
                "id": owner.id,
                "full_name": owner.full_name,
                "phone": owner.phone,
            }
            if owner
            else None
        ),
        "metrics": {
            "accrued_total": round(accrued_total, 2),
            "paid_total": round(paid_total, 2),
            "available": round(available, 2),
            "debt_total": round(debt_total, 2),
            "overpayment": round(overpayment, 2),
            "balance": round(balance, 2),
        },
        "services": services,
    }


@api_router.get("/accounts/{account_id}/statement")
def get_account_statement(
    account_id: int,
    db: Session = Depends(get_db),
    _auth: User = Depends(get_current_user),
):
    """Отчёт по лицевому счёту: начислено / оплачено / долг по услугам, внесено / переплата.

    Доступен любой аутентифицированной роли. Для роли resident в будущем (ЛК)
    будет ограничение только своим счётом.
    """
    try:
        return build_account_statement(db, account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Лицевой счёт не найден")


@api_router.get("/receipt_documents/{document_id}/items")
def get_receipt_items(
    document_id: int,
    db: Session = Depends(get_db)
):
    receipt = db.get(ReceiptDocument, document_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Квитанция не найдена")
    items = db.query(ReceiptItem).filter(ReceiptItem.receipt_id == document_id).all()
    serializer = SERIALIZERS.get(ReceiptItem)
    return {
        "document": receipt_document_serializer(receipt),
        "items": [serializer(i) for i in items] if serializer else [],
    }


@api_router.get("/receipt_documents/{document_id}/pdf")
def get_receipt_pdf(
    document_id: int,
    db: Session = Depends(get_db),
    inline: bool = Query(False, description="inline=true — показать в браузере, иначе скачивание"),
):
    """Генерирует PDF квитанции на лету. inline=true открывает в просмотрщике, иначе скачивает."""
    receipt = (
        db.query(ReceiptDocument)
        .options(joinedload(ReceiptDocument.items))
        .get(document_id)
    )
    if not receipt:
        raise HTTPException(status_code=404, detail="Квитанция не найдена")

    pdf_bytes = build_receipt_pdf(receipt)
    filename = f"receipt_{receipt.id}_{receipt.period_month:02d}_{receipt.period_year}.pdf"
    if inline:
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=\"{filename}\""},
        )
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )


@api_router.post("/receipt_documents/bulk_pdf")
def bulk_receipt_pdf(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    """Массово скачивает квитанции за период одним ZIP-архивом."""
    year = payload.get("year")
    month = payload.get("month")
    if year in (None, "") or month in (None, ""):
        raise HTTPException(status_code=422, detail="Укажите месяц и год")
    year = int(year)
    month = int(month)

    receipts = (
        db.query(ReceiptDocument)
        .options(joinedload(ReceiptDocument.items))
        .filter(ReceiptDocument.period_year == year, ReceiptDocument.period_month == month)
        .all()
    )
    if not receipts:
        raise HTTPException(status_code=404, detail="Квитанции за выбранный период не найдены")

    bio = io.BytesIO()
    with zipfile.ZipFile(bio, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rec in receipts:
            pdf = build_receipt_pdf(rec)
            fname = f"Квитанция_{rec.apartment_number}_{rec.period_month:02d}.{rec.period_year}.pdf"
            # безопасное имя в архиве
            zf.writestr(fname, pdf)
    bio.seek(0)

    return StreamingResponse(
        bio,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=\"receipts_{month:02d}_{year}.zip\""
        },
    )


@api_router.delete("/receipt_documents/bulk_delete")
def bulk_delete_receipts(
    year: int,
    month: int,
    db: Session = Depends(get_db),
):
    """Массово удаляет квитанции за период (строки удаляются каскадно)."""
    deleted = db.query(ReceiptDocument).filter(
        ReceiptDocument.period_year == year,
        ReceiptDocument.period_month == month,
    ).delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}


def _fmt_amount2(value) -> str:
    """Формат: пробелы как разделители тысяч, запятая как десятичный. Напр. «1 525,00»."""
    try:
        v = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        v = Decimal("0.00")
    neg = ""
    if v < 0:
        neg = "-"
        v = -v
    int_part, _, frac = f"{v}".partition(".")
    ip = f"{int(int_part):,}".replace(",", " ")
    return f"{neg}{ip},{frac}"


def _fmt_reading(value) -> str:
    if value is None:
        return "-"
    v = Decimal(str(value))
    if v == v.to_integral_value():
        return f"{int(v)}"
    return f"{v}"


def build_receipt_pdf(receipt: ReceiptDocument) -> bytes:
    """Вёрстка PDF квитанции в стиле шаблона «Квитанция.pdf» (+ столбец «Переплата»)."""
    # Поддержка кириллицы: регистрируем TTF-шрифты.
    FONT = rc.FONT_REGULAR
    FONT_B = rc.FONT_BOLD
    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT, rc.FONT_REGULAR_PATH))
    if FONT_B not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_B, rc.FONT_BOLD_PATH))

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "Title2", parent=styles["Normal"], fontSize=rc.TITLE_SIZE,
        leading=rc.TITLE_SIZE + 3, spaceAfter=2, leftIndent=0, fontName=FONT_B,
        textColor=colors.HexColor(rc.COLOR_TEXT_TITLE),
    )
    brand_style = ParagraphStyle(
        "Brand", parent=styles["Normal"], fontSize=rc.BRAND_SIZE,
        leading=rc.BRAND_SIZE + 2, fontName=FONT_B,
        textColor=colors.HexColor(rc.COLOR_BRAND_TEXT),
    )
    period_style = ParagraphStyle(
        "Period", parent=styles["Normal"], fontSize=rc.PERIOD_SIZE,
        spaceAfter=6, leftIndent=0, fontName=FONT_B,
        textColor=colors.HexColor(rc.COLOR_TEXT_PERIOD),
    )
    head_style = ParagraphStyle(
        "Head", parent=styles["Normal"], fontSize=rc.HEAD_SIZE,
        spaceAfter=14, leftIndent=0, fontName=FONT_B,
        textColor=colors.HexColor(rc.COLOR_TEXT_HEAD),
    )

    month_names = [
        "январь", "февраль", "март", "апрель", "май", "июнь",
        "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
    ]
    period = f"{month_names[receipt.period_month - 1].capitalize()} {receipt.period_year}"
    # Логотип (если файл доступен)
    logo_path = rc.LOGO_PATH
    if not os.path.isabs(logo_path):
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), logo_path)
    has_logo = os.path.exists(logo_path)
    logo_w = rc.LOGO_WIDTH
    # Пропорции: если включена высота не задана — берём из реального файла
    if rc.LOGO_HEIGHT:
        logo_h = rc.LOGO_HEIGHT
    elif has_logo:
        from PIL import Image as _PILImage
        _w, _h = _PILImage.open(logo_path).size
        logo_h = logo_w * (_h / _w) if _w else logo_w
    else:
        logo_h = logo_w * (90 / 73)

    # Строка шапки: слева «Квитанция», справа логотип + «Family Townhouse» (прижато вправо)
    left = Paragraph(rc.TEXT_TITLE, title_style)
    brand_text = Paragraph(rc.TEXT_BRAND, brand_style)
    if has_logo:
        brand = Table(
            [[
                Image(logo_path, width=logo_w, height=logo_h),
                brand_text,
            ]],
            colWidths=[logo_w + 6, 150],
            hAlign="LEFT",
        )
        brand.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        # head_row: левый блок, растягивающийся пустырь, brand — прижат вправо
        head_row = Table(
            [[left, "", brand]],
            colWidths=[120, None, 196],
            hAlign="LEFT",
        )
    else:
        head_row = Table(
            [[left, "", brand_text]],
            colWidths=[120, None, 196],
            hAlign="LEFT",
        )
    head_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))

    head_row.spaceBefore = 0
    header = [Spacer(1, rc.HEADER_SPACER), head_row]
    header.append(Paragraph(period, period_style))
    header.append(
        Paragraph(
            f"Квартира № {receipt.apartment_number} {receipt.owner_name}",
            head_style,
        )
    )

    # Двухуровневая шапка: «Показания» — объединённая ячейка над Пред./Послед.
    data = [
        [
            rc.COL_Услуга, rc.COL_Показания, rc.COL_Показания, rc.COL_Колво,
            rc.COL_Тариф, rc.COL_Сумма, rc.COL_Долг, rc.COL_Переплата, rc.COL_Коплате,
        ],
        [
            "", rc.COL_Пред, rc.COL_Послед, "", "", "", "", "", "",
        ],
    ]
    for it in sorted(receipt.items, key=lambda x: (x.services_type_id is None, x.id)):
        data.append([
            it.service_name,
            _fmt_reading(it.reading_prev),   # Пред.
            _fmt_reading(it.reading_curr),   # Послед.
            _fmt_amount2(it.quantity) if it.quantity is not None else "-",
            _fmt_amount2(it.tariff) if it.tariff is not None else "-",
            _fmt_amount2(it.amount),
            _fmt_amount2(it.debt) if it.debt else "0,00",
            _fmt_amount2(it.overpayment) if it.overpayment else "0,00",
            _fmt_amount2(it.payable),
        ])
    data.append([
        rc.COL_Итого, "", "", "", "", _fmt_amount2(receipt.total_amount),
        _fmt_amount2(receipt.debt) if receipt.debt else "0,00",
        _fmt_amount2(receipt.overpayment) if receipt.overpayment else "0,00",
        _fmt_amount2(receipt.payable_amount),
    ])

    col_widths = rc.COL_WIDTHS
    table = Table(data, colWidths=col_widths, repeatRows=2)
    gray = colors.HexColor(rc.COLOR_TABLE_GRID)          # серые границы
    even = colors.HexColor(rc.COLOR_ROW_EVEN)            # чётная строка
    odd = colors.HexColor(rc.COLOR_ROW_ODD)              # нечётная строка
    header_bg = colors.HexColor(rc.COLOR_HEADER_BG)
    total_bg = colors.HexColor(rc.COLOR_TOTAL_BG)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, gray),
        ("BOX", (0, 0), (-1, -1), 0.8, gray),
        # Чередование фона строк данных (перекрывается нижними командами для шапки/итога)
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [even, odd]),
        ("BACKGROUND", (0, 0), (-1, 1), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 1), colors.HexColor(rc.COLOR_TEXT_HEADER_TABLE)),
        ("TEXTCOLOR", (0, 2), (-1, -2), colors.HexColor(rc.COLOR_TEXT_CELL)),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor(rc.COLOR_TEXT_TOTAL)),
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), rc.TABLE_SIZE),
        ("FONTNAME", (0, 0), (-1, 1), FONT_B),
        ("ALIGN", (1, 2), (-1, -1), "RIGHT"),
        ("ALIGN", (1, 0), (-1, 1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), rc.CELL_TOP_PADDING),
        ("BOTTOMPADDING", (0, 0), (-1, -1), rc.CELL_BOTTOM_PADDING),
        # Объединение ячеек шапки (строка 0 и 1)
        ("SPAN", (1, 0), (2, 0)),
        ("SPAN", (0, 0), (0, 1)),
        ("SPAN", (3, 0), (3, 1)),
        ("SPAN", (4, 0), (4, 1)),
        ("SPAN", (5, 0), (5, 1)),
        ("SPAN", (6, 0), (6, 1)),
        ("SPAN", (7, 0), (7, 1)),
        ("SPAN", (8, 0), (8, 1)),
        ("SPAN", (0, -1), (4, -1)),
        ("FONTNAME", (0, -1), (-1, -1), FONT_B),
        ("BACKGROUND", (0, -1), (-1, -1), total_bg),
    ]))

    issued = receipt.issued_at
    stamp = issued.strftime("%d.%m.%Y %H:%M:%S") if issued else ""
    date_style = ParagraphStyle(
        "DateS", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor(rc.COLOR_STAMP),
        spaceBefore=18, alignment=2, fontName=FONT,
    )
    footer = [Paragraph(stamp, date_style)]

    story = header + [Spacer(1, 2), table] + footer
    buf = io.BytesIO()
    SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=rc.PAGE_TOP_MARGIN, bottomMargin=rc.PAGE_BOTTOM_MARGIN,
        leftMargin=rc.PAGE_LEFT_MARGIN, rightMargin=rc.PAGE_RIGHT_MARGIN,
    ).build(story)
    return buf.getvalue()


# --- УНИВЕРСАЛЬНЫЕ CRUD ЭНДПОИНТЫ ---
# ВАЖНО: должны быть ПОСЛЕ эндпоинтов /meta, /accrual_documents, /accruals_register, /meter_readings/bulk

@api_router.get("/{resource}")
def get_list(
    resource: str,
    _start: int = 0,
    _end: int = 10,
    _sort: str | None = None,
    _order: str | None = None,
    request: Request = None,
    db: Session = Depends(get_db),
    _auth: User = Depends(require_resource_access),
):
    if resource not in MODEL_MAP:
        raise HTTPException(status_code=404, detail="Resource not found")

    model = MODEL_MAP[resource]
    query = db.query(model)

    if resource == "accounts_register":
        query = query.options(
            joinedload(AccountsRegister.account).joinedload(Account.apartment),
            joinedload(AccountsRegister.services_type),
            joinedload(AccountsRegister.accrual).joinedload(AccrualsRegister.accrual_document),
            joinedload(AccountsRegister.transaction),
        )
    elif resource == "cash_register":
        query = query.options(
            joinedload(CashRegister.account).joinedload(Account.apartment),
            joinedload(CashRegister.transaction),
        )
    elif resource == "accruals_register":
        query = query.options(
            joinedload(AccrualsRegister.account).joinedload(Account.apartment),
            joinedload(AccrualsRegister.services_type),
            joinedload(AccrualsRegister.tariff),
            joinedload(AccrualsRegister.accrual_document),
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
    elif resource == "receipt_documents":
        query = query.options(
            joinedload(ReceiptDocument.account).joinedload(Account.apartment),
            joinedload(ReceiptDocument.items),
        )

    if _sort: 
        order_func = desc if (_order or "").lower() == "desc" else asc

        if _sort == "document_title":
            # document_title — расчётное поле сериализатора; сортируем по названию
            # документа-источника через подзапросы.
            if resource == "accruals_register":
                query = query.order_by(
                    order_func(
                        text("""(SELECT ad.title FROM accrual_documents ad
                                  WHERE ad.id = accruals_register.accrual_document_id)""")
                    )
                )
            elif resource == "accounts_register":
                query = query.order_by(
                    order_func(
                        text("""(
                            COALESCE(
                                (SELECT ad.title FROM accrual_documents ad
                                 WHERE ad.id = (SELECT arx.accrual_document_id FROM accruals_register arx
                                                WHERE arx.id = accounts_register.accrual_id)),
                                (SELECT t.title FROM transactions t
                                 WHERE t.id = accounts_register.transaction_id)
                            )
                        )""")
                    )
                )
        elif _sort == "apartment.apartment_number":
            # Сортировка по № квартиры. Для регистров (начислений, взаиморасчётов,
            # денежных средств) квартира находится через лицевой счёт, для показаний — напрямую.
            if resource in ("accruals_register", "accounts_register", "cash_register"):
                table = {
                    "accruals_register": "accruals_register",
                    "accounts_register": "accounts_register",
                    "cash_register": "cash_register",
                }[resource]
                query = query.order_by(
                    order_func(
                        text("""(SELECT a.apartment_number FROM apartments a
                                   WHERE a.id = (SELECT acc.apartment_id FROM accounts acc
                                                 WHERE acc.id = {0}.account_id))""".format(table))
                    )
                )
            elif resource == "meter_readings":
                query = query.order_by(
                    order_func(
                        text("""(SELECT a.apartment_number FROM apartments a
                                   WHERE a.id = meter_readings.apartment_id)""")
                    )
                )
        elif hasattr(model, _sort):
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
    request: Request = None,
    db: Session = Depends(get_db),
    _auth: User = Depends(require_resource_access),
):
    model = MODEL_MAP.get(resource)
    if not model:
        raise HTTPException(status_code=404, detail="Resource not found")

    if resource == "accounts_register":
        item = db.query(model).options(
            joinedload(AccountsRegister.account).joinedload(Account.apartment),
            joinedload(AccountsRegister.services_type),
            joinedload(AccountsRegister.accrual).joinedload(AccrualsRegister.accrual_document),
            joinedload(AccountsRegister.transaction),
        ).filter(model.id == item_id).first()
    elif resource == "cash_register":
        item = db.query(model).options(
            joinedload(CashRegister.account).joinedload(Account.apartment),
            joinedload(CashRegister.transaction),
        ).filter(model.id == item_id).first()
    elif resource == "accruals_register":
        item = db.query(model).options(
            joinedload(AccrualsRegister.account).joinedload(Account.apartment),
            joinedload(AccrualsRegister.services_type),
            joinedload(AccrualsRegister.tariff),
            joinedload(AccrualsRegister.accrual_document),
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
    elif resource == "receipt_documents":
        item = db.query(model).options(
            joinedload(ReceiptDocument.account).joinedload(Account.apartment),
            joinedload(ReceiptDocument.items),
        ).filter(model.id == item_id).first()
    elif resource == "receipt_items":
        item = db.query(model).options(
            joinedload(ReceiptItem.receipt)
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
    resource: str,
    payload: dict[str, Any] = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
    _auth: User = Depends(require_resource_access),
):
    if resource in ["accounts_register", "cash_register"]:
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

    # Для документов «Приход/Расход» после получения id и даты формируем название
    if resource in ["transactions", "payments"]:
        set_transaction_title(db, item)
        db.commit()
        db.refresh(item)

        # Шаг 3.4: автоматически выполняем списание задолженности по счёту документа.
        # Документ «Приход/Расход» уже записал движение в cash_register; пересчитываем
        # разнесение по услугам. Идемпотентно (списание перестраивается заново).
        # Ошибка здесь не откатывает создание самого документа.
        try:
            calculate_write_offs(db, [item.account_id])
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Ошибка авт. списания при создании документа Приход/Расход")

    serializer = SERIALIZERS.get(model)
    row = serializer(item) if serializer else {"id": item.id}
    return row


@api_router.patch("/{resource}/{item_id}")
async def update_resource_item(
    resource: str,
    item_id: int,
    payload: dict[str, Any] = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
    _auth: User = Depends(require_resource_access),
):
    if resource in ["accounts_register", "cash_register"]:
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

    # Для документов «Приход/Расход» пересчитываем название по формуле
    # (тип операции или дата могли измениться).
    if resource in ["transactions", "payments"]:
        set_transaction_title(db, item)
        db.commit()
        db.refresh(item)

    serializer = SERIALIZERS.get(model)
    row = serializer(item) if serializer else {"id": item.id}
    return row


@api_router.delete("/{resource}/{item_id}", status_code=204)
async def delete_resource_item(
    resource: str,
    item_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
    _auth: User = Depends(require_resource_access),
):
    if resource in ["accounts_register", "cash_register"]:
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


app.include_router(auth_router)
app.include_router(api_router)
