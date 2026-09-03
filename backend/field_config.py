# backend/field_config.py
"""Метаданные о ресурсах и полях форм + приведение значений полей.

Вынесены из `app.py` (п. 1.1 роадмапа). `MODEL_MAP` связывает имя ресурса
с моделью, `FIELD_CONFIG` описывает поля для динамической формы на фронтенде,
`coerce_field_value` приводит входящее значение к нужному типу поля.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException

from models import (
    Account,
    AccountsRegister,
    AccrualsRegister,
    AccrualDocument,
    AnalyticArticle,
    AnalyticKind,
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
    WriteoffDocument,
    WriteoffItem,
)


MODEL_MAP = {
    "owners": Owner,
    "apartments": Apartment,
    "accounts": Account,
    "cash_points": CashPoint,
    "analytic_articles": AnalyticArticle,
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
    "writeoff_documents": WriteoffDocument,
    "writeoff_items": WriteoffItem,
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
    "analytic_articles": [
        {"name": "name", "label": "Наименование", "type": "string", "required": True},
        {
            "name": "kind",
            "label": "Тип",
            "type": "enum",
            "enum_class": AnalyticKind,
            "required": True,
        },
        {"name": "is_active", "label": "Активна", "type": "boolean"},
    ],
    "transactions": [
        {"name": "title", "label": "Название", "type": "string", "required": False},
        {
            "name": "apartment_id",
            "label": "Квартира",
            "type": "reference",
            "reference": "apartments",
            "required": False,
        },
        {
            "name": "cash_point_id",
            "label": "Касса/Счёт",
            "type": "reference",
            "reference": "cash_points",
            "required": True,
        },
        {
            "name": "article_id",
            "label": "Аналитика",
            "type": "reference",
            "reference": "analytic_articles",
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
            "required": False,
        },
        {
            "name": "cash_point_id",
            "label": "Касса/Счёт",
            "type": "reference",
            "reference": "cash_points",
            "required": True,
        },
        {
            "name": "article_id",
            "label": "Аналитика",
            "type": "reference",
            "reference": "analytic_articles",
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
        {"name": "is_oneoff", "label": "Разовый сбор (не участвует в месячном пересчёте)", "type": "boolean", "required": False},
        {"name": "comment", "label": "Примечание", "type": "text", "required": False},
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
        {"name": "comment", "label": "Примечание", "type": "text", "required": False},
        {"name": "doc_kind", "label": "Тип", "type": "string", "required": False},
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
    "writeoff_documents": [
        {"name": "writeoff_date", "label": "Дата списания", "type": "date", "required": True},
        {"name": "title", "label": "Название", "type": "string", "required": False},
        {"name": "status", "label": "Статус", "type": "string", "required": False},
        {"name": "created_by", "label": "Автор", "type": "string", "required": False},
        {"name": "created_at", "label": "Дата создания", "type": "datetime", "required": False},
        {"name": "items_count", "label": "Количество записей", "type": "integer", "required": False},
        {"name": "total_allocated", "label": "Распределено", "type": "decimal", "required": False},
    ],
    "writeoff_items": [
        {"name": "document_id", "label": "Документ", "type": "integer", "required": False},
        {"name": "account_id", "label": "Лицевой счёт", "type": "reference", "reference": "accounts", "required": False},
        {"name": "services_type_id", "label": "Вид услуги", "type": "reference", "reference": "services_type", "required": False},
        {"name": "allocated", "label": "Списано", "type": "decimal", "required": False},
        {"name": "balance_after", "label": "Баланс после", "type": "decimal", "required": False},
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
            if isinstance(raw_value, str):
                return raw_value.strip().lower() in ("1", "true", "yes", "да", "on")
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
