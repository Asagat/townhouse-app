"""
Инициализация схемы БД «с нуля» из моделей (только для СВЕЖЕЙ, пустой БД).

`Base.metadata.create_all()` создаёт только отсутствующие таблицы и никогда не
меняет/не удаляет существующие — безопасен и на уже развёрнутой БД (там просто
ничего не создаст). Используется для быстрого старта нового окружения; дальнейшие
изменения схемы ведутся через Alembic (`alembic upgrade head`).

Запуск из каталога backend:
    python bootstrap_db.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import engine  # noqa: E402
from models import Base  # noqa: E402


def main() -> None:
    # Создаёт отсутствующие таблицы по декларативным моделям (идемпотентно).
    Base.metadata.create_all(bind=engine)
    print("Схема создана/дополнена из моделей (create_all).")


if __name__ == "__main__":
    main()
