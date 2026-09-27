"""
Задача 3.4 — аудит названий документов и лицевых счетов (dry-run + `--apply`).

Что проверяет:
  1. **Названия документов «Приход/Расход»** — соответствие формуле
     `build_transaction_title` («Тип операции №<id> от <дд.мм.гггг>»). С `--apply`
     названия приводятся к формуле (данные документов не меняются — только `title`).
  2. **Лицевые счета / квартиры (только чтение, отчёт)**:
     - счета без квартиры; активные счета без начислений;
     - квартиры без собственника; счета без номера; дубли номеров (если есть);
     - пользователи-жители без привязанного лицевого счёта.

Ничего, кроме названий документов (и только с `--apply`), скрипт не меняет.

Запуск из каталога backend:
    python migrations/audit_documents_and_accounts.py            # dry-run (отчёт)
    python migrations/audit_documents_and_accounts.py --apply    # привести названия к формуле
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import Account, Apartment, Transaction, User, UserRole  # noqa: E402
from services import build_transaction_title  # noqa: E402

_LIMIT = 20  # сколько строк печатать в списках


def _print_list(title: str, rows: list) -> None:
    print(f"  {title}: {len(rows)}")
    for r in rows[:_LIMIT]:
        print(f"      {r}")
    if len(rows) > _LIMIT:
        print(f"      … и ещё {len(rows) - _LIMIT}")


def audit_titles(db) -> list[tuple[int, str, str]]:
    """Возвращает список расхождений названий: (transaction_id, текущее, ожидаемое)."""
    mismatches: list[tuple[int, str, str]] = []
    for t in db.query(Transaction).all():
        expected = build_transaction_title(t)
        if (t.title or "") != expected:
            mismatches.append((t.id, t.title or "", expected))
    return mismatches


def apply_titles(db, mismatches: list[tuple[int, str, str]]) -> int:
    for tx_id, _old, new in mismatches:
        db.execute(
            text("UPDATE transactions SET title = :t WHERE id = :i"),
            {"t": new, "i": tx_id},
        )
    db.commit()
    return len(mismatches)


def audit_accounts(db) -> dict[str, list]:
    rows: dict[str, list] = {}

    rows["Счета без квартиры"] = [
        f"№ {a.id} ({a.account_number})"
        for a in db.query(Account).filter(Account.apartment_id.is_(None)).all()
    ]

    rows["Активные счета без начислений"] = [
        f"№ {a.id} ({a.account_number}, {a.account_name})"
        for a in db.execute(
            text(
                "SELECT a.id, a.account_number, a.account_name FROM accounts a "
                "LEFT JOIN accruals_register ar ON ar.account_id = a.id "
                "WHERE a.is_active IS TRUE AND ar.id IS NULL ORDER BY a.id"
            )
        ).fetchall()
    ]

    rows["Квартиры без собственника"] = [
        f"№ {ap.id} (кв. {ap.apartment_number})"
        for ap in db.query(Apartment).filter(Apartment.owner_id.is_(None)).all()
    ]

    rows["Дубли номеров лицевых счетов"] = [
        f"{num}: {cnt}"
        for num, cnt in db.execute(
            text(
                "SELECT account_number, count(*) FROM accounts "
                "GROUP BY account_number HAVING count(*) > 1"
            )
        ).fetchall()
    ]

    rows["Жители без лицевого счёта"] = [
        f"{u.username} (id {u.id})"
        for u in db.query(User)
        .filter(User.role == UserRole.resident, User.account_id.is_(None))
        .all()
    ]

    return rows


def main() -> None:
    apply_mode = "--apply" in sys.argv
    db = SessionLocal()
    try:
        print("=" * 70)
        print("Аудит названий документов «Приход/Расход»")
        print("=" * 70)
        mismatches = audit_titles(db)
        _print_list("Расхождений с формулой", mismatches)
        if apply_mode and mismatches:
            n = apply_titles(db, mismatches)
            print(f"\nПрименено: исправлено названий — {n}.")
        elif mismatches:
            print("\ndry-run: для приведения названий к формуле выполните с ключом --apply")

        print("\n" + "=" * 70)
        print("Аудит лицевых счетов / квартир (только чтение)")
        print("=" * 70)
        for title, items in audit_accounts(db).items():
            _print_list(title, items)
    finally:
        db.close()


if __name__ == "__main__":
    main()
