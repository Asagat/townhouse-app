"""resident_account_link

Привязка пользователя (роль resident) к лицевому счёту для Личного кабинета.

Добавляет колонку `users.account_id` (nullable FK -> accounts.id) и связь
User <-> Account. Для роли resident это определяет, какой счёт он может видеть
в ЛК. Идемпотентно: на свежей БД `0002_schema_squash` (create_all по актуальным
моделям) уже создаёт эту колонку/связь, поэтому `0003` лишь подстраховывает уже
развёрнутые БД.

Revision ID: 0003_resident_account_link
Revises: fce9ed483469
Create Date: 2026-08-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0003_resident_account_link"
down_revision: Union[str, Sequence[str], None] = "fce9ed483469"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    """Add users.account_id (idempotent against 0002_schema_squash create_all())."""
    if not _has_column("users", "account_id"):
        op.add_column("users", sa.Column("account_id", sa.Integer(), nullable=True))
    if not _fk_exists("users", "account_id"):
        op.create_foreign_key(
            None, "users", "accounts", ["account_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    """Downgrade schema (idempotent)."""
    if _fk_exists("users", "account_id"):
        op.drop_constraint(None, "users", type_="foreignkey")
    if _has_column("users", "account_id"):
        op.drop_column("users", "account_id")
