# backend/migrations/_import_rebuild.py
"""Пересборка производного Регистра взаиморасчётов (accounts_register) «с нуля».

Вызывается ядро проекта rebuild_accounts_register() — детерминированно повторяет
начисления (income) из accruals_register и разносит оплаты из cash_register по
приоритету (списания). Результат — балансы л/с (долг/переплата).

На этом этапе касса (оплаты) ещё не внесена: баланс = «долг по начислениям+старт».
После этапа кассы прогон пересборки нужно повторить, чтобы оплаты легли в списания.

Запуск (в контейнере backend):
    python migrations/_import_rebuild.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import database  # noqa: E402
from writeoffs import rebuild_accounts_register  # noqa: E402


def main() -> int:
    db = database.SessionLocal()
    try:
        res = rebuild_accounts_register(db)
        db.commit()
        processed = res["processed"]
        print(f"Пересобрано счетов: {len(processed)}.")
    except Exception as exc:
        db.rollback()
        print("ОШИБКА:", exc)
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
