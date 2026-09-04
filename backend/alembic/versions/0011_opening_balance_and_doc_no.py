"""opening_balance_and_doc_no

Милеза A (ссылки/справочник):

1. Добавляет отдельный тип статьи «Входящий остаток» (kind=opening) — для входящего
   остатка/«начальных» и сторно-записей (не Доход и не Расход).
2. Добавляет transactions.doc_no (nullable) — сквозной номер документа по хронологии
   (не по внутреннему id). Существующие записи заполняются порядковым номером по
   (transaction_date, id).

Revision ID: 0011_opening_balance_and_doc_no
Revises: 0010_owners_to_counterparties
Create Date: 2026-09-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0011_opening_balance_and_doc_no"
down_revision: Union[str, Sequence[str], None] = "0010_owners_to_counterparties"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(op.get_bind()).get_columns(table)]


def upgrade() -> None:
    # 1) входящий остаток — справочник статей
    bind = op.get_bind()
    has = bind.execute(sa.text(
        "SELECT 1 FROM analytic_articles WHERE name='Входящий остаток' AND kind='opening' LIMIT 1"
    )).first()
    if has is None:
        bind.execute(sa.text(
            "INSERT INTO analytic_articles (name, kind, is_active) "
            "VALUES ('Входящий остаток', 'opening', TRUE)"
        ))

    # 2) doc_no у транзакций
    if not _has_column("transactions", "doc_no"):
        op.add_column("transactions", sa.Column("doc_no", sa.Integer(), nullable=True))
    # заполняем сквозным номером по хронологии (оконная функция)
    bind.execute(sa.text("""
        WITH numbered AS (
            SELECT id, row_number() OVER (ORDER BY transaction_date ASC, id ASC) AS rn
            FROM transactions
        )
        UPDATE transactions t SET doc_no = numbered.rn
        FROM numbered WHERE t.id = numbered.id
    """))


def downgrade() -> None:
    if _has_column("transactions", "doc_no"):
        op.drop_column("transactions", "doc_no")
    bind = op.get_bind()
    bind.execute(sa.text(
        "DELETE FROM analytic_articles WHERE name='Входящий остаток' AND kind='opening'"
    ))
