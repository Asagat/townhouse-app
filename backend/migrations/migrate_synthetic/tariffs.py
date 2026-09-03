# backend/migrations/_import_tariffs.py
"""Отдельный шаг: построение месячных Tariff для услуг (вариант a, синтез).

Читает подготовленный accruals.csv (поля service_src, period, amount,
kind_in_source, tariff_price, consumption) и восстанавливает «исторический»
Tariff каждой услуги с правильной ценой и датой valid_from.

Логика:
  - Для услуги переменной (электро, code 1): tariff_price берём из строки
    (истинная ставка периода); цена меняется в месяцах смены — собираем интервалы.
  - Для фикс-услуг (2..7): месячная база = amount строки (reg/при разовых
    не участвуют); собираем интервалы по смене цены.
  - Создаётся Tariff на каждый интервал [первый день месяца .. смены цены),
    тип тарифа: услуга 1 = «По счетчику», остальные = «Фиксированный».

Контроль не связывает amount (это сделает этап начислений), но выводит,
сколько Tariff-интервалов получилось по каждой услуге.

Запуск (в контейнере backend):
    python migrations/_import_tariffs.py --csv /app/_migration_src
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
from models import ServiceType, Tariff, TariffType  # noqa: E402


def ym_date(s: str) -> dt.date:
    y, m = map(int, s.split("-"))
    return dt.date(y, m, 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="_migration_src")
    ap.add_argument("--commit", action="store_true",
                    help="если не указан — прогон без commit (показ плана)")
    args = ap.parse_args()
    p = Path(args.csv)
    with (p / "accruals.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    db = database.SessionLocal()
    try:
        svcs = {s.services_type: s for s in db.query(ServiceType).all()}
        # код услуг -> имя (из services.csv фактически code->name, но в таблице по имени)
        # Удержим по известным именам кодового порядка через приложение не нужно: построим
        # маппинг кода по порядку имени из services.csv — но мы имеем только в базе (7 шт по имени).
        # Для соответствия создадим словарь code->name в привязке по таблице services.csv.
        with (p / "services.csv").open(encoding="utf-8", newline="") as fh:
            code_name = {r["code"]: r["name"] for r in csv.DictReader(fh)}

        # Какую ставку услуги брать в месяц (режим по amount для фикс, по тариф для вар)
        price_info = defaultdict(lambda: defaultdict(lambda: {"price": None, "kind": None, "votes": 0}))
        for r in rows:
            code = r["service_src"]
            kind = r["kind_in_source"]
            per = r["period"]
            # только «базовые» строчки определяют тариф услуги: reg (обычная),
            # и переменная (vary). Разовые/ручные/вх. сальдо не формируют тариф.
            if kind not in ("reg", "vary"):
                continue
            try:
                if kind == "vary":
                    price = decimal.Decimal(r["tariff_price"])
                else:
                    price = decimal.Decimal(r["amount"])
            except Exception:
                continue
            info = price_info[code][per]
            info["votes"] += 1
            if info["price"] is None or info["votes"] == 1:
                info["price"] = price
            info["kind"] = kind
        # цена месяца = усреднён по голосам (обычно согласованно), лиш подсчет просто фикс меcе
        # Сохраняем режим: мода среди цен записи в месяц
        month_price = {}
        for code, months in price_info.items():
            for per, info in months.items():
                month_price[(code, per)] = info["price"]

        # Маппинг TariffType
        t0 = db.query(TariffType).all()
        tt = {x.name: x for x in t0}

        def add_tariffs(code: str, name: str, type_name: str):
            # отсобираем пары (per->price) в хрон, свернув подряд равные
            pairs = sorted([(k, v) for (c, k), v in month_price.items() if c == code],
                           key=lambda x: x[0])
            seg = []  # (start_per, price)
            for per, pr in pairs:
                if not seg or abs(seg[-1][1] - pr) > decimal.Decimal("0.001"):
                    seg.append((per, pr))
            made = 0
            for per, pr in seg:
                base = db.query(Tariff).filter(
                    Tariff.services_type_id == svcs[name].id,
                    Tariff.valid_from == ym_date(per)).first()
                # точная ставка близкая - поищем по цене не буdem (чтобы не дублить повтор от старта)
                if base is None:
                    db.add(Tariff(services_type_id=svcs[name].id,
                                  tariff_type_id=tt[type_name].id,
                                  price=pr, valid_from=ym_date(per)))
                    made += 1
            return made

        plan = {}
        for code in code_name:
            name = code_name[code]
            type_name = "По счетчику" if code == "1" else "Фиксированный"
            plan[code] = add_tariffs(code, name, type_name)

        if not args.commit:
            print("План Tariff-интервалов по услугам (commit не сделан):")
            for c in sorted(plan):
                print(f"  {code_name[c]:<22} ({c})  новых интервалов: {plan[c]}")
            db.rollback()
        else:
            db.commit()
            print("Tariff построены (commit ok):", dict(plan), " — всего",
                  sum(plan.values()))
    except Exception as exc:
        db.rollback()
        print("ОШИБКА:", exc)
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
