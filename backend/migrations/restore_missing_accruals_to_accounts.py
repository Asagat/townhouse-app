"""
Восстановление «потерянных» начислений в Регистре взаиморасчётов (accounts_register).

В $accruals_register лежат строки начислений, у которых НЕТ соответствующей записи
в accounts_register (нет ссылки accrual_id): такие начисления участвуют в первичном
регистре начислений, но не попали в срез взаиморасчётов и потому не влияют на долг.

Диагноз (проверен по данным): у всех 17 активных л/с сумма начислений в
accruals_register больше, чем «начислено с accrual_id» в accounts_register, ровно
на 425 951,00 ₸. Это даёт занижение долга (напр. кв.3 показывает 0 вместо ≈160 765).

Что делает скрипт (вариант А — точечно, без «сплющивания» существующих распределений):
  1. для каждого активного л/с находит accruals_register-строки, на которые нет
     строки в accounts_register с таким accrual_id;
  2. точечно вставляет их в accounts_register:
       operation_date   = accrual_date
       account_id       = account_id
       accrual_id/без изменения
       services_type_id = accrual.services_type_id
       income           = amount
       expense          = 0
  3. пересчитывает balance_after затронутых счетов (recalculate_account_balance).

Существующие строки списаний/оплат НЕ трогаются — только недостававшие начисления
добавляются, история движений по счёту сохраняется.

Идемпотентен: повторный запуск найдёт 0 обновляемых строк (останутся только те
accruals, у которых уже есть запись в accounts_register).

Запуск из каталога backend:
    python migrations/restore_missing_accruals_to_accounts.py             # dry-run
    python migrations/restore_missing_accruals_to_accounts.py --apply     # применить
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import recalculate_account_balance  # noqa: E402


def _missing_accruals(db, account_ids=None):
    """Возвращает список accruals-строк, не попавших в accounts_register."""
    if account_ids is None:
        acc_where = "TRUE"
    else:
        acc_where = "a.account_id = ANY(:ids)"
    q = text(f"""
        SELECT a.account_id, a.id AS accrual_id, a.accrual_date,
               a.services_type_id, a.amount
        FROM accruals_register a
        WHERE {acc_where}
          AND NOT EXISTS (
              SELECT 1 FROM accounts_register ar
              WHERE ar.accrual_id = a.id
          )
        ORDER BY a.account_id, a.accrual_date, a.id
    """)
    if account_ids is None:
        return db.execute(q).fetchall()
    return db.execute(q, {"ids": list(account_ids)}).fetchall()


def plan(db):
    """Собирает строки для восстановления (без изменений БД)."""
    return _missing_accruals(db)


def apply(db):
    """Точечно вносит недостающие начисления и пересчитывает балансы."""
    per_account_before = {x[0] for x in plan(db)}
    missing = _missing_accruals(db, None)
    if not missing:
        return 0, 0, []
    inserted = 0
    for row in missing:
        account_id = row[0]
        db.execute(
            text("""
                INSERT INTO accounts_register
                    (operation_date, account_id, accrual_id, services_type_id,
                     income, expense, balance_after)
                VALUES (:op, :a, :accr, :svc, :income, 0, 0)
            """),
            {
                "op": row[2],
                "a": account_id,
                "accr": row[1],
                "svc": row[3],
                "income": row[4],
            },
        )
        inserted += 1
    db.commit()

    # Активные счета + возможные неактивные, у которых есть потери.
    all_accounts = {x[0] for x in missing} | per_account_before
    for account_id in sorted(all_accounts):
        recalculate_account_balance(db, account_id)
    db.commit()
    return inserted, len(all_accounts), [(r[0], r[1], float(r[4])) for r in missing]


def main() -> None:
    apply_mode = "--apply" in sys.argv
    db = SessionLocal()
    try:
        missing = plan(db)
        total = sum(float(r[4]) for r in missing)
        print(f"Найдено начислений без записи в accounts_register: {len(missing)}")
        if missing:
            print("  примеры:")
            for r in missing[:12]:
                print(f"    л/с={r[0]} accrual_id={r[1]} date={r[2]} amount={float(r[4]):,.2f}")
            print(f"  сумма отсутствующих: {total:,.2f}")
        else:
            print("  расхождений нет — восстанавливать нечего.")
            return
        if not apply_mode:
            print("\ndry-run: для применения выполните скрипт с ключом --apply")
            return
        inserted, used_accounts, _ = apply(db)
        print(f"\nВнесено строк в accounts_register: {inserted}")
        print(f"Пересчитаны балансы счетов: {used_accounts}")
        print("Готово. Проверьте целостность (check_register_integrity) и контрольные суммы.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
