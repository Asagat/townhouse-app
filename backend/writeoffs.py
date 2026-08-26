"""
Ядро операции «Списание задолженностей».

Разнесение доступных денег лицевого счёта по видам услуг в порядке приоритета
(поле services_type.priority, меньшее значение — раньше; 0 — в последнюю очередь)
с записью результата в Регистр взаиморасчётов (accounts_register).

Конвенция знаков — см. блок «КОНВЕНЦИЯ ЗНАКОВ» в models.py. Источник входа —
первичные регистры (accruals_register, cash_register) и текущее состояние регистра
взаиморасчётов. Функция идемпотентна: существующие строки списания для затронутых
счетов удаляются и строятся заново, поэтому списание всегда можно пересоздать.
"""

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from models import ServiceType, recalculate_account_balance


def _active_account_ids(db: Session) -> list[int]:
    rows = db.execute(text("SELECT id FROM accounts WHERE is_active = true")).fetchall()
    return [r[0] for r in rows]


def _available_cash(db: Session, account_id: int) -> float:
    """Доступные деньги по счёту из Регистра денежных средств."""
    value = db.execute(
        text("SELECT COALESCE(SUM(income - expense), 0) FROM cash_register WHERE account_id = :a"),
        {"a": account_id},
    ).scalar()
    return float(value or 0.0)


def _accrued_per_service(db: Session, account_id: int) -> dict[int, float]:
    """
    Начислено по каждому виду услуги (income-строки accounts_register с видом услуги).
    Возвращает {services_type_id: сумма}.
    """
    rows = db.execute(
        text("""
            SELECT services_type_id, COALESCE(SUM(income), 0)
            FROM accounts_register
            WHERE account_id = :a AND services_type_id IS NOT NULL
            GROUP BY services_type_id
        """),
        {"a": account_id},
    ).fetchall()
    return {r[0]: float(r[1] or 0.0) for r in rows if r[0] is not None}


def _delete_writeoffs(db: Session, account_id: int) -> None:
    """
    Удаляет существующие строки списания счёта.

    Строки списания — записи accounts_register с расходной частью (expense > 0)
    и видом услуги (списание уменьшает долг). Начисления хранятся как income-строки.
    """
    db.execute(
        text("""
            DELETE FROM accounts_register
            WHERE account_id = :a AND services_type_id IS NOT NULL AND expense > 0
        """),
        {"a": account_id},
    )


def _services_in_priority_order(db: Session) -> list[ServiceType]:
    """Виды услуг в порядке списания: с заданным приоритетом сначала (по возрастанию),
    приоритет 0/NULL — в последнюю очередь."""
    return (
        db.query(ServiceType)
        .order_by(
            text("(CASE WHEN COALESCE(priority, 0) = 0 THEN 1 ELSE 0 END)"),
            ServiceType.priority.asc(),
            ServiceType.id.asc(),
        )
        .all()
    )


def calculate_write_offs(db: Session, account_ids: list[int] | None = None) -> dict:
    """
    Выполняет списание задолженностей.

    A. Для каждого счёта определяется начислено по видам услуг (accounts_register,
       income-строки начислений).
    B. Определяется доступная сумма по счёту (cash_register: SUM(income - expense)).
    C. Доступная сумма распределяется по услугам в порядке приоритета и записывается
       в accounts_register как списание (expense-строки с видом услуги).

    Конвенция знаков: income = начислено (долг растёт), expense = списано (долг падает),
    balance_after = SUM(income) - SUM(expense) — положительный = долг, отрицательный = переплата.

    Если доступных денег больше суммы всех начислений, переплата остаётся висящей
    отрицательным остатком balance_after счёта — дополнительные строки не создаём
    (вариант 1).

    account_ids=None — все активные счета. Итог предназначен для отчёта/фронтенда.
    """
    if account_ids is None:
        account_ids = _active_account_ids(db)
    elif isinstance(account_ids, int):
        account_ids = [account_ids]

    services = _services_in_priority_order(db)
    processed: list[dict] = []

    for account_id in account_ids:
        # Удаляем прежние строки списания, чтобы перестроить разнесение с нуля.
        _delete_writeoffs(db, account_id)

        accrued = _accrued_per_service(db, account_id)
        total_debt = sum(accrued.values())
        available = _available_cash(db, account_id)
        to_allocate = min(available, total_debt)

        allocations: list[dict] = []
        allocated_total = 0.0

        if to_allocate > 0:
            op_date = datetime.now()
            remaining = to_allocate
            for svc in services:
                if remaining <= 0:
                    break
                svc_id = svc.id
                debt_amt = accrued.get(svc_id, 0.0)
                if debt_amt <= 0:
                    continue
                amount = min(remaining, debt_amt)
                rounded = round(amount, 2)
                if rounded <= 0:
                    continue
                db.execute(
                    text("""
                        INSERT INTO accounts_register
                            (operation_date, account_id, services_type_id, income, expense, balance_after)
                        VALUES (:op, :a, :svc, 0, :expense, 0)
                    """),
                    {
                        "op": op_date,
                        "a": account_id,
                        "svc": svc_id,
                        "expense": rounded,
                    },
                )
                remaining -= amount
                allocated_total += rounded
                allocations.append({"services_type_id": svc_id, "allocated": rounded})

        recalculate_account_balance(db, account_id)
        processed.append(
            {
                "account_id": account_id,
                "accrued": round(total_debt, 2),
                "available": round(available, 2),
                "written_off": round(allocated_total, 2),
                "allocations": allocations,
            }
        )

    return {"processed": processed}


# --- ПЕРЕСОЗДАНИЕ ПРОИЗВОДНОГО СРЕЗА (пункт 3.3 роадмапа) ---


def rebuild_accounts_register(db: Session, account_ids: list[int] | None = None) -> dict:
    """
    Полностью пересоздаёт Регистр взаиморасчётов (accounts_register) для счетов
    «с нуля» из первичных регистров (accruals_register + cash_register).

    Это делает производный срез ДЕТЕРМИНИРОВАННЫМ и ПЕРЕСОЗДАВАЕМЫМ: результат не
    зависит от того, в каком порядке/успешно ли были применены операции, — он
    всегда выводится из истории первичных регистров.

    Алгоритм для каждого счёта:
      1. удаляет ВСЕ строки accounts_register счёта (и начисления, и списания);
      2. пересоздаёт начисления из accruals_register (operation_date = accrual_date,
         income = amount, сохраняя accrual_id) — детерминированно;
      3. перестраивает списания: calculate_write_offs(cчёт) — распределение денег из
         cash_register по приоритету;
      4. ре-пересчёт balance_after (делает calculate_write_offs).

    account_ids=None — все активные счета.
    """
    if account_ids is None:
        account_ids = _active_account_ids(db)
    elif isinstance(account_ids, int):
        account_ids = [account_ids]

    rebuilt: list[dict] = []
    for account_id in account_ids:
        db.execute(
            text("DELETE FROM accounts_register WHERE account_id = :a"),
            {"a": account_id},
        )
        # Начисления из первичного регистра начислений.
        db.execute(
            text("""
                INSERT INTO accounts_register
                    (operation_date, account_id, accrual_id, services_type_id, income, expense, balance_after)
                SELECT accrual_date, account_id, id, services_type_id, amount, 0, 0
                FROM accruals_register
                WHERE account_id = :a
            """),
            {"a": account_id},
        )
        # Списания из денежного регистра (по приоритету) + пересчёт баланса.
        w_result = calculate_write_offs(db, [account_id])
        rebuilt.append(
            {
                "account_id": account_id,
                **w_result["processed"][0],
            }
        )

    return {"processed": rebuilt}


def check_register_integrity(db: Session, account_id: int) -> dict:
    """
    Проверяет согласованность производного среза accounts_register с первичными
    регистрами для счёта. Возвращает метрики и флаг consistency.

    Сходимость считается выполненной, если:
      - начислено в срезе (Σ income с accrual_id) == начислено в accruals_register;
      - текущий balance_after == (начислено в срезе) - (списано в срезе);
      - списано не превышает доступных денег (из cash_register).
    """
    def _one(sql: str) -> float:
        return float(db.execute(text(sql), {"a": account_id}).scalar() or 0.0)

    accrued_register = _one(
        "SELECT COALESCE(SUM(amount), 0) FROM accruals_register WHERE account_id = :a"
    )
    accrued_settlement = _one(
        "SELECT COALESCE(SUM(income), 0) FROM accounts_register WHERE account_id = :a AND accrual_id IS NOT NULL"
    )
    written_off = _one(
        "SELECT COALESCE(SUM(expense), 0) FROM accounts_register WHERE account_id = :a"
    )
    available = _one(
        "SELECT COALESCE(SUM(income - expense), 0) FROM cash_register WHERE account_id = :a"
    )
    balance = _one(
        "SELECT COALESCE(balance_after, 0) FROM accounts_register WHERE account_id = :a "
        "ORDER BY operation_date DESC, id DESC LIMIT 1"
    )

    accrued_match = abs(accrued_settlement - accrued_register) < 0.005
    balance_match = abs(balance - (accrued_settlement - written_off)) < 0.005
    no_over_writeoff = written_off <= available + 0.005

    return {
        "account_id": account_id,
        "accrued_register": round(accrued_register, 2),
        "accrued_settlement": round(accrued_settlement, 2),
        "written_off": round(written_off, 2),
        "available": round(available, 2),
        "balance": round(balance, 2),
        "consistent": bool(accrued_match and balance_match and no_over_writeoff),
    }
    if account_ids is None:
        account_ids = _active_account_ids(db)
    elif isinstance(account_ids, int):
        account_ids = [account_ids]

    services = _services_in_priority_order(db)
    processed: list[dict] = []

    for account_id in account_ids:
        # Удаляем прежние строки списания, чтобы перестроить разнесение с нуля.
        _delete_writeoffs(db, account_id)

        accrued = _accrued_per_service(db, account_id)
        total_debt = sum(accrued.values())
        available = _available_cash(db, account_id)
        to_allocate = min(available, total_debt)

        allocations: list[dict] = []
        allocated_total = 0.0

        if to_allocate > 0:
            op_date = datetime.now()
            remaining = to_allocate
            for svc in services:
                if remaining <= 0:
                    break
                svc_id = svc.id
                debt_amt = accrued.get(svc_id, 0.0)
                if debt_amt <= 0:
                    continue
                amount = min(remaining, debt_amt)
                rounded = round(amount, 2)
                if rounded <= 0:
                    continue
                db.execute(
                    text("""
                        INSERT INTO accounts_register
                            (operation_date, account_id, services_type_id, income, expense, balance_after)
                        VALUES (:op, :a, :svc, 0, :expense, 0)
                    """),
                    {
                        "op": op_date,
                        "a": account_id,
                        "svc": svc_id,
                        "expense": rounded,
                    },
                )
                remaining -= amount
                allocated_total += rounded
                allocations.append({"services_type_id": svc_id, "allocated": rounded})

        recalculate_account_balance(db, account_id)
        processed.append(
            {
                "account_id": account_id,
                "accrued": round(total_debt, 2),
                "available": round(available, 2),
                "written_off": round(allocated_total, 2),
                "allocations": allocations,
            }
        )

    return {"processed": processed}
