import enum

from database import Base
from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Column,
    Date,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship


# --- ENUMS ---
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

    # passive_deletes=True: не подгружать/обнулять связанные квартиры в ORM при удалении владельца,
    # а положиться на реальное ограничение ondelete="RESTRICT" в БД
    apartments = relationship(
        "Apartment", back_populates="owner", passive_deletes=True
    )


class Apartment(Base):
    __tablename__ = "apartments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("owners.id", ondelete="RESTRICT"))
    apartment_number = Column(Integer, nullable=False, unique=True)
    address = Column(String(255), nullable=False)
    square = Column(Numeric(10, 2), default=0)
    created_at = Column(TIMESTAMP, server_default=func.now())

    owner = relationship("Owner", back_populates="apartments")
    # passive_deletes=True: доверяем БД самой применить ondelete (RESTRICT/CASCADE),
    # вместо того чтобы SQLAlchemy предварительно обнуляла FK у дочерних записей
    accounts = relationship(
        "Account", back_populates="apartment", passive_deletes=True
    )
    meters = relationship("Meter", back_populates="apartment", passive_deletes=True)


class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    apartment_id = Column(Integer, ForeignKey("apartments.id", ondelete="RESTRICT"))
    account_number = Column(String(20), nullable=False, unique=True)
    account_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    apartment = relationship("Apartment", back_populates="accounts")


class CashPoint(Base):
    __tablename__ = "cash_points"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)  # Касса №1, Счет в банке
    is_active = Column(Boolean, default=True)


class ServiceType(Base):
    __tablename__ = "services_type"
    id = Column(Integer, primary_key=True, autoincrement=True)
    services_type = Column(String(255), nullable=False)


class TariffType(Base):
    __tablename__ = "tariff_types"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)


class Tariff(Base):
    __tablename__ = "tariffs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    services_type_id = Column(
        Integer, ForeignKey("services_type.id", ondelete="RESTRICT"), nullable=False
    )
    tariff_type_id = Column(
        Integer, ForeignKey("tariff_types.id", ondelete="RESTRICT"), nullable=False
    )
    price = Column(Numeric(15, 2), nullable=False)
    valid_from = Column(Date, nullable=False)
    unit = Column(String(50))


class Meter(Base):
    __tablename__ = "meters"
    id = Column(Integer, primary_key=True, autoincrement=True)
    services_type_id = Column(
        Integer, ForeignKey("services_type.id", ondelete="RESTRICT"), nullable=False
    )
    apartment_id = Column(Integer, ForeignKey("apartments.id", ondelete="CASCADE"))
    serial_number = Column(String(100), unique=True)
    installed_at = Column(Date)

    readings = relationship(
        "MeterReading", back_populates="meter", passive_deletes=True
    )
    apartment = relationship("Apartment", back_populates="meters")


# --- ДОКУМЕНТЫ ---


class MeterReading(Base):
    __tablename__ = "meter_readings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    meter_id = Column(Integer, ForeignKey("meters.id", ondelete="CASCADE"))
    # Денормализовано: вид услуги также хранится напрямую на показании,
    # чтобы форма могла автоматически найти нужный счётчик по квартире + виду услуги
    services_type_id = Column(
        Integer, ForeignKey("services_type.id", ondelete="RESTRICT"), nullable=False
    )
    reading = Column(Numeric(12, 3), nullable=False)
    reading_date = Column(Date, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    meter = relationship("Meter", back_populates="readings")


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_date = Column(TIMESTAMP, server_default=func.now())
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="RESTRICT"))
    cash_point_id = Column(Integer, ForeignKey("cash_points.id", ondelete="RESTRICT"))
    transaction_type = Column(Enum(TransactionTypeEnum), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    notes = Column(String(255))

    # Однонаправленная связь для вывода квартиры в списке/форме (через account.apartment_id)
    account = relationship("Account")


# --- РЕГИСТРЫ ---


class AccrualsRegister(Base):
    __tablename__ = "accruals_register"
    id = Column(Integer, primary_key=True, autoincrement=True)
    accrual_date = Column(Date, nullable=False)
    account_id = Column(
        Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    tariff_id = Column(
        Integer, ForeignKey("tariffs.id", ondelete="RESTRICT"), nullable=False
    )
    services_type_id = Column(
        Integer, ForeignKey("services_type.id", ondelete="RESTRICT"), nullable=False
    )

    current_reading_id = Column(
        Integer, ForeignKey("meter_readings.id", ondelete="SET NULL")
    )
    past_reading_value = Column(Numeric(12, 3))
    current_reading_value = Column(Numeric(12, 3))

    consumption = Column(Numeric(12, 3), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)


class AccountsRegister(Base):
    __tablename__ = "accounts_register"
    id = Column(Integer, primary_key=True, autoincrement=True)
    operation_date = Column(TIMESTAMP, server_default=func.now())
    account_id = Column(
        Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )

    transaction_id = Column(
        Integer, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=True
    )
    accrual_id = Column(
        Integer, ForeignKey("accruals_register.id", ondelete="CASCADE"), nullable=True
    )

    income = Column(Numeric(15, 2), default=0)
    expense = Column(Numeric(15, 2), default=0)
    balance_after = Column(Numeric(15, 2))


# --- ОБРАБОТЧИКИ ---

from sqlalchemy import event, text
from datetime import datetime

# --- ОБРАБОТЧИКИ СОБЫТИЙ ДЛЯ АВТОМАТИЧЕСКОГО СОЗДАНИЯ/УДАЛЕНИЯ ЗАПИСЕЙ В РЕГИСТРЕ ---

@event.listens_for(Transaction, "after_insert")
def create_accounts_register_entry(mapper, connection, target):
    """
    Создает запись в регистре взаиморасчетов после создания транзакции
    """
    # Получаем последний баланс для этого аккаунта
    result = connection.execute(
        text("SELECT balance_after FROM accounts_register WHERE account_id = :account_id ORDER BY operation_date DESC, id DESC LIMIT 1"),
        {"account_id": target.account_id}
    ).scalar()

    previous_balance = result if result is not None else 0

    income = 0
    expense = 0
    if target.transaction_type in [TransactionTypeEnum.in_cash, TransactionTypeEnum.in_bank]:
        income = target.amount
    else:
        expense = target.amount

    new_balance = previous_balance + income - expense

    connection.execute(
        text("INSERT INTO accounts_register (operation_date, account_id, transaction_id, income, expense, balance_after) VALUES (:operation_date, :account_id, :transaction_id, :income, :expense, :balance_after)"),
        {
            "operation_date": target.transaction_date or datetime.now(),
            "account_id": target.account_id,
            "transaction_id": target.id,
            "income": income,
            "expense": expense,
            "balance_after": new_balance
        }
    )


@event.listens_for(Transaction, "after_delete")
def delete_accounts_register_entry(mapper, connection, target):
    """Удаляет запись из регистра взаиморасчетов при удалении транзакции"""
    connection.execute(
        text("DELETE FROM accounts_register WHERE transaction_id = :transaction_id"),
        {"transaction_id": target.id}
    )


@event.listens_for(Transaction, "after_update")
def update_accounts_register_entry(mapper, connection, target):
    """При обновлении транзакции пересчитываем запись в регистре"""
    # Проверяем, есть ли запись в регистре для этой транзакции
    old_entry = connection.execute(
        text("SELECT id FROM accounts_register WHERE transaction_id = :transaction_id"),
        {"transaction_id": target.id}
    ).first()

    if not old_entry:
        create_accounts_register_entry(mapper, connection, target)
        return

    # Удаляем старую запись
    connection.execute(
        text("DELETE FROM accounts_register WHERE transaction_id = :transaction_id"),
        {"transaction_id": target.id}
    )

    # Получаем баланс до этой транзакции
    previous_balance_result = connection.execute(
        text("SELECT balance_after FROM accounts_register WHERE account_id = :account_id ORDER BY operation_date DESC, id DESC LIMIT 1"),
        {"account_id": target.account_id}
    ).scalar()

    previous_balance = previous_balance_result if previous_balance_result is not None else 0

    income = 0
    expense = 0
    if target.transaction_type in [TransactionTypeEnum.in_cash, TransactionTypeEnum.in_bank]:
        income = target.amount
    else:
        expense = target.amount

    new_balance = previous_balance + income - expense

    # Создаем новую запись в регистре
    connection.execute(
        text("INSERT INTO accounts_register (operation_date, account_id, transaction_id, income, expense, balance_after) VALUES (:operation_date, :account_id, :transaction_id, :income, :expense, :balance_after)"),
        {
            "operation_date": target.transaction_date or datetime.now(),
            "account_id": target.account_id,
            "transaction_id": target.id,
            "income": income,
            "expense": expense,
            "balance_after": new_balance
        }
    )
