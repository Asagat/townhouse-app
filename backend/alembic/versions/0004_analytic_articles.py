"""analytic_articles

Справочник «Аналитики»: статьи доходов/расходов для документов «Приход/Расход»,
плюс связь `transactions.article_id` и снятие обязательности `cash_register.account_id`
(операции без привязки к квартире/л/с попадают в общий денежный регистр).

Идемпотентно: на свежей БД `0002_schema_squash` (create_all по актуальным моделям)
уже создаёт эти объекты, `0004` лишь подстраховывает уже развёрнутые БД.

Revision ID: 0004_analytic_articles
Revises: 0003_resident_account_link
Create Date: 2026-08-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0004_analytic_articles"
down_revision: Union[str, Sequence[str], None] = "0003_resident_account_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return table in inspect(bind).get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return column in [c["name"] for c in inspect(bind).get_columns(table)]


def _fk_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    for fk in inspect(bind).get_foreign_keys(table):
        if column in fk["constrained_columns"]:
            return True
    return False


def upgrade() -> None:
    """Add analytic_articles + transactions.article_id + nullable cash_register.account_id."""
    if not _has_table("analytic_articles"):
        op.create_table(
            "analytic_articles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(length=50), nullable=False, unique=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("kind", sa.String(length=20), nullable=False),  # income | expense
            sa.Column("is_active", sa.Boolean(), nullable=True),
        )
    if not _has_column("transactions", "article_id"):
        op.add_column("transactions", sa.Column("article_id", sa.Integer(), nullable=True))
    if not _fk_exists("transactions", "article_id"):
        op.create_foreign_key(
            None, "transactions", "analytic_articles", ["article_id"], ["id"],
            ondelete="SET NULL",
        )
    # cash_register.account_id становится nullable.
    if _has_column("cash_register", "account_id"):
        op.alter_column("cash_register", "account_id", nullable=True)


def downgrade() -> None:
    """Downgrade schema (идемпотентно, не трогаем данные)."""
    if _fk_exists("transactions", "article_id"):
        op.drop_constraint(None, "transactions", type_="foreignkey")
    if _has_column("transactions", "article_id"):
        op.drop_column("transactions", "article_id")
    if _has_table("analytic_articles"):
        op.drop_table("analytic_articles")
