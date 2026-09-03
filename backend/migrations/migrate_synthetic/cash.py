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
для каждого прихода/расхода.

Идемпотентность не гарантирована (для чистой БД). При повтор половой надо
сначала опустошить transactions/cash_register.

Запуск (в контейнере backend):
    python migrations/_import_cash.py --csv /app/_migration_src
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

        count = 0
        n_in = n_out = n_start = 0
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
        for r in cash_csv_rows:
            kind = r["kind"]
            amount = _dec(r["amount"])
            if amount is None:
                continue
            # date: преобраз входной даты (str) гггг-мм-дд
            raw_date = str(r["date"])[:10]
            ttype = "in_cash" if kind in ("in", "start_cash") else "out_cash"
            acc_raw = r["account"]
            account_id = None
            if acc_raw and str(acc_raw).strip() not in ("", "None"):
                key = str(acc_raw).strip().split(".")[0]
                account_id = acc_map.get(key) or acc_map.get(str(int(float(acc_raw))))
            art_id = inc_art if kind in ("in", "start_cash") else exp_art
            notes = r["comment"] or ""
            tid = db.execute(tx_insert, {
                "d": raw_date, "acc": account_id, "cp": cp_id, "art": art_id,
                "ttype": ttype, "amt": amount, "notes": notes, "mig": mig_id,
            }).scalar()
            is_in = kind in ("in", "start_cash")
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
        print(f"Касса записана (core): {count} (in={n_in}, out={n_out}, start={n_start}).")
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
