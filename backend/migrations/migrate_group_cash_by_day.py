"""
Идемпотентный скрипт-починка: свёртка «Приход в кассу» жителей в один документ
на квартиру/день.

Для уже импортированной БД (этап кассы проводился до добавления группировки в
`migrations/migrate_synthetic/cash.py`) каждая строка-приход по жителю
порождала ОТДЕЛЬНЫЙ документ `Transaction`, поэтому по одной квартире/дате
появлялось несколько «Приход в кассу» (например, 4 документа вместо 1).

Тут действует та же договорённость, что и на этапе синтеза:
  - жительские приходы (`transaction_type='in_cash'`, статья «Поступления от
    жителей», есть лицевой счёт) одной ДАТЫ сворачиваются в ОДИН документ:
    за «хозяина»/keeper берётся младший `id` группы, суммы остальных
    переносятся в него, `notes` объединяются, лишние документы удаляются;
  - сторно-проводки (`notes` содержит `[СТОРНО]`), «входящее сальдо кассы»
    и расходы НЕ сворачиваются;
  - учитываются только документы, созданные миграционным пользователем
    (`username='migration'`) — пользовательские документы не трогаем.

После правки кассы для каждого затронутого счёта вызывается штатный механизм
`rebuild_accounts_register` (первичные регистры делают производный срез
`accounts_register` детерминированно пересоздаваемым), т.к. строки списания
в нём привязаны к конкретным документам «Приход/Расход» (`transaction_id`), и
их надо перестроить по уже свернутой кассе.

Скрипт идемпотентен: повторный запуск находит пустое множество групп
(размер>1), а при необходимости «развернуть» перенос — достаточно пересоздать
кассу заново (`cash.py`) и вызвать `rebuild_accounts_register`.

Запуск из каталога backend:
    python migrations/migrate_group_cash_by_day.py             # сухой прогон (ничего не меняет)
    python migrations/migrate_group_cash_by_day.py --apply     # применить изменения
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from database import SessionLocal  # noqa: E402
from writeoffs import rebuild_accounts_register  # noqa: E402


# Группа: набор документов прихода одного счёта/даты/кассы/статьи, подлежащих
# сведению в один keeper. keeper — минимальный id (первичный по хронологии вставки).
def _find_groups(db, mig_id, income_article_id, limit=None):
    params = {"mig": mig_id, "art": income_article_id}
    lim = f" LIMIT {int(limit)}" if limit else ""
    rows = db.execute(
        text(
            """
            SELECT account_id,
                   transaction_date::date AS day,
                   cash_point_id,
                   article_id,
                   count(*)          AS cnt,
                   min(id)           AS keeper
            FROM transactions
            WHERE transaction_type = 'in_cash'
              AND account_id IS NOT NULL
              AND created_by = :mig
              AND article_id = :art
              AND (notes IS NULL OR (notes NOT LIKE '%[СТОРНО]%'
                                     AND notes NOT LIKE 'Начальный остаток кассы%'))
            GROUP BY account_id, transaction_date::date, cash_point_id, article_id
            HAVING count(*) > 1
            ORDER BY count(*) DESC, account_id, transaction_date::date
            """
            + lim
        ),
        params,
    ).mappings().all()
    return list(rows)


def _migration_user(db):
    row = db.execute(
        text("SELECT id FROM users WHERE username = 'migration'"), {}
    ).first()
    return row[0] if row else None


def _income_article(db):
    row = db.execute(
        text(
            "SELECT id FROM analytic_articles "
            "WHERE name = 'Поступления от жителей' AND kind = 'income' LIMIT 1"
        ),
        {},
    ).first()
    return row[0] if row else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="применить правки (без флага — только сухой прогон)")
    ap.add_argument("--limit", type=int, default=None,
                    help="ограничить число обрабатываемых групп (для контроля)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        mig_id = _migration_user(db)
        art_id = _income_article(db)
        if mig_id is None or art_id is None:
            print("Не найден миграционный пользователь или статья «Поступления от жителей».")
            return 1

        groups = _find_groups(db, mig_id, art_id, args.limit)
        if not groups:
            print("Групп для свёртки нет — БД уже соответствует договорённости "
                  "«один приход на квартиру/день» (идемпотентно).")
            return 0

        donors_total = 0
        affected_accounts: set[int] = set()
        for g in groups:
            acct = g["account_id"]
            cup = g["cash_point_id"]
            art = g["article_id"]
            dz = g["day"]
            gk = g["keeper"]
            members = db.execute(
                text(
                    """
                    SELECT id, amount, COALESCE(NULLIF(notes, ''), '') AS note
                    FROM transactions
                    WHERE transaction_type = 'in_cash'
                      AND account_id = :a AND cash_point_id = :cp AND article_id = :art
                      AND transaction_date::date = :dz
                      AND created_by = :mig
                      AND (notes IS NULL OR (notes NOT LIKE '%[СТОРНО]%'
                                             AND notes NOT LIKE 'Начальный остаток кассы%'))
                    ORDER BY id
                    """
                ),
                {"a": acct, "cp": cup, "art": art, "dz": dz, "mig": mig_id},
            ).mappings().all()

            keep = members[0]
            if int(keep["id"]) != int(gk):  # защита: первый по id == keeper
                print("Внутренняя ошибка порядка группы:", g)
                continue
            donors = [m for m in members[1:]]
            donors_total += len(donors)
            total = sum((Decimal(m["amount"]) for m in members), Decimal(0))

            # Эмулируем поведение cash-импорта: keeper хранит суммарный приход и
            # объединённый список комментариев групп (уникальные, через «; »).
            seen = []
            for m in members:
                if m["note"] and m["note"] not in seen:
                    seen.append(m["note"])
            combined_notes = "; ".join(seen)

            print(
                f"  {dz} | счёт {acct} | касса {cup} | групп {g['cnt']}->1 | "
                f"keeper №{gk} | сумма {total}"
            )
            if not args.apply:
                continue

            # 1) Свёртка кассы: income переносим в keeper, amount keeper = total.
            db.execute(
                text(
                    """
                    UPDATE cash_register
                    SET income = :total
                    WHERE transaction_id = :gk
                    """
                ),
                {"total": total, "gk": gk},
            )
            db.execute(
                text(
                    """
                    UPDATE transactions SET amount = :total, notes = :notes
                    WHERE id = :gk
                    """
                ),
                {"total": total, "notes": combined_notes, "gk": gk},
            )
            # 2) Удаление «лишних» документов: строки cash_register и строки списания
            #    accounts_register за эти документы удаляются каскадом СУБД.
            for d in donors:
                db.execute(text("DELETE FROM transactions WHERE id = :id"), {"id": int(d["id"])})
            affected_accounts.add(acct)

        if args.apply:
            # Производный срез accounts_register пересоздаётся из первичных регистров
            # по свернутой кассе (детерминированно).
            if affected_accounts:
                rebuild_accounts_register(db, sorted(affected_accounts))
            db.commit()
            print("Готово.")
            print("Свёрнуто групп:", len(groups))
            print("Перенесено/удалено документов:", donors_total)
            print("balances пересчитаны через rebuild_accounts_register.")
        else:
            print("\n[СУХОЙ ПРОГОН] Групп:", len(groups), "| будет удалено документов:",
                  donors_total, "| счетов:", len({g['account_id'] for g in groups}))
            print("Запустите с флагом --apply для применения.")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        import traceback
        traceback.print_exc()
        print("ОШИБКА:", exc)
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
