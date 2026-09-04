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
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import relationship


# --- ENUMS ---
class TransactionTypeEnum(enum.Enum):
    in_cash = "Приход в кассу"
    out_cash = "Расход из кассы"
    in_bank = "Приход в банк"
    out_bank = "Расход из банка"


class AnalyticKind(enum.Enum):
    income = "Доход"
    expense = "Расход"
    opening = "Входящий остаток"


class UserRole(enum.Enum):
    admin = "Администратор"
    operator = "Оператор"
    cashier = "Кассир"
    controller = "Контролер"
    resident = "Житель"


# --- ПОЛЬЗОВАТЕЛИ ---


class User(Base):
    """Пользователь системы с ролью для доступа к функциям."""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False, unique=True)
    # Соль и хеш пароля (PBKDF2-SHA256), формат: <iterations>$<salt_hex>$<hash_hex>.
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    # Роль хранится строкой (имя члена UserRole, напр. 'admin'), без нативного PG-enum.
    role = Column(Enum(UserRole, native_enum=False), nullable=False, default=UserRole.cashier)
    # Привязка жителя к лицевому счёту (для роли resident / ЛК).
    account_id = Column(
        Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    account = relationship("Account", back_populates="users")


# --- СПРАВОЧНИКИ ---


class Counterparty(Base):
    __tablename__ = "counterparties"
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
    owner_id = Column(Integer, ForeignKey("counterparties.id", ondelete="RESTRICT"))
    apartment_number = Column(Integer, nullable=False, unique=True)
    address = Column(String(255), nullable=False)
    square = Column(Numeric(10, 2), default=0)
    created_at = Column(TIMESTAMP, server_default=func.now())

    owner = relationship("Counterparty", back_populates="apartments")
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
    cash_register = relationship("CashRegister", back_populates="account", passive_deletes=True)
    receipts = relationship("ReceiptDocument", back_populates="account", passive_deletes=True)
    users = relationship("User", back_populates="account", passive_deletes=True)


class CashPoint(Base):
    __tablename__ = "cash_points"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)

    transactions = relationship("Transaction", back_populates="cash_point", passive_deletes=True)


class AnalyticArticle(Base):
    """Аналитика: статьи доходов/расходов для документов «Приход/Расход».

    Единый справочник: статьи типа `kind` (доход/расход) используются в отчётах и
    при разнесении приходов/расходов, в т.ч. по операциям без привязки к
    квартире/л/с (account_id = NULL). Уникальность — по (name, kind); отдельных
    кодов нет (они не нужны для отчётов и только усложняли ввод).
    """
    __tablename__ = "analytic_articles"
    __table_args__ = (
        Index("uq_analytic_articles_name_kind", "name", "kind", unique=True),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    kind = Column(Enum(AnalyticKind, native_enum=False), nullable=False)
    is_active = Column(Boolean, default=True)

    transactions = relationship("Transaction", back_populates="article", passive_deletes=True)


class ServiceType(Base):
    __tablename__ = "services_type"
    id = Column(Integer, primary_key=True, autoincrement=True)
    services_type = Column(String(255), nullable=False)
    # Порядок списания задолженности: меньший номер списывается раньше.
    # NULL/0 — списание в последнюю очередь (после услуг с заданным приоритетом).
    priority = Column(Integer, default=0)

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
    # Примечание/комментарий к тарифу (пояснение, от чего зависит ставка и т.п.).
    comment = Column(String(500))
    # Признак «разового/одноразового» сбора. Регулярные (повторяемые) тарифы
    # участвуют в ежемесячном пересчёте начислений; разовые — только хранят
    # историю (строки начислений ссылаются на них) и в месячный пересчёт НЕ входят
    # (см. calculate_accrual_for_account_service).
    is_oneoff = Column(Boolean, nullable=False, default=False, server_default=text("false"))

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
    # Примечание к документу показаний (заполняется пользователем); наследуется
    # строками «Регистра показаний» как «Примечание».
    comment = Column(String(500))
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Аудит документа (п. 2.9): автор и последнее изменение.
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    change_description = Column(String(500), nullable=True)

    services_type = relationship("ServiceType", back_populates="meter_reading_documents")
    readings = relationship(
        "MeterReading", back_populates="document", passive_deletes=True
    )
    creator = relationship("User", foreign_keys=[created_by], lazy="joined")
    updater = relationship("User", foreign_keys=[updated_by], lazy="joined")


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
    # Сквозной номер документа по хронологии (не совпадает с id). Заполняется при
    # импорте/создании документа; может быть NULL до назначения.
    doc_no = Column(Integer, nullable=True)
    transaction_date = Column(TIMESTAMP, server_default=func.now())
    # Дата создания документа (момент внесения записи) — отдельно от transaction_date,
    # который является «датой документа» (может быть установлена в прошлое).
    created_at = Column(TIMESTAMP, server_default=func.now())
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="RESTRICT"))
    cash_point_id = Column(Integer, ForeignKey("cash_points.id", ondelete="RESTRICT"))
    article_id = Column(
        Integer, ForeignKey("analytic_articles.id", ondelete="SET NULL"), nullable=True
    )
    # Контрагент, связанный с денежной операцией (из справочника «Контрагенты»=
    # owners). Необязательно: операции без конкретного контрагента хранят NULL.
    contractor_id = Column(
        Integer, ForeignKey("counterparties.id", ondelete="RESTRICT"), nullable=True
    )
    transaction_type = Column(Enum(TransactionTypeEnum), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    notes = Column(String(255))
    # Название документа «Приход/Расход», формируется автоматически по формуле
    # «Тип операции + №(ID) + дата операции» в момент создания/изменения.
    title = Column(String(255), nullable=True)

    # Аудит документа (п. 2.9): автор, последнее изменение и что именно изменилось.
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    change_description = Column(String(500), nullable=True)

    account = relationship("Account", back_populates="transactions")
    cash_point = relationship("CashPoint", back_populates="transactions")
    article = relationship("AnalyticArticle", back_populates="transactions")
    contractor = relationship("Counterparty", foreign_keys=[contractor_id])
    accounts_register = relationship("AccountsRegister", back_populates="transaction", passive_deletes=True)
    cash_register = relationship("CashRegister", back_populates="transaction", passive_deletes=True)
    creator = relationship("User", foreign_keys=[created_by], lazy="joined")
    updater = relationship("User", foreign_keys=[updated_by], lazy="joined")


# backend/models.py

class AccrualDocument(Base):
    __tablename__ = "accrual_documents"
    id = Column(Integer, primary_key=True, autoincrement=True)
    accrual_date = Column(Date, nullable=False)
    # Название документа начислений; опционально в БД (поле добавлено позже,
    # существующие строки могут хранить NULL), но приложение всегда заполняет его,
    # при отсутствии — авто-генерирует по accrual_date.
    title = Column(String(255), nullable=True)
    # Тип документа: 'monthly' (регулярное «Начисление за …») или 'oneoff'
    # («Разовые сборы …», «Персональное доначисление …»). Месячный (пере-)расчёт
    # работает только с monthly; one-офф хранит историю и не редактируется месяцев.
    doc_kind = Column(String(20), nullable=False, default="monthly",
                      server_default=text("'monthly'"))
    # Примечание/комментарий к документу начислений (их дописывает бухгалтер).
    comment = Column(String(500))
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Аудит документа (п. 2.9).
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    change_description = Column(String(500), nullable=True)

    accruals = relationship(
        "AccrualsRegister",
        back_populates="accrual_document",
        passive_deletes=True
    )
    creator = relationship("User", foreign_keys=[created_by], lazy="joined")
    updater = relationship("User", foreign_keys=[updated_by], lazy="joined")


# =====================================================================
# КОНВЕНЦИЯ ЗНАКОВ  (источник истины — РОАДМАП «Списание задолженностей»)
# =====================================================================
# Оба регистра используют ОДНУ формулу нарастающего итога:
#     balance_after = SUM(income) - SUM(expense)
# но смысл income/expense у них РАЗНЫЙ:
#
# 1) accounts_register (регистр взаиморасчётов) — «задолженность» жителя:
#    - income  = НАЧИСЛЕНО  (сумма к уплате по счёту/услуге)  -> долг растёт;
#    - expense = СПИСАНО/ОПЛАЧЕНО по счёту/услуге             -> долг падает;
#    balance_after > 0 = ДОЛГ;   balance_after < 0 = ПЕРЕПЛАТА/АВАНС.
#
# 2) cash_register (регистр денежных средств) — «денежный остаток» на счёте/кассе:
#    - income  = реальный приход денег;
#    - expense = реальный расход денег;
#    balance_after = сколько денег числится на счёте (НЕ является долгом).
#
# ДЕЙСТВУЮЩЕЕ ПОВЕДЕНИЕ: конвенция соблюдается с момента формального «переворота
# знаков» (начисления пишутся в income, списание/оплата — в expense в accounts_register;
# документ «Приход/Расход» пишет в cash_register). Квитанции и отчёт трактуют
# положительный balance_after как долг, отрицательный — как переплату.
# =====================================================================


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
    # Ссылка на документ «Списание задолженностей» — строки списания создаются
    # документом списания; удаление документа каскадно удаляет и его строки.
    writeoff_id = Column(
        Integer, ForeignKey("writeoff_documents.id", ondelete="CASCADE"), nullable=True
    )
    # Вид услуги — привязка записи к конкретной услуге. Заполняется для начислений
    # и для записей списания (разнесённых по услугам); записи денежного регистра
    # (см. cash_register, Фаза 1) услугу не имеют.
    services_type_id = Column(
        Integer, ForeignKey("services_type.id", ondelete="RESTRICT"), nullable=True
    )

    # Суммы по ЦЕЛЕВОЙ конвенции (см. блок «КОНВЕНЦИЯ ЗНАКОВ» ниже):
    #   income  = НАЧИСЛЕНО   (долг жителя растёт);
    #   expense = СПИСАНО/ОПЛАЧЕНО (долг жителя падает);
    #   balance_after > 0 = ДОЛГ,  balance_after < 0 = ПЕРЕПЛАТА/АВАНС.
    income = Column(Numeric(15, 2), default=0)
    expense = Column(Numeric(15, 2), default=0)
    balance_after = Column(Numeric(15, 2))

    account = relationship("Account", back_populates="accounts_register")
    transaction = relationship("Transaction", back_populates="accounts_register")
    accrual = relationship("AccrualsRegister", back_populates="accounts_register")
    writeoff = relationship("WriteoffDocument")
    services_type = relationship("ServiceType")


class CashRegister(Base):
    """Регистр денежных средств (история движения денег по лицевому счёту).

    Первичный регистр: заполняется документом «Приход/Расход» (Transaction).
    НЕ является задолженностью жителя — это денежный остаток на счёте/кассе:
    balance_after = SUM(income - expense), где income = реальный приход денег,
    expense = реальный расход. Смысл знаков см. в блоке «КОНВЕНЦИЯ ЗНАКОВ».
    """
    __tablename__ = "cash_register"
    # Индекс для быстрого пересчёта баланса регистра по счёту (ORDER BY operation_date, id).
    __table_args__ = (
        Index("idx_cash_register_account_date", "account_id", "operation_date", "id"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    operation_date = Column(TIMESTAMP, server_default=func.now())
    # account_id может быть NULL — операции «Приход/Расход» без привязки к квартире/л/с
    # попадают в общий денежный регистр (видны в отчёте по кассе и аналитике).
    account_id = Column(
        Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    transaction_id = Column(
        Integer, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    # Контрагент, связанный с операцией (зеркало из шапки «Приход/Расход»),
    # чтобы регистр фильтровался/отчитывался по «Контрагенту» без JOIN и без
    # потери при редактировании шапки (см. событие update_cash_register_entry).
    contractor_id = Column(
        Integer, ForeignKey("counterparties.id", ondelete="RESTRICT"), nullable=True
    )

    income = Column(Numeric(15, 2), default=0)
    expense = Column(Numeric(15, 2), default=0)
    balance_after = Column(Numeric(15, 2))

    account = relationship("Account", back_populates="cash_register")
    transaction = relationship("Transaction", back_populates="cash_register")
    contractor = relationship("Counterparty", foreign_keys=[contractor_id])


# --- ОБРАБОТЧИКИ ---

from sqlalchemy import event, text
from datetime import datetime


def transaction_income_expense(target) -> tuple[object, object]:
    """Возвращает пару (income, expense) для ТРАНЗАКЦИИ (документ «Приход/Расход»).

    Применяется к РЕГИСТРУ ДЕНЕЖНЫХ СРЕДСТВ (cash_register): приход денег -> income,
    расход -> expense. Не используется для accounts_register (задолженности) — туда
    деньги попадают только через операцию списания (Фаза 3). Целевая семантика
    обоих регистров описана в блоке «КОНВЕНЦИЯ ЗНАКОВ» выше.
    """
    if target.transaction_type in [TransactionTypeEnum.in_cash, TransactionTypeEnum.in_bank]:
        return target.amount, 0
    return 0, target.amount


_REGISTER_RUNNING_UPDATE = """
    WITH ordered AS (
        SELECT id,
               SUM(income - expense) OVER (
                   ORDER BY operation_date ASC, id ASC
               ) AS running
        FROM {table}
        WHERE account_id = :account_id
    )
    UPDATE {table} ar
    SET balance_after = ordered.running
    FROM ordered
    WHERE ar.id = ordered.id
"""

# Имена таблиц пересчёта — безопасные программные константы (без пользовательского ввода).
_RECALC_TABLES = ("accounts_register", "cash_register")


def recalculate_register_balance(executor, table: str, account_id) -> None:
    """Пересчитывает balance_after для ВСЕХ записей указанного регистра аккаунта
    «с нуля» по нарастающему итогу (SUM(income - expense)) в хронологическом порядке
    (operation_date, затем id).

    Функция МЕХАНИЧЕСКАЯ — она не знает смысла income/expense (долг или денежный
    остаток — см. блок «КОНВЕНЦИЯ ЗНАКОВ»). Принимает имя таблицы из фиксированного
    набора _RECALC_TABLES (никакой пользовательский ввод в SQL не попадает).

    executor — объект с .execute() (Session или Connection), чтобы функцию можно было
    вызывать и из SQLAlchemy-событий (connection), и из бизнес-логики приложения (session).
    """
    if table not in _RECALC_TABLES:
        raise ValueError(f"Недопустимое имя регистра для пересчёта: {table}")
    executor.execute(
        text(_REGISTER_RUNNING_UPDATE.format(table=table)),
        {"account_id": account_id},
    )


def recalculate_account_balance(executor, account_id) -> None:
    """Пересчитывает balance_after регистра взаиморасчётов (accounts_register).

    Обёртка над recalculate_register_balance для обратной совместимости с вызовами
    в бизнес-логике приложения (create_accounts_register_entries_for_accruals и т.п.).
    """
    recalculate_register_balance(executor, "accounts_register", account_id)


def recalculate_cash_balance(executor, account_id) -> None:
    """Пересчитывает balance_after регистра денежных средств (cash_register)."""
    recalculate_register_balance(executor, "cash_register", account_id)


def insert_cash_register_entry(connection, target) -> None:
    """Создаёт запись cash_register для вставленной транзакции («Приход/Расход»)."""
    income, expense = transaction_income_expense(target)
    connection.execute(
        text("INSERT INTO cash_register (operation_date, account_id, transaction_id, contractor_id, income, expense, balance_after) "
             "VALUES (:operation_date, :account_id, :transaction_id, :contractor_id, :income, :expense, :balance_after)"),
        {
            "operation_date": target.transaction_date or datetime.now(),
            "account_id": target.account_id,
            "transaction_id": target.id,
            "contractor_id": target.contractor_id,
            "income": income,
            "expense": expense,
            # значение пересчитается ниже по всей истории аккаунта
            "balance_after": 0,
        }
    )


def update_cash_register_entry(connection, target) -> None:
    """Обновляет содержимое записи cash_register для изменённой транзакции."""
    income, expense = transaction_income_expense(target)
    connection.execute(
        text("UPDATE cash_register SET operation_date = :operation_date, contractor_id = :contractor_id, income = :income, expense = :expense "
             "WHERE transaction_id = :transaction_id"),
        {
            "operation_date": target.transaction_date or datetime.now(),
            "transaction_id": target.id,
            "contractor_id": target.contractor_id,
            "income": income,
            "expense": expense,
        }
    )


@event.listens_for(Transaction, "after_insert")
def transaction_after_insert(mapper, connection, target):
    insert_cash_register_entry(connection, target)
    recalculate_cash_balance(connection, target.account_id)


@event.listens_for(Transaction, "after_update")
def transaction_after_update(mapper, connection, target):
    # Если строки в cash_register для этой транзакции нет — создаём (например,
    # транзакцию добавили напрямую в обход события вставки).
    existing = connection.execute(
        text("SELECT 1 FROM cash_register WHERE transaction_id = :transaction_id"),
        {"transaction_id": target.id},
    ).first()
    if existing:
        update_cash_register_entry(connection, target)
    else:
        insert_cash_register_entry(connection, target)
    recalculate_cash_balance(connection, target.account_id)


@event.listens_for(Transaction, "after_delete")
def transaction_after_delete(mapper, connection, target):
    # Каскадное удаление cash_register для этой транзакции выполняется СУБД;
    # пересчитываем балансы оставшихся записей аккаунта.
    recalculate_cash_balance(connection, target.account_id)


# --- КВИТАНЦИИ (документ-шапка + строки) ---


class ReceiptDocument(Base):
    """Квитанция — документ-шапка. Хранит реквизиты плательщика и итоги."""
    __tablename__ = "receipt_documents"
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Лицевой счёт, на который выставлена квитанция
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    # Период начисления (месяц/год)
    period_year = Column(Integer, nullable=False)
    period_month = Column(Integer, nullable=False)

    # Снимок реквизитов плательщика на момент формирования (неизменяемый документ)
    apartment_number = Column(Integer)
    address = Column(String(255))
    owner_name = Column(String(255))
    account_number = Column(String(20))

    # Итоги: начислено, долг (положительный), переплата (положительная), к оплате
    total_amount = Column(Numeric(15, 2), default=0)      # сумма начислений
    debt = Column(Numeric(15, 2), default=0)              # задолженность (>=0)
    overpayment = Column(Numeric(15, 2), default=0)       # переплата (>=0)
    payable_amount = Column(Numeric(15, 2), default=0)    # к оплате = total + debt - overpayment

    issued_at = Column(TIMESTAMP, server_default=func.now())
    # Дата создания записи о квитанции (момент внесения в БД), отдельно от `issued_at`
    # (момент выставления квитанции), чтобы даты документа и создания были различимы.
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Аудит документа (п. 2.9).
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    change_description = Column(String(500), nullable=True)

    account = relationship("Account", back_populates="receipts")
    items = relationship("ReceiptItem", back_populates="receipt", passive_deletes=True)
    creator = relationship("User", foreign_keys=[created_by], lazy="joined")
    updater = relationship("User", foreign_keys=[updated_by], lazy="joined")


class ReceiptItem(Base):
    """Строка квитанции: вид услуги, показания, тариф, сумма. Долг/переплату садим на «Фонд развития»."""
    __tablename__ = "receipt_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    receipt_id = Column(Integer, ForeignKey("receipt_documents.id", ondelete="CASCADE"), nullable=False)

    services_type_id = Column(Integer, ForeignKey("services_type.id", ondelete="RESTRICT"))
    service_name = Column(String(255), nullable=False)

    reading_prev = Column(Numeric(12, 3))   # показание предыдущее (может быть NULL)
    reading_curr = Column(Numeric(12, 3))   # показание последнее (может быть NULL)
    quantity = Column(Numeric(12, 3), default=0)  # потребление (для счётчика) или 1 (фикс.)
    tariff = Column(Numeric(15, 2), default=0)
    amount = Column(Numeric(15, 2), default=0)    # сумма по строке

    debt = Column(Numeric(15, 2), default=0)            # долг по строке (>=0)
    overpayment = Column(Numeric(15, 2), default=0)     # переплата по строке (>=0)
    payable = Column(Numeric(15, 2), default=0)         # к оплате по строке = amount + debt - overpayment

    receipt = relationship("ReceiptDocument", back_populates="items")
    services_type = relationship("ServiceType")


class WriteoffDocument(Base):
    """Документ «Списание задолженностей» — шапка.

    Создаётся при распределении доступных средств счетов по видам услуг в порядке
    приоритета. Объединяет строки списания (WriteoffItem) для всех затронутых счетов
    и даёт операции списания атрибуты документа (дата, № в журнале, автор, статус),
    а также возможность отмены/пересоздания (п. 2.5 роадмапа).
    """
    __tablename__ = "writeoff_documents"
    id = Column(Integer, primary_key=True, autoincrement=True)
    writeoff_date = Column(Date, nullable=False)
    title = Column(String(255), nullable=True)
    # Статус: new / cancelled. При отмене строки списания из accounts_register
    # удаляются каскадом (AccountsRegister.writeoff_id), а запись в журнале остаётся.
    status = Column(String(20), nullable=False, default="new")
    # Автор операции (связь с 2.9 «аудит документов»).
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    change_description = Column(String(500), nullable=True)

    items = relationship("WriteoffItem", back_populates="document", passive_deletes=True)
    creator = relationship("User", foreign_keys=[created_by], lazy="joined")
    updater = relationship("User", foreign_keys=[updated_by], lazy="joined")


class WriteoffItem(Base):
    """Строка документа «Списание задолженностей»: распределение по (счёт, услуга)."""
    __tablename__ = "writeoff_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        Integer, ForeignKey("writeoff_documents.id", ondelete="CASCADE"), nullable=False
    )
    account_id = Column(
        Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    services_type_id = Column(
        Integer, ForeignKey("services_type.id", ondelete="RESTRICT"), nullable=False
    )
    allocated = Column(Numeric(15, 2), nullable=False)  # списано по этой услуге
    balance_after = Column(Numeric(15, 2))              # баланс счёта после списания

    document = relationship("WriteoffDocument", back_populates="items")
    account = relationship("Account")
    services_type = relationship("ServiceType")
