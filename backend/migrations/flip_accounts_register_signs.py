"""
Формальный «переворот» знаков в Регистре взаиморасчётов (accounts_register).

Приводит исторические записи к целевой конвенции:
  - income  = НАЧИСЛЕНО   (долг растёт);
  - expense = СПИСАНО/ОПЛАЧЕНО (долг падает);
  - balance_after = SUM(income) - SUM(expense);  >0 = долг, <0 = переплата.

Что делает:
  1. Старые начисления (записи с accrual_id, хранящиеся как expense) переносятся в income.
  2. Старые списания (записи с видом услуги и expense, уже соответствующие целевой
     конвенции) НЕ трогаются; при пересоздании списания (calculate_write_offs) они
     всё равно перестраиваются заново.
  3. Полностью пересчитывает balance_after для затронутых счетов.

Применять ДО первой эксплуатации «переворота», т.е. перед вводом в строй, если в БД
уже есть исторические начисления в старой схеме (expense).

Запуск из каталога backend:
    python migrations/flip_accounts_register_signs.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import recalculate_account_balance  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        # Аккаунты с историческими начислениями (accrual-строки в expense).
        affected = db.execute(
            text("""
                SELECT DISTINCT account_id
                FROM accounts_register
                WHERE accrual_id IS NOT NULL AND expense > 0
            """),
        ).scalars().all()

        # 1) Уже из cash_register не перемещаем (там отдельная семантика).
        # 2) Старые начисления: expense -> income (долг растёт).
        flipped = db.execute(
            text("""
                UPDATE accounts_register
                SET income = expense, expense = 0
                WHERE accrual_id IS NOT NULL
            """),
        ).rowcount

        db.commit()

        for account_id in affected:
            recalculate_account_balance(db, account_id)
        db.commit()

        print(f"Перевёрнуто начислений (expense -> income): {flipped}")
        print(f"Затронутых лицевых счетов: {len(affected)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
