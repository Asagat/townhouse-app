# tests/test_reports.py
"""Минимальные проверки отчётов (по кассе и по расходам).

Проверяем, что построители отчётов выполняются без ошибок и возвращают данные
нужной формы (ключи среза и числовые агрегаты). Точные контрольные суммы не
закрепляем — тесты могут жить на общей БД с разным наполнением.
"""

from routers.reports import (
    build_cash_register_report,
    build_expense_report,
    build_debtors_report,
    build_statement_report,
)


def test_cash_register_report_shape(db):
    out = build_cash_register_report(db, None, None)
    assert isinstance(out, dict)
    for key in ("period", "totals", "cash_points", "movements"):
        assert key in out
    for k in ("opening", "income", "expense", "closing"):
        assert isinstance(out["totals"][k], (int, float))
    # Детализации (если есть) несут ссылку на документ.
    if out["movements"]:
        assert "transaction_id" in out["movements"][0]
        assert "cash_point_name" in out["movements"][0]


def test_cash_report_opening_is_cumulative_sum(db, account_factory):
    """«Остаток на начало» — накопительный Σ(income − expense) ДО периода.

    Регрессия: брался `cash_register.balance_after` последней строки, а он ведётся
    по лицевому счёту (и для расходов без л/с равен 0), поэтому «остаток на конец»
    за период показывался неверно.
    """
    from datetime import datetime
    from decimal import Decimal

    from models import Transaction, TransactionTypeEnum

    rec = account_factory("cashrep")
    income_july = Transaction(
        account_id=rec["account_id"], cash_point_id=rec["cash_point_id"],
        transaction_type=TransactionTypeEnum.in_cash, amount=Decimal("1000"),
        transaction_date=datetime(2026, 7, 10, 10, 0),
    )
    # Расход кассы без привязки к л/с — как реальные расходы (account_id IS NULL).
    expense_july = Transaction(
        account_id=None, cash_point_id=rec["cash_point_id"],
        transaction_type=TransactionTypeEnum.out_cash, amount=Decimal("300"),
        transaction_date=datetime(2026, 7, 20, 10, 0),
    )
    income_aug = Transaction(
        account_id=rec["account_id"], cash_point_id=rec["cash_point_id"],
        transaction_type=TransactionTypeEnum.in_cash, amount=Decimal("200"),
        transaction_date=datetime(2026, 8, 10, 10, 0),
    )
    db.add_all([income_july, expense_july, income_aug])
    db.commit()
    try:
        out = build_cash_register_report(
            db, "2026-08-01", "2026-08-31", cash_point_id=rec["cash_point_id"]
        )
        assert out["totals"]["opening"] == 700.0  # 1000 − 300
        assert out["totals"]["income"] == 200.0
        assert out["totals"]["expense"] == 0.0
        assert out["totals"]["closing"] == 900.0  # деньги на конец периода
        point = out["cash_points"][0]
        assert point["opening"] == 700.0
        assert point["closing"] == 900.0
    finally:
        # Расход без л/с автоочисткой не удаляется (она идёт по account_id).
        db.delete(expense_july)
        db.commit()


def test_expense_report_shape(db):
    out = build_expense_report(db, None, None)
    assert isinstance(out, dict)
    for key in ("period", "total_expense", "articles", "movements", "count"):
        assert key in out
    assert isinstance(out["total_expense"], (int, float))
    if out["articles"]:
        assert "name" in out["articles"][0] and "expense" in out["articles"][0]
    if out["movements"]:
        assert "transaction_id" in out["movements"][0]


def test_debtors_report_shape(db):
    out = build_debtors_report(db)
    for key in ("rows", "total_debt", "count"):
        assert key in out
    if out["rows"]:
        row = out["rows"][0]
        for k in ("account_id", "account_number", "debt"):
            assert k in row


def test_statement_report_shape(db):
    # Берём первый активный счёт из БД (наполнение dev-подобно).
    import sqlalchemy as sa
    acc = db.execute(sa.text(
        "SELECT id FROM accounts WHERE is_active ORDER BY account_number LIMIT 1"
    )).first()
    if acc is None:
        return
    out = build_statement_report(db, int(acc[0]))
    assert "account" in out and "monthly" in out and "closing" in out
    assert out["account"]["id"] == int(acc[0])
