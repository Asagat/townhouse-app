from fastapi import FastAPI
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
    engine,
)
from sqladmin import Admin, ModelView

app = FastAPI(title="Townhouse ERP System")

# Инициализация админки
# admin = Admin(app, engine)
admin = Admin(app, engine, title="Family Townhouse")
# Принудительная русификация интерфейса для версии 0.23.0
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
            "Reset": "Сбросить",
        }.get(s, s)
    }
)

# --- 1. СПРАВОЧНИКИ ---


class OwnerAdmin(ModelView, model=Owner):
    category = "1. Справочники"
    name_plural = "Владельцы"
    column_list = ["id", "full_name", "phone", "is_active"]  # Используем строки
    column_searchable_list = ["full_name", "phone"]
    icon = "fa-solid fa-user-tie"


class ApartmentAdmin(ModelView, model=Apartment):
    category = "1. Справочники"
    name_plural = "Квартиры"
    column_list = ["id", "apartment_number", "address", "square"]
    icon = "fa-solid fa-building"


class AccountAdmin(ModelView, model=Account):
    category = "1. Справочники"
    name_plural = "Лицевые счета"
    column_list = ["id", "account_number", "account_name", "is_active"]
    icon = "fa-solid fa-file-invoice-dollar"


class TariffTypeAdmin(ModelView, model=TariffType):
    category = "1. Справочники"
    name_plural = "Группы тарифов"
    column_list = ["id", "tariff_type"]
    icon = "fa-solid fa-layer-group"


class ServiceTypeAdmin(ModelView, model=ServiceType):
    category = "1. Справочники"
    name_plural = "Виды услуг"
    column_list = ["id", "services_type"]
    icon = "fa-solid fa-faucet-drip"


class TariffAdmin(ModelView, model=Tariff):
    category = "1. Справочники"
    name_plural = "Тарифы"
    column_list = ["id", "price", "unit", "valid_from"]
    icon = "fa-solid fa-tags"


# --- 2. УЧЕТ ---


class MeterAdmin(ModelView, model=Meter):
    category = "2. Учет"
    name_plural = "Счетчики"
    column_list = ["id", "serial_number", "installed_at"]
    icon = "fa-solid fa-gauge-high"


class MeterReadingAdmin(ModelView, model=MeterReading):
    category = "2. Учет"
    name_plural = "Показания"
    column_list = ["id", "reading_date", "reading"]
    icon = "fa-solid fa-pen-to-square"


# --- 3. ФИНАНСЫ ---


class TransactionAdmin(ModelView, model=Transaction):
    category = "3. Финансы"
    name_plural = "Транзакции"
    column_list = ["id", "transaction_date", "transaction_type", "amount"]
    icon = "fa-solid fa-money-bill-transfer"


class CashPointAdmin(ModelView, model=CashPoint):
    category = "3. Финансы"
    name_plural = "Кассы и Счета"
    column_list = ["id", "name", "point_type"]
    icon = "fa-solid fa-vault"


class AccrualsRegisterAdmin(ModelView, model=AccrualsRegister):
    category = "3. Финансы"
    name_plural = "Реестр начислений"
    column_list = ["id", "accrual_date", "consumption", "amount"]
    icon = "fa-solid fa-calculator"


class AccountsRegisterAdmin(ModelView, model=AccountsRegister):
    category = "3. Финансы"
    name_plural = "Итоговый баланс"
    column_list = ["id", "operation_date", "income", "expense"]
    icon = "fa-solid fa-book"


# Регистрация всех View
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
    return {"status": "Online", "admin_panel": "/admin"}
