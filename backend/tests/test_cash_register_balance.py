# tests/test_cash_register_balance.py

"""ТД-6: `cash_register.balance_after` — нарастающий остаток денег ПО КАССЕ/СЧЁТУ.

Проверяет новую семантику:
  - итог ведётся по каждому `cash_point_id` отдельно (а не по лицевому счёту);
  - у последней строки кассы значение равно Σ(income − expense) по этой кассе;
  - инвариант сохраняется после редактирования и удаления документа.

Тесты изолированы: `account_factory` создаёт для каждой кассы уникальный
`cash_point_id`, поэтому результат не зависит от наполнения живой БД.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import text

from models import Transaction, TransactionTypeEnum


def _tx(cash_point_id, account_id, ttype, amount, when) -> Transaction:
    return Transaction(
        account_id=account_id,
        cash_point_id=cash_point_id,
        transaction_type=ttype,
        amount=Decimal(amount),
        transaction_date=when,
    )


def _balances(db, cash_point_id) -> list[float]:
    rows = db.execute(
        text(
            "SELECT balance_after FROM cash_register WHERE cash_point_id = :c "
            "ORDER BY operation_date, id"
        ),
        {"c": cash_point_id},
    ).scalars().all()
    return [float(x) for x in rows]


def _total(db, cash_point_id) -> float:
    return float(
        db.execute(
            text(
                "SELECT COALESCE(SUM(income - expense), 0) FROM cash_register "
                "WHERE cash_point_id = :c"
            ),
            {"c": cash_point_id},
        ).scalar()
    )


def test_balance_is_running_per_cash_point(db, account_factory):
    """Остаток нарастает отдельно по каждой кассе, а не по лицевому счёту."""
    a = account_factory("cashrun-a")
    b = account_factory("cashrun-b")

    txs = [
        # Касса A: приход по л/с, расход без л/с, ещё приход без л/с.
        _tx(a["cash_point_id"], a["account_id"], TransactionTypeEnum.in_cash, "1000",
            datetime(2016, 11, 1, 9, 0)),
        _tx(a["cash_point_id"], None, TransactionTypeEnum.out_cash, "300",
            datetime(2016, 11, 2, 9, 0)),
        _tx(a["cash_point_id"], None, TransactionTypeEnum.in_cash, "500",
            datetime(2016, 11, 3, 9, 0)),
        # Касса B — независимый итог.
        _tx(b["cash_point_id"], b["account_id"], TransactionTypeEnum.in_bank, "200",
            datetime(2016, 11, 1, 9, 0)),
        _tx(b["cash_point_id"], None, TransactionTypeEnum.out_bank, "50",
            datetime(2016, 11, 4, 9, 0)),
    ]
    db.add_all(txs)
    db.commit()
    try:
        a_bal = _balances(db, a["cash_point_id"])
        b_bal = _balances(db, b["cash_point_id"])

        assert a_bal == [1000.0, 700.0, 1200.0]
        assert b_bal == [200.0, 150.0]
        # У последней строки каждой кассы — Σ по этой кассе.
        assert a_bal[-1] == _total(db, a["cash_point_id"]) == 1200.0
        assert b_bal[-1] == _total(db, b["cash_point_id"]) == 150.0
    finally:
        for t in txs:
            db.delete(t)
        db.commit()


def test_balance_recomputed_on_update_and_delete(db, account_factory):
    """Инвариант остатка сохраняется после правки и удаления документа."""
    rec = account_factory("cashinv")
    cp = rec["cash_point_id"]

    t1 = _tx(cp, rec["account_id"], TransactionTypeEnum.in_cash, "1000",
             datetime(2016, 10, 1, 9, 0))
    t2 = _tx(cp, None, TransactionTypeEnum.out_cash, "400",
             datetime(2016, 10, 2, 9, 0))
    db.add_all([t1, t2])
    db.commit()
    try:
        assert _balances(db, cp) == [1000.0, 600.0]
        assert _balances(db, cp)[-1] == _total(db, cp) == 600.0

        # Правка суммы документа — остаток пересчитывается, начиная с этой строки.
        t1.amount = Decimal("1500")
        db.commit()
        assert _balances(db, cp) == [1500.0, 1100.0]
        assert _balances(db, cp)[-1] == _total(db, cp) == 1100.0

        # Удаление документа — оставшаяся строка становится последней и равна Σ.
        db.delete(t2)
        db.commit()
        assert _balances(db, cp) == [1500.0]
        assert _balances(db, cp)[-1] == _total(db, cp) == 1500.0
    finally:
        for t in (t1, t2):
            if t in db:  # t2 мог быть уже удалён в ходе теста
                db.delete(t)
        db.commit()
