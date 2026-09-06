# backend/migrations/move_prochie_rashody_to_fond.py
"""Переносит начисления с услуги «Прочие расходы» на «Фонд развития» и удаляет её.

Решение владельца (09.2026): вида услуги «Прочие расходы» быть не должно —
«прочие» начисления идут через услугу «Фонд развития».

Что делает (в одной транзакции; при сбое — полный откат):
  1) Перепривязывает строки accruals_register с услуги-источника на цель:
     - services_type_id -> целевая услуга;
     - tariff_id -> действующий тариф целевой услуги на дату начисления
       (последний с valid_from <= accrual_date, иначе самый ранний), чтобы
       у строки не оставалась ссылка на тариф удаляемой услуги.
  2) Удаляет тарифы источника (после перепривязки они не используются).
  3) Переносит ссылки остальных таблиц (accounts_register, receipt_items,
     writeoff_items, meters, meter_readings, meter_reading_documents) 7 -> 6.
  4) Пересобирает производный Регистр взаиморасчётов «с нуля»
     (rebuild_accounts_register — детерминированный пересчёт из первичных регистров).
  5) Перегенерирует квитанции затронутых периодов (счёт × месяц), где были
     начисления источника (удаляет старую квитанцию и формирует заново).
  6) Удаляет саму услугу-источник.

Повторный запуск безопасен: если источника уже нет — выход без изменений.

Запуск (в контейнере backend, из каталога /app):
    python migrations/move_prochie_rashody_to_fond.py            # dry-run: план
    python migrations/move_prochie_rashody_to_fond.py --apply    # выполнить
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import date  # noqa: E402

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

import database  # noqa: E402
from models import Account, ServiceType  # noqa: E402
from writeoffs import rebuild_accounts_register  # noqa: E402
from routers.receipts import generate_receipt_document  # noqa: E402

SOURCE_NAME = "Прочие расходы"
TARGET_NAME = "Фонд развития"

# Таблицы со ссылкой на услугу (services_type_id), кроме tariffs — тарифы
# источника удаляются отдельно (шаг 2).
LINKED_TABLES = [
    "accounts_register",
    "receipt_items",
    "writeoff_items",
    "meters",
    "meter_readings",
    "meter_reading_documents",
]


def _count(db, sql: str, **params) -> int:
    return int(db.execute(text(sql), params).scalar() or 0)


def _pick_tariff_for(db, services_type_id: int, on_date: date) -> int | None:
    """Тариф услуги, действующий на дату; если нет — самый ранний."""
    tid = db.execute(
        text(
            "SELECT id FROM tariffs WHERE services_type_id = :s AND is_oneoff = false "
            "AND valid_from <= :d ORDER BY valid_from DESC, id DESC LIMIT 1"
        ),
        {"s": services_type_id, "d": on_date},
    ).scalar()
    if tid is None:
        tid = db.execute(
            text(
                "SELECT id FROM tariffs WHERE services_type_id = :s AND is_oneoff = false "
                "ORDER BY valid_from ASC, id ASC LIMIT 1"
            ),
            {"s": services_type_id},
        ).scalar()
    return int(tid) if tid is not None else None


def main() -> int:
    apply = "--apply" in sys.argv
    db = database.SessionLocal()
    try:
        source = db.query(ServiceType).filter(ServiceType.services_type == SOURCE_NAME).first()
        target = db.query(ServiceType).filter(ServiceType.services_type == TARGET_NAME).first()

        if source is None:
            print(f"Услуга «{SOURCE_NAME}» не найдена — вероятно, уже перенесена. Пропуск.")
            return 0
        if target is None:
            print(f"Целевая услуга «{TARGET_NAME}» не найдена — останов.")
            return 1
        s_id, t_id = source.id, target.id
        if s_id == t_id:
            return 0

        print(f"Источник: id={s_id} «{SOURCE_NAME}»")
        print(f"Цель:     id={t_id} «{TARGET_NAME}»")

        # --- План.
        n_acc = _count(db, "SELECT count(*) FROM accruals_register WHERE services_type_id = :s", s=s_id)
        acc_sum = db.execute(
            text("SELECT COALESCE(SUM(amount), 0) FROM accruals_register WHERE services_type_id = :s"),
            {"s": s_id},
        ).scalar()
        periods = db.execute(
            text(
                "SELECT DISTINCT account_id, EXTRACT(YEAR FROM accrual_date)::int AS y, "
                "EXTRACT(MONTH FROM accrual_date)::int AS m "
                "FROM accruals_register WHERE services_type_id = :s ORDER BY account_id, y, m"
            ),
            {"s": s_id},
        ).fetchall()
        print(f"\nНачислений у источника: {n_acc}, сумма: {float(acc_sum):.2f}")
        print(f"Затронутые периоды (счёт × месяц): {len(periods)}")
        for row in periods:
            print(f"  счёт id={row[0]}: {row[2]:02d}.{row[1]}")

        tariff_ids = [int(r) for r in db.execute(
            text("SELECT id FROM tariffs WHERE services_type_id = :s"), {"s": s_id}
        ).scalars().all()]
        print(f"\nТарифы источника (будут удалены после перепривязки): {len(tariff_ids)} {tariff_ids}")

        for table in LINKED_TABLES:
            cnt = _count(db, f"SELECT count(*) FROM {table} WHERE services_type_id = :s", s=s_id)
            if cnt:
                print(f"  {table}: строк со ссылкой на источник: {cnt}")

        if not apply:
            print("\nDry-run: изменения НЕ выполнены. Повторите с --apply для применения.")
            return 0

        # --- Применение.
        print("\nПрименяю…")
        # 1. Перепривязка начислений + тариф целевой услуги на дату начисления.
        accruals = db.execute(
            text("SELECT id, accrual_date FROM accruals_register WHERE services_type_id = :s"),
            {"s": s_id},
        ).fetchall()
        fixed = 0
        for acc_id, acc_date in accruals:
            new_tariff = _pick_tariff_for(db, t_id, acc_date)
            db.execute(
                text(
                    "UPDATE accruals_register SET services_type_id = :t, tariff_id = :tariff "
                    "WHERE id = :id"
                ),
                {"t": t_id, "tariff": new_tariff, "id": int(acc_id)},
            )
            fixed += 1
        print(f"  accruals_register: перепривязано {fixed} начислений -> «{TARGET_NAME}»")

        # 2. Удаление тарифов источника (после перепривязки они не используются).
        if tariff_ids:
            refs = _count(
                db,
                "SELECT count(*) FROM accruals_register WHERE tariff_id = ANY(:ids)",
                ids=tariff_ids,
            )
            if refs:
                print(f"СБОЙ: {refs} начислений всё ещё ссылаются на тарифы источника.")
                return 1
            db.execute(text("DELETE FROM tariffs WHERE id = ANY(:ids)"), {"ids": tariff_ids})
            print(f"  tariffs: удалено {len(tariff_ids)}")

        # 3. Остальные таблицы -> целевая услуга.
        for table in LINKED_TABLES:
            cnt = _count(db, f"SELECT count(*) FROM {table} WHERE services_type_id = :s", s=s_id)
            if cnt:
                db.execute(
                    text(f"UPDATE {table} SET services_type_id = :t WHERE services_type_id = :s"),
                    {"t": t_id, "s": s_id},
                )
                print(f"  {table}: перенесено {cnt} строк -> услуга id={t_id}")

        # 4. Пересборка Регистра взаиморасчётов «с нуля».
        res = rebuild_accounts_register(db)
        print(f"  accounts_register: пересобран (обработано счетов: {len(res.get('processed', []))}).")

        # 5. Перегенерация квитанций затронутых периодов.
        regen, deleted = 0, 0
        for row in periods:
            account_id, year, month = int(row[0]), int(row[1]), int(row[2])
            account = db.get(Account, account_id)
            if account is None:
                continue
            existing = db.execute(
                text(
                    "SELECT id FROM receipt_documents "
                    "WHERE account_id = :a AND period_year = :y AND period_month = :m"
                ),
                {"a": account_id, "y": year, "m": month},
            ).scalars().all()
            for rid in existing:
                db.execute(text("DELETE FROM receipt_items WHERE receipt_id = :r"), {"r": int(rid)})
                db.execute(text("DELETE FROM receipt_documents WHERE id = :r"), {"r": int(rid)})
                deleted += 1
            rec = generate_receipt_document(db, account, year, month, user_id=None)
            if rec:
                regen += 1
        print(f"  квитанции: удалено старых {deleted}, сформировано заново {regen}.")

        # 6. Удаление самой услуги-источника.
        db.delete(source)
        print(f"  services_type: удалена услуга id={s_id} «{SOURCE_NAME}»")
        db.commit()
        print("\nГотово. Транзакция закоммичена.")

        # --- Сверка.
        refs = sum(
            _count(db, f"SELECT count(*) FROM {table} WHERE services_type_id = :s", s=s_id)
            for table in LINKED_TABLES + ["accruals_register", "tariffs"]
        )
        n_acc_after = _count(db, "SELECT count(*) FROM accruals_register WHERE services_type_id = :s", s=s_id)
        total_svc = _count(db, "SELECT count(*) FROM services_type")
        receipts = _count(db, "SELECT count(*) FROM receipt_documents")
        print(f"Контроль: ссылок на удалённую услугу: {refs}; начислений источника после: {n_acc_after}; "
              f"всего услуг: {total_svc}; квитанций в БД: {receipts}.")
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
