"""comment_fields

Добавляет примечание/комментарий (`comment`) к документам начислений
(`accrual_documents`) и к тарифам (`tariffs`) — необязательное текстовое поле
для пояснений бухгалтера (напр. причину разового сбора или изменённой ставки).

Идемпотентно: на свежей БД колонки уже могут существовать (create_all по
актуальным моделям в 0002_schema_squash) — здесь лишь гарантируем их наличие.

Revision ID: 1e9f7c2a5b6d
Revises: 9a4d2c01e6f0
Create Date: 2026-09-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "1e9f7c2a5b6d"
down_revision: Union[str, Sequence[str], None] = "9a4d2c01e6f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return column in [c["name"] for c in inspect(bind).get_columns(table)]


def upgrade() -> None:
    for table in ("accrual_documents", "tariffs"):
        if not _has_column(table, "comment"):
            op.add_column(
                table,
                sa.Column("comment", sa.String(length=500), nullable=True),
            )


def downgrade() -> None:
    for table in ("accrual_documents", "tariffs"):
        if _has_column(table, "comment"):
            op.drop_column(table, "comment")
