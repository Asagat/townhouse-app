"""Восстановление пропущенных начислений «Вывоз мусора» по кв13 (2020-07..2026-08).

Диагноз: сверка 6 контрольных срезов начислений (месяц / месяц×услуга /
месяц×квартира / итог / итог×квартира / итог×услуга) между файлом-источником
(templates/Миграция данных FTH.xlsx) и БД показала единственное расхождение —
Δ=114 500 ₸ по «Вывозу мусора» кв13. В файле у кв13 есть начисления Вывоза с
2020-07 (500..1000..1500 ₸/мес — непрерывно до 2026-08), в БД их НЕТ ни в одном
месяце (74 мес). До 2020-07 в файле по кв13/Вывоз суммы были 0 — их не восстанавливаем.

Что делает (суммы НЕ выдуманы — берём действующую ставку тарифа, которая равна
сумме в файле для каждого месяца; проверено read-only):
  1. для каждого месяца в [2020-07..2026-08] находит «месячный» документ начислений
     (doc_kind='monthly', accrual_date в требуемом месяце) и действующую ставку тарифа
     «Вывоза мусора» на конец месяца;
  2. если у кв13 в этом месяце по Вывозу уже есть строка — пропускает (идемпотентно);
  3. вставляет AccrualsRegister-строку (accrual_document_id/дата счёт/тариф/услуга/amount=ставке);
  4. через create_accounts_register_entries_for_accruals пишет income-строки в
     accounts_register и пересчитывает балансы затронутых счетов.

Запуск из каталога backend:
    python migrations/recover_kv13_garbage_accruals.py            # dry-run
    python migrations/recover_kv13_garbage_accruals.py --apply    # применить
"""

import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal  # noqa: E402
from models import AccrualsRegister  # noqa: E402

KV = 13
SVC_NAME = "Вывоз мусора"
# непрерывный диапазон по файлу (74 мес)
FROM_YM = "2020-07"
TO_YM = "2026-08"


def _months():
    y, m = map(int, FROM_YM.split("-"))
    end_y, end_m = map(int, TO_YM.split("-"))
    out = []
    while (y, m) <= (end_y, end_m):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            m = 1
            y += 1
    return out


def _tariff_for(db, svc_id, month_end):
    r = db.execute(
        text(
            "SELECT price FROM tariffs WHERE services_type_id=:s "
            "AND valid_from <= :e AND (valid_to IS NULL OR valid_to >= "
            "to_date(substring(:m from 1 for 7)|| '-01','YYYY-MM-DD')) "
            "ORDER BY valid_from DESC, id DESC LIMIT 1"
        ),
        {"s": svc_id, "e": month_end, "m": month_end},
    ).first()
    return float(r[0]) if r else None


def _rows(db):
    """Спецификация восстановления (read-only): (month, acc_id, svc_id, doc_id, tariff_id, amount)."""
    acc = db.execute(
        text("SELECT a.id FROM accounts a JOIN apartments ap ON ap.id=a.apartment_id "
             "WHERE ap.apartment_number=:kv AND a.is_active"), {"kv": KV}).first()
    svc = db.execute(text("SELECT id FROM services_type WHERE services_type=:n"), {"n": SVC_NAME}).first()
    if not acc or not svc:
        return []
    rows = []
    for month in _months():
        y, mm = map(int, month.split("-"))
        import calendar as _cal
        last = _cal.monthrange(y, mm)[1]
        start = month + "-01"
        end = f"{y:04d}-{mm:02d}-{last:02d}"
        exists = db.execute(
            text("SELECT 1 FROM accruals_register WHERE account_id=:a AND services_type_id=:s "
                 "AND to_char(accrual_date,'YYYY-MM')=:m"), {"a": acc[0], "s": svc[0], "m": month}).first()
        if exists:
            continue  # уже есть
        # месячный документ, покрывающий период (accrual_date может быть не первое число)
        doc = db.execute(
            text("SELECT id FROM accrual_documents "
                 "WHERE accrual_date BETWEEN :st AND :en AND doc_kind='monthly' LIMIT 1"),
            {"st": start, "en": end}).first()
        tariff = db.execute(
            text("SELECT id, price FROM tariffs WHERE services_type_id=:s "
                 "AND valid_from <= :en AND (valid_to IS NULL OR valid_to >= :st) "
                 "ORDER BY valid_from DESC, id DESC LIMIT 1"),
            {"s": svc[0], "st": start, "en": end}).first()
        if not doc or not tariff:
            continue
        rows.append({
            "month": month, "acc_id": acc[0], "svc_id": svc[0],
            "doc_id": doc[0], "tariff_id": tariff[0], "amount": float(tariff[1]),
        })
    return rows


def apply(db):
    from services import create_accounts_register_entries_for_accruals

    rows = _rows(db)
    items = []
    for r in rows:
        items.append(AccrualsRegister(
            accrual_document_id=r["doc_id"],
            accrual_date=r["month"] + "-01",
            account_id=r["acc_id"],
            services_type_id=r["svc_id"],
            tariff_id=r["tariff_id"],
            past_reading_value=None,
            current_reading_value=None,
            consumption=0,
            amount=r["amount"],
        ))
    db.add_all(items)
    db.flush()
    # пишет income-строки в accounts_register и пересчитывает балансы затронутых счетов
    create_accounts_register_entries_for_accruals(db, items)
    db.flush()
    return len(items)


if __name__ == "__main__":
    db = SessionLocal()
    try:
        rows = _rows(db)
        total = round(sum(r["amount"] for r in rows), 2)
        print(f"месяцев для восстановления кв{KV}/{SVC_NAME}: {len(rows)} (сумма {total:,.2f})")
        if rows:
            print("пример:", rows[0]["month"], rows[0]["amount"], "doc_id", rows[0]["doc_id"])
        if "--apply" not in sys.argv:
            print("dry-run: для применения --apply")
        else:
            n = apply(db)
            db.commit()
            print("вставлено строк:", n)
    finally:
        db.close()
