"""users (аутентификация)

Убирает legacy-таблицу users ранней схемы и создаёт актуальную для аутентификации.

Legacy-таблица users существовала (пустая, 0 строк) и не соответствовала новой
модели User (перенесённые поля full_name, password_hash в формате PBKDF2, роль
строкой). Так как она была пустой, удаление не теряет данных. Прочие legacy-таблицы
(invoices, counterparties, debts, ...) намеренно НЕ трогаем.

Revision ID: 0001_users
Revises: 0000_baseline
Create Date: 2026-08-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_users"
down_revision: Union[str, Sequence[str], None] = "0000_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Сначала удаляем legacy users (если осталась от ранней схемы), затем создаём новую.
    op.execute("DROP TABLE IF EXISTS users CASCADE")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.UniqueConstraint("username", name="users_username_key"),
    )


def downgrade() -> None:
    op.drop_table("users")
