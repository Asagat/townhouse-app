# backend/serializers.py
"""Сериализаторы сущностей в словари (JSON-ответы API).

Вынесены из `app.py` (п. 1.1 роадмапа). Никакой логики роутеров/БД здесь нет —
только преобразование моделей в dict.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

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
    User,
)


def _user_serializer(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role.name if hasattr(user.role, "name") else str(user.role),
        "role_name": user.role.value if hasattr(user.role, "value") else str(user.role),
        "is_active": user.is_active,
    }


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
