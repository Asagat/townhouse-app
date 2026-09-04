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
