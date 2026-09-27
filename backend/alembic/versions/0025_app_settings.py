"""app_settings — глобальные настройки приложения (Б3)

Создаёт таблицу `app_settings` (key/value). Значения по умолчанию заданы в коде
(`app_settings.DEFAULTS`), поэтому сид не нужен.

Revision ID: 0025_app_settings
Revises: 0024_user_must_change_password
Create Date: 2026-09-27
"""

import os
import sys
from typing import Sequence, Union

from alembic import op

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from models import Base  # noqa: E402

revision: str = "0025_app_settings"
down_revision: Union[str, Sequence[str], None] = "0024_user_must_change_password"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Идемпотентно: создаёт недостающие таблицы по моделям (здесь — app_settings).
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app_settings")
