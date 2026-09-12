# backend/migrations/renumber_all_entities.py
"""Полная перенумерация ID всех таблиц: id с 1 без дырок (вариант B, ТД-2).

НАЗНАЧЕНИЕ
    Привести автогенерируемые id всех таблиц к непрерывной нумерации, начинающейся
    с 1, сохранив при этом бизнес-смысл самих данных. Выполняется ОДИН РАЗ на
    копии/переносе (dev → прод), НЕ в рабочем режиме.

ЗАЧЕМ
    ТД-2 роадмапа: перед финальным прод-развёртыванием пересоздать БД с ID=1 и
    «чистой» нумерацией. Здесь — старый порядок сохраняется, меняются только
    числовые ключи.

ВАЖНО — ЧЕГО ЭТОТ СКРИПТ НЕ ДЕЛАЕТ
    Он НЕ перестраивает хронологию документов и НЕ пересобирает регистры.
    Пересоздание начислений по хронологии, пересборку accounts_register и
    перегенерацию квитанций делает следующий шаг — renumber_finalize.py.

ПОРЯДОК (зависимости сверху вниз: от справочников к документам):
    counterparties → apartments → accounts → tariff_types → services_type →
    tariffs → meters → meter_reading_documents → meter_readings →
    users → user_preferences → analytic_articles → cash_points →
    transactions → accrual_documents → writeoff_documents → accruals_register →
    writeoff_items → receipt_documents → receipt_items

РЕЖИМЫ
    python migrations/renumber_all_entities.py            # dry-run (только отчёт)
    python migrations/renumber_all_entities.py --apply    # применить

ПРЕДУСЛОВИЯ
    - свежий бэкап БД (скрипт не создаёт его сам);
    - БД именно на нужной схеме (alembic upgrade head);
    - НИКТО не работает с приложением в момент --apply.

СЕМАНТИКА ID, КОТОРЫЕ МЕНЯТЬ НЕЛЬЗЯ/НЕЛЬЗЯ НАДО
    - accounts.account_number («LS/NNNN») — бизнес-номер лицевого счёта, НЕ id;
    - transactions.doc_no — сквозной хронологический номер документа, назначается
      отдельно (renumber_finalize.py);
    - все *_number/serial_number/serial — обязаны остаться прежними.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database

from sqlalchemy import text

# Порядок перенумерации для таблиц, где «естественный» порядок — не порядок создания
# записи (id), а бизнес-ключ.
# tariffs: единая лента по дате начала действия — новые тарифы заводятся по разным
# услугам вперемешку по времени, поэтому хронология важнее порядка создания записи
# (иначе конверсионные тарифы 0018, вставленные позже всех, уезжают в хвост).
ORDER_BY: dict[str, str] = {
    "tariffs": "valid_from, id",
}

# ---------------------------------------------------------------------------
# Порядок обработки таблиц и внешние ключи, которые нужно перепривязать вместе
# с таблицей. Формат: (таблица, [(таблица_с_fk, колонка_fk), ...])
# ---------------------------------------------------------------------------
TABLE_PLAN: list[tuple[str, list[tuple[str, str]]]] = [
    ("counterparties", [
        ("apartments", "owner_id"),
        ("transactions", "contractor_id"),
        ("cash_register", "contractor_id"),
    ]),
    ("apartments", [
        ("accounts", "apartment_id"),
        ("meters", "apartment_id"),
        ("meter_readings", "apartment_id"),
    ]),
    ("accounts", [
        ("users", "account_id"),
        ("transactions", "account_id"),
        ("accruals_register", "account_id"),
        ("accounts_register", "account_id"),
        ("cash_register", "account_id"),
        ("receipt_documents", "account_id"),
        ("writeoff_items", "account_id"),
    ]),
    ("tariff_types", [("services_type", "tariff_type_id")]),
    ("services_type", [
        ("tariffs", "services_type_id"),
        ("meters", "services_type_id"),
        ("meter_reading_documents", "services_type_id"),
        ("meter_readings", "services_type_id"),
        ("accruals_register", "services_type_id"),
        ("accounts_register", "services_type_id"),
        ("receipt_items", "services_type_id"),
        ("writeoff_items", "services_type_id"),
    ]),
    ("tariffs", [("accruals_register", "tariff_id")]),
    ("meters", [("meter_readings", "meter_id")]),
    ("meter_reading_documents", [("meter_readings", "document_id")]),
    ("meter_readings", [("accruals_register", "current_reading_id")]),
    ("users", [
        ("user_preferences", "user_id"),
        ("transactions", "created_by"),
        ("transactions", "updated_by"),
        ("meter_reading_documents", "created_by"),
        ("meter_reading_documents", "updated_by"),
        ("accrual_documents", "created_by"),
        ("accrual_documents", "updated_by"),
        ("receipt_documents", "created_by"),
        ("receipt_documents", "updated_by"),
        ("writeoff_documents", "created_by"),
        ("writeoff_documents", "updated_by"),
    ]),
    ("user_preferences", []),
    ("analytic_articles", [("transactions", "article_id")]),
    ("cash_points", [("transactions", "cash_point_id")]),
    ("transactions", [
        ("cash_register", "transaction_id"),
        ("accounts_register", "transaction_id"),
    ]),
    ("accrual_documents", [("accruals_register", "accrual_document_id")]),
    ("writeoff_documents", [
        ("writeoff_items", "document_id"),
        ("accounts_register", "writeoff_id"),
    ]),
    ("accruals_register", [
        ("accounts_register", "accrual_id"),
    ]),
    ("writeoff_items", []),
    # Квитанции — в самом конце: их содержимое всё равно перегенерируется
    # (renumber_finalize.py), но нумерация id приводится здесь же.
    ("receipt_documents", [("receipt_items", "receipt_id")]),
    ("receipt_items", []),
]


def _table_exists(db, table: str) -> bool:
    return bool(db.execute(
        text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{table}"}
    ).scalar())


def _pk_id(db, table: str) -> list[int]:
    """id таблицы в порядке перенумерации (по умолчанию — по возрастанию id;
    для отдельных таблиц — по бизнес-ключу, см. ORDER_BY)."""
    order = ORDER_BY.get(table, "id")
    rows = db.execute(text(f"SELECT id FROM {table} ORDER BY {order}")).fetchall()
    return [int(r[0]) for r in rows]


def _plan_table(db, table: str) -> tuple[list[int], dict[int, int]]:
    """Возвращает (старые id по порядку, карта old→new)."""
    old_ids = _pk_id(db, table)
    mapping = {old: new for new, old in enumerate(old_ids, start=1)}
    return old_ids, mapping


def _set_seq(db, table: str, max_id: int) -> None:
    """Устанавливает последовательность pk в max_id (id может быть не *_id_seq)."""
    seq = db.execute(
        text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": table}
    ).scalar()
    if not seq:
        return
    db.execute(text("SELECT setval(:s, :v, true)"), {"s": seq, "v": max(max_id, 1)})


def _fk_defs(db, ref_table: str, ref_col: str) -> list[tuple[str, str]]:
    """Имена и определения FK на колонку из каталога Postgres.

    Имя констрейнта задаёт SQLAlchemy, и оно НЕ всегда вида
    `<таблица>_<колонка>_fkey` — есть явные имена `fk_...` (см. models.py).
    Возвращаем и имя, и `pg_get_constraintdef(oid)`, чтобы вернуть констрейнт
    ровно таким, каким он был (включая поведение ON DELETE/CASCADE).
    """
    rows = db.execute(
        text(
            "SELECT c.conname, pg_get_constraintdef(c.oid) "
            "FROM pg_constraint c "
            "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey) "
            "WHERE c.contype = 'f' AND c.conrelid = to_regclass(:tbl) AND a.attname = :col"
        ),
        {"tbl": f"public.{ref_table}", "col": ref_col},
    ).fetchall()
    return [(str(r[0]), str(r[1])) for r in rows]


def _rebuild_table(db, table: str, old_ids: list[int], mapping: dict[int, int],
                   refs: list[tuple[str, str]]) -> int:
    """Перенумеровывает таблицу и все ссылающиеся на неё FK.

    Приём: id уводим в отрицательную «буферную» зону (id — положительные, коллизий
    нет), затем ставим новые положительные значения. FK с ondelete=SET NULL / CASCADE
    не срабатывают при UPDATE родителя, поэтому перепривязка безопасна.
    """
    changed = 0

    # Фаза 1: снимаем FK-констрейнты, которые могут помешать во время переноса
    # (например, cash_register.transaction_id NOT NULL при UPDATE родителя).
    # Имена/определения берём из каталога и запоминаем, чтобы вернуть их как было.
    saved_fks: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for ref_table, ref_col in refs:
        if not _table_exists(db, ref_table):
            continue
        defs = _fk_defs(db, ref_table, ref_col)
        saved_fks[(ref_table, ref_col)] = defs
        for name, _ in defs:
            db.execute(text(f'ALTER TABLE {ref_table} DROP CONSTRAINT "{name}"'))

    # Фаза 2: родитель → отрицательная зона.
    for oid in old_ids:
        db.execute(text(f"UPDATE {table} SET id = :n WHERE id = :o"),
                   {"n": -oid, "o": oid})

    # Фаза 3: родитель → новые положительные.
    for oid in old_ids:
        db.execute(text(f"UPDATE {table} SET id = :n WHERE id = :o"),
                   {"n": mapping[oid], "o": -oid})
        changed += 1

    # Фаза 4: перепривязка FK во всех ссылающихся таблицах.
    for ref_table, ref_col in refs:
        if not _table_exists(db, ref_table):
            continue
        # Ссылающиеся значения тоже уводим в отрицательную зону (через старый id),
        # затем ставим новые. Через параметры, чтобы не строить огромный VALUES.
        for oid in old_ids:
            db.execute(
                text(f"UPDATE {ref_table} SET {ref_col} = :n WHERE {ref_col} = :o"),
                {"n": -oid, "o": oid},
            )
        for oid in old_ids:
            db.execute(
                text(f"UPDATE {ref_table} SET {ref_col} = :n WHERE {ref_col} = :o"),
                {"n": mapping[oid], "o": -oid},
            )

    # Фаза 5: возвращаем FK-констрейнты с исходными именами и определениями.
    for ref_table, ref_col in refs:
        if not _table_exists(db, ref_table):
            continue
        for name, condef in saved_fks.get((ref_table, ref_col), []):
            db.execute(text(
                f'ALTER TABLE {ref_table} ADD CONSTRAINT "{name}" {condef}'
            ))

    _set_seq(db, table, len(old_ids))
    return changed


def _report(db) -> None:
    print("-- Состояние таблиц (до):")
    for table, _ in TABLE_PLAN:
        if not _table_exists(db, table):
            print(f"   {table:28s} НЕТ ТАБЛИЦЫ (пропуск)")
            continue
        row = db.execute(text(
            f"SELECT count(*), min(id), max(id) FROM {table}"
        )).fetchone()
        cnt, mn, mx = row
        holes = int(mx or 0) - int(mn or 1) + 1 - int(cnt or 0) if cnt else 0
        flag = "OK" if (cnt == (mx or 0)) else f"дыр: {holes}"
        print(f"   {table:28s} строк={cnt:<8} min={mn} max={mx}  {flag}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Полная перенумерация id (ТД-2, вариант B)")
    ap.add_argument("--apply", action="store_true",
                    help="применить изменения (без флага — только отчёт)")
    args = ap.parse_args()

    db = database.SessionLocal()
    try:
        _report(db)

        if not args.apply:
            print("\nDRY-RUN: изменения не применены. Повторите с --apply.")
            return 0

        print("\n-- Применяю перенумерацию...")
        for table, refs in TABLE_PLAN:
            if not _table_exists(db, table):
                print(f"   {table:28s} пропуск (нет таблицы)")
                continue
            old_ids, mapping = _plan_table(db, table)
            if not old_ids:
                print(f"   {table:28s} пусто")
                continue
            # Таблица уже 1..N без дырок? Тогда трогаем только если нужно
            # (всё равно прогоняем — дешево и выравнивает последовательность).
            moved = _rebuild_table(db, table, old_ids, mapping, refs)
            db.flush()
            print(f"   {table:28s} перенумеровано {moved}")

        db.commit()
        print("\n-- Перенумерация применена. Контроль (после):")
        _report(db)
        print("\nГотово. Следующий шаг: renumber_finalize.py "
              "(хронология начислений/кассы, регистры, квитанции).")
        return 0
    except Exception as exc:  # noqa: BLE001 — откат при любой ошибке переноса
        db.rollback()
        print("СБОЙ — изменения откачены полностью.")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
