import os
from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, Date, TIMESTAMP, Boolean, Enum, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.sql import func
import enum
from dotenv import load_dotenv

# --- Загрузка настроек ---
load_dotenv() # Ищет .env в текущей папке

# Берем URL из окружения, если нет - используем дефолт (для безопасности)
DATABASE_URL = os.getenv("DATABASE_URL")

# pool_pre_ping=True — проверяет соединение перед каждым запросом.
# Если фаервол оборвал сессию, SQLAlchemy прозрачно создаст новую.
engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True,
    pool_recycle=3600  # Пересоздавать соединения каждый час
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- ПЕРЕЧИСЛЕНИЯ (ENUMS) ---
class TransactionTypeEnum(enum.Enum):
    in_cash = "Приход в кассу"
    out_cash = "Расход из кассы"
    in_bank = "Приход в банк"
    out_bank = "Расход из банка"

# --- СПРАВОЧНИКИ ---

class Owner(Base):
    __tablename__ = "owners"
    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(255), nullable=False)
    first_name = Column(String(255), nullable=False)
    last_name = Column(String(255))
    middle_name = Column(String(255))
    contact_info = Column(Text)
    phone = Column(Text)
    email = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    apartments = relationship("Apartment", back_populates="owner")

    def __str__(self):
        return self.full_name

class Apartment(Base):
    __tablename__ = "apartments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("owners.id", ondelete="RESTRICT"))
    apartment_number = Column(Integer, nullable=False, unique=True)
    address = Column(String(255), nullable=False)
    square = Column(Numeric(10, 2), default=0)
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    owner = relationship("Owner", back_populates="apartments")
    accounts = relationship("Account", back_populates="apartment")
    meters = relationship("Meter", back_populates="apartment")

    def __str__(self):
        return f"Кв. №{self.apartment_number}"

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    apartment_id = Column(Integer, ForeignKey("apartments.id", ondelete="RESTRICT"))
    account_number = Column(String(20), nullable=False, unique=True)
    account_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    apartment = relationship("Apartment", back_populates="accounts")

    def __str__(self):
        return f"Л/С {self.account_number} ({self.account_name})"

class CashPoint(Base):
    __tablename__ = "cash_points"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    point_type = Column(String(50), nullable=False) # Касса / Расчетный счет

    def __str__(self):
        return self.name

class TariffType(Base):
    __tablename__ = "tariff_types"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tariff_type = Column(String(255), nullable=False) # Коммунальные, Целевые

    def __str__(self):
        return self.tariff_type

class ServiceType(Base):
    __tablename__ = "services_type"
    id = Column(Integer, primary_key=True, autoincrement=True)
    services_type = Column(String(255), nullable=False) # Свет, Вода, Охрана

    def __str__(self):
        return self.services_type

class Tariff(Base):
    __tablename__ = "tariffs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tariff_type_id = Column(Integer, ForeignKey("tariff_types.id", ondelete="CASCADE"), nullable=False)
    services_type_id = Column(Integer, ForeignKey("services_type.id", ondelete="CASCADE"), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    valid_from = Column(Date, nullable=False)
    unit = Column(String(50))

    def __str__(self):
        return f"{self.price} руб/{self.unit or 'ед'}"

class Meter(Base):
    __tablename__ = "meters"
    id = Column(Integer, primary_key=True, autoincrement=True)
    services_type_id = Column(Integer, ForeignKey("services_type.id", ondelete="CASCADE"), nullable=False)
    apartment_id = Column(Integer, ForeignKey("apartments.id", ondelete="CASCADE"))
    serial_number = Column(String(100), unique=True)
    installed_at = Column(Date)
    
    apartment = relationship("Apartment", back_populates="meters")
    readings = relationship("MeterReading", back_populates="meter")

    def __str__(self):
        return f"Счетчик {self.serial_number}"

# --- ДОКУМЕНТЫ ---

class MeterReading(Base):
    __tablename__ = "meter_readings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    meter_id = Column(Integer, ForeignKey("meters.id", ondelete="CASCADE"))
    reading = Column(Numeric(10, 2), nullable=False)
    reading_date = Column(Date, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    meter = relationship("Meter", back_populates="readings")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_date = Column(TIMESTAMP, server_default=func.now())
    point_type_id = Column(Integer, ForeignKey("cash_points.id", ondelete="RESTRICT"))
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="RESTRICT"))
    transaction_type = Column(Enum(TransactionTypeEnum), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    notes = Column(String(255))

# --- РЕГИСТРЫ ---

class AccrualsRegister(Base):
    __tablename__ = "accruals_register"
    id = Column(Integer, primary_key=True, autoincrement=True)
    accrual_date = Column(Date, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    tariff_id = Column(Integer, ForeignKey("tariffs.id", ondelete="RESTRICT"), nullable=False)
    services_type_id = Column(Integer, ForeignKey("services_type.id"), nullable=False)
    
    current_reading_id = Column(Integer, ForeignKey("meter_readings.id", ondelete="SET NULL"))
    past_reading_value = Column(Numeric(10, 2))
    current_reading_value = Column(Numeric(10, 2))
    
    consumption = Column(Numeric(10, 2), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    notes = Column(String(255))

class AccountsRegister(Base):
    __tablename__ = "accounts_register"
    id = Column(Integer, primary_key=True, autoincrement=True)
    operation_date = Column(Date, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    services_type_id = Column(Integer, ForeignKey("services_type.id", ondelete="CASCADE"), nullable=False)
    transaction_id = Column(Integer, ForeignKey("transactions.id", ondelete="CASCADE"))
    accrual_id = Column(Integer, ForeignKey("accruals_register.id", ondelete="CASCADE"))
    income = Column(Numeric(10, 2), default=0)
    expense = Column(Numeric(10, 2), default=0)
    notes = Column(String(255))

def init_db():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db()
