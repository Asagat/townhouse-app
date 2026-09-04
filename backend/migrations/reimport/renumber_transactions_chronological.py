# backend/migrations/reimport/renumber_transactions_chronological.py
"""Перенумеровывает документы «Приход/Расход» (transactions) в хронологическом порядке.

Цель: «Начальный остаток» (общий входящий остаток кассы дома, без лицевого счёта)
становится первой записью (id/doc_no = 1), далее всё идёт по возрастанию даты, а
внутри одной даты сначала идут общие «входящие остатки» (account_id IS NULL и статья
kind='opening'), затем остальные приходы/расходы (сохраняя стабильный прежний порядок).

Переприсвоение id каскадно затрагивает:
  - cash_register.transaction_id  (1:1 с транзакцией, NOT NULL) — обновляется парно;
  - accounts_register            (срез пересоздаётся заново ядром rebuild_accounts_register);
  - transactions.doc_no           = новый id (сквозной хронологический номер).

Всё выполняется в ОДНОЙ транзакции; при сбое — полный откат.

Запуск (в контейнере backend):
    python migrations/reimport/renumber_transactions_chronological.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import text  # noqa: E402

import database  # noqa: E402
from writeoffs import rebuild_accounts_register  # noqa: E402


def main() -> int:
    db = database.SessionLocal()
    try:
        # --- Предикат «общий входящих остаток дома»: статья kind='opening' И без л/с.
        opening_kind_ids = {
            r[0] for r in db.execute(
                text("SELECT id FROM analytic_articles WHERE kind='opening'")
            ).fetchall()
        }

        rows = db.execute(
            text("SELECT id, transaction_date, account_id, article_id, doc_no FROM transactions")
        ).fetchall()
        recs = [dict(r._mapping) for r in rows]

        def is_house_opening(r: dict) -> bool:
            return r["account_id"] is None and r["article_id"] in opening_kind_ids

        # Хронологическая сортировка:
        #   1) по дате,
        #   2) внутри даты — общие входящих остатки (без л/с) первыми,
        #   3) иначе — стабильно по текущему id (прежний относительный порядок).
        recs.sort(key=lambda r: (
            str(r["transaction_date"]),
            0 if is_house_opening(r) else 1,
            r["id"],
        ))

        old_to_new: dict[int, int] = {}
        for rank, r in enumerate(recs, start=1):
            old_to_new[int(r["id"])] = rank
        n = len(recs)
        print(f"Перенумеровываем транзакций: {n}.")

        # На время переименования снимаем FK (они носят technical ссылки на id транзакции
        # и заново создаются ниже идентичными). Без снятия UPDATE по id транзакции
        # нарушал бы целостность cash_register посреди изменения.
        db.execute(text(
            "ALTER TABLE cash_register DROP CONSTRAINT cash_register_transaction_id_fkey"
        ))
        db.execute(text(
            "ALTER TABLE accounts_register DROP CONSTRAINT accounts_register_transaction_id_fkey"
        ))

        # --- Фаза 1: переносим id в отрицательную «буферную» зону (избегает коллизий). ---
        for r in recs:
            oid = int(r["id"])
            nid = -oid
            db.execute(text("UPDATE transactions SET id=:n WHERE id=:o"), {"n": nid, "o": oid})
            db.execute(text("UPDATE cash_register SET transaction_id=:n WHERE transaction_id=:o"),
                       {"n": nid, "o": oid})

        # --- Фаза 2: ставим новые хронологические id. ---
        for r in recs:
            oid = int(r["id"])
            new_id = old_to_new[oid]
            db.execute(text("UPDATE transactions SET id=:n WHERE id=:o"), {"n": new_id, "o": -oid})
            db.execute(text("UPDATE cash_register SET transaction_id=:n WHERE transaction_id=:o"),
                       {"n": new_id, "o": -oid})

        # doc_no = новый сквозной хронологический номер.
        stmt = text(
            "WITH x AS (SELECT id, row_number() OVER (ORDER BY id ASC) rn FROM transactions) "
            "UPDATE transactions t SET doc_no = x.rn FROM x WHERE t.id = x.id"
        )
        db.execute(stmt)

        # Последовательность под max(id).
        db.execute(text("SELECT setval('transactions_id_seq', (SELECT max(id) FROM transactions))"))

        # Восстанавливаем FK кассы (уже на новые id).
        db.execute(text(
            "ALTER TABLE cash_register ADD CONSTRAINT cash_register_transaction_id_fkey "
            "FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE"
        ))
        db.commit()
        print("Транзакции (ид + cash_register) перенумерованы и doc_no обновлён.")

        # --- Пересборка производного регистра взаиморасчётов (связь по новым id). ---
        res = rebuild_accounts_register(db)
        # Пересоздаём FK accounts_register->transactions (после пересоздания среза.).
        db.execute(text(
            "ALTER TABLE accounts_register ADD CONSTRAINT accounts_register_transaction_id_fkey "
            "FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE"
        ))
        db.commit()
        print(f"Регистр взаиморасчётов пересобран: счетов={len(res['processed'])}.")

        # Контроль: Начальный остаток id/doc_no=1.
        top = db.execute(text(
            "SELECT id, doc_no, COALESCE(amount,0) amt, COALESCE(notes,'') notes "
            "FROM transactions ORDER BY id ASC LIMIT 3"
        )).fetchall()
        for t in top:
            print("  первая запись ->", tuple(t))
        print("ГОТОВО.")
    except Exception:
        db.rollback()
        print("СБОЙ — изменения ОТКАЧЕНЫ полностью.")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
