"""accounts.opened_at (правило не-по-всем = перс; вариант ii)

Добавляет на лицевой счёт дату открытия/ввода `opened_at DATE NULL` — момент,
с которого счёт считается «в составе дома» на месяц. Используется при создании/
пересоздании месячных начислений (вперёд): л/с попадает в месячный документ только
если opened_at <= последний день месяца. Что не на все «уже открытые» л/с — перс.

Определение даты открытия по варианту (ii): открытие = дата ПЕРВОГО начисления л/с
(MIN(accrual_date) в accruals_register, без ограничения doc_kind).
По данным:
  15 л/с -> 2017-10 (Входящие остатки) ; кв8 -> 2017-11 ; кв4 -> 2017-12.

Revision ID: 0020_account_opened_at
Revises: 0019_drop_tariff_oneoff
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020_account_opened_at"
down_revision: Union[str, Sequence[str], None] = "0019_drop_tariff_oneoff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    from sqlalchemy import inspect

    return column in [c["name"] for c in inspect(op.get_bind()).get_columns(table)]


def upgrade() -> None:
    if not _has_column("accounts", "opened_at"):
        with op.batch_alter_table("accounts") as batch:
            batch.add_column(sa.Column("opened_at", sa.Date(), nullable=True))

    # Бэкафилл: дата первого начисления л/с (MIN accrual_date по accruals_register).
    op.execute(
        """
        UPDATE accounts a
        SET opened_at = (
            SELECT MIN(ar.accrual_date)
            FROM accruals_register ar
            WHERE ar.account_id = a.id
        )
        """
    )


def downgrade() -> None:
    if _has_column("accounts", "opened_at"):
        op.drop_column("accounts", "opened_at")
