"""
Приведение Регистра взаиморасчётов (accounts_register) к документам начислений.

Контекст ТД-4: фактическое распределение expense по услугам в accounts_register
должно в точности воспроизводиться моделью «переливов» — деньги счёта раскладываются
по накопленным долгам услуг в порядке приоритета (services_type.priority, Фонд —
последний). Если после изменения начислений счёт не пересчитывался, expense остаётся
«старым»: часть долгов (например, «Вывоз мусора») не погашена, а деньги числятся на
«Фонде развития».

Диагноз (проверен тестом tests/check_sum/test_registers_services_vs_writeoff_model.py):
у 16 из 17 л/с регистр согласован с первичкой; расходится счёт 13 (кв.13):
  Вывоз мусора: начислено 114 500, expense = 0 (модель: 114 500);
  Фонд развития: expense 1 401 526 (модель: 1 287 026).
Сумма списаний счёта при пересчёте НЕ меняется — меняется только разбивка по услугам.

Что делает скрипт:
  1. dry-run: сравнивает фактический expense по услугам с моделью переливов
     (источник долгов — accruals_register, деньги — cash_register) и печатает
     расхождения по счетам;
  2. --apply: для расходящихся счетов запускает штатный rebuild_accounts_register
     (полное пересоздание среза accounts_register из первичных регистров
     accruals_register + cash_register), затем повторяет сверку (должно стать 0).

Запуск из каталога backend:
    python migrations/resync_accounts_register_to_accruals.py             # dry-run
    python migrations/resync_accounts_register_to_accruals.py --apply     # применить
"""

import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from database import SessionLocal  # noqa: E402
from writeoffs import rebuild_accounts_register  # noqa: E402


def _services_in_priority_order(db):
    rows = db.execute(text(
        "SELECT id, services_type FROM services_type "
        "ORDER BY (CASE WHEN COALESCE(priority, 0) = 0 THEN 1 ELSE 0 END), "
        "priority ASC, id ASC"
    )).fetchall()
    return [(int(r[0]), str(r[1])) for r in rows]


def _accrued_per_service(db):
    """Чистый долг по услуге на счёт из accruals_register (сторно < 0 учтено)."""
    out = {}
    for acc, sid, v in db.execute(text(
        "SELECT account_id, services_type_id, COALESCE(SUM(amount), 0) "
        "FROM accruals_register "
        "WHERE amount IS NOT NULL AND services_type_id IS NOT NULL "
        "GROUP BY 1, 2"
    )).fetchall():
        out.setdefault(int(acc), {})[int(sid)] = Decimal(str(v))
    return out


def _available_cash(db):
    out = {}
    for acc, v in db.execute(text(
        "SELECT account_id, COALESCE(SUM(income - expense), 0) "
        "FROM cash_register WHERE account_id IS NOT NULL GROUP BY 1"
    )).fetchall():
        out[int(acc)] = Decimal(str(v))
    return out


def _actual_expense(db):
    out = {}
    for acc, sid, v in db.execute(text(
        "SELECT account_id, services_type_id, COALESCE(SUM(expense), 0) "
        "FROM accounts_register "
        "WHERE expense > 0 AND services_type_id IS NOT NULL GROUP BY 1, 2"
    )).fetchall():
        out.setdefault(int(acc), {})[int(sid)] = Decimal(str(v))
    return out


def _model_expense(db, accrued, available):
    services = _services_in_priority_order(db)
    model = {}
    for acc, debts in accrued.items():
        total_debt = sum(d for d in debts.values() if d > 0)
        to_alloc = min(available.get(acc, Decimal(0)), total_debt)
        remaining = to_alloc
        alloc = {}
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


def _account_number(db, acc_id):
    row = db.execute(text(
        "SELECT ap.apartment_number FROM accounts a "
        "JOIN apartments ap ON ap.id = a.apartment_id WHERE a.id = :i"), {"i": acc_id}).first()
    return row[0] if row else acc_id


def _diffs(db, accrued, available, actual, model):
    names = {sid: name for sid, name in _services_in_priority_order(db)}
    out = []
    for acc in sorted(set(actual) | set(model)):
        f = actual.get(acc, {})
        m = model.get(acc, {})
        for sid in sorted(set(f) | set(m)):
            fv = f.get(sid, Decimal(0))
            mv = m.get(sid, Decimal(0))
            if abs(fv - mv) >= Decimal("0.01"):
                out.append((acc, names.get(sid, f"#{sid}"), mv, fv))
    return out


def main() -> None:
    apply_mode = "--apply" in sys.argv
    db = SessionLocal()
    try:
        accrued = _accrued_per_service(db)
        available = _available_cash(db)
        actual = _actual_expense(db)
        model = _model_expense(db, accrued, available)
        diffs = _diffs(db, accrued, available, actual, model)

        print(f"Сверка expense по услугам с моделью переливов: расхождений {len(diffs)}")
        for acc, svc, mv, fv in diffs:
            kv = _account_number(db, acc)
            print(f"  счёт {acc} (кв.{kv}) '{svc}': модель {mv:,.2f} vs факт {fv:,.2f}")
        if not diffs:
            print("  регистр согласован с документами начислений — пересчёт не нужен.")
            return
        if not apply_mode:
            print("\ndry-run: для пересчёта выполните скрипт с ключом --apply")
            return

        ids = sorted({acc for acc, _svc, _m, _f in diffs})
        print(f"\nПересоздаю accounts_register для счетов: {ids} ...")
        rebuild_accounts_register(db, ids)
        db.commit()

        # контроль после пересчёта
        actual2 = _actual_expense(db)
        diffs2 = _diffs(db, accrued, available, actual2, model)
        print(f"Контроль после пересчёта: расхождений {len(diffs2)}")
        for acc, svc, mv, fv in diffs2:
            print(f"  счёт {acc} '{svc}': модель {mv:,.2f} vs факт {fv:,.2f}")
        print("Готово. Проверьте check_register_integrity и контрольные суммы.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
