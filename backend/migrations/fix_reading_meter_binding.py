"""
Исправление привязки показания к счётчику: показания, ошибочно записанные на
УСТАРЕВШИЙ счётчик, переносятся на действующий (активный) прибор пары
(квартира, вид услуги).

Зачем: при вводе показаний приложение выбирает счётчик по
`installed_at DESC NULLS LAST, id DESC` (`services.resolve_meter_reading_values`,
`routers/documents.bulk_create_readings`). Если у старого прибора `installed_at`
оказался больше, чем у действующего (единичная порча данных), новое показание
запишется на старый прибор — и начисление возьмёт «предыдущее» показание того же
старого прибора (годы назад). Реальный случай (прод, 26.09.2026): у `M-01-1`
(кв.1) `installed_at` был `2026-01-01` вместо `2017-10-26`, из-за чего показание за
сентябрь 2026 (39 208) легло на `M-01-1`, а начисление посчитало расход 27 533
вместо 504.

Правило отбора кандидатов (консервативное, чтобы не трогать легитимную историю
старого прибора вокруг даты замены):
  показание лежит НЕ на активном счётчике пары,
  дата показания ПОЗЖЕ даты установки активного счётчика,
  значение показания >= максимального показания активного счётчика
  (т.е. явно продолжает шкалу действующего прибора, а не старого).

Активный счётчик пары — `ORDER BY installed_at DESC NULLS LAST, id DESC`.

Показания, привязанные к активному счётчику, и исторические показания старого
прибора (значение ниже шкалы нового) НЕ трогаются.

Запуск из каталога backend:
    python migrations/fix_reading_meter_binding.py            # dry-run (план)
    python migrations/fix_reading_meter_binding.py --apply    # применить
Идемпотентно: после переноса показание уже на активном счётчике, кандидатов нет.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from database import SessionLocal  # noqa: E402

CANDIDATES_SQL = """
    WITH active AS (
        SELECT DISTINCT ON (apartment_id, services_type_id)
               apartment_id, services_type_id, id AS meter_id, installed_at
        FROM meters
        WHERE apartment_id IS NOT NULL
        ORDER BY apartment_id, services_type_id,
                 installed_at DESC NULLS LAST, id DESC
    ),
    act_max AS (
        SELECT a.meter_id, max(r.reading) AS max_reading
        FROM active a
        JOIN meter_readings r ON r.meter_id = a.meter_id
        GROUP BY a.meter_id
    )
    SELECT r.id AS reading_id,
           m.apartment_id,
           m.serial_number AS old_serial,
           m2.serial_number AS new_serial,
           a.meter_id AS new_meter_id,
           r.reading_date,
           r.reading
    FROM meter_readings r
    JOIN meters m  ON m.id = r.meter_id
    JOIN active a  ON a.apartment_id = m.apartment_id
                  AND a.services_type_id = m.services_type_id
    JOIN meters m2 ON m2.id = a.meter_id
    JOIN act_max am ON am.meter_id = a.meter_id
    WHERE r.meter_id <> a.meter_id
      AND a.installed_at IS NOT NULL
      AND r.reading_date > a.installed_at
      AND r.reading >= am.max_reading
    ORDER BY r.reading_date, r.id
"""


def main() -> None:
    apply_mode = "--apply" in sys.argv
    db = SessionLocal()
    try:
        rows = db.execute(text(CANDIDATES_SQL)).fetchall()
        print(f"Показаний на устаревшем счётчике (кандидаты на перенос): {len(rows)}")
        for r in rows:
            print(
                f"  reading id={r[0]} кв.{r[1]}: {r[2]} -> {r[3]} (meter_id={r[4]}), "
                f"{r[5]} значение {r[6]}"
            )

        if not rows:
            print("Правок не требуется.")
            return
        if not apply_mode:
            print("\ndry-run: для записи запустите скрипт с ключом --apply")
            return

        for r in rows:
            db.execute(
                text("UPDATE meter_readings SET meter_id = :new WHERE id = :id"),
                {"new": r[4], "id": r[0]},
            )
        db.commit()
        print(f"\nПрименено: перенесено показаний — {len(rows)}")
        print(
            "Проверьте: начисления за затронутый период нужно пересоздать "
            "(уже сохранённые строки регистра не пересчитываются этим скриптом)."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
