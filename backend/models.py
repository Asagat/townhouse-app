#/opt/townhouse/backend/models.py

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
    accounts = relationship(
        "Account", back_populates="apartment", passive_deletes=True
    )
    meters = relationship("Meter", back_populates="apartment", passive_deletes=True)
    meter_readings = relationship(
        "MeterReading", back_populates="apartment", passive_deletes=True
    )


class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    apartment_id = Column(Integer, ForeignKey("apartments.id", ondelete="RESTRICT"))
    account_number = Column(String(20), nullable=False, unique=True)
    account_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    apartment = relationship("Apartment", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account", passive_deletes=True)
    accruals = relationship("AccrualsRegister", back_populates="account", passive_deletes=True)
    accounts_register = relationship("AccountsRegister", back_populates="account", passive_deletes=True)


class CashPoint(Base):
    __tablename__ = "cash_points"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)

    transactions = relationship("Transaction", back_populates="cash_point", passive_deletes=True)


class ServiceType(Base):
    __tablename__ = "services_type"
    id = Column(Integer, primary_key=True, autoincrement=True)
    services_type = Column(String(255), nullable=False)

    tariffs = relationship("Tariff", back_populates="services_type", passive_deletes=True)
    meters = relationship("Meter", back_populates="services_type", passive_deletes=True)
    meter_readings = relationship("MeterReading", back_populates="services_type", passive_deletes=True)
    meter_reading_documents = relationship(
        "MeterReadingDocument", back_populates="services_type", passive_deletes=True
    )
    accruals = relationship("AccrualsRegister", back_populates="services_type", passive_deletes=True)


class TariffType(Base):
    __tablename__ = "tariff_types"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)

    tariffs = relationship("Tariff", back_populates="tariff_type", passive_deletes=True)


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

    services_type = relationship("ServiceType", back_populates="tariffs")
    tariff_type = relationship("TariffType", back_populates="tariffs")
    accruals = relationship("AccrualsRegister", back_populates="tariff", passive_deletes=True)


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
    services_type = relationship("ServiceType", back_populates="meters")


# --- ДОКУМЕНТЫ ---


class MeterReadingDocument(Base):
    __tablename__ = "meter_reading_documents"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    reading_date = Column(Date, nullable=False)
    services_type_id = Column(
        Integer, ForeignKey("services_type.id", ondelete="RESTRICT"), nullable=False
    )
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    services_type = relationship("ServiceType", back_populates="meter_reading_documents")
    readings = relationship(
        "MeterReading", back_populates="document", passive_deletes=True
    )


class MeterReading(Base):
    __tablename__ = "meter_readings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        Integer, ForeignKey("meter_reading_documents.id", ondelete="CASCADE")
    )
    apartment_id = Column(Integer, ForeignKey("apartments.id", ondelete="CASCADE"), nullable=False)
    meter_id = Column(Integer, ForeignKey("meters.id", ondelete="CASCADE"))
    services_type_id = Column(
        Integer, ForeignKey("services_type.id", ondelete="RESTRICT"), nullable=False
    )
    reading = Column(Numeric(12, 3), nullable=False)
    reading_date = Column(Date, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    document = relationship("MeterReadingDocument", back_populates="readings")
    apartment = relationship("Apartment", back_populates="meter_readings")
    meter = relationship("Meter", back_populates="readings")
    services_type = relationship("ServiceType", back_populates="meter_readings")
    accruals = relationship("AccrualsRegister", back_populates="current_reading", passive_deletes=True)


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_date = Column(TIMESTAMP, server_default=func.now())
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="RESTRICT"))
    cash_point_id = Column(Integer, ForeignKey("cash_points.id", ondelete="RESTRICT"))
    transaction_type = Column(Enum(TransactionTypeEnum), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    notes = Column(String(255))

    account = relationship("Account", back_populates="transactions")
    cash_point = relationship("CashPoint", back_populates="transactions")
    accounts_register = relationship("AccountsRegister", back_populates="transaction", passive_deletes=True)


# backend/models.py

class AccrualDocument(Base):
    __tablename__ = "accrual_documents"
    id = Column(Integer, primary_key=True, autoincrement=True)
    accrual_date = Column(Date, nullable=False)
    # Название документа начислений; опционально в БД (поле добавлено позже,
    # существующие строки могут хранить NULL), но приложение всегда заполняет его,
    # при отсутствии — авто-генерирует по accrual_date.
    title = Column(String(255), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    accruals = relationship(
        "AccrualsRegister",
        back_populates="accrual_document",
        passive_deletes=True
    )


# --- РЕГИСТРЫ ---


class AccrualsRegister(Base):
    __tablename__ = "accruals_register"
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Ссылка на документ-шапку с каскадным удалением
    accrual_document_id = Column(
        Integer, ForeignKey("accrual_documents.id", ondelete="CASCADE"), nullable=False
    )

    # Добавляем поле даты начисления
    accrual_date = Column(Date, nullable=False)  # <-- ДОБАВИТЬ ЭТУ СТРОКУ

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

    # Связи
    accrual_document = relationship("AccrualDocument", back_populates="accruals")
    account = relationship("Account", back_populates="accruals")
    tariff = relationship("Tariff", back_populates="accruals")
    services_type = relationship("ServiceType", back_populates="accruals")
    current_reading = relationship("MeterReading", back_populates="accruals")
    accounts_register = relationship("AccountsRegister", back_populates="accrual", passive_deletes=True)


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
    # Вид услуги — заполняется для операций начислений (платежи его не имеют),
    # задаётся в момент записи документа начисления в регистр.
    services_type_id = Column(
        Integer, ForeignKey("services_type.id", ondelete="RESTRICT"), nullable=True
    )

    income = Column(Numeric(15, 2), default=0)
    expense = Column(Numeric(15, 2), default=0)
    balance_after = Column(Numeric(15, 2))

    account = relationship("Account", back_populates="accounts_register")
    transaction = relationship("Transaction", back_populates="accounts_register")
    accrual = relationship("AccrualsRegister", back_populates="accounts_register")
    services_type = relationship("ServiceType")


# --- ОБРАБОТЧИКИ ---

from sqlalchemy import event, text
from datetime import datetime


def transaction_income_expense(target) -> tuple[object, object]:
    """Возвращает пару (income, expense) для транзакции."""
    if target.transaction_type in [TransactionTypeEnum.in_cash, TransactionTypeEnum.in_bank]:
        return target.amount, 0
    return 0, target.amount


def recalculate_account_balance(executor, account_id) -> None:
    """
    Полностью пересчитывает balance_after для ВСЕХ записей accounts_register аккаунта
    «с нуля» по истории операций (приходы минус расходы) в хронологическом порядке
    (operation_date, затем id).

    executor — объект с .execute() (Session или Connection), чтобы функцию можно было
    вызывать и из SQLAlchemy-событий (connection), и из бизнес-логики приложения (session).
    """
    executor.execute(
        text("""
            WITH ordered AS (
                SELECT id,
                       SUM(income - expense) OVER (
                           ORDER BY operation_date ASC, id ASC
                       ) AS running
                FROM accounts_register
                WHERE account_id = :account_id
            )
            UPDATE accounts_register ar
            SET balance_after = ordered.running
            FROM ordered
            WHERE ar.id = ordered.id
        """),
        {"account_id": account_id},
    )


def insert_accounts_register_entry(connection, target) -> None:
    """Создаёт запись accounts_register для вставленной транзакции."""
    income, expense = transaction_income_expense(target)
    connection.execute(
        text("INSERT INTO accounts_register (operation_date, account_id, transaction_id, income, expense, balance_after) "
             "VALUES (:operation_date, :account_id, :transaction_id, :income, :expense, :balance_after)"),
        {
            "operation_date": target.transaction_date or datetime.now(),
            "account_id": target.account_id,
            "transaction_id": target.id,
            "income": income,
            "expense": expense,
            # значение пересчитается ниже по всей истории аккаунта
            "balance_after": 0,
        }
    )


def update_accounts_register_entry(connection, target) -> None:
    """Обновляет содержимое записи accounts_register для изменённой транзакции."""
    income, expense = transaction_income_expense(target)
    connection.execute(
        text("UPDATE accounts_register SET operation_date = :operation_date, income = :income, expense = :expense "
             "WHERE transaction_id = :transaction_id"),
        {
            "operation_date": target.transaction_date or datetime.now(),
            "transaction_id": target.id,
            "income": income,
            "expense": expense,
        }
    )


@event.listens_for(Transaction, "after_insert")
def transaction_after_insert(mapper, connection, target):
    insert_accounts_register_entry(connection, target)
    recalculate_account_balance(connection, target.account_id)


@event.listens_for(Transaction, "after_update")
def transaction_after_update(mapper, connection, target):
    # Если строки в accounts_register для этой транзакции нет — создаём (например,
    # транзакцию добавили напрямую в обход события вставки).
    existing = connection.execute(
        text("SELECT 1 FROM accounts_register WHERE transaction_id = :transaction_id"),
        {"transaction_id": target.id},
    ).first()
    if existing:
        update_accounts_register_entry(connection, target)
    else:
        insert_accounts_register_entry(connection, target)
    recalculate_account_balance(connection, target.account_id)


@event.listens_for(Transaction, "after_delete")
def transaction_after_delete(mapper, connection, target):
    # Каскадное удаление accounts_register для этой транзакции выполняется СУБД;
    # пересчитываем балансы оставшихся записей аккаунта.
    recalculate_account_balance(connection, target.account_id)
