# Импортируем подключение к базе
# Убедись, что в database.py есть функция get_db и объект SessionLocal
from database import engine, get_db
from fastapi import APIRouter, Depends, FastAPI, HTTPException
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
)
from sqladmin import Admin, ModelView
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
)

# --- НАСТРОЙКА API РОУТЕРА ---
api_router = APIRouter(prefix="/api")


@api_router.get("/")
def api_index():
    return {"status": "API is Online"}


# Словарь сопоставления имен ресурсов и моделей
MODEL_MAP = {
    "owners": Owner,
    "houses": Apartment,  # У тебя в коде ApartmentAdmin используется для домов
    "flats": Apartment,  # Если квартиры тоже там
    "accounts": Account,
    "transactions": Transaction,
}


@api_router.get("/{resource}")
async def get_resource(resource: str, db: Session = Depends(get_db)):
    """
    Универсальный эндпоинт: /api/owners, /api/houses и т.д.
    """
    model = MODEL_MAP.get(resource)
    if not model:
        raise HTTPException(status_code=404, detail="Resource not found")

    items = db.query(model).all()

    # Универсальная конвертация в JSON
    result = []
    for item in items:
        # Пытаемся найти ФИО или Номер или Название для колонки "ФИО/Наименование"
        name_val = (
            getattr(item, "full_name", None)
            or getattr(item, "number", None)
            or getattr(item, "name", None)
            or "—"
        )

        result.append(
            {"id": item.id, "full_name": name_val, "phone": getattr(item, "phone", "—")}
        )

    return result


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
