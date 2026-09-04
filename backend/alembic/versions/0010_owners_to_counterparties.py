"""owners_to_counterparties

Вариант B: единая таблица «Контрагенты» без разделения.

Переименовывает таблицу `owners` в `counterparties` (модель Owner → Counterparty).
Владельцы квартир остаются тем же справочником; в UI по роли показывается ярлык
«Собственник» (для квартир/л/с) или «Контрагент» (для денежных операций), а сам
справочник меню — «Контрагенты». FK-ссылки на таблицу (квартиры.owner_id,
транзакции/регистр.contractor_id) в PostgreSQL обновляются автоматически при
ALTER TABLE ... RENAME TO.

Revision ID: 0010_owners_to_counterparties
Revises: 0009_document_comment
Create Date: 2026-09-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0010_owners_to_counterparties"
down_revision: Union[str, Sequence[str], None] = "0009_document_comment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("owners") and not _has_table("counterparties"):
        op.rename_table("owners", "counterparties")


def downgrade() -> None:
    if _has_table("counterparties") and not _has_table("owners"):
        op.rename_table("counterparties", "owners")
