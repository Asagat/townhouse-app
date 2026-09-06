# backend/migrations/dedupe_electricity_service.py
"""Объединяет дубль вида услуги «Электричество» в «Электроэнергию».

Причина (09.2026): в dev-БД рядом с канонической услугой «Электроэнергия» (на неё
ссылаются счётчики/показания/начисления) заведён семантический дубль
«Электричество» — в связанных таблицах он НЕ используется (только собственный
тариф без ссылок из начислений).

Что делает:
  1) Переносит строки ВСЕХ таблиц со ссылкой на источник (services_type_id =
     источник) на целевую услугу.
  2) Тарифы источника: если на тариф НЕТ ссылок из accruals_register (мусор) —
     удаляет; если ссылки есть (реальная история) — переносит тариф на цель.
  3) Удаляет саму услугу-источник.
Всё в одной транзакции; при любом сбое — полный откат.

Повторный запуск безопасен: если источника уже нет — скрипт выходит без изменений.

Запуск (в контейнере backend, из каталога /app):
    python migrations/dedupe_electricity_service.py            # dry-run: план
    python migrations/dedupe_electricity_service.py --apply    # выполнить
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

import database  # noqa: E402
from models import ServiceType  # noqa: E402

SOURCE_NAME = "Электричество"
TARGET_NAME = "Электроэнергия"

# Таблицы с внешним ключом на services_type (services_type_id) — см. pg_constraint.
LINKED_TABLES = [
    "tariffs",
    "meters",
    "meter_readings",
    "meter_reading_documents",
    "accruals_register",
    "accounts_register",
    "writeoff_items",
    "receipt_items",
]


def _count(db, sql: str, **params) -> int:
    return int(db.execute(text(sql), params).scalar() or 0)


def main() -> int:
    apply = "--apply" in sys.argv
    db = database.SessionLocal()
    try:
        source = db.query(ServiceType).filter(ServiceType.services_type == SOURCE_NAME).first()
        target = db.query(ServiceType).filter(ServiceType.services_type == TARGET_NAME).first()

        if source is None:
            print(f"Дубль «{SOURCE_NAME}» не найден — вероятно, уже объединён. Пропуск.")
            return 0
        if target is None:
            print(f"Целевая услуга «{TARGET_NAME}» не найдена — останов (нечего объединять).")
            return 1
        s_id, t_id = source.id, target.id
        if s_id == t_id:
            return 0

        print(f"Источник: id={s_id} «{SOURCE_NAME}»")
        print(f"Цель:     id={t_id} «{TARGET_NAME}»")

        # --- План: сколько строк «переедет» по каждой таблице.
        print("\nСтроки источника по связанным таблицам:")
        plan: list[tuple[str, int]] = []
        for table in LINKED_TABLES:
            cnt = _count(db, f"SELECT count(*) FROM {table} WHERE services_type_id = :s", s=s_id)
            plan.append((table, cnt))
            print(f"  {table}: {cnt}")
        moved_total = sum(cnt for _, cnt in plan)

        # --- Тарифы источника и их использование в начислениях.
        tariff_ids = [
            int(r) for r in db.execute(
                text("SELECT id FROM tariffs WHERE services_type_id = :s"), {"s": s_id}
            ).scalars().all()
        ]
        print(f"\nТарифы источника: {len(tariff_ids)}")
        delete_tariffs: list[int] = []
        move_tariffs: list[int] = []
        if tariff_ids:
            rows = db.execute(
                text(
                    "SELECT t.id, count(a.id) AS refs "
                    "FROM tariffs t LEFT JOIN accruals_register a ON a.tariff_id = t.id "
                    "WHERE t.id = ANY(:ids) GROUP BY t.id"
                ),
                {"ids": tariff_ids},
            ).fetchall()
            for row in rows:
                tid = int(row[0])
                refs = int(row[1])
                (delete_tariffs if refs == 0 else move_tariffs).append(tid)
                print(f"  тариф id={tid}: ссылок из начислений={refs} "
                      f"-> {'удалить' if refs == 0 else 'перенести на цель'}")
        if delete_tariffs:
            print(f"Мусорные тарифы к удалению: {delete_tariffs}")
        if move_tariffs:
            print(f"Используемые тарифы к переносу на цель: {move_tariffs}")

        if not apply:
            print("\nDry-run: изменения НЕ выполнены. Повторите с --apply для применения.")
            return 0

        # --- Применение (одна транзакция).
        print("\nПрименяю…")
        for table, cnt in plan:
            if cnt:
                db.execute(
                    text(f"UPDATE {table} SET services_type_id = :t WHERE services_type_id = :s"),
                    {"t": t_id, "s": s_id},
                )
                print(f"  {table}: перенесено {cnt} строк -> услуга id={t_id}")
        if move_tariffs:
            db.execute(
                text("UPDATE tariffs SET services_type_id = :t WHERE id = ANY(:ids)"),
                {"t": t_id, "ids": move_tariffs},
            )
            print(f"  tariffs: перенесено используемых тарифов {len(move_tariffs)}")
        if delete_tariffs:
            db.execute(text("DELETE FROM tariffs WHERE id = ANY(:ids)"), {"ids": delete_tariffs})
            print(f"  tariffs: удалено мусорных тарифов {len(delete_tariffs)}")

        db.delete(source)
        print(f"  services_type: удалён дубль id={s_id} «{SOURCE_NAME}»")
        db.commit()
        print("\nГотово. Транзакция закоммичена.")

        # --- Сверка после.
        still = db.query(ServiceType).filter(ServiceType.services_type == SOURCE_NAME).first()
        total_svc = _count(db, "SELECT count(*) FROM services_type")
        moved_check = sum(
            _count(db, f"SELECT count(*) FROM {table} WHERE services_type_id = :s", s=s_id)
            for table in LINKED_TABLES
        )
        print(f"Контроль: осталось ссылок на удалённую услугу: {moved_check}; "
              f"всего видов услуг: {total_svc}; дубль ещё существует: {still is not None}.")
        return 0
    except IntegrityError as exc:
        db.rollback()
        print("СБОЙ (нарушение целостности) — изменения ОТКАЧЕНЫ полностью.")
        print(str(exc).splitlines()[-1] if str(exc) else exc)
        return 1
    except Exception:
        db.rollback()
        print("СБОЙ — изменения ОТКАЧЕНЫ полностью.")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
