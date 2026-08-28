"""drop_analytic_code

Убирает поле `code` из справочника «Аналитики» (analytic_articles).
Код аналитики не использовался в отчётах и только усложнял ввод пользователю;
статья идентифицируется по `name` + `kind`. Добавляем уникальность по (name, kind)
вместо прежнего уникального `code`.

Идемпотентно: на свежей БД `0002`/`0004` могут не создавать `code` — здесь лишь
чистим уже развёрнутые БД и гарантируем уникальность (name, kind).

Revision ID: 0005_drop_analytic_code
Revises: 0004_analytic_articles
Create Date: 2026-08-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0005_drop_analytic_code"
down_revision: Union[str, Sequence[str], None] = "0004_analytic_articles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UNIQUE_NAME = "uq_analytic_articles_name_kind"


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return column in [c["name"] for c in inspect(bind).get_columns(table)]


def upgrade() -> None:
    """Drop analytic_articles.code, ensure unique (name, kind)."""
    if _has_column("analytic_articles", "code"):
        op.drop_column("analytic_articles", "code")
    # PostgreSQL: добавляем unique-constraint (name, kind), если его ещё нет.
    op.execute(f"""
        ALTER TABLE analytic_articles
        ADD CONSTRAINT {_UNIQUE_NAME} UNIQUE (name, kind);
    """)


def downgrade() -> None:
    """Восстанавливаем code (без данных) и убираем уникальность (name, kind)."""
    op.execute(f"ALTER TABLE analytic_articles DROP CONSTRAINT IF EXISTS {_UNIQUE_NAME}")
    if not _has_column("analytic_articles", "code"):
        op.add_column("analytic_articles", sa.Column("code", sa.String(length=50), nullable=True))
