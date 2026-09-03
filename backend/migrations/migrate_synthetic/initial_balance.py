# backend/migrations/_import_initial_balance.py
"""Первичный «старт»: вносит ВХОДЯЩИЕ ОСТАТКИ (enter, из accruals.csv) как строки
accruals_register за 2017-10 под услугу «Фонд развития».

Нужны accruals.csv; документируется единый AccrualDocument «Входящие остатки (старт)»
на 2017-10-01. Так первичный регистр содержит и «долг старта л/с», который затем
rebuild_accounts_register переносит в accounts_register как самые ранние income
(= начальное сальдо долга).

Тариф на этих строках ценен только наличием NOT NULL FK — за rebuild берёт amount,
поэтому подключаем самый ранний существующий тариф «Фонд развития».

Запуск (в контейнере backend):
    python migrations/_import_initial_balance.py --csv /app/_migration_src
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
from models import (  # noqa: E402
    Account,
    AccrualDocument,
    AccrualsRegister,
    ServiceType,
    Tariff,
    User,
)

START_DATE = dt.date(2017, 10, 1)


def _dec(v):
    try:
        return decimal.Decimal(str(v))
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="_migration_src")
    args = ap.parse_args()
    with (Path(args.csv) / "accruals.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    db = database.SessionLocal()
    try:
        mig = db.query(User).filter(User.username == "migration").first()
        fund_svc = db.query(ServiceType).filter(ServiceType.services_type == "Фонд развития").first()
        if mig is None or fund_svc is None:
            print("Нет user migration / услуги Фонд развития.")
            return 1
        # самый ранний тариф фонда (для NOT NULL FK; итог берёт amount, не тариф)
        fund_tariff = db.query(Tariff).filter(
            Tariff.services_type_id == fund_svc.id).order_by(Tariff.valid_from.asc()).first()
        if fund_tariff is None:
            print("Нет тарифа Фонда.")
            return 1

        acc_list = {}
        for acc in db.query(Account).all():
            if acc.apartment is not None:
                acc_list[str(acc.apartment.apartment_number)] = acc

        # пропуск повтора при повторном прогоне (ищем существующий старт-документ)
        if db.query(AccrualDocument).filter(AccrualDocument.title == "Входящие остатки (старт)").first():
            print("Стартовый документ уже создан — пропуск.")
            db.rollback()
            return 0

        doc = AccrualDocument(accrual_date=START_DATE,
                              title="Входящие остатки (старт)",
                              created_by=mig.id)
        db.add(doc)
        db.flush()

        n = 0
        s = decimal.Decimal(0)
        for r in rows:
            if r["kind_in_source"] != "enter":
                continue
            kv_key = r["apartment"]
            acc = acc_list.get(str(kv_key)) or acc_list.get(f"{int(kv_key):02d}")
            amt = _dec(r["amount"])
            if acc is None or amt is None:
                continue
            db.add(AccrualsRegister(
                accrual_document_id=doc.id,
                accrual_date=START_DATE,
                account_id=acc.id,
                services_type_id=fund_svc.id,
                tariff_id=fund_tariff.id,
                amount=amt,
                consumption=1,
            ))
            n += 1
            s += amt

        db.commit()
        print(f"СИНТЕЗ вх.остатков: строк={n}, сумма(старта долга)={s}.")
    except Exception as exc:
        db.rollback()
        print("ОШИБКА:", exc)
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
