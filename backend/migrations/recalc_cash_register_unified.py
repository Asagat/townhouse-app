"""
Пересчёт balance_after в Регистре денежных средств (cash_register) под НОВУЮ
семантику ТД-6: нарастающий остаток денег ПО КАССЕ/СЧЁТУ (`cash_point_id`).

Причина: раньше `balance_after` считался как сальдо ЛИЦЕВОГО СЧЁТА (группа по
`account_id`), из-за чего в группе строк без л/с накапливался «мусор» (например,
−58 691 998 ₸), а фактический остаток кассы нигде не читался. Теперь это
нарастающий остаток по каждому кэшпоинту, и последняя строка каждого из них
равна Σ(income − expense) по нему.

Что делает:
  1. dry-run: показывает «до» — строк всего, строк с расхождением (balance_after
     != ожидаемый нарастающий итог), Σ(income − expense) по всей кассе и итог по
     каждой кассе/счёту (последняя строка vs Σ);
  2. --apply: пересчитывает весь регистр штатным механизмом
     (`models.recalculate_cash_register_balance`);
  3. печатает контроль «после»: у каждой кассы последняя строка == Σ по ней;
     Σ по всей таблице == фактическому остатку денег.

Требует применённой миграции `0021_cash_register_cash_point` (колонка
`cash_register.cash_point_id` + бэкфилл из `transactions`).

Запуск из каталога backend:
    python migrations/recalc_cash_register_unified.py            # dry-run
    python migrations/recalc_cash_register_unified.py --apply    # применить
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import recalculate_cash_register_balance  # noqa: E402


def _summary(db) -> dict:
    """«До»/«после»: тотал по таблице, число расхождений и разбивка по кэшпоинтам."""
    total = db.execute(
        text("""
            SELECT count(*), COALESCE(SUM(income - expense), 0)
            FROM cash_register
        """)
    ).first()

    mismatch = db.execute(
        text("""
            WITH ordered AS (
                SELECT id,
                       SUM(income - expense) OVER (
                           PARTITION BY cash_point_id
                           ORDER BY operation_date ASC, id ASC
                       ) AS running
                FROM cash_register
            )
            SELECT count(*)
            FROM cash_register cr
            JOIN ordered o ON o.id = cr.id
            WHERE cr.balance_after IS DISTINCT FROM o.running
        """)
    ).scalar()

    # Итог по каждому кэшпоинту: сколько строк, Σ(income − expense),
    # balance_after последней строки (по (operation_date, id)).
    points = db.execute(
        text("""
            WITH agg AS (
                SELECT cash_point_id,
                       count(*) AS rows,
                       COALESCE(SUM(income - expense), 0) AS total
                FROM cash_register
                GROUP BY cash_point_id
            ),
            last AS (
                SELECT DISTINCT ON (cash_point_id)
                       cash_point_id, balance_after
                FROM cash_register
                ORDER BY cash_point_id, operation_date DESC, id DESC
            )
            SELECT agg.cash_point_id, agg.rows, agg.total, last.balance_after
            FROM agg
            LEFT JOIN last ON last.cash_point_id IS NOT DISTINCT FROM agg.cash_point_id
            ORDER BY agg.cash_point_id NULLS FIRST
        """)
    ).all()

    return {
        "rows": total[0],
        "total_sum": float(total[1]),
        "mismatch": mismatch,
        "points": [
            {
                "cash_point_id": p[0],
                "rows": p[1],
                "total": float(p[2]),
                "last": float(p[3]) if p[3] is not None else None,
            }
            for p in points
        ],
    }


def _print_summary(title: str, data: dict) -> None:
    print(title)
    print(f"  всего строк:                 {data['rows']}")
    print(f"  строк с расхождением:        {data['mismatch']}")
    print(f"  Σ(income − expense) по кассе: {data['total_sum']:.2f}")
    print("  по кассам/счетам (cash_point_id):")
    for p in data["points"]:
        cid = "без кассы (NULL)" if p["cash_point_id"] is None else p["cash_point_id"]
        ok = (
            p["last"] is not None
            and abs(p["last"] - p["total"]) < 0.01
        )
        print(
            f"    {cid}: строк {p['rows']}, "
            f"Σ {p['total']:.2f}, последняя {p['last']}, "
            f"{'OK' if ok else 'РАСХОЖДЕНИЕ'}"
        )


def _all_ok(data: dict) -> bool:
    return all(
        p["last"] is not None and abs(p["last"] - p["total"]) < 0.01
        for p in data["points"]
    )


def main() -> None:
    apply_mode = "--apply" in sys.argv
    db = SessionLocal()
    try:
        before = _summary(db)
        _print_summary("Касса «до» пересчёта:", before)

        if not apply_mode:
            print("\ndry-run: для пересчёта выполните скрипт с ключом --apply")
            return

        recalculate_cash_register_balance(db)
        db.commit()

        after = _summary(db)
        print()
        _print_summary("Касса «после» пересчёта:", after)
        print(f"\n  контроль (все кассы: последняя == Σ): "
              f"{'OK' if _all_ok(after) else 'РАСХОЖДЕНИЕ'}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
