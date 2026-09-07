"""receipt document comment

Добавляет квитанции (`receipt_documents`) поле `comment` — свободное
текстовое «Примечание», заполняется оператором вручную (Б6). Поле чисто
информационное и на расчётные суммы квитанции не влияет.

Revision ID: 0016_receipt_comment
Revises: 0015_user_preferences
Create Date: 2026-09-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0016_receipt_comment"
down_revision: Union[str, Sequence[str], None] = "0015_user_preferences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    insp = sa_inspect(op.get_bind())
    columns = {c["name"] for c in insp.get_columns(table)}
    return column in columns


def upgrade() -> None:
    # Идемпотентно: поле nullable, не требуется server_default.
    if _has_column("receipt_documents", "comment"):
        return
    op.add_column(
        "receipt_documents",
        sa.Column("comment", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    if not _has_column("receipt_documents", "comment"):
        return
    op.drop_column("receipt_documents", "comment")
