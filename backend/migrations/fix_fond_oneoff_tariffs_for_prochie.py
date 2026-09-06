# backend/migrations/fix_fond_oneoff_tariffs_for_prochie.py
"""Корректирует тарифы у начислений, перенесённых с «Прочие расходы» на «Фонд развития».

Контекст (09.2026): при переносе 30 начислений с «Прочие расходы» на «Фонд
развития» их тариф_id был заменён действующим РЕГУЛЯРНЫМ тарифом Фонда на дату
начисления (10000/2000 ₸), хотя сумма начисления осталась прежней (6000/7560 ₸)
— тариф перестал соответствовать сумме.

Что делает (в одной транзакции; при сбое — откат):
  1) Находит «разовые» тарифы Фонда с ценами 6000 (valid_from 2022-01-01) и
     7560 (valid_from 2024-03-01); если их нет — создаёт (is_oneoff = true),
     чтобы они не участвовали в обычных месячных пересчётах.
  2) Перепривязывает перенесённые начисления (services_type_id = Фонд развития,
     amount = 6000 или 7560) на эти разовые тарифы — сумма не меняется, но
     tariff_id снова соответствует сумме.
  3) Перегенерирует квитанции затронутых периодов (счёт × месяц).

Идентификация «наших» 30 строк: у Фонда регулярные суммы никогда не были равны
6000/7560, поэтому amount IN (6000, 7560) + services_type_id = Фонда выделяет
именно перенесённые начисления. Если количество отличается от ожидаемого (30) —
скрипт останавливается.

Повторный запуск безопасен (идемпотентен): при уже созданных тарифах просто
сверяет привязку.

Запуск (в контейнере backend, из каталога /app):
    python migrations/fix_fond_oneoff_tariffs_for_prochie.py            # dry-run
    python migrations/fix_fond_oneoff_tariffs_for_prochie.py --apply    # выполнить
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import date  # noqa: E402
from decimal import Decimal  # noqa: E402

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

import database  # noqa: E402
from models import Account, ServiceType, Tariff  # noqa: E402
from routers.receipts import generate_receipt_document  # noqa: E402

FOND_NAME = "Фонд развития"

# (сумма начисления, цена разового тарифа, valid_from) — по факту перенесённых строк.
ONE_OFFS = [
    (Decimal("6000.00"), Decimal("6000.00"), date(2022, 1, 1)),
    (Decimal("7560.00"), Decimal("7560.00"), date(2024, 3, 1)),
]


def _count(db, sql: str, **params) -> int:
    return int(db.execute(text(sql), params).scalar() or 0)


def _find_tariff(db, price, valid_from) -> int | None:
    tid = db.execute(
        text(
            "SELECT id FROM tariffs WHERE services_type_id = :s AND is_oneoff = true "
            "AND price = :p AND valid_from = :d ORDER BY id LIMIT 1"
        ),
        {"s": _FOND_ID, "p": price, "d": valid_from},
    ).scalar()
    return int(tid) if tid is not None else None


_FOND_ID: int | None = None


def main() -> int:
    global _FOND_ID
    apply = "--apply" in sys.argv
    db = database.SessionLocal()
    try:
        fond = db.query(ServiceType).filter(ServiceType.services_type == FOND_NAME).first()
        if fond is None:
            print(f"Услуга «{FOND_NAME}» не найдена — останов.")
            return 1
        _FOND_ID = fond.id

        # Строки, перенесённые с «Прочие расходы» (см. docstring про идентификацию).
        n_6000 = _count(
            db, "SELECT count(*) FROM accruals_register WHERE services_type_id = :s AND amount = 6000.00",
            s=_FOND_ID,
        )
        n_7560 = _count(
            db, "SELECT count(*) FROM accruals_register WHERE services_type_id = :s AND amount = 7560.00",
            s=_FOND_ID,
        )
        n_total = n_6000 + n_7560
        print(f"Перенесённые начисления: 6000 ₸ = {n_6000}, 7560 ₸ = {n_7560} (всего {n_total}).")
        if n_total != 30:
            print("Ожидалось 30 строк — данные отличаются от ожидания. Останов (нужен ручной разбор).")
            return 1

        periods = db.execute(
            text(
                "SELECT DISTINCT account_id, EXTRACT(YEAR FROM accrual_date)::int AS y, "
                "EXTRACT(MONTH FROM accrual_date)::int AS m "
                "FROM accruals_register WHERE services_type_id = :s AND amount IN (6000.00, 7560.00) "
                "ORDER BY account_id, y, m"
            ),
            {"s": _FOND_ID},
        ).fetchall()

        print("План:")
        tariff_by_amount: dict[Decimal, int | None] = {}
        for amount, price, valid_from in ONE_OFFS:
            existing = _find_tariff(db, price, valid_from)
            tariff_by_amount[amount] = existing
            print(
                f"  разовый тариф {price} ₸ (valid_from {valid_from}): "
                f"{'уже есть (id=' + str(existing) + ')' if existing else 'будет создан'}"
            )
        print(f"  затронутых периодов (квитанции): {len(periods)}")

        if not apply:
            print("\nDry-run: изменения НЕ выполнены. Повторите с --apply для применения.")
            return 0

        # --- Применение.
        print("\nПрименяю…")
        new_tariffs: dict[Decimal, int] = {}
        for amount, price, valid_from in ONE_OFFS:
            existing = tariff_by_amount[amount]
            if existing is not None:
                new_tariffs[amount] = existing
                continue
            t = Tariff(
                services_type_id=_FOND_ID,
                tariff_type_id=None,  # проставится ниже по системному типу «Фиксированный»?
                price=price,
                valid_from=valid_from,
                unit=None,
                comment=f"Разовый: историч. начисление «Прочие расходы» (перенос на «{FOND_NAME}», 09.2026)",
                is_oneoff=True,
            )
            # Тип тарифа — «Фиксированный» (разовый сбор, сумма = цена).
            row = db.execute(
                text("SELECT id FROM tariff_types WHERE name = 'Фиксированный' LIMIT 1")
            ).scalar()
            if row is None:
                print("Тип тарифа «Фиксированный» не найден — останов.")
                return 1
            t.tariff_type_id = int(row)
            db.add(t)
            db.flush()
            new_tariffs[amount] = t.id
            print(f"  + создан разовый тариф id={t.id}: {price} ₸ (valid_from {valid_from})")

        for amount, price, valid_from in ONE_OFFS:
            tid = new_tariffs[amount]
            cnt = _count(
                db,
                "SELECT count(*) FROM accruals_register "
                "WHERE services_type_id = :s AND amount = :a AND tariff_id <> :t",
                s=_FOND_ID,
                a=amount,
                t=tid,
            )
            if cnt:
                db.execute(
                    text(
                        "UPDATE accruals_register SET tariff_id = :t "
                        "WHERE services_type_id = :s AND amount = :a"
                    ),
                    {"t": tid, "s": _FOND_ID, "a": amount},
                )
                print(f"  accruals_register: перепривязано {cnt} начислений на разовый тариф {price} ₸")
            else:
                print(f"  accruals_register: начисления {price} ₸ уже привязаны к разовому тарифу")

        # Перегенерация квитанций затронутых периодов (обновляет «Тариф» в строках).
        regen, deleted = 0, 0
        for row in periods:
            account_id, year, month = int(row[0]), int(row[1]), int(row[2])
            account = db.get(Account, account_id)
            if account is None:
                continue
            existing_ids = db.execute(
                text(
                    "SELECT id FROM receipt_documents "
                    "WHERE account_id = :a AND period_year = :y AND period_month = :m"
                ),
                {"a": account_id, "y": year, "m": month},
            ).scalars().all()
            for rid in existing_ids:
                db.execute(text("DELETE FROM receipt_items WHERE receipt_id = :r"), {"r": int(rid)})
                db.execute(text("DELETE FROM receipt_documents WHERE id = :r"), {"r": int(rid)})
                deleted += 1
            if generate_receipt_document(db, account, year, month, user_id=None):
                regen += 1
        print(f"  квитанции: удалено старых {deleted}, сформировано заново {regen}.")

        db.commit()
        print("\nГотово. Транзакция закоммичена.")

        # Сверка.
        for amount, price, valid_from in ONE_OFFS:
            tid = new_tariffs[amount]
            linked = _count(
                db,
                "SELECT count(*) FROM accruals_register WHERE tariff_id = :t AND amount = :a",
                t=tid,
                a=amount,
            )
            print(f"Контроль: тариф {price} ₸ (id={tid}): начислений привязано {linked}.")
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
