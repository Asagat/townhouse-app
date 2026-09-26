"""
Санитарная правка `meters.installed_at`: дата установки не может быть ПОЗЖЕ первого
показания счётчика.

Зачем: при вводе показаний приложение выбирает «действующий» счётчик квартиры по
`installed_at DESC` (`services.resolve_meter_reading_values`,
`routers/documents.bulk_create_readings`/`update_meter_reading_document_full`).
Если у старого прибора `installed_at` ошибочно новее, чем у фактически работающего,
новые показания запишутся НА СТАРЫЙ прибор — и начисление по счётчику посчитается
неверно (предыдущим окажется показание многолетней давности).

Реальный случай: `M-01-1` (кв.1) — `installed_at = 2026-01-01`, хотя показания
идут с 2017-10-26; при вводе показаний по кв.1 активным выбирался именно он.

Правило правки: если у счётчика есть показания и `installed_at` позже первого из
них — ставим `installed_at = дата первого показания`. Идемпотентно.

Запуск из каталога backend:
    python migrations/fix_meter_installed_at.py            # dry-run (показывает план)
    python migrations/fix_meter_installed_at.py --apply    # применить
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from database import SessionLocal  # noqa: E402


def main() -> None:
    apply_mode = "--apply" in sys.argv
    db = SessionLocal()
    try:
        rows = db.execute(
            text("""
                SELECT m.id, m.serial_number, m.apartment_id, m.installed_at,
                       min(r.reading_date) AS first_reading
                FROM meters m
                JOIN meter_readings r ON r.meter_id = m.id
                GROUP BY m.id, m.serial_number, m.apartment_id, m.installed_at
                HAVING m.installed_at IS NOT NULL AND m.installed_at > min(r.reading_date)
                ORDER BY m.serial_number
            """)
        ).fetchall()

        print(f"Счётчиков с installed_at позже первого показания: {len(rows)}")
        for r in rows:
            print(
                f"  id={r[0]} {r[1]} (кв.{r[2]}): installed_at "
                f"{r[3]} -> {r[4]}"
            )

        if not rows:
            print("Правок не требуется.")
            return
        if not apply_mode:
            print("\ndry-run: для записи запустите скрипт с ключом --apply")
            return

        db.execute(
            text("""
                UPDATE meters m
                SET installed_at = first.min_d
                FROM (
                    SELECT meter_id, min(reading_date) AS min_d
                    FROM meter_readings
                    GROUP BY meter_id
                ) first
                WHERE first.meter_id = m.id
                  AND m.installed_at IS NOT NULL
                  AND m.installed_at > first.min_d
            """)
        )
        db.commit()
        print(f"\nПрименено: исправлено счётчиков — {len(rows)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
