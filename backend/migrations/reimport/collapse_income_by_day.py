# backend/migrations/reimport/collapse_income_by_day.py
"""Свёртка приходов в один документ на (лицевой счёт, день) без отрицательных приходов.

Проблема: в старой базе не было лицевых счетов, поэтому переплаты жителей относились
на статью «Фонд развития», а при очередном взносе «снимались» с неё отрицательными
строками «Приход в кассу». В итоге в истории по одному л/с за день лежит несколько
документов «Приход в кассу», среди которых есть отрицательные суммы (статья
«Входящий остаток»).

Правило свёртки (по договорённости, 09.2026):
  - группа = ВСЕ приходы (transaction_type='in_cash') одного лицевого счёта за одну
    дату (transaction_date::date), кроме возвратов от контрагентов (это не платёж
    жителя — они остаются отдельными документами);
  - «keeper» = младший id группы; сумма документа = НЕТТО группы (алгебраическая
    сумма всех строк дня), статья = «Поступления от жителей», notes объединяются;
  - остальные документы группы удаляются (каскадно — их строки cash_register и
    accounts_register);
  - если нетто дня <= 0 — реального прихода в этот день не было (только технические
    корректировки): документы дня УДАЛЯЮТСЯ, но такие случаи полностью печатаются
    (нужен разбор владельцем — в данных 09.2026 таких дней нет).

После свёртки для каждого затронутого л/с:
  - пересчитываются balance_after в cash_register (recalculate_cash_balance);
  - пересоздаётся срез accounts_register (rebuild_accounts_register).

Сумма приходов по каждому счёту НЕ меняется (нетто сохраняется) — меняется только
количество документов, поэтому квитанции пересоздавать не нужно (при отсутствии
дней с нетто<=0). Если такие дни появятся — их удаление меняет балансы, и по этим
счетам квитанции надо будет пересматривать вручную.

Идемпотентен: повторный запуск не находит групп размером >1.

Запуск:
    python migrations/reimport/collapse_income_by_day.py            # dry
    python migrations/reimport/collapse_income_by_day.py --apply
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import text  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import recalculate_cash_balance  # noqa: E402
from writeoffs import rebuild_accounts_register  # noqa: E402

_GROUP_SELECT = """
    SELECT t.account_id,
           t.transaction_date::date AS dz,
           min(t.id) AS keeper,
           count(*) AS cnt,
           sum(t.amount) AS net,
           sum(t.amount) FILTER (WHERE t.amount < 0) AS neg_sum
    FROM transactions t
    JOIN analytic_articles a ON a.id = t.article_id
    WHERE t.transaction_type = 'in_cash'
      AND t.account_id IS NOT NULL
      AND a.name <> 'Возвраты от контрагентов'
    GROUP BY t.account_id, t.transaction_date::date
    HAVING count(*) > 1
    ORDER BY t.account_id, t.transaction_date::date
"""

_MEMBERS_SELECT = """
    SELECT t.id, t.amount, COALESCE(NULLIF(t.notes, ''), '') AS note
    FROM transactions t
    JOIN analytic_articles a ON a.id = t.article_id
    WHERE t.transaction_type = 'in_cash'
      AND t.account_id = :a
      AND t.transaction_date::date = :dz
      AND a.name <> 'Возвраты от контрагентов'
    ORDER BY t.id
"""


def _income_article(db) -> int | None:
    return db.execute(text(
        "SELECT id FROM analytic_articles "
        "WHERE name='Поступления от жителей' AND kind='income' LIMIT 1"
    )).scalar()


def _groups(db):
    return [dict(r._mapping) for r in db.execute(text(_GROUP_SELECT)).fetchall()]


def _members(db, account_id, dz):
    return [dict(r._mapping) for r in db.execute(
        text(_MEMBERS_SELECT), {"a": account_id, "dz": dz}).fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="применить изменения")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        income_art = _income_article(db)
        if income_art is None:
            print("Статья «Поступления от жителей» не найдена.")
            db.close()
            return 1
        groups = _groups(db)
        if not groups:
            print("Групп для свёртки нет (уже свёрнуто / идемпотентно).")
            db.close()
            return 0

        if not args.apply:
            net_le0 = [g for g in groups if g["net"] <= 0]
            print("[СУХОЙ ПРОГОН] Групп (счёт, день):", len(groups))
            print("  будет удалено документов-«доноров»:",
                  sum(g["cnt"] - 1 for g in groups))
            print("  счетов затронуто:", len({g["account_id"] for g in groups}))
            print("  групп с нетто <= 0:", len(net_le0))
            for g in net_le0:
                print("    ТРЕБУЕТ РАЗБОРА: счёт", g["account_id"],
                      "дата", g["dz"], "строк", g["cnt"], "нетто", g["net"])
            print("Запустите с --apply.")
            db.close()
            return 0

        affected = set()
        donors = 0
        net_le0_cases = []
        merged = 0
        before_rows = 0
        before_sum = Decimal(0)

        for g in groups:
            rows = _members(db, g["account_id"], g["dz"])
            if not rows:
                continue
            keeper = int(rows[0]["id"])  # группа отсортирована по id => младший id
            net = sum((Decimal(r["amount"]) for r in rows), Decimal(0))
            before_rows += len(rows)
            before_sum += net
            seen = []
            for r in rows:
                n = (r["note"] or "").strip()
                if n and n not in seen:
                    seen.append(n)
            combined = "; ".join(seen)

            if net <= 0:
                # Реального прихода в этот день не было — удаляем все документы дня.
                net_le0_cases.append({"account_id": g["account_id"], "dz": g["dz"],
                                      "net": net, "ids": [int(r["id"]) for r in rows]})
                for r in rows:
                    db.execute(text("DELETE FROM transactions WHERE id=:id"),
                               {"id": int(r["id"])})
                donors += len(rows)
                affected.add(int(g["account_id"]))
                continue

            # keeper получает нетто дня и статью «Поступления от жителей».
            db.execute(text(
                "UPDATE transactions SET amount=:t, notes=:n, article_id=:art "
                "WHERE id=:k"),
                {"t": net, "n": combined or None, "art": income_art, "k": keeper})
            db.execute(text(
                "UPDATE cash_register SET income=:t WHERE transaction_id=:k"),
                {"t": net, "k": keeper})
            for r in rows[1:]:
                db.execute(text("DELETE FROM transactions WHERE id=:id"),
                           {"id": int(r["id"])})
            donors += len(rows) - 1
            affected.add(int(g["account_id"]))
            merged += 1

        if not affected:
            print("Нечего применять.")
            db.close()
            return 0

        # Пересчёт кассовых остатков и пересборка взаиморасчётов по затронутым счетам.
        acc_ids = sorted(affected)
        for acc in acc_ids:
            recalculate_cash_balance(db, acc)
        rebuild_accounts_register(db, acc_ids)
        db.commit()

        # Контрольные суммы по квартирам.
        print("ГОТОВО.")
        print("  групп свёрнуто (нетто > 0):", merged,
              "| удалено документов:", donors,
              "| счетов:", len(acc_ids))
        print("  групп с нетто <= 0 (удалены, требуют разбора):", len(net_le0_cases))
        for c in net_le0_cases:
            print("    РАЗБОР: счёт", c["account_id"], "дата", c["dz"],
                  "нетто", c["net"], "удалены id:", c["ids"])

        print("\nКонтроль по квартирам (счёт: документов/сумма приходов после свёртки):")
        total_docs = 0
        total_sum = Decimal(0)
        q = db.execute(text("""
            SELECT t.account_id, a.apartment_number,
                   count(*) AS docs, sum(t.amount) AS s
            FROM transactions t
            JOIN accounts ac ON ac.id = t.account_id
            LEFT JOIN apartments a ON a.id = ac.apartment_id
            WHERE t.transaction_type = 'in_cash' AND t.account_id IS NOT NULL
              AND t.article_id = (SELECT id FROM analytic_articles
                                  WHERE name='Поступления от жителей' LIMIT 1)
            GROUP BY t.account_id, a.apartment_number
            ORDER BY a.apartment_number
        """))
        for r in q.fetchall():
            apt = r[1] if r[1] is not None else "?"
            print(f"  кв {apt:>3} | счёт {r[0]:>3} | документов {r[2]:>3} | "
                  f"приход {Decimal(r[3]):,.2f}")
            total_docs += r[2]
            total_sum += Decimal(r[3])
        print(f"ИТОГО приходов «Поступления от жителей»: документов {total_docs}, "
              f"сумма {total_sum:,.2f}")
        print("(сумма нетто приходов сохранена; квитанции пересоздавать не требуется)")

        # Сверка: сумма нетто по свёрнутым группам сохраняется (до == после).
        after = sum(
            (Decimal(g["net"]) for g in groups if g["net"] > 0), Decimal(0))
        neg_left = db.execute(text(
            "SELECT count(*) FROM transactions WHERE transaction_type='in_cash' "
            "AND amount < 0")).scalar()
        print(f"Сверка по свёрнутым группам (счёт, день): до {before_sum:,.2f} | "
              f"после {after:,.2f} | разница {before_sum - after:,.2f}")
        print(f"Отрицательных приходов в БД осталось: {neg_left}")
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
