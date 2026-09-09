# tests/test_accruals_sums_method.py
"""AccrualsSumCheck — сверка сумм начислений «файл-источник ↔ БД» по методике.

Методика владельца (6 независимых срезов — для переноса/проверки при миграции в прод):
  1. месячные суммы начислений по месяцу;
  2. месячные суммы по виду услуги  (месяц × услуга);
  3. месячные суммы по квартире     (месяц × квартира);
  4. итоговая вилка начислений (по всем периодам);
  5. итоговая сумма по квартире;
  6. итоговая сумма по виду услуги.

Источник истины — accrual_date строк accruals_register (в файле «Период_Начисление» —
первое число месяца); «вид услуги» приводится к каноническим ключам (в т.ч. слияние
«Прочие расходы» → «Фонд развития», варианты «охрана-электроэнергия»). Нулевые строки
источника не участвуют (в БД они не создаются).

Если файла-источника / openpyxl / импортированной БД нет — тест пропускается, чтобы
набор оставался зелёным на пустой (CI) и нативной dev-БД.

Запуск с файлом:  MIGRATION_SRC_XLSX=/path/Миграция данных FTH.xlsx \
                  pytest tests/test_accruals_sums_method.py -q
"""

import importlib.util
import os
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


def _source_path() -> Path | None:
    env = os.getenv("MIGRATION_SRC_XLSX")
    if env:
        p = Path(env)
        return p if p.exists() else None
    p = _REPO_ROOT / "templates" / "Миграция данных FTH.xlsx"
    return p if p.exists() else None


def _load_module():
    path = _BACKEND_DIR / "migrations" / "accruals_sum_check.py"
    spec = importlib.util.spec_from_file_location("acc_sum_check", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def checker(db):
    if openpyxl is None:
        pytest.skip("Нет пакета openpyxl — сверка по методике недоступна")
    src = _source_path()
    if src is None:
        pytest.skip("Файл-источник не найден (задайте MIGRATION_SRC_XLSX)")
    has = db.execute(text("SELECT EXISTS (SELECT 1 FROM accruals_register)")).scalar()
    if not has:
        pytest.skip("БД без начислений — сверка не применима")
    mod = _load_module()
    c = mod.AccrualsSumCheck(db, src)
    c.load()
    return c, mod


def test_six_slices_match_source(checker):
    """Все шесть срезов методики дают файл == БД."""
    c, _ = checker
    d = c.diff_summary()
    labels = {
        "month": "Месячные суммы по месяцам",
        "month_service": "Месяц × вид услуги",
        "month_apt": "Месяц × квартира",
        "total": "Итог начислений (все периоды)",
        "total_apt": "Итог по квартире",
        "total_svc": "Итог по виду услуги",
    }
    bad = []
    total_src = c.source_slices()["total"]
    total_db = c.db_slices()["total"]
    for key, label in labels.items():
        lst = d[key]
        if not lst:
            continue
        head = "\n".join(f"    {k}: файл {a:.2f} vs БД {b:.2f} (Δ={b - a:.2f})" for k, a, b in lst[:10])
        bad.append(f"{label}: {len(lst)} расхождений\n{head}")
    assert not bad, (
        "Сверка начислений файл↔БД по методике:\n"
        f"  итог: файл {total_src:.2f} vs БД {total_db:.2f}\n" + "\n".join(bad)
    )
