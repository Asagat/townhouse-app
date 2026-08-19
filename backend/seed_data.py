from datetime import date

from database import SessionLocal
from models import (
    Account,
    Apartment,
    CashPoint,
    Meter,
    Owner,
    ServiceType,
    Transaction,
    TransactionTypeEnum,
)


def seed():
    db = SessionLocal()
    try:
        # 1. Создаем Владельца
        owner = Owner(
            full_name="Arman Sagat",
            first_name="Arman",
            last_name="Sagat",
            phone="+77001234567",
            is_active=True,
        )
        db.add(owner)
        db.flush()

        # 2. Создаем Квартиру
        apt = Apartment(
            apartment_number=101,
            address="Zhibek Zholy 15",
            square=120.5,
            owner_id=owner.id,
        )
        db.add(apt)
        db.flush()

        # 3. Создаем Тип услуги (теперь с правильным полем services_type)
        service = ServiceType(services_type="Холодная вода")
        db.add(service)
        db.flush()

        # 4. Создаем Счетчик
        meter = Meter(
            serial_number="W-100200",
            apartment_id=apt.id,
            services_type_id=service.id,
            installed_at=date.today(),
        )
        db.add(meter)

        # 5. Создаем Лицевой счёт
        account = Account(
            apartment_id=apt.id,
            account_number="LS-000101",
            account_name="Лицевой счёт кв. 101",
            is_active=True,
        )
        db.add(account)
        db.flush()

        # 6. Создаем Кассу
        cash_point = CashPoint(name="Касса №1", is_active=True)
        db.add(cash_point)
        db.flush()

        # 7. Создаем тестовую Транзакцию (платёж)
        transaction = Transaction(
            account_id=account.id,
            cash_point_id=cash_point.id,
            transaction_type=TransactionTypeEnum.in_cash,
            amount=15000,
            notes="Оплата за коммунальные услуги",
        )
        db.add(transaction)

        db.commit()
        print("✅ Тестовые данные успешно загружены!")
    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка при заполнении: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
