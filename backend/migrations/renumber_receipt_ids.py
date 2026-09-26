"""
Уплотнение нумерации квитанций: перенос id квитанций года в непрерывный блок.

Зачем: удаление/пересоздание квитанций «уводит» их id вперёд и оставляет «дыры»
(пример: квитанции 2026 занимают 1953…2105, а диапазон 1817…1952 свободен).
Скрипт переносит квитанции указанного года в непрерывный блок сразу после
максимального id квитанций ДРУГИХ лет, в порядке (месяц, № квартиры, id), и
выставляет счётчик id квитанций на конец блока.

Безопасность:
  - целевой блок обязан быть свободен от квитанций других лет (иначе — стоп);
  - строки квитанций (`receipt_items.receipt_id`) перенумеровываются вместе с шапками;
  - FK `receipt_items → receipt_documents` на время снимается и восстанавливается;
  - всё в одной транзакции: dry-run по умолчанию (rollback), --apply — коммит;
  - идемпотентно: повторный прогон даёт тот же блок и 0 изменений.

Запуск из каталога backend:
    python migrations/renumber_receipt_ids.py --year 2026
    python migrations/renumber_receipt_ids.py --year 2026 --apply
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from database import SessionLocal  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Уплотнение id квитанций за год")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--apply", action="store_true", help="записать изменения (иначе dry-run)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = db.execute(
            text("""
                SELECT id FROM receipt_documents
                WHERE period_year = :y
                ORDER BY period_month, apartment_number NULLS LAST, id
            """),
            {"y": args.year},
        ).fetchall()
        if not rows:
            print("Квитанций за указанный год не найдено — нечего перенумеровывать.")
            return

        max_other = int(
            db.execute(
                text("SELECT COALESCE(max(id), 0) FROM receipt_documents WHERE period_year <> :y"),
                {"y": args.year},
            ).scalar()
            or 0
        )
        start = max_other + 1
        end = start + len(rows) - 1

        conflict = int(
            db.execute(
                text(
                    "SELECT count(*) FROM receipt_documents "
                    "WHERE id BETWEEN :s AND :e AND period_year <> :y"
                ),
                {"s": start, "e": end, "y": args.year},
            ).scalar()
            or 0
        )
        if conflict:
            print(
                f"ОШИБКА: целевой блок {start}…{end} занят квитанциями других лет "
                f"({conflict} шт.) — перенумерация невозможна, прерываю."
            )
            return

        seq = db.execute(
            text("SELECT pg_get_serial_sequence('receipt_documents','id')")
        ).scalar()
        seq_now = int(db.execute(text(f"SELECT last_value FROM {seq}")).scalar()) if seq else 0

        old_ids = [int(r[0]) for r in rows]
        mapping = [(old, start + i) for i, old in enumerate(old_ids)]
        changed = sum(1 for old, new in mapping if old != new)

        print(f"Квитанций {args.year}: {len(rows)}")
        print(f"Их id сейчас: {min(old_ids)}…{max(old_ids)}")
        print(f"Целевой блок: {start}…{end} (после max(id) других лет = {max_other})")
        print(f"Счётчик id сейчас: {seq_now}")
        print(f"К перенумерации: {changed} из {len(mapping)}")
        for old, new in mapping[:2] + mapping[-2:]:
            print(f"  id {old} -> {new}")

        if not args.apply:
            db.rollback()
            print("\ndry-run: изменения в БД не записаны. Для записи запустите с ключом --apply")
            return

        fk = db.execute(
            text("""
                SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conrelid = 'receipt_items'::regclass
                  AND confrelid = 'receipt_documents'::regclass AND contype = 'f'
            """)
        ).first()

        db.execute(
            text(
                "CREATE TEMP TABLE _receipt_id_map "
                "(old_id int PRIMARY KEY, new_id int UNIQUE) ON COMMIT DROP"
            )
        )
        db.execute(
            text("""
                INSERT INTO _receipt_id_map (old_id, new_id)
                SELECT id, :start + row_number() OVER (
                           ORDER BY period_month, apartment_number NULLS LAST, id) - 1
                FROM receipt_documents WHERE period_year = :y
            """),
            {"start": start, "y": args.year},
        )

        if fk:
            db.execute(text(f"ALTER TABLE receipt_items DROP CONSTRAINT {fk[0]}"))
        # 1) уводим id шапок года в минус (гарантированно без коллизий);
        # 2) переносим строки квитанций на новые id;
        # 3) ставим новые id шапкам.
        db.execute(
            text("UPDATE receipt_documents SET id = -id WHERE period_year = :y"),
            {"y": args.year},
        )
        db.execute(
            text("""
                UPDATE receipt_items i SET receipt_id = m.new_id
                FROM _receipt_id_map m WHERE i.receipt_id = m.old_id
            """)
        )
        db.execute(
            text("""
                UPDATE receipt_documents d SET id = m.new_id
                FROM _receipt_id_map m WHERE d.id = -m.old_id
            """)
        )
        if fk:
            db.execute(text(f"ALTER TABLE receipt_items ADD CONSTRAINT {fk[0]} {fk[1]}"))

        db.execute(text(f"SELECT setval('{seq}', (SELECT max(id) FROM receipt_documents))"))
        db.commit()

        check = db.execute(
            text("SELECT count(*), min(id), max(id) FROM receipt_documents WHERE period_year = :y"),
            {"y": args.year},
        ).first()
        orphans = int(
            db.execute(
                text("""
                    SELECT count(*) FROM receipt_items i
                    LEFT JOIN receipt_documents d ON d.id = i.receipt_id
                    WHERE d.id IS NULL
                """)
            ).scalar()
            or 0
        )
        seq_after = int(db.execute(text(f"SELECT last_value FROM {seq}")).scalar())
        print(f"\nПрименено: квитанции {args.year} — {check[0]} шт., id {check[1]}…{check[2]}.")
        print(f"Контроль: «осиротевших» строк квитанций — {orphans}; счётчик id = {seq_after}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
