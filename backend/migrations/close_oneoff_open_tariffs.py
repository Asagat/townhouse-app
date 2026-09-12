"""
Закрытие «разовых, записанных как бессрочная база» (превращение в тариф-период).

Контекст (12.09.2026). Часть разовых месячных сборов была заведена как ОТКРЫТЫЕ
тарифы (`valid_to IS NULL`), а не как тарифы-периоды. Поскольку
`resolve_tariff_for_accrual_period` берёт последнюю ОТКРЫТУЮ ставку с `valid_from <=
конца месяца` (поле `status` не читает), такая запись продолжает подставляться как
«база» в месяцы, не покрытые закрытым тарифом. Реальные случаи — «Фонд развития»:

  * id 22 — 20 000 ₸ с 01.01.2023 (использован только в янв-2023);
  * id 23 —  8 600 ₸ с 01.04.2023 (использован только в апр-2023).

Скрипт проставляет у таких тарифов `valid_to` = конец месяца старта и переносит
причину в «Примечание». Существующие начисления и регистры НЕ меняются (тарифы
остаются, ссылки `accruals_register.tariff_id` сохраняются).

Цели заданы явно (услуга, дата начала, цена) — скрипт id-независим и идемпотентен.
dry-run дополнительно проверяет: тариф существует и открыт; все его начисления лежат
внутри ОДНОГО месяца, равного месяцу старта; нет пересечения с другим закрытым
периодом той же услуги.

Запуск из каталога backend:
    python migrations/close_oneoff_open_tariffs.py          # dry-run
    python migrations/close_oneoff_open_tariffs.py --apply
"""

import argparse
import calendar
import os
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from database import SessionLocal  # noqa: E402

# Явные цели: услуга, дата начала открытой «разовой» записи, цена.
TARGETS = [
    {"service": "Фонд развития", "valid_from": date(2023, 1, 1), "price": Decimal("20000.00")},
    {"service": "Фонд развития", "valid_from": date(2023, 4, 1), "price": Decimal("8600.00")},
]


def _month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _usage(db, tariff_id: int):
    row = db.execute(
        text(
            "SELECT count(*), min(to_char(accrual_date,'YYYY-MM')), "
            "max(to_char(accrual_date,'YYYY-MM')) "
            "FROM accruals_register WHERE tariff_id = :t"
        ),
        {"t": tariff_id},
    ).fetchone()
    return int(row[0] or 0), row[1], row[2]


def main():
    parser = argparse.ArgumentParser(
        description="Превращение «разовых» открытых тарифов в тарифы-периоды"
    )
    parser.add_argument("--apply", action="store_true", help="применить изменения")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        for t in TARGETS:
            vf: date = t["valid_from"]
            me = _month_end(vf)
            label = f"{t['service']} · {float(t['price']):,.2f} ₸ · с {vf:%d.%m.%Y}"

            svc = db.execute(
                text("SELECT id FROM services_type WHERE services_type = :n"),
                {"n": t["service"]},
            ).fetchone()
            if svc is None:
                print(f"[пропуск] услуга не найдена: {label}")
                continue
            svc_id = int(svc[0])

            row = db.execute(
                text(
                    "SELECT id, status, comment FROM tariffs "
                    "WHERE services_type_id = :s AND valid_from = :vf AND price = :p "
                    "AND valid_to IS NULL"
                ),
                {"s": svc_id, "vf": vf, "p": t["price"]},
            ).fetchone()
            if row is None:
                print(f"[пропуск] открытый тариф не найден (уже закрыт?): {label}")
                continue

            tid = int(row[0])
            refs, first_m, last_m = _usage(db, tid)
            month_label = f"{vf.year}-{vf.month:02d}"
            single_month_ok = refs == 0 or (first_m == last_m == month_label)

            clash = db.execute(
                text(
                    "SELECT id, price FROM tariffs "
                    "WHERE services_type_id = :s AND valid_to IS NOT NULL AND id <> :tid "
                    "AND valid_from <= :me AND valid_to >= :ms"
                ),
                {"s": svc_id, "tid": tid, "ms": vf, "me": me},
            ).fetchone()

            print(
                f"{label}\n"
                f"    id {tid}, status={row[1]}, начислений: {refs}"
                + (f" ({first_m}..{last_m})" if refs else "")
                + (f"\n    ⚠ начисления вне месяца старта — пропуск" if not single_month_ok else "")
                + (f"\n    ⚠ пересечение с закрытым периодом id {clash[0]} — пропуск" if clash else "")
            )

            if not single_month_ok or clash is not None:
                continue

            if not args.apply:
                print(f"    [dry-run] будет закрыт периодом {vf:%d.%m.%Y}..{me:%d.%m.%Y}")
                continue

            reason = (
                f"Разовый месячный сбор: оформлен как тариф-период "
                f"{vf:%d.%m.%Y}..{me:%d.%m.%Y} (закрытие открытой записи, 12.09.2026)"
            )
            comment = f"{row[2]} | {reason}" if row[2] else reason
            db.execute(
                text("UPDATE tariffs SET valid_to = :me, comment = :c WHERE id = :id"),
                {"me": me, "c": comment, "id": tid},
            )
            print(f"    [apply] период закрыт: {vf:%d.%m.%Y}..{me:%d.%m.%Y}")

        if args.apply:
            db.commit()
            print("\nГотово.")

            print("\nКонтроль — какая ставка выбирается по услугам (текущий месяц):")
            row = db.execute(
                text(
                    "SELECT st.services_type, t.id, t.price, t.valid_to "
                    "FROM services_type st "
                    "LEFT JOIN LATERAL ("
                    "  SELECT id, price, valid_to FROM tariffs "
                    "  WHERE services_type_id = st.id AND valid_to IS NULL "
                    "  ORDER BY valid_from DESC, id DESC LIMIT 1"
                    ") t ON true ORDER BY st.id"
                )
            ).fetchall()
            for r in row:
                vto = f"{r[3]:%d.%m.%Y}" if r[3] else "—"
                price = f"{float(r[2]):,.2f}" if r[2] is not None else "—"
                print(f"  {r[0]:<24} id {r[1]}  {price:>14}  до {vto}")
        else:
            print("\n[dry-run] Изменений не вносилось. Применить: --apply")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
