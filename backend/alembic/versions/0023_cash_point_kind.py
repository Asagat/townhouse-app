"""cash_points.kind — тип «Касса/Счёт» (задача 2.15)

Добавляет справочнику «Кассы/Счета» поле «Тип»: «Касса» (наличные) или «Счёт»
(банковский). В БД хранится имя члена `CashPointKind` (cash/bank, native_enum=False).
Существующие кэшпоинты (сейчас один — «Касса») получают тип `cash`.

Revision ID: 0023_cash_point_kind
Revises: 0022_role_permissions
Create Date: 2026-09-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0023_cash_point_kind"
down_revision: Union[str, Sequence[str], None] = "0022_role_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(op.get_bind()).get_columns(table)]


def upgrade() -> None:
    if not _has_column("cash_points", "kind"):
        op.add_column(
            "cash_points",
            sa.Column("kind", sa.String(20), nullable=False, server_default="cash"),
        )
        # Дальше дефолт задаёт модель (ORM); убираем серверный, как в 0014/0019.
        op.alter_column("cash_points", "kind", server_default=None)


def downgrade() -> None:
    if _has_column("cash_points", "kind"):
        op.drop_column("cash_points", "kind")
