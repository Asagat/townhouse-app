# tests/check_sum/test_registers_services_vs_writeoff_model.py
"""Остатки по видам услуг ↔ модель приоритетного распределения («переливы»).

Контекст ТД-4. В файле-источнике приход кассы несёт «Код_Аналитика» (вид
задолженности, на который кассир записал платёж). В новой модели платёж ложится на
счёт целиком и автоматически распределяется между услугами долга в порядке приоритета
(`services_type.priority`: меньшее значение — раньше, 0 — в последнюю очередь; на
текущем наборе «Фонд развития» — последний). Поэтому суммы по старым статьям
(аналитика файла) НЕ обязаны совпадать с `accounts_register.expense` по услугам
«напрямую»: платежи, помеченные в файле как «Фонд», фактически гасят долги других
услуг (переливы).

Тест проверяет, что фактическое распределение `expense` по услугам (а значит, и
остатки `income − expense` по каждой услуге) в БД в точности воспроизводится моделью
переливов: доступные деньги счёта раскладываются по накопленным долгам услуг в
порядке приоритета. Если регистр взаиморасчётов согласован с первичкой — расхождений
нет (0). Расхождение означает: счёт не был пересчитан после изменения начислений
(требуется `rebuild_accounts_register`/`auto_recalculate_writeoffs`).

Модель повторяет логику `writeoffs.calculate_write_offs`/`_distribute` на уровне
итоговых сумм (детали FIFO по документам влияют только на operation_date строк
списания, но не на итог по услуге). Начисления берутся из первичного регистра
`accruals_register` (источник income-строк при пересоздании accounts_register),
доступные деньги — из `cash_register`. Тест только читает БД.
"""

from decimal import Decimal

import pytest
from sqlalchemy import text


@pytest.fixture
def checker(db):
    has_acc = db.execute(text("SELECT EXISTS (SELECT 1 FROM accruals_register)")).scalar()
    has_cash = db.execute(text("SELECT EXISTS (SELECT 1 FROM cash_register)")).scalar()
    if not (has_acc and has_cash):
        pytest.skip("БД без начислений/кассы — модель переливов не применима")
    return db


def _services_in_priority_order(db) -> list[tuple[int, str]]:
    """Виды услуг в порядке списания — как `writeoffs._services_in_priority_order`."""
    rows = db.execute(text(
        "SELECT id, services_type FROM services_type "
        "ORDER BY (CASE WHEN COALESCE(priority, 0) = 0 THEN 1 ELSE 0 END), "
        "priority ASC, id ASC"
    )).fetchall()
    return [(int(r[0]), str(r[1])) for r in rows]


def _accrued_per_service(db) -> dict[int, dict[int, Decimal]]:
    """Чистый долг по услуге на счёт: SUM(amount) из accruals_register (сторно < 0 учтено)."""
    out: dict[int, dict[int, Decimal]] = {}
    for acc, sid, v in db.execute(text(
        "SELECT account_id, services_type_id, COALESCE(SUM(amount), 0) "
        "FROM accruals_register "
        "WHERE amount IS NOT NULL AND services_type_id IS NOT NULL "
        "GROUP BY 1, 2"
    )).fetchall():
        out.setdefault(int(acc), {})[int(sid)] = Decimal(str(v))
    return out


def _available_cash(db) -> dict[int, Decimal]:
    """Доступные деньги по счёту (первичный регистр денежных средств)."""
    out: dict[int, Decimal] = {}
    for acc, v in db.execute(text(
        "SELECT account_id, COALESCE(SUM(income - expense), 0) "
        "FROM cash_register WHERE account_id IS NOT NULL GROUP BY 1"
    )).fetchall():
        out[int(acc)] = Decimal(str(v))
    return out


def _actual_expense(db) -> dict[int, dict[int, Decimal]]:
    """Фактические погашения по услуге на счёт (accounts_register.expense)."""
    out: dict[int, dict[int, Decimal]] = {}
    for acc, sid, v in db.execute(text(
        "SELECT account_id, services_type_id, COALESCE(SUM(expense), 0) "
        "FROM accounts_register "
        "WHERE expense > 0 AND services_type_id IS NOT NULL GROUP BY 1, 2"
    )).fetchall():
        out.setdefault(int(acc), {})[int(sid)] = Decimal(str(v))
    return out


def _model_expense(db, accrued, available) -> dict[int, dict[int, Decimal]]:
    """Модель переливов: деньги счёта раскладываются по долгам услуг в порядке приоритета.

    Как в `_distribute`: услуги с долгом <= 0 (сторно/переплата) пропускаются; сумма
    распределения ограничена min(доступно, Σ положительных долгов).
    """
    services = _services_in_priority_order(db)
    model: dict[int, dict[int, Decimal]] = {}
    for acc, debts in accrued.items():
        total_debt = sum(d for d in debts.values() if d > 0)
        to_alloc = min(available.get(acc, Decimal(0)), total_debt)
        remaining = to_alloc
        alloc: dict[int, Decimal] = {}
        for sid, _name in services:
            if remaining <= 0:
                break
            d = debts.get(sid, Decimal(0))
            if d <= 0:
                continue
            amt = min(remaining, d)
            alloc[sid] = amt
            remaining -= amt
        model[acc] = alloc
    return model


def test_expense_services_match_writeoff_model(db, checker):
    """expense по услугам == модель переливов из первички (0 расхождений)."""
    accrued = _accrued_per_service(db)
    available = _available_cash(db)
    names = {sid: name for sid, name in _services_in_priority_order(db)}
    actual = _actual_expense(db)
    model = _model_expense(db, accrued, available)

    bad = []
    for acc in sorted(set(actual) | set(model)):
        f = actual.get(acc, {})
        m = model.get(acc, {})
        for sid in sorted(set(f) | set(m)):
            fv = f.get(sid, Decimal(0))
            mv = m.get(sid, Decimal(0))
            if abs(fv - mv) >= Decimal("0.01"):
                bad.append((acc, names.get(sid, f"#{sid}"), mv, fv, fv - mv))

    assert not bad, (
        "expense по услугам расходится с моделью переливов "
        "(счёт не пересчитан после изменения начислений): "
        f"{len(bad)} расхождений:\n"
        + "\n".join(
            f"  счёт {a} '{s}': модель {mv:,.2f} vs факт {fv:,.2f} (Δ={d:,.2f})"
            for a, s, mv, fv, d in bad[:30]
        )
    )


def test_service_balances_match_model(db, checker):
    """Остатки по услугам (начислено − погашено) == модель (0 расхождений)."""
    accrued = _accrued_per_service(db)
    available = _available_cash(db)
    names = {sid: name for sid, name in _services_in_priority_order(db)}
    model_exp = _model_expense(db, accrued, available)

    model_bal: dict[int, dict[int, Decimal]] = {}
    for acc, debts in accrued.items():
        for sid, debt in debts.items():
            rest = debt - model_exp.get(acc, {}).get(sid, Decimal(0))
            if rest != 0:
                model_bal.setdefault(acc, {})[sid] = rest

    # фактический остаток: income − expense по услуге (net, с учётом сторно)
    actual_bal: dict[int, dict[int, Decimal]] = {}
    for acc, sid, v in db.execute(text(
        "SELECT account_id, services_type_id, COALESCE(SUM(income - expense), 0) "
        "FROM accounts_register "
        "WHERE services_type_id IS NOT NULL GROUP BY 1, 2"
    )).fetchall():
        val = Decimal(str(v))
        if val != 0:
            actual_bal.setdefault(int(acc), {})[int(sid)] = val

    bad = []
    for acc in sorted(set(actual_bal) | set(model_bal)):
        f = actual_bal.get(acc, {})
        m = model_bal.get(acc, {})
        for sid in sorted(set(f) | set(m)):
            fv = f.get(sid, Decimal(0))
            mv = m.get(sid, Decimal(0))
            if abs(fv - mv) >= Decimal("0.01"):
                bad.append((acc, names.get(sid, f"#{sid}"), mv, fv, fv - mv))

    assert not bad, (
        "Остатки по услугам расходятся с моделью переливов "
        "(счёт не пересчитан после изменения начислений): "
        f"{len(bad)} расхождений:\n"
        + "\n".join(
            f"  счёт {a} '{s}': модель {mv:,.2f} vs факт {fv:,.2f} (Δ={d:,.2f})"
            for a, s, mv, fv, d in bad[:30]
        )
    )
