"""user preferences

Серверное хранение настроек интерфейса пользователя (роадмап 2.13).

Одна строка на (user_id, resource): колонка `data` (JSON) хранит настройки
раздела — порядок/видимость/ширины колонок, сортировку, применённые фильтры,
число строк на странице. Настройки переживают перезагрузку и смену устройства.

Revision ID: 0015_user_preferences
Revises: 0014_tariff_status
Create Date: 2026-09-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0015_user_preferences"
down_revision: Union[str, Sequence[str], None] = "0014_tariff_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    # Идемпотентно: на «свежей» БД таблицу уже создал шаг 0002 (create_all по
    # актуальным моделям) — здесь гарантируем её наличие на ранее развёрнутых БД.
    if not _has_table("user_preferences"):
        op.create_table(
            "user_preferences",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column(
                "user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("resource", sa.String(100), nullable=False),
            sa.Column("data", sa.JSON, nullable=False),
            sa.UniqueConstraint(
                "user_id", "resource", name="uq_user_preferences_user_resource"
            ),
        )
        op.create_index(
            "ix_user_preferences_user_id", "user_preferences", ["user_id"]
        )


def downgrade() -> None:
    op.drop_table("user_preferences")
