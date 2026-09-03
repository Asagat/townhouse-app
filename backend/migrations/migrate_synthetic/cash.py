# backend/migrations/_import_cash.py
"""ЭТАП кассы (синтез), версия на «чистых» core-SQL.

Причина: ORM-событие модели Transaction (transaction_after_insert) вносит кассу
и пересчитывает баланс на каждую строку/O(n^2), и его сложно надёжно погасить.
Здесь Transaction и cash_register вставляются ПРЯМЫМ SQL (text) — mapper-события
на core-INSERT не срабатывают, поэтому без дублей и быстро. В конце один раз
пересчитываем балансы кассы по затронутым л/с (как наличный остаток).

SQL:
  INSERT INTO transactions (...) VALUES (...) RETURNING id
  INSERT INTO cash_register (...) VALUES (...)
на каждую результирующую операцию.

Группировка приходов: по договорённости при миграции все жительские приходы
(квартира/л/с) одной даты сливаются в ОДИН документ «Приход в кассу» (суммы
складываются, комментарии-фрагменты объединяются через «; »). Сторно-проводки,
входящее сальдо и расходы остаются отдельными документами. До группировки каждая
строка CSV порождала отдельный документ, из-за чего на одну квартиру/дату
создавались лишние приходы (например, 4 документа вместо 1).

Идемпотентность не гарантирована (для чистой БД). При повтор половой надо
сначала опустошить transactions/cash_register.

Запуск (в контейнере backend):
    python migrations/migrate_synthetic/cash.py --csv /app/_migration_src
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import decimal
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import database  # noqa: E402
from models import recalculate_cash_balance  # noqa: E402
from sqlalchemy import text  # noqa: E402


def _dec(v):
    try:
        return decimal.Decimal(str(v))
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="_migration_src")
    args = ap.parse_args()
    with (Path(args.csv) / "cash.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    # аналитика / учёт: получим id
    cash_csv_rows = rows  # kind in=Приход, out=Расход, start_cash=Приход(сальдо)

    db = database.SessionLocal()
    try:
        mig_id = db.execute(text("SELECT id FROM users WHERE username='migration'")).scalar()
        cp_id = db.execute(text("SELECT id FROM cash_points LIMIT 1")).scalar()
        if not mig_id or not cp_id:
            print("Нет user migration / cash_point.")
            return 1
        # статьи (income/expense) - get or create
        def art(name, kind):
            row = db.execute(text("SELECT id FROM analytic_articles WHERE name=:n AND kind=:k"),
                             {"n": name, "k": kind}).first()
            if row:
                return row[0]
            db.execute(text("INSERT INTO analytic_articles (name, kind, is_active) VALUES (:n,:k,true) RETURNING id"),
                       {"n": name, "k": kind})
            return db.execute(text("SELECT id FROM analytic_articles WHERE name=:n AND kind=:k"),
                              {"n": name, "k": kind}).scalar()

        inc_art = art("Поступления от жителей", "income")
        exp_art = art("Расходы по дому", "expense")

        acc_map = {}
        rows_acc = db.execute(text("""
            SELECT a.id, ap.apartment_number FROM accounts a
            JOIN apartments ap ON ap.id = a.apartment_id""")).all()
        for acc_id, num in rows_acc:
            acc_map[str(num)] = acc_id

        # ------------------------------------------------------------------
        # Группировка приходов в один документ на квартиру/день.
        # По соглашению при миграции: строки прихода по одной квартире (л/с) за
        # одну дату сливаются в ОДИН документ «Приход в кассу» (суммы складыва-
        # ются, комментарии-фрагменты объединяются). Сторно-проводки, «входящее
        # сальдо» и расходы НЕ сливаются — они остаются отдельными документами.
        # ------------------------------------------------------------------
        count = 0
        n_in = n_out = n_start = n_merged = 0
        tx_insert = text("""
            INSERT INTO transactions
              (transaction_date, account_id, cash_point_id, article_id, transaction_type,
               amount, notes, title, created_by)
            VALUES (:d, :acc, :cp, :art, :ttype, :amt, :notes, '', :mig)
            RETURNING id
        """)
        cr_insert = text("""
            INSERT INTO cash_register
              (operation_date, account_id, transaction_id, income, expense, balance_after)
            VALUES (:d, :acc, :txid, :income, :expense, 0)
        """)

        # Каждая запись — dict-«операция»; для корректного порядка единицы групп
        # ставятся на место первой строки группы (по аналогии со слиянием при
        # перечислении cash_csv_rows).
        def _acc_of(acc_raw):
            if acc_raw and str(acc_raw).strip() not in ("", "None"):
                key = str(acc_raw).strip().split(".")[0]
                return acc_map.get(key) or acc_map.get(str(int(float(acc_raw))))
            return None

        records = []  # упорядоченный список операций к вставке
        groups = {}   # (account_id, raw_date) -> индекс в records
        n_src_rows = 0
        for r in cash_csv_rows:
            n_src_rows += 1
            kind = r["kind"]
            amount = _dec(r["amount"])
            if amount is None:
                continue
            raw_date = str(r["date"])[:10]
            account_id = _acc_of(r["account"])
            is_in = kind in ("in", "start_cash")
            is_storno = str(r.get("is_storno") or "").strip() == "1"
            notes = (r["comment"] or "").strip()
            # строка resident-прихода попадает в группу (квартира + дата)
            if kind == "in" and account_id is not None and not is_storno:
                gkey = (account_id, raw_date)
                if gkey not in groups:
                    groups[gkey] = len(records)
                    records.append({"kind": kind, "amount": amount, "raw_date": raw_date,
                                    "account_id": account_id, "is_in": is_in, "notes": notes})
                else:
                    rec = records[groups[gkey]]
                    rec["amount"] = rec["amount"] + amount
                    n_merged += 1
                    # объединяем разные комментарии-фрагменты (например,
                    # разные статьи платежа за один день) через «; »
                    if notes and notes not in rec["notes"].split("; "):
                        if rec["notes"]:
                            rec["notes"] += "; "
                        rec["notes"] += notes
                continue
            records.append({"kind": kind, "amount": amount, "raw_date": raw_date,
                            "account_id": account_id, "is_in": is_in, "notes": notes})

        for rec in records:
            kind = rec["kind"]
            amount = rec["amount"]
            raw_date = rec["raw_date"]
            account_id = rec["account_id"]
            is_in = rec["is_in"]
            ttype = "in_cash" if is_in else "out_cash"
            art_id = inc_art if kind in ("in", "start_cash") else exp_art
            notes = rec["notes"]
            tid = db.execute(tx_insert, {
                "d": raw_date, "acc": account_id, "cp": cp_id, "art": art_id,
                "ttype": ttype, "amt": amount, "notes": notes, "mig": mig_id,
            }).scalar()
            db.execute(cr_insert, {
                "d": raw_date, "acc": account_id, "txid": tid,
                "income": amount if is_in else decimal.Decimal(0),
                "expense": decimal.Decimal(0) if is_in else amount,
            })
            # суффиксу названия после id
            label = "Приход в кассу" if kind in ("in", "start_cash") else "Расход из кассы"
            db.execute(text("UPDATE transactions SET title=:t WHERE id=:id"),
                       {"t": f"{label} №{tid} от {raw_date[8:]}.{raw_date[5:7]}.{raw_date[:4]}",
                        "id": tid})
            count += 1
            if kind == "in":
                n_in += 1
            elif kind == "out":
                n_out += 1
            else:
                n_start += 1
        db.commit()
        print(f"Касса записана (core): {count} документов из {n_src_rows} строк CSV"
              f" (in={n_in}, out={n_out}, start={n_start}, слито строк в общий приход={n_merged}).")
    except Exception as exc:
        db.rollback()
        print("ОШИБКА кассы:", exc)
        db.close()
        return 1

    # один раз пересчитываем баланс наличных по затронутым л/с
    try:
        acc_ids = [x[0] for x in db.execute(text(
            "SELECT DISTINCT account_id FROM cash_register WHERE account_id IS NOT NULL")).all()]
        for acc_id in acc_ids:
            recalculate_cash_balance(db, acc_id)
        db.commit()
        print(f"Пересчитано кассовых баланс.по счетам: {len(acc_ids)}.")
    except Exception as exc:
        db.rollback()
        print("ОШИБКА пересчёта кассы:", exc)
        db.close()
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
