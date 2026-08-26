# tests/test_writeoffs.py

"""
Тесты операции «Списание задолженностей» и связанных регистров.

Покрывают:
  - Фаза 1: документ «Приход/Расход» пишет в cash_register, а не во взаиморасчёты;
  - Фаза 2: распределение денег по услугам в порядке приоритета (0 — в последнюю
            очередь), идемпотентность повторного списания;
  - Фаза 4: отчёт по лицевому счёту (начислено/оплачено/долг/переплата).
"""

from models import Account, AccountsRegister, CashRegister, Transaction, TransactionTypeEnum
from sqlalchemy import text

from writeoffs import calculate_write_offs
from app import build_account_statement


def _count(db, table: str, account_id: int) -> int:
    return db.execute(text(f"SELECT count(*) FROM {table} WHERE account_id = :a"), {"a": account_id}).scalar()


def _accrual(db, account_id: int, svc_id: int, amount):
    """Добавляет строку начисления (income) в accounts_register по услуге.

    По целевой конвенции начисление хранится в income (долг растёт).
    """
    db.execute(
        text("INSERT INTO accounts_register (account_id, services_type_id, income, expense, balance_after) "
             "VALUES (:a, :s, :amt, 0, 0)"),
        {"a": account_id, "s": svc_id, "amt": amount},
    )


def _payment(db, account_id: int, cash_point_id: int, amount) -> int:
    """Создаёт документ «Приход/Расход» (приход в кассу). Возвращает transaction_id."""
    t = Transaction(
        account_id=account_id,
        cash_point_id=cash_point_id,
        transaction_type=TransactionTypeEnum.in_cash,
        amount=amount,
    )
    db.add(t)
    db.flush()
    db.commit()
    return t.id


# --- Фаза 1: Приход/Расход -> cash_register, а не accounts_register ---


def test_payment_writes_cash_register_not_accounts_register(db, account_factory):
    rec = account_factory("w0")
    tx_id = _payment(db, rec["account_id"], rec["cash_point_id"], 1000)

    cash = db.query(CashRegister).filter(CashRegister.transaction_id == tx_id).first()
    assert cash is not None
    assert float(cash.income) == 1000.0
    assert float(cash.expense) == 0.0

    # В регистр взаиморасчётов документ «Приход/Расход» напрямую НЕ пишет.
    assert _count(db, "accounts_register", rec["account_id"]) == 0


def test_payment_update_recalculates_cash_balance(db, account_factory):
    rec = account_factory("w1")
    tx_id = _payment(db, rec["account_id"], rec["cash_point_id"], 500)
    t = db.get(Transaction, tx_id)
    t.amount = 700
    db.add(t)
    db.commit()

    rows = db.query(CashRegister).filter(CashRegister.account_id == rec["account_id"]).order_by(CashRegister.id).all()
    assert len(rows) == 1
    assert float(rows[0].income) == 700.0
    assert float(rows[0].balance_after) == 700.0


def test_payment_delete_cascades_cash_register(db, account_factory):
    rec = account_factory("w2")
    tx_id = _payment(db, rec["account_id"], rec["cash_point_id"], 300)
    t = db.get(Transaction, tx_id)
    db.delete(t)
    db.commit()
    assert _count(db, "cash_register", rec["account_id"]) == 0


# --- Фаза 2: приоритет списания и идемпотентность ---


def test_write_offs_respects_priority(db, account_factory):
    rec = account_factory("p0")
    # Начисления: Электричество(1, prio1)=1000, Холодная вода(3, prio2)=500, Фонд развития(7, prio0)=200
    # Всего долг 1700; доступно денег 1200.
    _accrual(db, rec["account_id"], 1, 1000)
    _accrual(db, rec["account_id"], 3, 500)
    _accrual(db, rec["account_id"], 7, 200)
    db.commit()
    _payment(db, rec["account_id"], rec["cash_point_id"], 1200)

    result = calculate_write_offs(db, [rec["account_id"]])
    db.commit()

    assert result["processed"][0]["written_off"] == 1200.0
    for svc_id, expected in ((1, 1000.0), (3, 200.0)):
        assert any(a["services_type_id"] == svc_id and a["allocated"] == expected
                   for a in result["processed"][0]["allocations"])
    # Фонд развития (приоритет 0) — НЕ должен получить ничего, т.к. деньги кончились.
    assert not any(a["services_type_id"] == 7 for a in result["processed"][0]["allocations"])


def test_write_offs_idempotent(db, account_factory):
    rec = account_factory("id0")
    _accrual(db, rec["account_id"], 1, 1000)
    db.commit()
    _payment(db, rec["account_id"], rec["cash_point_id"], 600)

    calculate_write_offs(db, [rec["account_id"]])
    db.commit()
    after_first = _count(db, "accounts_register", rec["account_id"])

    calculate_write_offs(db, [rec["account_id"]])
    db.commit()
    after_second = _count(db, "accounts_register", rec["account_id"])

    # Повторный запуск не накапливает строки (не задваивается).
    assert after_first == after_second == 2  # 1 начисление + 1 списание

    # По целевой конвенции: начисление в income, списание в expense.
    expense_sum = db.execute(
        text("SELECT COALESCE(SUM(expense),0) FROM accounts_register WHERE account_id=:a"),
        {"a": rec["account_id"]},
    ).scalar()
    assert float(expense_sum) == 600.0
    # Остаток по услуге = income(начислено) - expense(списано) = 1000 - 600 = 400 (долг).
    balance = db.execute(
        text("SELECT balance_after FROM accounts_register WHERE account_id=:a "
             "ORDER BY operation_date DESC, id DESC LIMIT 1"),
        {"a": rec["account_id"]},
    ).scalar()
    assert float(balance) == 400.0  # положительный = долг, по целевой конвенции


def test_write_offs_overpayment_stays_negative_balance(db, account_factory):
    rec = account_factory("op0")
    _accrual(db, rec["account_id"], 1, 1000)
    db.commit()
    _payment(db, rec["account_id"], rec["cash_point_id"], 1500)  # больше, чем долг

    calculate_write_offs(db, [rec["account_id"]])
    db.commit()

    # Переплата не порождает фиктивных строк: только 1 начисление + 1 списание.
    assert _count(db, "accounts_register", rec["account_id"]) == 2
    # Списано только начисленное (1000) — списание в expense.
    expense_sum = db.execute(
        text("SELECT COALESCE(SUM(expense),0) FROM accounts_register WHERE account_id=:a"),
        {"a": rec["account_id"]},
    ).scalar()
    assert float(expense_sum) == 1000.0

    # Переплата = внесено 1500 - распределено по услугам 1000 = 500.
    # Она остаётся «висящим» авансом: в отчёте видна как overpayment, а в
    # accounts_register баланс по услугам сходится к 0 (долга нет).
    stmt = build_account_statement(db, rec["account_id"])
    assert stmt["metrics"]["overpayment"] == 500.0
    assert stmt["metrics"]["debt_total"] == 0.0
    balance = db.execute(
        text("SELECT balance_after FROM accounts_register WHERE account_id=:a "
             "ORDER BY operation_date DESC, id DESC LIMIT 1"),
        {"a": rec["account_id"]},
    ).scalar()
    assert float(balance) == 0.0  # долга по услугам нет


# --- Фаза 4: отчёт по лицевому счёту ---


def test_account_statement_metrics(db, account_factory):
    rec = account_factory("st0")
    _accrual(db, rec["account_id"], 1, 400)  # Электричество
    _accrual(db, rec["account_id"], 3, 500)  # Холодная вода
    db.commit()
    _payment(db, rec["account_id"], rec["cash_point_id"], 1000)

    calculate_write_offs(db, [rec["account_id"]])
    db.commit()

    stmt = build_account_statement(db, rec["account_id"])

    assert stmt["account"]["id"] == rec["account_id"]
    m = stmt["metrics"]
    assert m["accrued_total"] == 900.0
    assert m["paid_total"] == 900.0
    assert m["available"] == 1000.0
    assert m["debt_total"] == 0.0
    assert m["overpayment"] == 100.0  # внесено 1000 - распределено 900

    services = {s["services_type_id"]: s for s in stmt["services"]}
    assert services[1]["accrued"] == 400.0 and services[1]["debt"] == 0.0
    assert services[3]["accrued"] == 500.0 and services[3]["debt"] == 0.0


def test_account_statement_partial_debt(db, account_factory):
    rec = account_factory("st1")
    _accrual(db, rec["account_id"], 1, 800)
    db.commit()
    _payment(db, rec["account_id"], rec["cash_point_id"], 300)

    calculate_write_offs(db, [rec["account_id"]])
    db.commit()

    stmt = build_account_statement(db, rec["account_id"])
    m = stmt["metrics"]
    assert m["accrued_total"] == 800.0
    assert m["paid_total"] == 300.0
    assert m["overpayment"] == 0.0
    assert m["debt_total"] == 500.0
    s = stmt["services"][0]
    assert s["accrued"] == 800.0 and s["paid"] == 300.0 and s["debt"] == 500.0
