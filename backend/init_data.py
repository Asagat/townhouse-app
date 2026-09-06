"""
Инициализация СИСТЕМНЫХ справочников (идемпотентно).

Запускается ПОСЛЕ bootstrap_db.py (создание схемы) и ПЕРЕД первым запуском
приложения на новом окружении (локально или на VPS). Создаёт справочники,
которые раньше заводились вручную в БД:

  - типы тарифов: «По счетчику», «Фиксированный», «По площади» (зашиты логикой,
    неизменяемы) — см. app.calculate_accrual_for_account_service;
  - типовые виды услуг (с приоритетом списания);
  - дефолтные тарифы для услуг (если у услуги тарифа ещё нет).

Скрипт идемпотентен: ничего не перезаписывает, только создаёт отсутствующее.
Безопасен и на уже существующей БД (там просто ничего не создаст повторно).

Запуск из каталога backend:
    python init_data.py
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Гарантируем UTF-8 для stdout/stderr (кириллица в логах на любом окружении,
# включая серверы с локалью ASCII). PYTHONUTF8 обычно уже решает это при старте,
# но страхуемся и здесь — обёрнуто в try/except, чтобы сбой кодировки никогда
# не обрывал реальную работу скрипта.
try:
    for _stream in (sys.stdout, sys.stderr):
        if _stream and hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from database import SessionLocal  # noqa: E402
from models import AnalyticArticle, AnalyticKind, ServiceType, Tariff, TariffType  # noqa: E402


# Типы тарифов (системные, имена зашиты в логику расчёта — не менять).
_TARIFF_TYPES = ["По счетчику", "Фиксированный", "По площади", "На человека"]

# Услуги по умолчанию: (название, тип тарифа, приоритет списания). Ниже — вариант
# по умолчанию. Тип тарифа задаётся на ВИДЕ УСЛУГИ (09.2026) и наследуется тарифами.
# ВНИМАНИЕ (09.2026): «Электричество», «Холодная вода» и «Прочие расходы» здесь
# НЕ заводятся — канонический набор услуг задаётся импортом истории (код 1..7,
# см. migrations/migrate_prepare_sources.py SRC_SERVICE: Электроэнергия и т.д.),
# а эти имена создавали дубли/лишние строки при запуске поверх импортированной БД.
_SERVICES = [
    ("Охрана", "Фиксированный", 3),
    ("Обслуживание ТП", "По площади", 4),
    ("Фонд развития", "Фиксированный", 5),
]

# Дефолтные тарифы: (название_услуги, цена). Тип берётся с услуги (см. _SERVICES).
# Создаются, только если у услуги вообще нет ни одного тарифа.
_DEFAULT_TARIFFS = [
    ("Охрана", 2000.00),
    ("Фонд развития", 5000.00),
    ("Обслуживание ТП", 10.00),
]

# Эталонный справочник «Статьи доходов и расходов» (для документа «Приход/Расход»).
# Доходы / Расходы — по решению владельца (сент. 2026), эталон для миграции.
_ANALYTIC_ARTICLES = [
    # --- Доходы ---
    ("Поступления от жителей", AnalyticKind.income),
    ("Возвраты от контрагентов", AnalyticKind.income),
    ("Прочие доходы", AnalyticKind.income),
    # --- Расходы ---
    ("Электроэнергия", AnalyticKind.expense),
    ("Водоснабжение", AnalyticKind.expense),
    ("Вывоз мусора и утилизация", AnalyticKind.expense),
    ("Заработная плата персонала", AnalyticKind.expense),
    ("Обслуживание инженерных систем", AnalyticKind.expense),
    ("Благоустройство территории", AnalyticKind.expense),
    ("Безопасность и проверки", AnalyticKind.expense),
    ("Материалы и инвентарь", AnalyticKind.expense),
    ("Возвраты жителям", AnalyticKind.expense),
    ("Прочие расходы", AnalyticKind.expense),
    # Отдельный тип: входящее сальдо/сторно, не доход и не расход.
    ("Входящий остаток", AnalyticKind.opening),
]


def _ensure_tariff_types(db) -> dict[str, TariffType]:
    """Создаёт недостающие типы тарифов, возвращает {имя: объект}."""
    result: dict[str, TariffType] = {}
    for name in _TARIFF_TYPES:
        tt = db.query(TariffType).filter(TariffType.name == name).first()
        if not tt:
            tt = TariffType(name=name)
            db.add(tt)
            db.flush()
            print(f"  + тип тарифа: {name}")
        result[name] = tt
    return result


def _ensure_services(db, tariff_types: dict[str, TariffType]) -> dict[str, ServiceType]:
    """Создаёт недостающие услуги по умолчанию, возвращает {название: объект}.

    Тип тарифа задаётся на услуге (09.2026). Уже существующие услуги не трогаем
    (их тип проставила миграция 0012 из фактических тарифов).
    """
    result: dict[str, ServiceType] = {}
    for sname, ttype_name, prio in _SERVICES:
        svc = db.query(ServiceType).filter(ServiceType.services_type == sname).first()
        if not svc:
            tt = tariff_types[ttype_name]
            svc = ServiceType(services_type=sname, priority=prio, tariff_type_id=tt.id)
            db.add(svc)
            db.flush()
            print(f"  + услуга: {sname} (приоритет {prio}, тип тарифа «{ttype_name}»)")
        result[sname] = svc
    return result


def _ensure_tariffs(db, services: dict[str, ServiceType]) -> None:
    """Создаёт дефолтные тарифы (тип наследуется от услуги), если у услуги их нет."""
    for sname, price in _DEFAULT_TARIFFS:
        svc = services.get(sname)
        if svc is None:
            continue
        has_tariff = db.query(Tariff).filter(Tariff.services_type_id == svc.id).count() > 0
        if has_tariff:
            continue
        db.add(Tariff(
            services_type_id=svc.id,
            price=price,
            valid_from=date(2000, 1, 2),  # до всех реальных периодов — чтобы не мешать
        ))
        print(f"  + тариф: {sname} = {price}")


def _ensure_analytic_articles(db) -> None:
    """Создаёт недостающие статьи аналитики (идемпотентно, по (name, kind))."""
    for name, kind in _ANALYTIC_ARTICLES:
        existing = (
            db.query(AnalyticArticle)
            .filter(AnalyticArticle.name == name, AnalyticArticle.kind == kind)
            .first()
        )
        if existing:
            continue
        db.add(AnalyticArticle(name=name, kind=kind, is_active=True))
        db.flush()
        print(f"  + статья аналитики: {name} ({kind.value})")


def main() -> None:
    db = SessionLocal()
    try:
        print("Инициализация системных справочников:")
        tariff_types = _ensure_tariff_types(db)
        services = _ensure_services(db, tariff_types)
        _ensure_tariffs(db, services)
        _ensure_analytic_articles(db)
        db.commit()
        print("Готово.")
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"Ошибка: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
