# backend/migrations/fill_accrual_readings.py
"""Наполняет past/current показания и current_reading_id в «Регистре начислений»
(роадмап Б4+Б13) для исторических строк, созданных миграцией данных (у них заполнен
только consumption).

У части квартир счётчик менялся (старый M-XX-1 до ~04.2018 и новый M-XX-2), поэтому
просто «первый счётчик квартиры» не подходит. Для строки месяца M ищется показание
«текущее» (последнее с reading_date <= конца M) по КАЖДОМУ счётчику (квартира+услуга),
и «прошлое» — предыдущее показание того же счётчика; выбирается пара, у которой
разность совпадает с consumption строки (погрешность 0.011). Ненайденные строки
остаются без показаний (выводятся в отчёте). consumption не меняется.

Запуск из каталога backend:
    python fill_accrual_readings.py            # предпросмотр (dry-run)
    python fill_accrual_readings.py --apply    # записать в БД
Идемпотентно: заполняет только строки без показаний.
"""

import calendar
import os
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal  # noqa: E402
from sqlalchemy import text  # noqa: E402

APPLY = "--apply" in sys.argv
TOL = Decimal("0.011")


def month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def main() -> None:
    session = SessionLocal()
    try:
        meter_svc_ids = {
            r[0]
            for r in session.execute(
                text("SELECT DISTINCT services_type_id FROM meters")
            ).fetchall()
        }
        if not meter_svc_ids:
            print("Нет услуг со счётчиками — заполнять нечего.")
            return

        # Все счётчики по (квартира, услуга): их может быть несколько (замена прибора).
        meters_by_apt_svc: dict[tuple[int, int], list[int]] = {}
        for mid, apt, svc in session.execute(
            text("SELECT id, apartment_id, services_type_id FROM meters")
        ).fetchall():
            meters_by_apt_svc.setdefault((apt, svc), []).append(mid)

        readings_by_meter: dict[int, list[tuple[date, int, Decimal]]] = {}
        for mid, rdate, val in session.execute(
            text(
                "SELECT meter_id, reading_date, reading FROM meter_readings "
                "ORDER BY meter_id, reading_date, id"
            )
        ).fetchall():
            readings_by_meter.setdefault(mid, []).append((rdate, mid, val))

        rows = session.execute(
            text(
                "SELECT ar.id, ar.account_id, ar.services_type_id, ar.accrual_date, "
                "ar.consumption "
                "FROM accruals_register ar "
                "WHERE ar.services_type_id IN ("
                + ",".join(str(i) for i in sorted(meter_svc_ids))
                + ") AND ar.past_reading_value IS NULL"
            )
        ).fetchall()

        account_apartment = {
            r[0]: r[1]
            for r in session.execute(text("SELECT id, apartment_id FROM accounts")).fetchall()
        }

        updates = []
        unmatched = 0
        unmatched_samples = []
        for acc_id, account_id, svc_id, accrual_date, consumption in rows:
            apt = account_apartment.get(account_id)
            meter_ids = meters_by_apt_svc.get((apt, svc_id)) if apt else None
            if not meter_ids:
                unmatched += 1
                continue
            end = month_end(accrual_date)
            target = Decimal(str(consumption))

            best = None  # (delta, past, current, reading_id)
            for meter_id in meter_ids:
                lst = readings_by_meter.get(meter_id) or []
                idx = -1
                for i, (rd, _, _) in enumerate(lst):
                    if rd <= end:
                        idx = i
                    else:
                        break
                if idx < 0:
                    continue
                cur = lst[idx][2]
                past = lst[idx - 1][2] if idx >= 1 else Decimal("0")
                delta = abs((cur - past) - target)
                if delta <= TOL and (best is None or delta < best[0]):
                    best = (delta, past, cur, lst[idx][1])

            if best is None:
                unmatched += 1
                if len(unmatched_samples) < 5:
                    unmatched_samples.append((acc_id, accrual_date, target))
                continue
            updates.append((acc_id, best[1], best[2], best[3]))

        print(
            f"Строк к заполнению: {len(rows)}; обновлено: {len(updates)}; "
            f"не найдено пары: {unmatched}"
        )
        for s in unmatched_samples:
            print("  нет пары:", s)
        if not APPLY:
            print("\nПредпросмотр (dry-run). Для записи запустите: --apply")
            return

        for row_id, past, cur, reading_id in updates:
            session.execute(
                text(
                    "UPDATE accruals_register SET past_reading_value = :p, "
                    "current_reading_value = :c, current_reading_id = :rid WHERE id = :id"
                ),
                {"p": past, "c": cur, "rid": reading_id, "id": row_id},
            )
        session.commit()
        print(f"Записано обновлений: {len(updates)}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
