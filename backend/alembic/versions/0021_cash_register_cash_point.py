"""cash_register.cash_point_id (ТД-6: остаток по кассе/счёту)

ТД-6: `cash_register.balance_after` перестаёт быть сальдо лицевого счёта и
становится нарастающим ДЕНЕЖНЫМ остатком по кассе/счёту. Чтобы вести итог
раздельно по кассам (нал/безнал и т.п.), в `cash_register` добавляется
`cash_point_id` — зеркало `transactions.cash_point_id` из шапки «Приход/Расход».

Изменения:
  - колонка `cash_register.cash_point_id` (FK на `cash_points`, NULL);
  - бэкфилл из `transactions` по `transaction_id` (в фактических данных пустых
    значений нет — все операции привязаны к кассе/счёту);
  - индекс `idx_cash_register_cashpoint_date (cash_point_id, operation_date, id)`
    под оконный пересчёт остатка по кэшпоинту.

Идемпотентно: на свежей БД `0002_schema_squash` (create_all по актуальным
моделям) уже создаёт колонку/индекс/FK; на развёрнутой БД этот шаг их добавляет.

Revision ID: 0021_cash_register_cash_point
Revises: 0020_account_opened_at
Create Date: 2026-09-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0021_cash_register_cash_point"
down_revision: Union[str, Sequence[str], None] = "0020_account_opened_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(op.get_bind()).get_columns(table)]


def _fk_exists(table: str, column: str) -> bool:
    for fk in inspect(op.get_bind()).get_foreign_keys(table):
        if column in fk["constrained_columns"]:
            return True
    return False


def upgrade() -> None:
    if not _has_column("cash_register", "cash_point_id"):
        op.add_column("cash_register", sa.Column("cash_point_id", sa.Integer(), nullable=True))
    if not _fk_exists("cash_register", "cash_point_id"):
        op.create_foreign_key(
            "fk_cash_register_cash_point_id",
            "cash_register",
            "cash_points",
            ["cash_point_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    # Бэкфилл зеркала из шапки «Приход/Расход».
    op.execute(
        """
        UPDATE cash_register cr
        SET cash_point_id = t.cash_point_id
        FROM transactions t
        WHERE t.id = cr.transaction_id
          AND cr.cash_point_id IS DISTINCT FROM t.cash_point_id
        """
    )

    # Индекс под оконный пересчёт остатка по кэшпоинту (ORDER BY operation_date, id).
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cash_register_cashpoint_date "
        "ON cash_register (cash_point_id, operation_date, id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cash_register_cashpoint_date")
    if _fk_exists("cash_register", "cash_point_id"):
        op.drop_constraint("fk_cash_register_cash_point_id", "cash_register", type_="foreignkey")
    if _has_column("cash_register", "cash_point_id"):
        op.drop_column("cash_register", "cash_point_id")
