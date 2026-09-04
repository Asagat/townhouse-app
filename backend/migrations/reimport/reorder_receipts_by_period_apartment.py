# backend/migrations/reimport/reorder_receipts_by_period_apartment.py
"""Перенумеровывает квитанции (receipt_documents + строки) по хронологии периода
«Дата документа» и внутри — по возрастанию № квартиры.

Цель: order ID квитанций соответствует сортировке
      (period_year, period_month) ASC, затем apartment_number ASC,
чтобы журнал читался по дате и квартирам, а id шёл в том же порядке.

При выполнении:
  1) снимает снимок текущих receipt_documents и receipt_items;
  2) очищает обе таблицы (RESTART IDENTITY);
  3) вставляет документы в нужном порядке (получая последовательные id),
     затем строки квитанций со ссылкой на новые id (содержимое сохраняется);
  4) восстанавливает последовательность под max(id).

Всё в ОДНОЙ транзакции; при сбое — полный откат.

Запуск (в контейнере backend):
    python migrations/reimport/reorder_receipts_by_period_apartment.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import text  # noqa: E402

import database  # noqa: E402


def main() -> int:
    db = database.SessionLocal()
    try:
        # --- Снимок текущего содержимого квитанций (до удаления). ---
        docs = [dict(r._mapping, id=int(r[0])) for r in db.execute(text(
            "SELECT id, account_id, period_year, period_month, apartment_number, address, "
            "owner_name, account_number, total_amount, debt, overpayment, payable_amount, "
            "issued_at, created_by, updated_by, updated_at, change_description, created_at "
            "FROM receipt_documents"
        )).fetchall()]
        items = [dict(r._mapping) for r in db.execute(text(
            "SELECT receipt_id, services_type_id, service_name, reading_prev, reading_curr, "
            "quantity, tariff, amount, debt, overpayment, payable FROM receipt_items"
        )).fetchall()]
        n_docs, n_items = len(docs), len(items)
        print(f"Снимок квитанций: документов={n_docs}, строк={n_items}.")

        # --- Порядок «Дата документа + № квартиры». ---
        docs.sort(key=lambda r: (r["period_year"], r["period_month"],
                                 (r["apartment_number"] if r["apartment_number"] is not None else 0),
                                 r["account_id"]))

        # --- Очистка и пересоздание. ---
        db.execute(text(
            "TRUNCATE TABLE receipt_items, receipt_documents RESTART IDENTITY CASCADE"
        ))

        old_to_new: dict[int, int] = {}
        doc_cols = ("account_id", "period_year", "period_month", "apartment_number", "address",
                    "owner_name", "account_number", "total_amount", "debt", "overpayment",
                    "payable_amount", "issued_at", "created_by", "updated_by", "updated_at",
                    "change_description", "created_at")
        for d in docs:
            new_id = db.execute(
                text(
                    "INSERT INTO receipt_documents "
                    "(account_id, period_year, period_month, apartment_number, address, "
                    " owner_name, account_number, total_amount, debt, overpayment, "
                    " payable_amount, issued_at, created_by, updated_by, updated_at, "
                    " change_description, created_at) "
                    "VALUES (:account_id,:period_year,:period_month,:apartment_number,:address,"
                    ":owner_name,:account_number,:total_amount,:debt,:overpayment,"
                    ":payable_amount,:issued_at,:created_by,:updated_by,:updated_at,"
                    ":change_description,:created_at) RETURNING id"
                ),
                {c: d[c] for c in doc_cols},
            ).scalar()
            old_to_new[int(d["id"])] = int(new_id)

        item_cols = ("services_type_id", "service_name", "reading_prev", "reading_curr",
                     "quantity", "tariff", "amount", "debt", "overpayment", "payable")
        for it in items:
            db.execute(
                text(
                    "INSERT INTO receipt_items "
                    "(receipt_id, services_type_id, service_name, reading_prev, reading_curr,"
                    " quantity, tariff, amount, debt, overpayment, payable) "
                    "VALUES (:rid,:services_type_id,:service_name,:reading_prev,:reading_curr,"
                    ":quantity,:tariff,:amount,:debt,:overpayment,:payable)"
                ),
                {"rid": old_to_new[int(it["receipt_id"])], **{c: it[c] for c in item_cols}},
            )

        db.execute(text(
            "SELECT setval('receipt_documents_id_seq', (SELECT max(id) FROM receipt_documents))"
        ))
        db.execute(text(
            "SELECT setval('receipt_items_id_seq', (SELECT max(id) FROM receipt_items))"
        ))
        db.commit()
        print(f"Квитанции пересозданы: документов={n_docs}, строк={n_items} в порядке периода+квартиры.")

        # --- Контроль: первые строки целевого порядка. ---
        top = db.execute(text(
            "SELECT id, period_year, period_month, apartment_number, account_number "
            "FROM receipt_documents ORDER BY id ASC LIMIT 5"
        )).fetchall()
        for t in top:
            print(" первая ->", tuple(t))
        print("ГОТОВО.")
    except Exception:
        db.rollback()
        print("СБОЙ — изменения ОТКАЧЕНЫ полностью.")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
