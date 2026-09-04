"""ensure_analytic_articles.py — приводит справочник «Статьи доходов и расходов»
к эталонному набору (источник истины: _ANALYTIC_ARTICLES в init_data.py).

Только ДОБАВЛЯЕТ отсутствующие статьи (name, kind) и никогда не удаляет/не меняет
существующие (статьи могут быть привязаны к документам «Приход/Расход»). Удаление
устаревших значений, например «Расходы по дому», выполняется отдельным шагом строго
после переноса документов на новые статьи (см. ремиграцию справочников).

Запуск: python seed_analytic_articles.py   (идемпотентно)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import init_data  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import AnalyticArticle, AnalyticKind  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        added = 0
        for name, kind in init_data._ANALYTIC_ARTICLES:
            exists = (
                db.query(AnalyticArticle)
                .filter(AnalyticArticle.name == name, AnalyticArticle.kind == kind)
                .first()
            )
            if exists:
                continue
            db.add(AnalyticArticle(name=name, kind=kind, is_active=True))
            added += 1
        db.commit()
        total = db.query(AnalyticArticle).count()
        print(f"Добавлено статей: {added}. Всего в справочнике (с устаревшими): {total}.")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"Ошибка: {exc}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
