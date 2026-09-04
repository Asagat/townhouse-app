"""meter_reading_document_comment

Добавляет «Примечание» в документ «Показания» (`meter_reading_documents.comment`),
чтобы его можно было показывать/заполнять в документе и наследовать в строках
«Регистра показаний» (`meter_readings`).

Revision ID: 0009_document_comment
Revises: 0008_cash_contractor
Create Date: 2026-09-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0009_document_comment"
down_revision: Union[str, Sequence[str], None] = "0008_cash_contractor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(op.get_bind()).get_columns(table)]


def upgrade() -> None:
    if not _has_column("meter_reading_documents", "comment"):
        op.add_column("meter_reading_documents", sa.Column("comment", sa.String(length=500), nullable=True))


def downgrade() -> None:
    if _has_column("meter_reading_documents", "comment"):
        op.drop_column("meter_reading_documents", "comment")
