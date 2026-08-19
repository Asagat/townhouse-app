import enum
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

# Импортируем подключение к базе
# Убедись, что в database.py есть функция get_db и объект SessionLocal
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
from sqlalchemy.orm import Session

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


@api_router.get("/")
def api_index():
    return {"status": "API is Online"}


# Словарь сопоставления имен ресурсов и моделей (соответствует разделам админ-панели)
MODEL_MAP = {
    # 1. Основные
    "owners": Owner,
    "apartments": Apartment,
    "accounts": Account,
    # 3. Учет
    "cash_points": CashPoint,
    "transactions": Transaction,
    "payments": Transaction,  # алиас: платежи/транзакции = денежные операции
    "accruals_register": AccrualsRegister,
    "accounts_register": AccountsRegister,
    # 2. Справочники
    "service_types": ServiceType,
    "tariff_types": TariffType,
    "tariffs": Tariff,
    "meters": Meter,
    "meter_readings": MeterReading,
}


def default_serializer(item) -> dict:
    """Сериализация по умолчанию: ФИО/Номер/Название + телефон."""
    name_val = (
        getattr(item, "full_name", None)
        or getattr(item, "number", None)
        or getattr(item, "name", None)
        or "—"
    )
    return {"id": item.id, "full_name": name_val, "phone": getattr(item, "phone", "—")}


def make_serializer(fields: list[str]):
    """Фабрика сериализаторов: возвращает id + указанные поля с приведением
    Decimal/date/datetime/Enum к JSON-совместимым типам.
    """

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


def meter_reading_serializer(item: MeterReading) -> dict:
    """Показания вводятся по квартире + виду услуги, поэтому apartment_id
    выводится из связанного счётчика (он не хранится напрямую в таблице).
    Также добавляет meter_label — серийный номер фактически использованного счётчика,
    чтобы было видно, какой именно счётчик был автоматически подобран.
    """
    meter = item.meter
    return {
        "id": item.id,
        "apartment_id": meter.apartment_id if meter else None,
        "services_type_id": item.services_type_id,
        "reading": float(item.reading) if item.reading is not None else None,
        "reading_date": item.reading_date.isoformat() if item.reading_date else None,
        "meter_id": item.meter_id,
        "meter_label": meter.serial_number if meter else None,
    }


def transaction_serializer(item: Transaction) -> dict:
    """Транзакции вводятся по квартире, поэтому apartment_id выводится
    из связанного лицевого счёта (он не хранится напрямую в таблице).
    Также добавляет account_label — номер фактически использованного лицевого счёта,
    чтобы было видно, какой именно счёт был автоматически подобран.
    """
    account = item.account
    return {
        "id": item.id,
        "apartment_id": account.apartment_id if account else None,
        "cash_point_id": item.cash_point_id,
        "transaction_type": item.transaction_type.value if item.transaction_type else None,
        "amount": float(item.amount) if item.amount is not None else None,
        "transaction_date": item.transaction_date.isoformat()
        if item.transaction_date
        else None,
        "notes": item.notes,
        "account_id": item.account_id,
        "account_label": account.account_number if account else None,
    }


# Кастомные сериализаторы по моделям (иначе используется default_serializer)
# Важно: набор полей здесь должен совпадать с FIELD_CONFIG ниже —
# именно эти данные подставляются в форму редактирования на фронтенде.
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
    Apartment: make_serializer(["apartment_number", "address", "square", "owner_id"]),
    Account: make_serializer(
        ["account_number", "account_name", "is_active", "apartment_id"]
    ),
    CashPoint: make_serializer(["name", "is_active"]),
    Transaction: transaction_serializer,
    ServiceType: make_serializer(["services_type"]),
    TariffType: make_serializer(["name"]),
    Tariff: make_serializer(
        ["services_type_id", "tariff_type_id", "price", "valid_from", "unit"]
    ),
    Meter: make_serializer(
        ["serial_number", "apartment_id", "services_type_id", "installed_at"]
    ),
    MeterReading: meter_reading_serializer,
    AccrualsRegister: make_serializer(
        [
            "accrual_date",
            "account_id",
            "tariff_id",
            "services_type_id",
            "consumption",
            "amount",
        ]
    ),
    AccountsRegister: make_serializer(
        ["operation_date", "account_id", "income", "expense", "balance_after"]
    ),
}


# --- МЕТАДАННЫЕ О ПОЛЯХ (для динамической формы на фронтенде) ---
# Каждое поле описывает: имя атрибута, подпись, тип ввода,
# обязательность и, для связей/перечислений, дополнительные данные.
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
        # Лицевой счёт не выбирается напрямую: по квартире сервер сам находит
        # последний зарегистрированный лицевой счёт (см. resolve_transaction_values)
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
        # Счётчик не выбирается напрямую: по квартире + виду услуги
        # сервер сам находит последний зарегистрированный счётчик (см. resolve_meter_reading_values)
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
    """Преобразует значение из JSON-запроса в тип, подходящий для колонки SQLAlchemy."""
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


# --- ДРУЖЕЛЮБНЫЕ НАЗВАНИЯ ДЛЯ ПОЛЕЙ-ССЫЛОК (FK) В ТАБЛИЦАХ/ФОРМАХ ---
# Как подписать запись справочника, если на неё ссылаются через reference-поле
REFERENCE_LABEL_BUILDERS: dict[str, Any] = {
    "owners": lambda row: row.get("full_name") or f"#{row['id']}",
    "apartments": lambda row: f"№ {row.get('apartment_number')} — {row.get('address')}",
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
    """Для каждого reference-поля добавляет в строку '{имя_поля}_label'
    с человечески понятным названием связанной записи вместо голого ID.
    Запросы батчатся по id, чтобы избежать N+1.
    """
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
    """Находит ближайшее предыдущее (по дате, затем по id) показание того же
    счётчика — с ним сравнивается новое значение, чтобы не допустить убывания.
    """
    query = db.query(MeterReading).filter(
        MeterReading.meter_id == meter_id,
        MeterReading.reading_date <= reading_date_value,
    )
    if exclude_id is not None:
        query = query.filter(MeterReading.id != exclude_id)
    return query.order_by(
        MeterReading.reading_date.desc(), MeterReading.id.desc()
    ).first()


# --- АВТОПОДБОР СЧЁТЧИКА ДЛЯ ПОКАЗАНИЙ (квартира + вид услуги -> счётчик) ---
def resolve_meter_reading_values(
    db: Session, payload: dict[str, Any], exclude_id: int | None = None
) -> dict[str, Any]:
    """Пользователь вводит квартиру и вид услуги — а не счётчик напрямую.
    Здесь мы находим последний (по дате установки) зарегистрированный счётчик
    для этой квартиры и этого вида услуги и привязываем к нему показание.
    Также проверяем, что новое показание не меньше предыдущего по этому счётчику.
    Параметр exclude_id используется при редактировании, чтобы запись
    не сравнивалась сама с собой.
    """
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


# --- АВТОПОДБОР ЛИЦЕВОГО СЧЁТА ДЛЯ ТРАНЗАКЦИЙ (квартира -> лицевой счёт) ---
def resolve_transaction_values(
    db: Session, payload: dict[str, Any], exclude_id: int | None = None
) -> dict[str, Any]:
    """Пользователь выбирает квартиру, а не лицевой счёт напрямую.
    Здесь мы находим последний (по дате создания) зарегистрированный лицевой
    счёт для этой квартиры и привязываем к нему транзакцию. exclude_id здесь
    не используется (принят, чтобы сигнатура совпадала с остальными билдерами),
    но оставлен для единообразия вызова из create/update.
    """
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


# Ресурсы, для которых payload из формы не напрямую маппится на поля модели
# (нужна дополнительная бизнес-логика перед сохранением)
CUSTOM_VALUE_BUILDERS: dict[str, Any] = {
    "meter_readings": resolve_meter_reading_values,
    "transactions": resolve_transaction_values,
    "payments": resolve_transaction_values,
}


@api_router.get("/meta/{resource}")
async def get_resource_meta(resource: str):
    """Описание полей ресурса для построения динамической формы на фронтенде."""
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
    """
    Универсальный эндпоинт списка: /api/owners, /api/apartments, /api/payments и т.д.
    Поддерживает пагинацию (_start/_end) и сортировку (_sort/_order),
    как ожидает @refinedev/simple-rest.
    """
    model = MODEL_MAP.get(resource)
    if not model:
        raise HTTPException(status_code=404, detail="Resource not found")

    query = db.query(model)
    total = query.count()

    if _sort and hasattr(model, _sort):
        column = getattr(model, _sort)
        query = query.order_by(
            column.desc() if (_order or "").lower() == "desc" else column.asc()
        )

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
    """Отдаёт одну запись по id (для формы редактирования)."""
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
    """Массовый ввод показаний: один вид услуги и одна дата на всю партию,
    построчно — квартира + показание. Пустые строки (квартиры, которые
    оператор не заполнял) пропускаются. Ошибки по отдельным квартирам
    (например, нет зарегистрированного счётчика) не блокируют остальные строки.
    """
    services_type_id = payload.get("services_type_id")
    reading_date = payload.get("reading_date") or date.today().isoformat()
    entries = payload.get("entries") or []

    if services_type_id in (None, ""):
        raise HTTPException(status_code=422, detail="Укажите вид услуги")
    if not isinstance(entries, list) or not entries:
        raise HTTPException(
            status_code=422, detail="Нет ни одной заполненной строки с показаниями"
        )

    # Проход 1: разрешаем каждую строку (только SELECT), ничего ещё не пишем
    to_create: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for entry in entries:
        apartment_id = entry.get("apartment_id")
        reading = entry.get("reading")
        if reading in (None, ""):
            continue  # квартиру не показывали в этом обходе — пропускаем

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

    # Проход 2: пишем одним батчем только те, что успешно прошли валидацию
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
    """Создаёт новую запись в ресурсе (кнопка «Добавить»)."""
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
    """Обновляет запись в ресурсе (кнопка «Редактировать»)."""
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
    """Удаляет запись из ресурса (кнопка «Удалить»)."""
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


# Подключаем API роутер к основному приложению
app.include_router(api_router)

# --- НАСТРОЙКА АДМИН-ПАНЕЛИ ---
admin = Admin(app, engine, title="Family Townhouse")

# Переводы и настройки админки
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


# --- ОПРЕДЕЛЕНИЕ ПРЕДСТАВЛЕНИЙ (VIEWS) ---
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
    column_list = ["id", "accrual_date", "amount"]
    icon = "fa-solid fa-calculator"


class AccountsRegisterAdmin(ModelView, model=AccountsRegister):
    category = "3. Учет"
    name_plural = "Регистр взаиморасчетов"
    column_list = ["id", "operation_date", "income", "expense"]
    icon = "fa-solid fa-book"


# Регистрация представлений в админке
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


# Корневой эндпоинт приложения (вне /api)
@app.get("/")
def index():
    return {"status": "Online", "admin_panel": "/admin", "api_v1": "/api"}
