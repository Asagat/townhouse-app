"""
Миграция исторических данных: перенос старых строк «Приход/Расход» из Регистра
взаиморасчётов (accounts_register) в Регистр денежных средств (cash_register).

Зачем: до ввода Фазы 1 документ «Приход/Расход» писал движение денег напрямую
в accounts_register (строки с transaction_id и без accrual_id). После Фазы 1
деньги должны лежать в cash_register, а во взаиморасчёты попадать через операцию
списания.

Скрипт:
  1. Копирует устаревшие платёжные строки accounts_register в cash_register
     (только если для данного transaction_id в cash_register ещё нет записи).
  2. Удаляет их из accounts_register.
  3. Полностью пересчитывает balance_after обоих регистров для затронутых счетов.

Запуск из каталога backend:
    python migrations/migrate_old_payments_to_cash_register.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import recalculate_account_balance, recalculate_cash_balance  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        # Аккаунты, у которых есть устаревшие платёжные строки в accounts_register.
        affected = db.execute(
            text("""
                SELECT DISTINCT ar.account_id
                FROM accounts_register ar
                WHERE ar.transaction_id IS NOT NULL AND ar.accrual_id IS NULL
            """),
        ).scalars().all()

        moved = db.execute(
            text("""
                INSERT INTO cash_register (operation_date, account_id, transaction_id, income, expense, balance_after)
                SELECT ar.operation_date, ar.account_id, ar.transaction_id, ar.income, ar.expense, 0
                FROM accounts_register ar
                WHERE ar.transaction_id IS NOT NULL AND ar.accrual_id IS NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM cash_register cr WHERE cr.transaction_id = ar.transaction_id
                  )
            """),
        ).rowcount

        deleted = db.execute(
            text("""
                DELETE FROM accounts_register
                WHERE transaction_id IS NOT NULL AND accrual_id IS NULL
            """),
        ).rowcount

        db.commit()

        # Пересчёт балансов затронутых счетов в обоих регистрах.
        for account_id in affected:
            recalculate_account_balance(db, account_id)
            recalculate_cash_balance(db, account_id)
        db.commit()

        print(f"Перенесено строк в cash_register: {moved}")
        print(f"Удалено устаревших строк из accounts_register: {deleted}")
        print(f"Затронутых лицевых счетов: {len(affected)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
