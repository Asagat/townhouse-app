# backend/migrations/reimport/group_resident_income_by_day.py
"""Свёртка жительских приходов «Поступления от жителей» в один документ
на (лицевой счёт, день, касса, статья, комментарий).

Проблема: история внесена построчно — на один платёж квартиры за день создано
несколько документов «Приход в кассу» с одинаковым смыслом (номером-комментарием),
которые по договорённости должны быть одним документом на квартиру/день.

Правило (консервативное, notes-aware):
  - берутся жительские приходы (transaction_type='in_cash'), у которых есть лицевой
    счёт и статья «Поступления от жителей»;
  - группа = все строки, совпадающие по (account_id, cash_point_id, article_id,
    transaction_date::date, COALESCE(notes,'')) — то есть ОДИН платёж, разбитый
    на суммы или продублированный;
  - «keeper» = младший id группы: получает суммарную сумму, notes объединяются
    уникальными через «; »; остальные документы группы удаляются;
  - сторно-[СТОРНО], «Начальный остаток кассы» и расходы НЕ трогаются;
  - ограничения по создателю НЕТ (записи могут быть и без created_by).

После для каждого затронутого л/с пересобирается срез accounts_register
(rebuild_accounts_register), т.к. строки списания в нём привязаны к конкретным
документам «Приход/Расход» (transaction_id).

Идемпотентен: повторный запуск не находит групп размером >1.

Запуск:
    python migrations/reimport/group_resident_income_by_day.py            # dry
    python migrations/reimport/group_resident_income_by_day.py --apply
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import text  # noqa: E402
from database import SessionLocal  # noqa: E402
from writeoffs import rebuild_accounts_register  # noqa: E402

_GROUP_SELECT = """
    SELECT account_id, cash_point_id, article_id,
           transaction_date::date AS dz,
           COALESCE(NULLIF(notes, ''), '<без>') AS note_key,
           min(id) AS keeper, count(*) AS cnt
    FROM transactions
    WHERE transaction_type='in_cash'
      AND account_id IS NOT NULL
      AND article_id = (SELECT id FROM analytic_articles
                        WHERE name='Поступления от жителей' AND kind='income' LIMIT 1)
      AND (notes IS NULL OR (notes NOT LIKE '%%[СТОРНО]%%'
                             AND notes NOT LIKE 'Начальный остаток кассы%%'))
    GROUP BY account_id, cash_point_id, article_id, transaction_date::date, note_key
    HAVING count(*) > 1
"""


def _income_article(db) -> int | None:
    return db.execute(text(
        "SELECT id FROM analytic_articles "
        "WHERE name='Поступления от жителей' AND kind='income' LIMIT 1"
    )).scalar()


def _groups(db, limit=None):
    sql = _GROUP_SELECT
    if limit:
        sql = ("SELECT * FROM ( " + sql + ") z LIMIT :lim")
    params = {"lim": int(limit)} if limit else {}
    return [dict(r._mapping) for r in db.execute(text(sql), params).fetchall()]


def _members(db, acct, cp, art, dz, note_key):
    return db.execute(text(
        """
        SELECT id, amount, COALESCE(NULLIF(notes,''), '') AS note
        FROM transactions
        WHERE transaction_type='in_cash' AND account_id=:a AND cash_point_id=:cp
          AND article_id=:art AND transaction_date::date=:dz
          AND COALESCE(NULLIF(notes,''), '<без>') = :note
          AND (notes IS NULL OR (notes NOT LIKE '%[СТОРНО]%'
                                 AND notes NOT LIKE 'Начальный остаток кассы%'))
        ORDER BY id
        """),
        {"a": acct, "cp": cp, "art": art, "dz": dz, "note": note_key},
    ).fetchall()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    db = SessionLocal()
    try:
        art = _income_article(db)
        if art is None:
            print("Статья «Поступления от жителей» не найдена.")
            db.close(); return 1
        groups = _groups(db, args.limit)
        if not groups:
            print("Групп для свёртки нет (уже свёрнуто / идемпотентно).")
            db.close(); return 0

        affected = set()
        donors = 0
        for g in groups:
            keep = g["keeper"]
            rows = _members(db, g["account_id"], g["cash_point_id"],
                            g["article_id"], g["dz"], g["note_key"])
            # безопасность: keeper должен быть первой строкой членов
            if not rows or int(rows[0][0]) != int(keep):
                print("Пропуск (порядок группы):", g); continue
            total = sum((Decimal(r[1]) for r in rows), Decimal(0))
            seen = []
            for r in rows:
                n = (r[2] or "").strip()
                if n and n not in seen:
                    seen.append(n)
            combined = "; ".join(seen)

            if not args.apply:
                print(f"  {g['dz']} | счёт {g['account_id']} | касса {g['cash_point_id']} "
                      f"| групп {g['cnt']}->1 | keeper №{keep} | сумма {total}")
            else:
                db.execute(text(
                    "UPDATE transactions SET amount=:t, notes=:n WHERE id=:k"),
                    {"t": total, "n": combined or None, "k": keep})
                db.execute(text(
                    "UPDATE cash_register SET income=:t WHERE transaction_id=:k"),
                    {"t": total, "k": keep})
                for r in rows[1:]:
                    db.execute(text("DELETE FROM transactions WHERE id=:id"),
                               {"id": int(r[0])})
                donors += len(rows) - 1
                affected.add(int(g["account_id"]))

        if args.apply:
            if affected:
                rebuild_accounts_register(db, sorted(affected))
            db.commit()
            print("ГОТОВО. Групп свёрнуто:", len(groups),
                  "| удалено документов:", donors,
                  "| затронуто счетов:", len(affected))
        else:
            print("\n[СУХОЙ ПРОГОН] Групп:", len(groups),
                  "| будет удалено документов:",
                  sum(g["cnt"] - 1 for g in groups),
                  "| счетов:", len({g['account_id'] for g in groups}))
            print("Запустите с --apply.")
    except Exception:
        db.rollback()
        import traceback
        traceback.print_exc()
        db.close()
        return 1
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
