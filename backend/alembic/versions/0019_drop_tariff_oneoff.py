"""drop tariff is_oneoff (2.18, завершение перевода на единую модель по срокам)

Финальная фаза редизайна тарифов задачи 2.18: снимается колонка `is_oneoff`.

К этому моменту (после 0017/0018) расчёт и месячный ввод тарифов уже опираются
только на единую запись «ставка + срок» (valid_from..valid_to): открытая ставка
(valid_to = NULL) и закрытые тарифы-периоды. Признак разовости в коде/UI больше
не используется, поэтому колонка удаляется.

Выполнять только в цепочке песочницы 0016 -> 0017 -> 0018 -> 0019 (см. 2.18).
Прод не менять без единого релиза CODE+миграции.

Revision ID: 0019_drop_tariff_oneoff
Revises: 0018_tariff_period_conversion
Create Date: 2026-09-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0019_drop_tariff_oneoff"
down_revision: Union[str, Sequence[str], None] = "0018_tariff_period_conversion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(op.get_bind()).get_columns(table)]


def upgrade() -> None:
    if _has_column("tariffs", "is_oneoff"):
        with op.batch_alter_table("tariffs") as batch:
            batch.drop_column("is_oneoff")


def downgrade() -> None:
    # Добавляем признак обратно (все строки как регулярные, default false).
    # Восстановление прежних разрядов теряется — оно невыводимо из новых данных.
    if not _has_column("tariffs", "is_oneoff"):
        op.add_column(
            "tariffs",
            sa.Column(
                "is_oneoff",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        op.alter_column("tariffs", "is_oneoff", server_default=None)
