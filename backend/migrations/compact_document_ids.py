"""
Полное уплотнение id «документных» таблиц (удаление «дыр» в нумерации).

Зачем: из-за удалений/правок id документов идут с разрывами (напр. `receipt_documents`
1…1952 при 1816 строках). Скрипт перенумеровывает таблицу в непрерывный диапазон
1…N, сохраняя естественный порядок, и обновляет ссылающиеся колонки (FK).

Целевые таблицы и порядок нумерации:
  - `receipt_documents`  — хронологически: (период года/месяца, № квартиры, id);
    их id исторически выдавались «вперемешку» по годам, поэтому хронология — естественный порядок;
  - `accrual_documents`, `meter_readings`, `transactions` — по возрастанию id (порядок
    не меняется, только убираются разрывы: эти документы и создавались в порядке id).

Безопасность:
  - ссылающиеся FK снимаются на время перенумерации и восстанавливаются с тем же
    определением (`ON DELETE CASCADE`/`SET NULL` сохраняются); значения дочерних
    колонок переносятся по карте old→new;
  - id временно уводятся в минус, чтобы не было коллизий при перестановке;
  - всё в одной транзакции: dry-run по умолчанию (rollback + восстановление счётчиков),
    --apply — коммит; идемпотентно.

Регистры (`*_register`) и `receipt_items` НЕ трогаются: это производные данные,
они пересобираются при расчётах, и уплотнение там бессмысленно.

Запуск из каталога backend:
    python migrations/compact_document_ids.py
    python migrations/compact_document_ids.py --apply
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from database import SessionLocal  # noqa: E402


# Порядок нумерации по каждой таблице. Квитанции — хронологически (их id исторически
# перемешаны по годам); остальные документные таблицы — по id (чистое устранение дыр).
TARGETS: dict[str, str] = {
    "receipt_documents": "period_year, period_month, apartment_number NULLS LAST, id",
    "accrual_documents": "id",
    "meter_readings": "id",
    "transactions": "id",
}


def _fk_refs(db, table: str):
    """FK, ссылающиеся на `table`: (дочерняя таблица, колонка, имя, определение)."""
    return db.execute(
        text("""
            SELECT c.conrelid::regclass::text AS child,
                   a.attname AS col,
                   c.conname,
                   pg_get_constraintdef(c.oid) AS def
            FROM pg_constraint c
            JOIN LATERAL unnest(c.conkey) AS k(attnum) ON true
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
            WHERE c.contype = 'f' AND c.confrelid = to_regclass(:t)
            ORDER BY 1, 2
        """),
        {"t": table},
    ).fetchall()


def _seq_state(db, table: str):
    """Состояние последовательности id: (имя, last_value, is_called) или None."""
    seq = db.execute(
        text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": table}
    ).scalar()
    if not seq:
        return None
    row = db.execute(text(f"SELECT last_value, is_called FROM {seq}")).first()
    return (seq, int(row[0]), bool(row[1]))


def _restore_seq(db, state) -> None:
    if not state:
        return
    seq, last_value, is_called = state
    db.execute(text(f"SELECT setval('{seq}', :v, :c)"), {"v": last_value, "c": is_called})
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Уплотнение id документных таблиц")
    parser.add_argument("--apply", action="store_true", help="записать изменения (иначе dry-run)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        db.execute(
            text(
                "CREATE TEMP TABLE IF NOT EXISTS _id_map "
                "(old_id int PRIMARY KEY, new_id int UNIQUE) ON COMMIT DROP"
            )
        )

        seq_states = {t: _seq_state(db, t) for t in TARGETS}
        report = []
        for table, order_by in TARGETS.items():
            ids = [int(r[0]) for r in db.execute(text(f"SELECT id FROM {table} ORDER BY {order_by}"))]
            n = len(ids)
            changed = sum(1 for i, old in enumerate(ids) if old != i + 1)
            report.append((table, n, min(ids) if ids else 0, max(ids) if ids else 0, changed))

            if n == 0 or changed == 0:
                continue

            refs = _fk_refs(db, table)
            db.execute(text("TRUNCATE _id_map"))
            db.execute(
                text(
                    f"INSERT INTO _id_map (old_id, new_id) "
                    f"SELECT id, row_number() OVER (ORDER BY {order_by}) FROM {table}"
                )
            )
            for child, col, conname, _condef in refs:
                db.execute(text(f"ALTER TABLE {child} DROP CONSTRAINT {conname}"))
            # id в минус — затем раскладываем по новым значениям без коллизий.
            db.execute(text(f"UPDATE {table} SET id = -id"))
            for child, col, _conname, _condef in refs:
                db.execute(
                    text(
                        f"UPDATE {child} c SET {col} = m.new_id "
                        f"FROM _id_map m WHERE c.{col} = m.old_id"
                    )
                )
            db.execute(
                text(f"UPDATE {table} t SET id = m.new_id FROM _id_map m WHERE t.id = -m.old_id")
            )
            for child, _col, conname, condef in refs:
                db.execute(text(f"ALTER TABLE {child} ADD CONSTRAINT {conname} {condef}"))
            seq = seq_states[table]
            if seq:
                db.execute(text(f"SELECT setval('{seq[0]}', {n})"))

        print(f"{'таблица':<18}{'строк':>8}{'было id':>16}{'стало id':>14}{'к правке':>10}")
        for table, n, old_min, old_max, changed in report:
            new_range = f"1…{n}" if n else "—"
            print(f"{table:<18}{n:>8}{f'{old_min}…{old_max}':>16}{new_range:>14}{changed:>10}")

        # Контроль «осиротевших» ссылок по всем FK на целевые таблицы.
        orphans = 0
        for table in TARGETS:
            for child, col, _conname, _condef in _fk_refs(db, table):
                orphans += int(
                    db.execute(
                        text(
                            f"SELECT count(*) FROM {child} c "
                            f"LEFT JOIN {table} p ON p.id = c.{col} "
                            f"WHERE c.{col} IS NOT NULL AND p.id IS NULL"
                        )
                    ).scalar()
                    or 0
                )
        print(f"\nКонтроль: «осиротевших» ссылок — {orphans}")

        if not args.apply:
            db.rollback()
            for state in seq_states.values():
                _restore_seq(db, state)
            print("dry-run: изменения в БД не записаны. Для записи запустите с ключом --apply")
            return

        db.commit()
        print("Применено: id документных таблиц уплотнены.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
