# backend/migrations/_import_accruals.py
"""ЭТАП начислений (синтез): первичный регистр начислений.

Вход: prepared accruals.csv (с колонками consumption/tariff_price) + уже
созданные справочники (этап ref+meters) и Tariff (после _import_tariffs).

Создаёт документы начислений:
  - обычные (reg+vary)  -> ОДИН AccrualDocument в месяц (одна шапка),
    строки AccrualsRegister по (услуга, л/с) с настоящим tariff_id и amount;
  - razov (дом-разовое) -> отдельный документ начислений «разовые за месяц»;
  - manual (персональные)-> отдельный документ-доначисление на л/с;
  - enter (входящие)    -> единственный документ «Входящие остатки»;
    (строки заносятся как обычные начисления, флаг do_not_recalc соблюдён на
    уровне взятой из файла суммы, без последующей пересборки по тарифам).

Запуск (в контейнере backend):
    python migrations/_import_accruals.py --csv /app/_migration_src
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import decimal
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import database  # noqa: E402
from models import (  # noqa: E402
    Account,
    AccrualDocument,
    AccrualsRegister,
    ServiceType,
    Tariff,
    TariffType,
    User,
)

MONTHS_RU = ["январь", "февраль", "март", "апрель", "май", "июнь",
             "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
D = decimal.Decimal


def _d(v: str) -> dt.date:
    y, m = map(int, str(v).split("-"))
    return dt.date(y, m, 1)


def _s(v: str) -> D:
    return D(str(v))


def account_of(db) -> dict:
    """Картирование «код квартиры(номера)» -> Account (в базе Account по каждому
    л/с, account_number = LS-NNNN, где NNNN — номер квартиры == код в листе)."""
    out = {}
    for acc in db.query(Account).all():
        ap = acc.apartment
        if ap is None:
            continue
        num = ap.apartment_number
        out[str(num)] = acc
        # также удержание под 2-значным кодом, на случай записи "01"
        out[f"{num:02d}"] = acc if f"{num:02d}" not in out else out[f"{num:02d}"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="_migration_src")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()
    p = Path(args.csv)
    with (p / "accruals.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    with (p / "services.csv").open(encoding="utf-8", newline="") as fh:
        code_name = {r["code"]: r["name"] for r in csv.DictReader(fh)}

    db = database.SessionLocal()
    try:
        mig = db.query(User).filter(User.username == "migration").first()
        if mig is None:
            print("Нет пользователя migration.")
            return 1
        accoun = account_of(db)
        svc_by_code = {}
        for code, name in code_name.items():
            st = db.query(ServiceType).filter(ServiceType.services_type == name).first()
            if st is not None:
                svc_by_code[code] = st

        # тип тарифа «Фиксированный» (для отсутствующих/разовых периодов)
        tt_fixed = db.query(TariffType).filter(TariffType.name == "Фиксированный").first()

        # tariff-интервалы услуги по коду (по уже построенной Tariff-таблице)
        code_of_svcid = {st.id: c for c, st in svc_by_code.items()}
        tarr_by_svc = defaultdict(list)
        for t in db.query(Tariff).all():
            code = code_of_svcid.get(t.services_type_id)
            if code:
                tarr_by_svc[code].append(t)
        for code in tarr_by_svc:
            tarr_by_svc[code].sort(key=lambda t: t.valid_from)

        tarr_auto_created = set()  # (services_id, valid) уже созданные авто-тарифы

        def tariff_at(code, period: dt.date):
            # Для обычных (reg/vary) строк — только РЕГУЛЯРНЫЕ тарифы.
            # Разовые (is_oneoff) могут быть добавлены с той же датой и не должны
            # перехватывать выбор «последнего действующего ≤ дате» (иначе разовая
            # акция «протекает» в обычное начисление — см. ошибку 121000@2018-04).
            chosen = None
            for t in tarr_by_svc.get(code, []):
                if t.valid_from <= period and not t.is_oneoff:
                    chosen = t
            return chosen

        docs_month = {}
        n_doc = 0
        n_row = 0
        n_auto_tariff = 0

        def make_doc(title, dt_doc, kind="monthly"):
            nonlocal n_doc
            doc = AccrualDocument(accrual_date=dt_doc, title=title,
                                  doc_kind=kind, created_by=mig.id)
            db.add(doc)
            db.flush()
            n_doc += 1
            return doc

        def add_row(doc, ap_key, code, amt, period, cons, kind):
            nonlocal n_row, n_auto_tariff
            acc = accoun.get(str(ap_key)) or accoun.get(f"{int(ap_key):02d}")
            svc = svc_by_code.get(code)
            if acc is None or svc is None:
                return
            tariff = None
            if kind == "razov":
                # Разовые акции: отдельный месячный тариф по цене акции. Переиспользуем
                # только уже созданный разовый (is_oneoff) тариф того же месяца/цены —
                # обычную регулярную ставку для разовой строки не занимаем.
                for t in tarr_by_svc.get(code, []):
                    if (t.is_oneoff and t.valid_from == period
                            and abs(t.price - amt) < decimal.Decimal("0.05")):
                        tariff = t
                        break
                if tariff is None:
                    if tt_fixed is None:
                        return
                    tariff = Tariff(services_type_id=svc.id, tariff_type_id=tt_fixed.id,
                                    price=amt, valid_from=period, is_oneoff=True)
                    db.add(tariff)
                    db.flush()
                    tarr_by_svc[code].append(tariff)
                    n_auto_tariff += 1
            else:
                tariff = tariff_at(code, period)
                if tariff is None:
                    return
            db.add(AccrualsRegister(
                accrual_document_id=doc.id,
                accrual_date=period,
                account_id=acc.id,
                services_type_id=svc.id,
                tariff_id=tariff.id,
                amount=amt,
                consumption=cons,
            ))
            n_row += 1

        for r in rows:
            code = r["service_src"]
            period = _d(r["period"])
            amt = _s(r["amount"])
            cons = _s(r["consumption"])
            kind = r["kind_in_source"]
            ap_key = r["apartment"]
            if kind in ("reg", "vary"):
                # одна шапка на месяц
                month_key = (period.year, period.month)
                if month_key not in docs_month:
                    docs_month[month_key] = make_doc(
                        f"Начисление за {MONTHS_RU[period.month - 1]} {period.year}",
                        period)
                add_row(docs_month[month_key], ap_key, code, amt, period, cons, kind)
            elif kind == "razov":
                # дом/разовый месяц отдельной шапкой (по месяцу акции)
                mk = ("raz", period.year, period.month)
                if mk not in docs_month:
                    docs_month[mk] = make_doc(
                        f"Разовые сборы за {MONTHS_RU[period.month - 1]} {period.year}",
                        period, kind="oneoff")
                add_row(docs_month[mk], ap_key, code, amt, period, cons, kind)
            elif kind == "manual":
                # персональное доначисление на квартиру — отдельный документ
                doc = make_doc(
                    f"Персональное доначисление за {MONTHS_RU[period.month - 1]} "
                    f"{period.year} (кв {ap_key})", period, kind="oneoff")
                add_row(doc, ap_key, code, amt, period, cons, kind)
            elif kind == "enter":
                # Входящие остатки НЕ вносим как начисление: это стартовое сальдо
                # л/с — его учтём отдельной логикой пересборки (по решению пользователя).
                continue

        db.commit()
        n_enter_skip = sum(1 for r in rows if r["kind_in_source"] == "enter")
        print(f"СИНТЕЗ начислений: документов={n_doc}; строк={n_row}; "
              f"автотарифов={n_auto_tariff}; enter-строк пропущено(старт.сальдо)= {n_enter_skip}.")
    except Exception as exc:
        db.rollback()
        print("ОШИБКА:", exc)
        import traceback; traceback.print_exc()
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
