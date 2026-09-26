"""
Перегенерация квитанций за период по текущей методике расчёта.

Когда нужно: после изменения методики расчёта «К оплате/Долг/Переплата» в квитанциях
уже сохранённые документы остаются по старой методике. Чтобы привести их к актуальной,
их надо пересоздать штатным генератором.

Что делает:
  1. dry-run (по умолчанию) — считает, какими СТАНУТ квитанции за период, и печатает
     построчное сравнение с текущими; в БД ничего не пишется (транзакция откатывается,
     счётчик id квитанций восстанавливается);
  2. --apply — удаляет существующие квитанции за период и формирует заново штатным
     генератором (`routers.receipts.generate_receipt_document`), затем коммит.

Набор периодов: существующие квитанции за год + явно заданный `--month` (поэтому
`--month` умеет и пересоздать, и СФОРМИРОВАТЬ период с нуля, если квитанций за него ещё
нет). Повторный запуск идемпотентен: пересоздаёт те же документы.

Запуск из каталога backend:
    python migrations/regenerate_receipts_period.py --year 2026 --month 8
    python migrations/regenerate_receipts_period.py --year 2026 --month 8 --apply
    python migrations/regenerate_receipts_period.py --year 2026 --apply          # весь год
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from database import SessionLocal  # noqa: E402
from models import Account, ReceiptDocument  # noqa: E402
from routers.receipts import generate_receipt_document  # noqa: E402


def _fmt(value) -> str:
    return f"{float(value or 0):,.2f}".replace(",", " ")


def _receipt_seq_state(db):
    """Состояние последовательности id квитанций: (имя, last_value, is_called).

    Нужно, чтобы dry-run был без побочных эффектов: INSERT расходует id даже при
    последующем ROLLBACK (последовательности в PostgreSQL не транзакционные), поэтому
    после отката возвращаем счётчик в исходное состояние.
    """
    seq = db.execute(
        text("SELECT pg_get_serial_sequence('receipt_documents','id')")
    ).scalar()
    if not seq:
        return None
    row = db.execute(text(f"SELECT last_value, is_called FROM {seq}")).first()
    return (seq, int(row[0]), bool(row[1]))


def _restore_receipt_seq(db, state) -> None:
    """Возвращает счётчик id квитанций в состояние до dry-run (после rollback)."""
    if not state:
        return
    seq, last_value, is_called = state
    db.execute(text(f"SELECT setval('{seq}', :v, :c)"), {"v": last_value, "c": is_called})
    db.commit()


def _periods(db, year: int, month: int | None) -> list[tuple[int, int]]:
    """Периоды (year, month) к обработке.

    Существующие за год квитанции + явно заданный `--month` (включается даже если
    квитанций за него ещё нет — так можно сформировать период с нуля).
    """
    q = db.query(ReceiptDocument).filter(ReceiptDocument.period_year == year)
    if month is not None:
        q = q.filter(ReceiptDocument.period_month == month)
    rows = q.with_entities(ReceiptDocument.period_year, ReceiptDocument.period_month).all()
    periods = {(int(y), int(m)) for y, m in rows}
    if month is not None:
        periods.add((year, month))
    return sorted(periods)


def _payable_by_account(db, periods: list[tuple[int, int]]) -> dict[int, float]:
    """Сумма «К оплате» по каждой квитанции за периоды (для сравнения было/стало)."""
    result: dict[int, float] = {}
    for year, month in periods:
        rows = (
            db.query(ReceiptDocument)
            .filter(
                ReceiptDocument.period_year == year,
                ReceiptDocument.period_month == month,
            )
            .all()
        )
        for rec in rows:
            result[rec.account_id] = result.get(rec.account_id, 0.0) + float(rec.payable_amount or 0)
    return result


def _receipts_count(db, periods: list[tuple[int, int]]) -> int:
    total = 0
    for year, month in periods:
        total += (
            db.query(ReceiptDocument)
            .filter(
                ReceiptDocument.period_year == year,
                ReceiptDocument.period_month == month,
            )
            .count()
        )
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Перегенерация квитанций за период")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, default=None, choices=range(1, 13))
    parser.add_argument("--apply", action="store_true", help="записать изменения (иначе dry-run)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        periods = _periods(db, args.year, args.month)
        if not periods:
            print("За указанный период квитанций не найдено — нечего перегенерировать.")
            return

        before = _payable_by_account(db, periods)
        periods_label = ", ".join(f"{m:02d}.{y}" for y, m in periods)
        print(f"Периоды: {periods_label}")
        print(f"Квитанций сейчас: {_receipts_count(db, periods)}")

        # id квитанций выдаются из sequence и расходуются даже при ROLLBACK —
        # запоминаем счётчик, чтобы в dry-run его вернуть.
        seq_state = _receipt_seq_state(db)

        # Удаляем квитанции периода и формируем заново.
        del_q = db.query(ReceiptDocument).filter(ReceiptDocument.period_year == args.year)
        if args.month is not None:
            del_q = del_q.filter(ReceiptDocument.period_month == args.month)
        del_q.delete(synchronize_session=False)
        db.flush()

        accounts = db.query(Account).filter(Account.is_active == True).all()  # noqa: E712
        created = 0
        for year, month in periods:
            for acc in accounts:
                if generate_receipt_document(db, acc, year, month) is not None:
                    created += 1
        db.flush()

        after = _payable_by_account(db, periods)

        changed = 0
        print(f"{'Л/С':<9}{'Было':>14}{'Стало':>14}{'Разница':>14}")
        for acc in sorted(accounts, key=lambda a: a.account_number or ""):
            old_v = before.get(acc.id, 0.0)
            new_v = after.get(acc.id, 0.0)
            if abs(old_v - new_v) < 0.005 and (acc.id in before) == (acc.id in after):
                continue
            changed += 1
            print(
                f"{acc.account_number:<9}{_fmt(old_v):>14}{_fmt(new_v):>14}"
                f"{_fmt(new_v - old_v):>14}"
            )
        print(
            f"{'ИТОГО':<9}{_fmt(sum(before.values())):>14}{_fmt(sum(after.values())):>14}"
            f"{_fmt(sum(after.values()) - sum(before.values())):>14}"
        )
        print(f"\nСоздано квитанций: {created}; изменилось счетов: {changed}")

        if not args.apply:
            db.rollback()
            _restore_receipt_seq(db, seq_state)
            print("\ndry-run: изменения в БД НЕ записаны. Для записи запустите с ключом --apply")
            return

        db.commit()
        print("\nПрименено: квитанции за период пересозданы.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
