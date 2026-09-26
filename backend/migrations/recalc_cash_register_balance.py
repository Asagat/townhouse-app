"""
Пересчёт balance_after в Регистре денежных средств (cash_register) для строк
БЕЗ лицевого счёта (account_id IS NULL).

Причина: до фикса `recalculate_register_balance` фильтровал строки условием
`WHERE account_id = :account_id`, а в SQL `NULL = NULL` не истинно. Поэтому
операции без л/с (расходы кассы, «входящий остаток») навсегда оставались с
`balance_after = 0`. Теперь группа `account_id IS NULL` пересчитывается
(`models.recalculate_register_balance`, `IS NOT DISTINCT FROM`), но уже
существующие строки надо один раз пересчитать — это и делает скрипт.

Что делает:
  1. dry-run: показывает, сколько строк без л/с имеют «застрявший» balance_after;
  2. --apply: пересчитывает нарастающий итог Σ(income − expense) по группе
     `account_id IS NULL` штатным механизмом (`recalculate_cash_balance(db, None)`)
     и печатает контроль (balance_after последней строки группы == Σ по группе).

Строки с лицевым счётом скрипт не трогает — их нарастающий итог считался
корректно и до фикса.

Запуск из каталога backend:
    python migrations/recalc_cash_register_balance.py            # dry-run
    python migrations/recalc_cash_register_balance.py --apply    # применить
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import recalculate_cash_balance  # noqa: E402


def _stats(db) -> dict:
    row = db.execute(
        text("""
            SELECT count(*)                                  AS total,
                   count(*) FILTER (WHERE balance_after = 0)  AS zero,
                   COALESCE(SUM(income - expense), 0)         AS total_sum
            FROM cash_register
            WHERE account_id IS NULL
        """)
    ).first()
    last = db.execute(
        text("""
            SELECT balance_after
            FROM cash_register
            WHERE account_id IS NULL
            ORDER BY operation_date DESC, id DESC
            LIMIT 1
        """)
    ).scalar()
    return {
        "total": row[0],
        "zero": row[1],
        "total_sum": float(row[2]),
        "last": float(last) if last is not None else None,
    }


def main() -> None:
    apply_mode = "--apply" in sys.argv
    db = SessionLocal()
    try:
        before = _stats(db)
        print("Регистр кассы, строки без лицевого счёта (account_id IS NULL):")
        print(f"  всего строк:                 {before['total']}")
        print(f"  с balance_after == 0:        {before['zero']}")
        print(f"  balance_after последней:     {before['last']}")
        print(f"  Σ(income − expense) группы:  {before['total_sum']}")

        if before["total"] == 0:
            print("\nСтрок без л/с нет — пересчитывать нечего.")
            return

        if not apply_mode:
            print("\ndry-run: для пересчёта выполните скрипт с ключом --apply")
            return

        recalculate_cash_balance(db, None)
        db.commit()

        after = _stats(db)
        print("\nПрименено:")
        print(f"  balance_after последней:     {after['last']}")
        print(f"  Σ(income − expense) группы:  {after['total_sum']}")
        print(f"  строк с balance_after == 0:  {after['zero']}")
        ok = after["last"] is not None and abs(after["last"] - after["total_sum"]) < 0.01
        print(f"  контроль (последняя == Σ):   {'OK' if ok else 'РАСХОЖДЕНИЕ'}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
