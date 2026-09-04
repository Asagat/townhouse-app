# backend/migrations/reimport/build_receipts.py
"""Заполняет квитанции для всех счетов и периодов, где есть начисления
(эквивалент mass-generate за каждый месяц). Только для townhouse_stage.

Использует прямые модели, без тяжёлых зависимостей роутера квитанций.
"""

import os
import sys
from calendar import monthrange
from datetime import date

ROOT = Path = __import__("pathlib").Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import database  # noqa: E402
from models import (  # noqa: E402
    Account,
    AccrualsRegister,
    ReceiptDocument,
    ReceiptItem,
    ServiceType,
)
from sqlalchemy import func, text  # noqa: E402


def _account_debt_overpayment(db, account_id, since):
    rows = db.execute(text("""
        WITH bal AS (
            SELECT income, expense
            FROM accounts_register
            WHERE account_id=:a
        )
        SELECT COALESCE(SUM(income-expense),0) FROM accounts_register
        WHERE account_id=:a AND operation_date < :since
    """), {"a": account_id, "since": since}).scalar() or 0
    bal = float(rows)
    return (bal if bal > 0 else 0.0, abs(bal) if bal < 0 else 0.0)


def _fund_service_id(db):
    row = db.execute(text(
        "SELECT id FROM services_type WHERE services_type LIKE 'Фонд развития%' LIMIT 1"
    )).scalar()
    return row


def main() -> int:
    dburl = database.SQLALCHEMY_DATABASE_URL
    if "townhouse_stage" not in dburl:
        print("Только для townhouse_stage."); return 3
    db = database.SessionLocal()
    try:
        accounts = db.query(Account).all()
        periods = db.execute(text(
            "SELECT DISTINCT EXTRACT(YEAR FROM accrual_date)::int yr, "
            " EXTRACT(MONTH FROM accrual_date)::int mo FROM accruals_register "
            "ORDER BY 1,2"
        )).fetchall()
        made = skipped = 0
        for acc in accounts:
            for (yr, mo) in periods:
                start = date(yr, mo, 1)
                end = date(yr, mo, monthrange(yr, mo)[1])
                accs = db.query(AccrualsRegister).filter(
                    AccrualsRegister.account_id == acc.id,
                    AccrualsRegister.accrual_date >= start,
                    AccrualsRegister.accrual_date <= end,
                ).all()
                if not accs:
                    skipped += 1
                    continue
                # есть ли уже кв-ия за период
                exists = db.query(ReceiptDocument).filter_by(
                    account_id=acc.id, period_year=yr, period_month=mo).first()
                if exists:
                    skipped += 1
                    continue
                apartment = acc.apartment
                owner_name = (apartment.owner.full_name if apartment and apartment.owner else "")
                rec = ReceiptDocument(
                    account_id=acc.id, period_year=yr, period_month=mo,
                    apartment_number=apartment.apartment_number if apartment else None,
                    address=apartment.address if apartment else None,
                    owner_name=owner_name, account_number=acc.account_number,
                )
                db.add(rec); db.flush()
                total = 0.0
                items = []
                fund_sid = _fund_service_id(db)
                for a in accs:
                    amount = float(a.amount); total += amount
                    st = db.get(ServiceType, a.services_type_id)
                    it = ReceiptItem(
                        receipt_id=rec.id,
                        services_type_id=a.services_type_id,
                        service_name=st.services_type if st else "",
                        reading_prev=a.past_reading_value,
                        reading_curr=a.current_reading_value,
                        quantity=a.consumption,
                        tariff=float(a.tariff.price) if a.tariff else 0,
                        amount=amount,
                    )
                    db.add(it); items.append(it)
                debt, ovp = _account_debt_overpayment(db, acc.id, since=start)
                rec.total_amount = total
                rec.debt = debt
                rec.overpayment = ovp
                rec.payable_amount = total + debt - ovp
                if fund_sid is not None and not any(i.services_type_id == fund_sid for i in items):
                    row = ReceiptItem(receipt_id=rec.id, services_type_id=fund_sid,
                                      service_name="Фонд развития", quantity=1,
                                      amount=0.0, debt=debt, overpayment=ovp,
                                      payable=total + debt - ovp)
                    db.add(row)
                made += 1
        db.commit()
        cnt = db.execute(text("SELECT count(*) FROM receipt_documents")).scalar()
        print("квитанций создано:", made, "пропусков:", skipped, "итого:", cnt)
    except Exception as exc:  # noqa: BLE001
        db.rollback(); print("Ошибка:", exc); return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
