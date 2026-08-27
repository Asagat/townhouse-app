"""schema-squash: полная схема через Alembic

Вводит в Alembic все таблицы, которых ещё нет в БД, НА ОСНОВЕ ДЕКЛАРАТИВНЫХ МОДЕЛЕЙ
(Base.metadata.create_all) — идемпотентно. Это делает Alembic ЕДИНЫМ каналом создания
схемы: на свежей БД `alembic upgrade head` создаёт полную схему, без отдельного
bootstrap_db.py. На уже развёрнутой БД ничего не создаётся повторно и не ломается.

Revision ID: 0002_schema_squash
Revises: 0001_users
Create Date: 2026-08-27
"""

import os
import sys

from alembic import op

# Разрешаем импорт моделей (схема в актуальном виде).
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from models import Base  # noqa: E402

revision = "0002_schema_squash"
down_revision = "0001_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Создаёт недостающие таблицы по моделям (идемпотентно, ничего не удаляет).
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    # Обратной операции нет: squash приводит к текущей схеме моделей.
    pass
