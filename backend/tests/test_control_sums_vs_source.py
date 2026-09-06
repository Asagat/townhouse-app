# tests/test_control_sums_vs_source.py
"""Контрольные суммы: регистры БД против исходного файла миграции.

Сверяет «файл-источник» (templates/Миграция данных FTH.xlsx) с фактическим
состоянием регистров dev/pre-prod БД:

  - начисления (accruals_register): суммы по каждой квартире, итог и число строк
    (квартира = apartments.apartment_number, в источнике Код_Квартира == Номер == 1..17);
  - касса (cash_register):
      * расход (expense) итог == сумме листа «Касса-Расход»;
      * приход по квартире == «Касса-Приход» по квартире ЗА ВЫЧЕТОМ сторно
        (возвратов) — в БД жительские платежи учитываются нетто;
      * итоговый приход (income) == приход источника минус ВСЕ сторно (включая
        операции без квартиры).

Проверка работает, только если доступен файл-источник (в dev/CI-контейнере backend
каталог templates/ не примонтирован — задайте переменную MIGRATION_SRC_XLSX или
положите файл по пути ../templates/Миграция данных FTH.xlsx). Если файла или
openpyxl нет — тест пропускается (pytest.skip), чтобы набор оставался зелёным.

Запуск с файлом:  MIGRATION_SRC_XLSX=/path/Миграция данных FTH.xlsx pytest tests/test_control_sums_vs_source.py -q
"""

import importlib.util
import os
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

try:
    import openpyxl  # noqa: F401
except Exception:  # pragma: no cover
    openpyxl = None  # type: ignore

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _require_imported_data(db):
    """Сверка с файлом-источником имеет смысл только на БД с импортированной
    историей (dev/pre-prod/stage). На пустой БД (свежая схема после alembic —
    например disposable-БД в CI) сверять нечего: набор пропускается целиком,
    чтобы CI оставался зелёным.
    """
    has_apartments = db.execute(text("SELECT EXISTS (SELECT 1 FROM apartments)")).scalar()
    has_accruals = db.execute(text("SELECT EXISTS (SELECT 1 FROM accruals_register)")).scalar()
    if not has_apartments and not has_accruals:
        pytest.skip("БД без импортированных данных — сверка с файлом-источником не применима")


def _source_path() -> Path | None:
    env = os.getenv("MIGRATION_SRC_XLSX")
    if env:
        p = Path(env)
        return p if p.exists() else None
    p = _REPO_ROOT / "templates" / "Миграция данных FTH.xlsx"
    return p if p.exists() else None


def _load_mps():
    """Загружает backend/migrations/migrate_prepare_sources.py как модуль."""
    path = _BACKEND_DIR / "migrations" / "migrate_prepare_sources.py"
    spec = importlib.util.spec_from_file_location("mps_control", path)
    mps = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mps)
    return mps


@pytest.fixture(scope="module")
def source():
    if openpyxl is None:
        pytest.skip("Нет пакета openpyxl — сверка с файлом-источником недоступна")
    src = _source_path()
    if src is None:
        pytest.skip(
            "Файл-источник не найден (задайте MIGRATION_SRC_XLSX или положите "
            "templates/Миграция данных FTH.xlsx рядом с backend/)"
        )
    mps = _load_mps()
    acc_rows, _ = mps.build_accruals_plan(src)
    cash_rows, _ = mps.build_cash_plan(src)
    return {"accruals": acc_rows, "cash": cash_rows}


def _apt_accruals(db):
    """sum(amount) начислений по квартире (по accounts → apartments)."""
    rows = db.execute(text(
        "SELECT ap.apartment_number, COALESCE(SUM(a.amount), 0) "
        "FROM accruals_register a "
        "JOIN accounts acc ON acc.id = a.account_id "
        "JOIN apartments ap ON ap.id = acc.apartment_id "
        "GROUP BY ap.apartment_number"
    )).fetchall()
    return {int(r[0]): Decimal(str(r[1])) for r in rows}


def _cash_by_apartment(db, kind: str):
    col = "income" if kind == "income" else "expense"
    rows = db.execute(text(
        f"SELECT ap.apartment_number, COALESCE(SUM(c.{col}), 0) "
        "FROM cash_register c "
        "JOIN accounts acc ON acc.id = c.account_id "
        "JOIN apartments ap ON ap.id = acc.apartment_id "
        "GROUP BY ap.apartment_number"
    )).fetchall()
    return {int(r[0]): Decimal(str(r[1])) for r in rows}


def _assert_close_dicts(left: dict[int, Decimal], right: dict[int, Decimal], label: str):
    keys = sorted(set(left) | set(right))
    diffs = [
        (k, left.get(k, Decimal(0)), right.get(k, Decimal(0)))
        for k in keys
        if abs(left.get(k, Decimal(0)) - right.get(k, Decimal(0))) >= Decimal("0.01")
    ]
    assert not diffs, (
        f"{label}: расхождения (квартира, ожидаемо, в БД):\n"
        + "\n".join(f"  кв.{k}: {a:.2f} vs {b:.2f} (Δ={b - a:.2f})" for k, a, b in diffs)
    )


def test_accruals_match_per_apartment_and_total(db, source):
    """Начисления: суммы по каждой квартире, итог и число строк совпадают с файлом."""
    src_rows = source["accruals"]
    src_by_apt: dict[int, Decimal] = defaultdict(Decimal)
    for r in src_rows:
        if r[0] is not None:
            src_by_apt[int(r[0])] += r[4]

    db_by_apt = _apt_accruals(db)
    _assert_close_dicts(src_by_apt, db_by_apt, "Начисления по квартирам")

    total_src = sum(src_by_apt.values())
    total_db = sum(db_by_apt.values())
    assert abs(total_src - total_db) < Decimal("0.01"), (
        f"Итог начислений: файл {total_src:.2f} vs БД {total_db:.2f}"
    )

    db_count = int(db.execute(text("SELECT count(*) FROM accruals_register")).scalar())
    assert len(src_rows) == db_count, (
        f"Число строк начислений: файл {len(src_rows)} vs БД {db_count}"
    )


def test_cash_expense_total_matches_source(db, source):
    """Касса: итоговый расход в БД == сумме листа «Касса-Расход»."""
    src_out = sum(r[2] for r in source["cash"] if r[0] == "out")
    db_expense = Decimal(str(db.execute(
        text("SELECT COALESCE(SUM(expense), 0) FROM cash_register")
    ).scalar()))
    assert abs(src_out - db_expense) < Decimal("0.01"), (
        f"Расход кассы: файл {src_out:.2f} vs БД {db_expense:.2f}"
    )


def test_cash_resident_income_per_apartment_is_net_of_storno(db, source):
    """Касса: приход по квартире в БД == приход файла по квартире минус сторно."""
    src_in_net: dict[int, Decimal] = defaultdict(Decimal)
    for r in source["cash"]:
        if r[0] != "in" or r[1] is None:
            continue
        amt = r[2]
        src_in_net[int(r[1])] += -amt if r[6] else amt  # сторно вычитается

    db_income = _cash_by_apartment(db, "income")
    _assert_close_dicts(src_in_net, db_income, "Касса: приход по квартирам (нетто)")


def test_cash_income_total_is_source_in_minus_all_storno_plus_opening(db, source):
    """Касса: итоговый приход БД == приход источника (нетто) + входящее сальдо кассы."""
    src_total = Decimal(0)
    for r in source["cash"]:
        if r[0] == "in":
            amt = r[2]
            src_total += -amt if r[6] else amt  # сторно вычитается
        elif r[0] == "start_cash":
            src_total += r[2]  # «Начальный остаток кассы» в БД тоже приход
    db_income = Decimal(str(db.execute(
        text("SELECT COALESCE(SUM(income), 0) FROM cash_register")
    ).scalar()))
    assert abs(src_total - db_income) < Decimal("0.01"), (
        f"Приход кассы итог: файл {src_total:.2f} vs БД {db_income:.2f}"
    )
