"""
Синхронизация счётчиков id (последовательностей) с фактическими `max(id)`.

Причина: после удалений/переносов/регенераций документов sequence «убегает» вперёд
`max(id)` — следующий INSERT получает id с большой дырой (пример: `accounts`
max(id)=17, счётчик=84 → новая квартира получила бы id 85).

Что делает:
  1. dry-run: печатает таблицы, где счётчик ≠ max(id), величину разрыва и число
     «внутренних» дыр в уже существующих id (для справки);
  2. --apply: `setval(seq, max(id))` → следующий id = max(id)+1 (пустая таблица → 1).

ВНИМАНИЕ: скрипт выравнивает только БУДУЩИЕ id. Уже существующие разрывы внутри
диапазона (от удалённых строк) он не убирает — для этого нужна полная перенумерация
(`renumber_all_entities.py`, ТД-2), это отдельная операция с прогоном контроля.

Идемпотентно: после выравнивания счётчиков script находит 0 изменений.

Запуск из каталога backend:
    python migrations/sync_id_sequences.py            # dry-run (план)
    python migrations/sync_id_sequences.py --apply    # применить
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text  # noqa: E402
from database import engine  # noqa: E402


def _next_id(conn, seq: str) -> int:
    """Следующий id, который выдаст sequence (без его расходования)."""
    last_value, is_called = conn.execute(
        text(f"SELECT last_value, is_called FROM {seq}")
    ).first()
    return int(last_value) + (1 if is_called else 0)


def main() -> None:
    apply_mode = "--apply" in sys.argv
    insp = inspect(engine)
    rows: list[tuple[str, str, int, int, int]] = []  # table, seq, max_id, next_id, count

    with engine.connect() as conn:
        for table in sorted(insp.get_table_names()):
            cols = [c["name"] for c in insp.get_columns(table)]
            if "id" not in cols:
                continue
            seq = conn.execute(
                text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": table}
            ).scalar()
            if not seq:
                continue
            max_id = int(conn.execute(text(f"SELECT COALESCE(max(id),0) FROM {table}")).scalar() or 0)
            next_id = _next_id(conn, seq)
            count = int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0)
            if next_id != max_id + 1:
                rows.append((table, seq, max_id, next_id, count))

        print(f"Счётчиков к выравниванию: {len(rows)}")
        for table, _seq, max_id, next_id, count in rows:
            holes = max_id - count
            target = max_id + 1
            print(
                f"  {table:28} max(id)={max_id:<7} след.id={next_id:<7} "
                f"-> {target}   внутренних дыр: {holes}"
            )

        if not rows:
            print("Все счётчики совпадают с max(id) — правок не требуется.")
            return
        if not apply_mode:
            print("\ndry-run: для записи запустите скрипт с ключом --apply")
            return

        for table, seq, max_id, _next_id_val, _count in rows:
            if max_id:
                conn.execute(text(f"SELECT setval('{seq}', :m, true)"), {"m": max_id})
            else:
                conn.execute(text(f"SELECT setval('{seq}', 1, false)"))
        conn.commit()

    # Контроль: повторный проход должен показать 0 изменений.
    with engine.connect() as conn:
        left = 0
        for table, _seq, _max, _next, _count in rows:
            seq = conn.execute(
                text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": table}
            ).scalar()
            max_id = int(conn.execute(text(f"SELECT COALESCE(max(id),0) FROM {table}")).scalar() or 0)
            if _next_id(conn, seq) != max_id + 1:
                left += 1
        print(f"\nПрименено: выровнено счётчиков — {len(rows)}; осталось расхождений: {left}")


if __name__ == "__main__":
    main()
