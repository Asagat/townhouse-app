# tests/test_dashboard.py
"""Дашборд главной (2.19): форма ответа и внутренняя согласованность метрик.

Строители читают только «живые» регистры и не модифицируют их, поэтому тесты
живут на общей БД (как и другие отчёты в test_reports.py) без точных контрольных
сумм. Проверяем форму среза и не противоречие между раздельными построителями.
"""

from routers.dashboard import (
    build_debt_dynamics,
    build_expenses,
    build_house_metrics,
    build_top_debtors,
)


def test_dashboard_shape(db):
    m = build_house_metrics(db)
    for key in ("accrued", "received", "written_off", "debt", "cash_balance", "debtors_count"):
        assert key in m["metrics"]
        assert isinstance(m["metrics"][key], (int, float))


def test_top_debtors_shape(db):
    top = build_top_debtors(db, limit=5)
    assert isinstance(top, list) and len(top) <= 5
    for row in top:
        for k in ("account_id", "account_number", "apartment_number", "owner_name", "debt"):
            assert k in row
        assert row["debt"] >= 0


def test_debt_dynamics_len_and_shape(db):
    dyn = build_debt_dynamics(db, months=12)
    assert isinstance(dyn, list) and len(dyn) == 12
    for point in dyn:
        for k in ("month", "debt", "label"):
            assert k in point
        assert isinstance(point["debt"], (int, float))
    # Периоды строго по возрастанию, год-месяц.
    months = [p["month"] for p in dyn]
    assert months == sorted(months)


def test_expenses_shape(db):
    out = build_expenses(db)
    assert "total" in out and "articles" in out and "count" in out
    assert isinstance(out["total"], (int, float))
    for art in out["articles"]:
        assert "name" in art and "expense" in art


def test_metrics_debt_matches_dynamics_last(db):
    """Долг «сейчас» совпадает с точкой динамики за текущий месяц (на конец месяца).

    Хвоста будущих записей в регистрах нет (начисления за будущие периоды
    запрещены), поэтому долг на конец текущего месяца == долгу «на сейчас».
    """
    metrics = build_house_metrics(db)["metrics"]
    dyn = build_debt_dynamics(db, months=12)
    last = dyn[-1]
    assert abs(metrics["debt"] - last["debt"]) < 0.01
