"""
Удаление «двойников» тарифов-периодов (дублей, оставшихся от конверсии 2.18).

Проблема (11.09.2026): миграция `0018_tariff_period_conversion` для каждого
исторического разового сбора месяца создала ЗАКРЫТЫЙ тариф-период (`valid_to` = конец
месяца, комментарий «Конверсия 2.18…») и оставила ОТКРЫТЫЙ тариф с той же датой начала
(`valid_to IS NULL`) — как «базу» того месяца. Последующие реальные изменения базовой
ставки вытесняли такие открытые «двойники», но последний по каждой услуге остался
«бессрочной базой»:

  * Фонд развития, id 35 (148 850 ₸, с 01.04.2026): `resolve_tariff_for_accrual_period`
    игнорирует поле `status` и для месяцев без закрытого тарифа берёт ПОСЛЕДНИЙ
    открытый тариф с датой начала ≤ конца месяца — поэтому любое НОВОЕ начисление
    с мая 2026 подставляло 148 850 ₸/мес вместо базовых 2 000 ₸ (id 24);
  * всего 11 таких пар: «Фонд развития» (25, 26, 27, 171, 172, 32, 35),
    «Охрана» (28, 29, 34), «Обслуживание ТП» (33).

Критерий «двойника» (жёсткий, чтобы не тронуть легитимные тарифы):
  * открытый тариф (`valid_to IS NULL`);
  * существует закрытый тариф того же вида услуги с ТОЙ ЖЕ датой начала (`valid_from`)
    и комментарием «Конверсия 2.18…»;
  * на открытый тариф нет НИ ОДНОЙ ссылки в `accruals_register` (месяц разового сбора
    полностью покрыт закрытым тарифом-периодом, поэтому открытый «двойник» избыточен —
    он ошибочно продлевает разовую сумму как бессрочную базу).

Что делает скрипт:
  1. dry-run (по умолчанию): печатает найденные пары, ссылки и план удаления, а также
     какую ставку расчёт выберет для ТЕКУЩЕГО месяца по каждой услуге;
  2. `--apply`: удаляет «двойники» (если на тариф есть ссылки — НЕ удаляет, пишет
     предупреждение; FK `accruals_register.tariff_id` — RESTRICT, дополнительная защита);
  3. `--apply --normalize-status`: дополнительно приводит статусы к смыслу «Действующий =
     действует сейчас»: у каждой услуги «Действующим» остаётся ровно один тариф — тот,
     который расчёт применяет для текущего месяца, остальные — «Архивный» (иначе в фильтре
     «Действующие» висят исторические разовые сборы).

Правка касается ТОЛЬКО справочника тарифов: строки `accruals_register`/`accounts_register`
не меняются, суммы начислений не пересчитываются. После применения — контроль:
`python migrations/accruals_sum_check.py` и/или `check_register_integrity` (регистры не
затрагивались, поэтому пересчёт балансов не требуется).

Идемпотентно: повторный запуск на почищенной базе ничего не находит.

Запуск из каталога backend:
    python migrations/fix_duplicate_open_tariffs.py                          # dry-run
    python migrations/fix_duplicate_open_tariffs.py --apply
    python migrations/fix_duplicate_open_tariffs.py --apply --normalize-status
"""

import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from database import SessionLocal  # noqa: E402
from services import (  # noqa: E402
    TARIFF_STATUS_ACTIVE,
    TARIFF_STATUS_ARCHIVED,
    resolve_tariff_for_accrual_period,
)

TWINS_SQL = text("""
    SELECT o.id AS open_id, st.services_type,
           o.price AS open_price, c.price AS closed_price,
           o.valid_from, c.id AS closed_id,
           (SELECT count(*) FROM accruals_register ar WHERE ar.tariff_id = o.id) AS refs
    FROM tariffs o
    JOIN services_type st ON st.id = o.services_type_id
    JOIN tariffs c
      ON c.services_type_id = o.services_type_id
     AND c.valid_from = o.valid_from
     AND c.valid_to IS NOT NULL
     AND c.comment LIKE 'Конверсия 2.18%'
    WHERE o.valid_to IS NULL
    ORDER BY st.services_type, o.valid_from, o.id
""")


def _services(db):
    return [
        (int(r[0]), str(r[1]))
        for r in db.execute(
            text("SELECT id, services_type FROM services_type ORDER BY id")
        ).fetchall()
    ]


def _base_after_exclusion(db, services_type_id, period_end, excluded_ids):
    """Прогноз `resolve_tariff_for_accrual_period` с исключением удаляемых тарифов.

    Повторяет приоритеты расчёта (закрытый тариф периода → последний открытый
    с valid_from ≤ конца месяца), пропуская открытые тарифы из excluded_ids.
    """
    month_start = date(period_end.year, period_end.month, 1)
    closed = db.execute(
        text(
            "SELECT id, price, valid_from, valid_to FROM tariffs "
            "WHERE services_type_id = :sid AND valid_from <= :pe "
            "AND valid_to IS NOT NULL AND valid_to >= :ms "
            "ORDER BY valid_from DESC, id DESC LIMIT 1"
        ),
        {"sid": services_type_id, "pe": period_end, "ms": month_start},
    ).fetchone()
    if closed is not None:
        return closed
    for r in db.execute(
        text(
            "SELECT id, price, valid_from, valid_to FROM tariffs "
            "WHERE services_type_id = :sid AND valid_to IS NULL AND valid_from <= :pe "
            "ORDER BY valid_from DESC, id DESC"
        ),
        {"sid": services_type_id, "pe": period_end},
    ).fetchall():
        if int(r[0]) not in excluded_ids:
            return r
    return None


def _print_projected_bases(db, today, excluded_ids):
    print(f"\nПосле очистки — прогноз «базы» на {today.isoformat()}:")
    for sid, name in _services(db):
        r = _base_after_exclusion(db, sid, today, excluded_ids)
        if r is None:
            print(f"  {name:<24} — тарифа нет")
            continue
        vto = r[3].isoformat() if r[3] else "NULL"
        print(f"  {name:<24} — id {r[0]:<4} {float(r[1]):>14,.2f}  [{r[2]} .. {vto}]")


def _print_current_bases(db, today):
    print(f"\nТекущая «база» по услугам (расчёт для {today.isoformat()}):")
    for sid, name in _services(db):
        t = resolve_tariff_for_accrual_period(db, sid, today)
        if t is None:
            print(f"  {name:<24} — тарифа нет")
            continue
        vto = t.valid_to.isoformat() if t.valid_to else "NULL"
        print(
            f"  {name:<24} — id {t.id:<4} {float(t.price):>14,.2f}  "
            f"[{t.valid_from} .. {vto}]  status={t.status}"
        )


def _normalize_statuses(db, today):
    """«Действующий» — ровно один тариф услуги: применяемый для текущего месяца."""
    changed = 0
    for sid, name in _services(db):
        keep = resolve_tariff_for_accrual_period(db, sid, today)
        keep_id = keep.id if keep else None
        if keep_id is not None:
            db.execute(
                text(
                    "UPDATE tariffs SET status = :arch "
                    "WHERE services_type_id = :sid AND id <> :keep"
                ),
                {"arch": TARIFF_STATUS_ARCHIVED, "sid": sid, "keep": keep_id},
            )
            res = db.execute(
                text("UPDATE tariffs SET status = :act WHERE id = :keep"),
                {"act": TARIFF_STATUS_ACTIVE, "keep": keep_id},
            )
        else:
            res = db.execute(
                text("UPDATE tariffs SET status = :arch WHERE services_type_id = :sid"),
                {"arch": TARIFF_STATUS_ARCHIVED, "sid": sid},
            )
        changed += res.rowcount or 0
    return changed


def main():
    parser = argparse.ArgumentParser(
        description="Удаление «двойников» тарифов-периодов (конверсия 2.18)"
    )
    parser.add_argument("--apply", action="store_true", help="применить изменения")
    parser.add_argument(
        "--normalize-status",
        action="store_true",
        help="вместе с --apply: «Действующий» — ровно один тариф на услугу",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = db.execute(TWINS_SQL).fetchall()
        today = date.today()

        print(f"Открытых «двойников» тарифов-периодов найдено: {len(rows)}")
        if not rows:
            print("  ничего — база уже почищена (скрипт идемпотентен).")
        for r in rows:
            m = r._mapping
            price_note = ""
            if m["open_price"] != m["closed_price"]:
                price_note = (
                    f"  ⚠ цена отличается от закрытого (id {m['closed_id']}: "
                    f"{float(m['closed_price']):,.2f})"
                )
            print(
                f"  id {m['open_id']:<4} {m['services_type']:<24} "
                f"{float(m['open_price']):>14,.2f}  с {m['valid_from']}  "
                f"ссылок в начислениях: {m['refs']}  (закрытый id {m['closed_id']})"
                f"{price_note}"
            )

        if not args.apply:
            _print_current_bases(db, today)
            _print_projected_bases(
                db, today, {int(r._mapping["open_id"]) for r in rows}
            )
            print(
                "\n[dry-run] Изменений не вносилось.\n"
                "Применить: --apply (и опционально --normalize-status)."
            )
            return

        deleted = 0
        skipped = 0
        for r in rows:
            m = r._mapping
            if int(m["refs"]) > 0:
                print(
                    f"  ПРОПУСК id {m['open_id']}: есть {m['refs']} ссылок "
                    "в accruals_register"
                )
                skipped += 1
                continue
            db.execute(
                text("DELETE FROM tariffs WHERE id = :id"), {"id": int(m["open_id"])}
            )
            deleted += 1
        db.flush()
        db.expire_all()

        if args.normalize_status:
            changed = _normalize_statuses(db, today)
            print(f"Нормализация статусов: обновлено записей {changed}")

        db.commit()
        print(
            f"\n[apply] Удалено «двойников»: {deleted}"
            + (f", пропущено: {skipped}" if skipped else "")
        )

        _print_current_bases(db, today)
        print(
            "\nКонтроль (рекомендуется): python migrations/accruals_sum_check.py "
            "и/или check_register_integrity."
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
