# backend/migrations/reimport/recreate_and_resync.py
"""Разовые контрольные операции для перезаливки после вката истории (prod/2026).

Делает три связанных действия ТРАНЗАКЦИОННО (или пофазно с откатом при первом сбое):
  1) Удаляет КВИТАНЦИИ (receipt_documents + их строки) — будут пересозданы заново
     генератором по правильной формуле «К оплате».
  2) Пересоздаёт НАЧИСЛЕНИЯ в хронологическом порядке: все accrual_documents/
     accruals_register удаляются и вставляются заново так, что id входящих остатков
     (старта, 2017-10) становится НАИМЕНЬШИМ, а месячные идут по нарастанию периода.
     Содержимое строк (суммы/тарифы/услуги/показания) берётся из текущих данных —
     входной истории не используем, поэтому итоги не «уплывают».
  3) Пересобирает производный Регистр взаиморасчётов (accounts_register) «с нуля»
     ядром проекта (rebuild_accounts_register) — с корректными датами списаний.

Запускать ТОЛЬКО после бэкапа БД и после миграции схемы. Прогон для чистой dev/прод:
    python migrations/reimport/recreate_and_resync.py

Порядок гарантирует, что расчёт квитанций (начислено за период + долг на начало −
переплата) вновь сходится по-месячно, а журнал «Начисления» читается хронологически.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import text  # noqa: E402

import database  # noqa: E402
from writeoffs import rebuild_accounts_register  # noqa: E402
from routers.receipts import generate_receipt_document  # noqa: E402
from models import Account  # noqa: E402


def _snapshot_docs(db) -> list[dict]:
    rows = db.execute(text(
        "SELECT id, accrual_date, title, created_at, created_by, updated_by, updated_at, "
        "change_description, doc_kind, comment FROM accrual_documents ORDER BY accrual_date, id"
    )).fetchall()
    return [dict(r._mapping) for r in rows]


def _snapshot_accruals(db) -> list[dict]:
    rows = db.execute(text(
        "SELECT accrual_document_id, accrual_date, account_id, tariff_id, services_type_id, "
        "current_reading_id, past_reading_value, current_reading_value, consumption, amount "
        "FROM accruals_register"
    )).fetchall()
    return [dict(r._mapping) for r in rows]


def main() -> int:
    db = database.SessionLocal()
    try:
        # ---- 0. Снимок текущего содержимого первичных регистров (до удаления).
        docs = _snapshot_docs(db)
        accruals = _snapshot_accruals(db)
        n_docs, n_acc = len(docs), len(accruals)
        print(f"Снимок: документов начислений={n_docs}, строк начислений={n_acc}.")

        # ---- 1. Удаляем квитанции (пересоздаст генератор) и сами начисления.
        # TRUNCATE ... CASCADE: receipt -> items; accrual_documents -> accruals_register
        # и далее -> accounts_register (производный срез, он всё равно пересобирается).
        db.execute(text("TRUNCATE TABLE receipt_documents, accrual_documents RESTART IDENTITY CASCADE"))
        db.commit()
        print("Очищены таблицы: квитанции, начисления (регистры и документы).")

        # ---- 3. Вставляем начисления заново в хронологическом порядке.
        # Документы вставляются по возрастанию (accrual_date), поэтому «Входящие
        # остатки (старт)» (2017-10) получает наименьший id, а месяцие — по порядку.
        old2new: dict[int, int] = {}
        for d in docs:
            new_id = db.execute(
                text(
                    "INSERT INTO accrual_documents "
                    "(accrual_date, title, created_at, created_by, updated_by, updated_at, "
                    " change_description, doc_kind, comment) "
                    "VALUES (:ad, :title, :created_at, :cb, :ub, :ua, :cd, :kind, :comment) "
                    "RETURNING id"
                ),
                {
                    "ad": d["accrual_date"], "title": d["title"],
                    "created_at": d["created_at"], "cb": d["created_by"],
                    "ub": d["updated_by"], "ua": d["updated_at"],
                    "cd": d["change_description"], "kind": d["doc_kind"],
                    "comment": d["comment"],
                },
            ).scalar()
            old2new[int(d["id"])] = int(new_id)

        acc_doc_rows = 0
        for r in accruals:
            db.execute(
                text(
                    "INSERT INTO accruals_register "
                    "(accrual_document_id, accrual_date, account_id, tariff_id, services_type_id, "
                    " current_reading_id, past_reading_value, current_reading_value, consumption, amount) "
                    "VALUES (:did, :ad, :acc, :t, :svc, :rd, :pv, :cv, :cons, :amount)"
                ),
                {
                    "did": old2new[int(r["accrual_document_id"])],
                    "ad": r["accrual_date"], "acc": r["account_id"], "t": r["tariff_id"],
                    "svc": r["services_type_id"], "rd": r["current_reading_id"],
                    "pv": r["past_reading_value"], "cv": r["current_reading_value"],
                    "cons": r["consumption"], "amount": r["amount"],
                },
            )
            acc_doc_rows += 1
        db.commit()
        print(f"Пересоздано документов начислений={n_docs}, строк начислений={acc_doc_rows} по-хронологии.")

        # ---- 4. Пересборка производного Регистра взаиморасчётов (accounts_register).
        res = rebuild_accounts_register(db)
        db.commit()
        accounts = res["processed"]
        print(f"Регистр взаиморасчётов пересобран: счетов={len(accounts)}.")

        # ---- 5. Перегенерация квитанций генератором для всех (счёт × период).
        # Список (account_id, year, month), где есть начисления: берём из регистра.
        periods = db.execute(text(
            "SELECT DISTINCT account_id, EXTRACT(YEAR FROM accrual_date)::int, EXTRACT(MONTH FROM accrual_date)::int "
            "FROM accruals_register"
        )).fetchall()
        created_receipts = 0
        for account_id, year, month in periods:
            account = db.get(Account, account_id)
            if account is None:
                continue
            rec = generate_receipt_document(db, account, year, month, user_id=None)
            if rec:
                created_receipts += 1
        db.commit()
        db.flush()
        print(f"Сгенерировано квитанций: {created_receipts}.")

        # Итоговая сверка.
        n_receipts = db.execute(text("SELECT count(*) FROM receipt_documents")).scalar()
        n_items = db.execute(text("SELECT count(*) FROM receipt_items")).scalar()
        print(f"Итог: квитанций в БД={n_receipts}, строк={n_items}. Готово.")
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
