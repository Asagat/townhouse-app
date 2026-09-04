"""document_create_ts

Отдельная «Дата создания» для документов «Приход/Расход» и «Квитанции».

Добавляет `created_at` в `transactions` и `receipt_documents`, чтобы «Дата документа»
(`transaction_date` / `issued_at`) и «Дата создания» были разными метками времени
(дата документа может быть в прошлом; создание — момент внесения записи). Существующие
строки дохистории заполняются датой документа (лучшее доступное приближение).

Revision ID: 0007_document_create_ts
Revises: 0006_cash_service_link
Create Date: 2026-09-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0007_document_create_ts"
down_revision: Union[str, Sequence[str], None] = "0006_cash_service_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(op.get_bind()).get_columns(table)]


def upgrade() -> None:
    """Добавляет created_at в transactions и receipt_documents и заполняет дохисторию."""
    if not _has_column("transactions", "created_at"):
        op.add_column(
            "transactions",
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"),
                      nullable=True),
        )
        # Существующие операции: дата создания по умолчанию = дата документа.
        op.execute(
            "UPDATE transactions SET created_at = COALESCE(transaction_date, now()) "
            "WHERE created_at IS NULL"
        )
        # После заполнения делаем not null server_default сохраняется.
        op.alter_column("transactions", "created_at", nullable=False,
                        server_default=sa.text("now()"))

    if not _has_column("receipt_documents", "created_at"):
        op.add_column(
            "receipt_documents",
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"),
                      nullable=True),
        )
        op.execute(
            "UPDATE receipt_documents SET created_at = COALESCE(issued_at, now()) "
            "WHERE created_at IS NULL"
        )
        op.alter_column("receipt_documents", "created_at", nullable=False,
                        server_default=sa.text("now()"))


def downgrade() -> None:
    """Downgrade schema (идемпотентно)."""
    if _has_column("receipt_documents", "created_at"):
        op.drop_column("receipt_documents", "created_at")
    if _has_column("transactions", "created_at"):
        op.drop_column("transactions", "created_at")
