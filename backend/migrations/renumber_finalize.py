# backend/migrations/renumber_finalize.py
"""Финализация после полной перенумерации: хронология, регистры, квитанции.

НАЗНАЧЕНИЕ
    Второй (и последний) шаг варианта B / ТД-2. Выполняется ПОСЛЕ
    renumber_all_entities.py. Восстанавливает бизнес-смысл, который перенумерация
    могла «сплющить»: хронологический порядок документов и согласованность
    производных регистров.

ЧТО ДЕЛАЕТ ПО ШАГАМ
    1) Пересоздаёт документы начислений и их строки по хронологии — входящий
       остаток (самая ранняя дата) получает минимальный id;
    2) Перенумеровывает «Приход/Расход» по хронологии: «Начальный остаток» → id/doc_no=1,
       обновляет doc_no и title («Тип операции №<id> от <дд.мм.гггг>»);
    3) Пересобирает accounts_register ядром проекта (rebuild_accounts_register)
       и пересчитывает балансы;
    4) Перегенеряет квитанции по (счёт × период) с начислениями;
    5) Контроль: check_register_integrity по всем счетам + контрольные суммы.

ПОЧЕМУ ОТДЕЛЬНЫЙ СКРИПТ
    renumber_all_entities.py меняет только числовые ключи; он не должен знать про
    бизнес-хронологию. Здесь — семантика. Такое разделение позволяет прогнать
    каждый шаг и проверить результат по отдельности (в т.ч. dry-run первого).

РЕЖИМЫ
    python migrations/renumber_finalize.py --dry-run   # только отчёт/план
    python migrations/renumber_finalize.py             # применить

ПРЕДУСЛОВИЕ
    Свежий бэкап. Перед запуском приложение лучше остановить (backend).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

import database
from models import Account, TransactionTypeEnum
from routers.receipts import generate_receipt_document
from writeoffs import check_register_integrity, rebuild_accounts_register


def _snapshot_accrual_docs(db) -> list[dict]:
    rows = db.execute(text(
        "SELECT id, accrual_date, title, created_at, created_by, updated_by, updated_at, "
        "change_description, doc_kind, comment FROM accrual_documents "
        "ORDER BY accrual_date ASC, id ASC"
    )).fetchall()
    return [dict(r._mapping) for r in rows]


def _snapshot_accruals(db) -> list[dict]:
    rows = db.execute(text(
        "SELECT accrual_document_id, accrual_date, account_id, tariff_id, services_type_id, "
        "current_reading_id, past_reading_value, current_reading_value, consumption, amount "
        "FROM accruals_register"
    )).fetchall()
    return [dict(r._mapping) for r in rows]


def _finalize_accruals(db) -> None:
    """Пересоздаёт начисления по хронологии (входящий остаток → минимальный id)."""
    docs = _snapshot_accrual_docs(db)
    accruals = _snapshot_accruals(db)
    print(f"Начисления: документов={len(docs)}, строк={len(accruals)}.")

    # TRUNCATE ... RESTART IDENTITY CASCADE: дочерние регистры (accruals_register,
    # accounts_register) очищаются каскадом и далее пересоздаются.
    db.execute(text(
        "TRUNCATE TABLE receipt_documents, accrual_documents RESTART IDENTITY CASCADE"
    ))
    db.flush()

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
    db.commit()
    print("Начисления пересозданы по хронологии.")


def _finalize_transactions(db) -> None:
    """Перенумеровывает «Приход/Расход» в хронологическом порядке.

    Логика повторяет migrations/reimport/renumber_transactions_chronological.py,
    но вызывается уже ПОСЛЕ полной перенумерации, поэтому дополнительно
    выравнивает последовательность. Работает прямым SQL, минуя ORM-события
    (иначе transaction_after_update насоздаёт дублей в cash_register).
    """
    opening_kind_ids = {
        r[0] for r in db.execute(
            text("SELECT id FROM analytic_articles WHERE kind = 'opening'")
        ).fetchall()
    }
    rows = db.execute(text(
        "SELECT id, transaction_date, account_id, article_id FROM transactions"
    )).fetchall()
    recs = [dict(r._mapping) for r in rows]
    print(f"Транзакции: {len(recs)}.")

    def is_house_opening(r: dict) -> bool:
        return r["account_id"] is None and r["article_id"] in opening_kind_ids

    recs.sort(key=lambda r: (
        str(r["transaction_date"]), 0 if is_house_opening(r) else 1, r["id"]
    ))
    old_to_new = {int(r["id"]): rank for rank, r in enumerate(recs, start=1)}

    # Снимаем FK на время переноса id (восстановим идентичными ниже).
    for tbl, col in (("cash_register", "transaction_id"),
                     ("accounts_register", "transaction_id")):
        db.execute(text(f"ALTER TABLE {tbl} DROP CONSTRAINT IF EXISTS {tbl}_{col}_fkey"))

    for r in recs:
        oid = int(r["id"])
        db.execute(text("UPDATE transactions SET id = :n WHERE id = :o"),
                   {"n": -oid, "o": oid})
        db.execute(text(
            "UPDATE cash_register SET transaction_id = :n WHERE transaction_id = :o"),
            {"n": -oid, "o": oid})

    for r in recs:
        oid = int(r["id"])
        db.execute(text("UPDATE transactions SET id = :n WHERE id = :o"),
                   {"n": old_to_new[oid], "o": -oid})
        db.execute(text(
            "UPDATE cash_register SET transaction_id = :n WHERE transaction_id = :o"),
            {"n": old_to_new[oid], "o": -oid})

    # doc_no = сквозной хронологический номер (= id после перенумерации).
    db.execute(text(
        "WITH x AS (SELECT id, row_number() OVER (ORDER BY id ASC) rn FROM transactions) "
        "UPDATE transactions t SET doc_no = x.rn FROM x WHERE t.id = x.id"
    ))

    # Названия по формуле «Тип операции №<id> от <дд.мм.гггг>».
    type_label = {m.name: m.value for m in TransactionTypeEnum}

    def label_of(raw):
        return type_label.get(raw) or next(
            (v for k, v in type_label.items() if v == raw), None)

    titles = 0
    for t in db.execute(text(
        "SELECT id, transaction_type, transaction_date FROM transactions"
    )).fetchall():
        label = label_of(t[1])
        if not label:
            continue
        d = t[2]
        date_label = d.strftime("%d.%m.%Y") if d is not None else ""
        db.execute(text("UPDATE transactions SET title = :t WHERE id = :id"),
                   {"t": f"{label} №{t[0]} от {date_label}".strip(), "id": int(t[0])})
        titles += 1

    # Восстанавливаем FK кассы и пересчитываем последовательность.
    db.execute(text(
        "ALTER TABLE cash_register ADD CONSTRAINT cash_register_transaction_id_fkey "
        "FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE"
    ))
    db.execute(text(
        "SELECT setval('transactions_id_seq', (SELECT max(id) FROM transactions))"
    ))
    db.commit()
    print(f"Транзакции перенумерованы, doc_no и названия обновлены ({titles}).")


def _finalize_registers(db) -> None:
    """Пересборка accounts_register + восстановление FK-констрейнта транзакций."""
    res = rebuild_accounts_register(db)
    db.execute(text(
        "ALTER TABLE accounts_register ADD CONSTRAINT accounts_register_transaction_id_fkey "
        "FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE"
    ))
    db.commit()
    print(f"Регистр взаиморасчётов пересобран: счетов={len(res['processed'])}.")


def _regenerate_receipts(db) -> None:
    periods = db.execute(text(
        "SELECT DISTINCT account_id, EXTRACT(YEAR FROM accrual_date)::int, "
        "EXTRACT(MONTH FROM accrual_date)::int FROM accruals_register"
    )).fetchall()
    made = 0
    for account_id, year, month in periods:
        account = db.get(Account, account_id)
        if account is None:
            continue
        if generate_receipt_document(db, account, year, month, user_id=None):
            made += 1
    db.commit()
    n_rec = db.execute(text("SELECT count(*) FROM receipt_documents")).scalar()
    print(f"Квитанции: сгенерировано {made}, всего в БД {n_rec}.")


def _control(db) -> int:
    """Контроль целостности регистров; возвращает число несогласованных счетов."""
    ids = [int(r[0]) for r in db.execute(text(
        "SELECT id FROM accounts ORDER BY id ASC"
    )).fetchall()]
    bad = []
    for aid in ids:
        res = check_register_integrity(db, aid)
        if not res["consistent"]:
            bad.append(res)
    print(f"Контроль целостности: счетов={len(ids)}, несогласованных={len(bad)}.")
    for r in bad[:20]:
        print(f"   счёт {r['account_id']}: начислено {r['accrued_register']} vs "
              f"{r['accrued_settlement']}, списано {r['written_off']}, "
              f"доступно {r['available']}, баланс {r['balance']}")
    return len(bad)


def main() -> int:
    ap = argparse.ArgumentParser(description="Финализация после перенумерации (ТД-2)")
    ap.add_argument("--dry-run", action="store_true",
                    help="только показать, что будет сделано")
    args = ap.parse_args()

    db = database.SessionLocal()
    try:
        if args.dry_run:
            n_docs = db.execute(text("SELECT count(*) FROM accrual_documents")).scalar()
            n_acc = db.execute(text("SELECT count(*) FROM accruals_register")).scalar()
            n_tx = db.execute(text("SELECT count(*) FROM transactions")).scalar()
            n_rec = db.execute(text("SELECT count(*) FROM receipt_documents")).scalar()
            print("DRY-RUN. Будет выполнено:")
            print(f"  - пересоздание начислений по хронологии (док={n_docs}, строк={n_acc});")
            print(f"  - перенумерация «Приход/Расход» по хронологии ({n_tx});")
            print("  - пересборка accounts_register и пересчёт балансов;")
            print(f"  - перегенерация квитанций (сейчас {n_rec});")
            print("  - контроль целостности регистров.")
            return 0

        _finalize_accruals(db)
        _finalize_transactions(db)
        _finalize_registers(db)
        _regenerate_receipts(db)
        bad = _control(db)
        print("\nГотово." if bad == 0 else f"\nГотово, но несогласованных счетов: {bad}.")
        return 0 if bad == 0 else 2
    except Exception as exc:  # noqa: BLE001 — откат дочерних шагов при любой ошибке
        db.rollback()
        print(f"СБОЙ ({exc!r}) — изменения откачены.")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
