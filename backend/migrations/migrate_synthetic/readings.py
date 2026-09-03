# backend/migrations/_import_readings.py
"""ЭТАП 2 (синтез): перенос показаний в документы показаний.

Входные CSV (подгот.): readings.csv. Требует, чтобы уже были справочники и метры
(из migrate_import --stage ref,meters). Слишком мал самодостаточно.

Логика:
  - Метр каждого показания ищется по serial «M-<кв>-<idx>» (созданы в этапе ref).
  - Показание группируется в документ-шапку MeterReadingDocument по месяцу даты
    показания + услуге (в данных это всегда «Электроэнергия»- метод службой 1).
  - Строка MeterReading хранит точную дату и значение из CSV.

Запуск (в контейнере backend, где смонтирован ./backend):
    python migrations/_import_readings.py --csv /app/_migration_src
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
    Meter,
    MeterReading,
    MeterReadingDocument,
    ServiceType,
    User,
)

MONTHS_RU = ["январь", "февраль", "март", "апрель", "май", "июнь",
             "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


def _d(v):
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def _dec(v):
    try:
        return decimal.Decimal(str(v))
    except Exception:
        return None


def _readings_csv(path: Path):
    with (path / "readings.csv").open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="_migration_src")
    args = ap.parse_args()
    if not Path(args.csv).is_dir():
        print(f"Каталог CSV не найден: {args.csv}")
        return 2

    db = database.SessionLocal()
    try:
        el = db.query(ServiceType).filter(ServiceType.services_type == "Электроэнергия").first()
        mig = db.query(User).filter(User.username == "migration").first()
        if el is None or mig is None:
            print("Нет служебной услуги Электроэнергия/юзера migration. Сначала этап ref.")
            return 1

        # Маппинг serial -> Meter.id
        serial_to_meter = {m.serial_number: m for m in db.query(Meter).all()}

        mk = "M-"
        docs: dict[tuple[int, int], MeterReadingDocument] = {}
        n_new_doc = 0
        n_new_reading = 0
        missing = 0

        for row in _readings_csv(Path(args.csv)):
            ap_key = row["apartment_key"]
            midx = row["meter_idx"]
            serial = f"{mk}{int(ap_key):02d}-{midx}"
            meter = serial_to_meter.get(serial)
            if meter is None:
                missing += 1
                continue
            d = _d(row["reading_date"])
            val = _dec(row["reading"])
            if d is None or val is None:
                continue
            key = (d.year, d.month)
            doc = docs.get(key)
            if doc is None:
                doc = MeterReadingDocument(
                    reading_date=dt.date(d.year, d.month, 1),
                    services_type_id=el.id,
                    title=f"Показания за {MONTHS_RU[d.month - 1]} {d.year}",
                    created_by=mig.id,
                )
                db.add(doc)
                db.flush()
                docs[key] = doc
                n_new_doc += 1
            db.add(MeterReading(
                document_id=doc.id,
                apartment_id=meter.apartment_id,
                meter_id=meter.id,
                services_type_id=el.id,
                reading=val,
                reading_date=d,
            ))
            n_new_reading += 1

        db.commit()
        print(f"СИНТЕЗ показаний: документов={n_new_doc}, строк={n_new_reading}, "
              f"метров не найдено={missing}.")
    except Exception as exc:
        db.rollback()
        print("ОШИБКА", exc)
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
