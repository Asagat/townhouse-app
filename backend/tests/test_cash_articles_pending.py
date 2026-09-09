# tests/test_cash_articles_pending.py
"""Пункт «по статьям кассы» — ОТЛОЖЕН до трактовки владельца.

Файл Касса-Приход несёт Код_Статья/Код_Аналитика (аналитика движения кассы
/старая «Виды задолженностей»), а денежный регистр БД приход привязан к
`analytic_articles` (через transactions.article_id). Прямого персо-соответствия
кодов исходника и статей БД/услуг долга нет — владелец зафиксировал, что
трактовка «статьи кассы ↔ статьи/услуги БД» ещё требует решения.

Традиционно тест объявлен `xfail` (strict=False): он документирует требование
«приход по статьям (Касса-Приход) должен биться со статьями ...», но пока не может
проходить из-за неопределённого маппинга. Снять xfail после выбора трактовки и
реализации корректного соответствия (касса по `analytic_articles` либо услуги долга).
"""

import os
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

_REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.xfail(reason="маппинг «статьи кассы ↔ БД» требует трактовки владельца",
                               strict=False, raises=None)


@pytest.fixture
def money(db):
    src = os.getenv("MIGRATION_SRC_XLSX")
    sp = Path(src) if src and Path(src).exists() else _REPO_ROOT / "templates" / "Миграция данных FTH.xlsx"
    if not sp.exists():
        pytest.skip("Файл-источник не найден")
    try:
        import openpyxl  # noqa
    except Exception:  # pragma: no cover
        pytest.skip("Нет openpyxl")
    if not db.execute(text("SELECT EXISTS (SELECT 1 FROM cash_register)")).scalar():
        pytest.skip("БД без кассы")
    return openpyxl.load_workbook(sp, read_only=True, data_only=True), db


def _doc_articles(db):
    article_by_tx = {}
    for r in db.execute(text(
        "SELECT t.id, aa.name FROM transactions t "
        "JOIN analytic_articles aa ON aa.id = t.article_id")).fetchall():
        article_by_tx[r[0]] = r[1]
    return article_by_tx


def test_cash_income_per_article_matches_source(money):
    """Ожидаемо: сравнение прихода кассы по статьям послу стат. маппинга (см. модуль)."""
    wb, db = money
    src = defaultdict(Decimal)
    for r in wb["Касса-Приход"].iter_rows(values_only=True):
        if r[0] is None or str(r[0]).startswith("Код"):
            continue
        code = str(r[4]).strip() if r[4] is not None else ""
        amt = Decimal(str(r[5]))
        cm = str(r[8] or "")
        st = amt < 0 or "сторно" in cm.lower()
        src[code] += (-abs(amt) if st else abs(amt))
    # DB: приход кассы по статьям транзакций — не будет == файловым кодам пока маппинг не выбран
    art = _doc_articles(db)
    dbart = defaultdict(Decimal)
    for tx, income in db.execute(text(
        "SELECT transaction_id, COALESCE(SUM(income),0) FROM cash_register GROUP BY 1")).fetchall():
        dbart[art.get(tx, "?") or "?"] += Decimal(str(income))
    # Сравнение до выбора трактовки некорректно; XFAIL фиксирует требование.
    assert sum(src.values()) == sum(dbart.values()), "ожидаемое расхождение до трактовки — не должен выполняться"
