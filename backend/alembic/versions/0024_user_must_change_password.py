"""users.must_change_password — принудительная смена пароля (Б9)

Добавляет флаг «сменить пароль при первом входе» и выставляет его жителям
(у них дефолтный пароль `fth123`). После установки нового пароля флаг снимается
через `POST /api/auth/change-password`.

Revision ID: 0024_user_must_change_password
Revises: 0023_cash_point_kind
Create Date: 2026-09-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0024_user_must_change_password"
down_revision: Union[str, Sequence[str], None] = "0023_cash_point_kind"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(op.get_bind()).get_columns(table)]


def upgrade() -> None:
    if not _has_column("users", "must_change_password"):
        op.add_column(
            "users",
            sa.Column(
                "must_change_password",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        op.alter_column("users", "must_change_password", server_default=None)
    # Жители (fth001…) получили дефолтный пароль — обязываем сменить при входе.
    op.execute("UPDATE users SET must_change_password = true WHERE role = 'resident'")


def downgrade() -> None:
    if _has_column("users", "must_change_password"):
        op.drop_column("users", "must_change_password")
