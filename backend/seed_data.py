from datetime import date

from database import SessionLocal
from models import Apartment, Meter, Owner, ServiceType


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

        db.commit()
        print("✅ Тестовые данные успешно загружены!")
    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка при заполнении: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
