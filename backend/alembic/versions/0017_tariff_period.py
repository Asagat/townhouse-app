"""tariff period (двухфазная миграция, Фаза schema)

Первая (схемная) фаза редизайна тарифов к задаче 2.18 «единая модель
тарифа по срокам действия»:

* В `tariffs` добавляется `valid_to DATE NULL` — дата окончания действия ставки.
  NULL = открытая (текущая) ставка. Поле аддитивно и пока не используется
  расчётом: существующий код по-прежнему опирается на `is_oneoff`/`valid_from`.

Это ЧИСТО схемный шаг БЕЗ снятия `is_oneoff` и без конверсии данных/начислений.
Полная «единая лента ставок» и демонтаж признака разовости выносятся в
отдельные последующие фазы (конверсия истории + код), каждая со своей
контрольной сверкой (60 008 492 по начислениям).

Идемпотентно: колонки добавляются только при отсутствии.

Revision ID: 0017_tariff_period
Revises: 0016_receipt_comment
Create Date: 2026-09-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0017_tariff_period"
down_revision: Union[str, Sequence[str], None] = "0016_receipt_comment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    insp = sa_inspect(op.get_bind())
    columns = {c["name"] for c in insp.get_columns(table)}
    return column in columns


def upgrade() -> None:
    if not _has_column("tariffs", "valid_to"):
        op.add_column(
            "tariffs",
            sa.Column("valid_to", sa.Date(), nullable=True),
        )


def downgrade() -> None:
    if _has_column("tariffs", "valid_to"):
        op.drop_column("tariffs", "valid_to")
