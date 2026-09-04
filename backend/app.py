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
    Counterparty,
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
from sqlalchemy import desc, asc

import receipt_config as rc
from writeoffs import (
    calculate_write_offs,
    create_writeoff_document,
    auto_recalculate_writeoffs,
    rebuild_accounts_register,
    check_register_integrity,
)
from permissions import require_resource_access
from field_config import FIELD_CONFIG, MODEL_MAP, coerce_field_value
from sorting import build_order_clause
from serializers import SERIALIZERS, _user_serializer
from services import (build_accrual_register_items, build_transaction_title, calculate_accrual_for_account_service, calculate_accruals_preview, create_accounts_register_entries_for_accruals, resolve_meter_reading_values, resolve_meter_reading_document_values, resolve_transaction_values, set_transaction_title, audit_document_create, audit_document_update)


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
        account_id=payload.get("account_id") or None,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Не удалось создать пользователя") from exc
    db.refresh(user)
    return _user_serializer(user)


@auth_router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("admin")),
):
    """Список пользователей (только администратор)."""
    users = db.query(User).order_by(User.id.asc()).all()
    return [_user_serializer(u) for u in users]


@auth_router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("admin")),
):
    """Обновление пользователя: роль, имя, активность, опционально пароль (admin)."""
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if "role" in payload and payload["role"]:
        try:
            role = UserRole[payload["role"]]
        except KeyError:
            raise HTTPException(status_code=422, detail="Недопустимая роль")
        if target.role == UserRole.admin and role != UserRole.admin and admin.id == target.id:
            raise HTTPException(status_code=403, detail="Нельзя изменить роль собственного аккаунта")
        target.role = role

    if "full_name" in payload:
        target.full_name = payload["full_name"] or None

    if "is_active" in payload:
        new_active = bool(payload["is_active"])
        if not new_active and admin.id == target.id:
            raise HTTPException(status_code=403, detail="Нельзя отключить собственный аккаунт")
        target.is_active = new_active

    # Привязка к лицевому счёту (для роли resident / ЛК).
    if "account_id" in payload:
        val = payload["account_id"]
        target.account_id = int(val) if val not in (None, "") else None

    if payload.get("password"):
        if len(payload["password"]) < 6:
            raise HTTPException(status_code=422, detail="Пароль слишком короткий (мин. 6 символов)")
        target.password_hash = hash_password(payload["password"])

    db.add(target)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Не удалось обновить пользователя") from exc
    db.refresh(target)
    return _user_serializer(target)


@auth_router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("admin")),
):
    """Удаление пользователя (только администратор). Нельзя удалить самого себя."""
    if admin.id == user_id:
        raise HTTPException(status_code=403, detail="Нельзя удалить собственный аккаунт")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    db.delete(target)
    db.commit()
    return Response(status_code=204)


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ СЕРИАЛИЗАЦИИ ---

CUSTOM_VALUE_BUILDERS: dict[str, Any] = {
    "meter_readings": resolve_meter_reading_values,
    "meter_reading_documents": resolve_meter_reading_document_values,
    "transactions": resolve_transaction_values,
    "payments": resolve_transaction_values,
}

# Сортировка по вложенным/вычисляемым полям (роадмап 1.5) вынесена в sorting.py: там
# декларативно описаны пути по relationship, а коррелированные SQL-подзапросы строятся
# автоматически (build_order_clause). Прямые атрибуты моделей сортируются через hasattr.


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
            joinedload(CashRegister.transaction).joinedload(Transaction.article),
            joinedload(CashRegister.contractor),
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
            joinedload(Transaction.cash_point),
            joinedload(Transaction.article),
            joinedload(Transaction.contractor),
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
        # payments и transactions — одна и та же таблица; ресурс нормализуем для словаря.
        norm_resource = "transactions" if resource in ("transactions", "payments") else resource

        # Общее решение сортировки (роадмап 1.5): build_order_clause разрешает и прямые
        # столбцы модели, и вложенные поля через декларативные пути по relationship
        # (авто-генерируемый подзапрос), и агрегаты/вычисляемые выражения.
        expr = build_order_clause(norm_resource, model, _sort)
        if expr is not None:
            query = query.order_by(order_func(expr))
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
            joinedload(CashRegister.transaction).joinedload(Transaction.article),
            joinedload(CashRegister.contractor),
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
            joinedload(Transaction.cash_point),
            joinedload(Transaction.article),
            joinedload(Transaction.contractor),
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
    if resource in ["accounts_register", "cash_register", "tariff_types"]:
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
    # Аудит: фиксируем автора и время создания документа (п. 2.9).
    audit_document_create(item, _auth.id)
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

        # Автозапуск пересчёта распределения по счёту документа (влияет на регистр
        # взаиморасчётов). Ошибка здесь не откатывает создание самого документа.
        auto_recalculate_writeoffs(db, [item.account_id])

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
    if resource in ["accounts_register", "cash_register", "tariff_types"]:
        raise HTTPException(
            status_code=403,
            detail=f"Редактирование записей в '{resource}' запрещено."
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

    # Аудит: фиксируем автора последнего изменения (п. 2.9).
    audit_document_update(item, _auth.id)

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
        # Изменение прихода/расхода меняет денежный регистр -> пересчитываем распределение.
        auto_recalculate_writeoffs(db, [item.account_id])

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
    if resource in ["accounts_register", "cash_register", "tariff_types"]:
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

    # Для «Приход/Расход» запоминаем счёт до удаления, чтобы после удаления
    # пересчитать распределение (изменение денежного регистра влияет на взаиморасчёты).
    deleted_account_id = item.account_id if resource in ["transactions", "payments"] else None

    db.delete(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Не удалось удалить: запись используется в других таблицах",
        ) from exc

    if deleted_account_id is not None:
        auto_recalculate_writeoffs(db, [deleted_account_id])

    return Response(status_code=204)


# --- РЕГИСТРАЦИЯ СПЕЦИАЛИЗИРОВАННЫХ РОУТЕРОВ (ЭТАП 3) ---
# Специализированные эндпоинты вынесены в пакет `routers` (см. роадмап).
# Они регистрируются ПОСЛЕ создания app, но ДО api_router, чтобы их конкретные пути
# сопоставлялись раньше catch-all generic CRUD (`/{resource}`, `/{resource}/{item_id}`),
# как это было порядком эндпоинтов внутри исходного api_router. auth_router — тем же.
from routers.documents import router as documents_router
from routers.registers import router as registers_router
from routers.receipts import router as receipts_router
from routers.others import router as others_router
from routers.reports import router as reports_router
# Реэкспорт для обратной совместимости: тесты импортируют `build_account_statement` из `app`.
from routers.others import build_account_statement

app.include_router(auth_router)
# Специализированные роутеры включаются РАНЬШЕ api_router, чтобы их конкретные пути
# (напр. /receipt_documents/bulk_delete) сопоставлялись раньше catch-all generic CRUD
# (/{resource}, /{resource}/{item_id}) — как это было внутри исходного api_router.
app.include_router(documents_router)
app.include_router(registers_router)
app.include_router(receipts_router)
app.include_router(others_router)
app.include_router(reports_router)
app.include_router(api_router)
