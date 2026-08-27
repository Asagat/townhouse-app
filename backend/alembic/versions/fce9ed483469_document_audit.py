"""document_audit

Revision ID: fce9ed483469
Revises: c1c2a44669d3
Create Date: 2026-08-27 11:13:57.880931

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'fce9ed483469'
down_revision: Union[str, Sequence[str], None] = 'c1c2a44669d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return column in [c["name"] for c in inspect(bind).get_columns(table)]


def _fk_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    for fk in inspect(bind).get_foreign_keys(table):
        if column in fk["constrained_columns"]:
            return True
    return False


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if not _has_column(table, column.name):
        op.add_column(table, column)


def _add_fk_if_missing(table: str, fk_col: str, ref_table: str) -> None:
    if not _fk_exists(table, fk_col):
        op.create_foreign_key(None, table, ref_table, [fk_col], ['id'], ondelete='SET NULL')


def upgrade() -> None:
    """Add document audit columns (idempotent against 0002_schema_squash create_all())."""
    _add_column_if_missing('accrual_documents', sa.Column('created_by', sa.Integer(), nullable=True))
    _add_column_if_missing('accrual_documents', sa.Column('updated_by', sa.Integer(), nullable=True))
    _add_column_if_missing('accrual_documents', sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True))
    _add_column_if_missing('accrual_documents', sa.Column('change_description', sa.String(length=500), nullable=True))
    _add_fk_if_missing('accrual_documents', 'created_by', 'users')
    _add_fk_if_missing('accrual_documents', 'updated_by', 'users')

    _add_column_if_missing('meter_reading_documents', sa.Column('created_by', sa.Integer(), nullable=True))
    _add_column_if_missing('meter_reading_documents', sa.Column('updated_by', sa.Integer(), nullable=True))
    _add_column_if_missing('meter_reading_documents', sa.Column('change_description', sa.String(length=500), nullable=True))
    _add_fk_if_missing('meter_reading_documents', 'created_by', 'users')
    _add_fk_if_missing('meter_reading_documents', 'updated_by', 'users')

    _add_column_if_missing('receipt_documents', sa.Column('created_by', sa.Integer(), nullable=True))
    _add_column_if_missing('receipt_documents', sa.Column('updated_by', sa.Integer(), nullable=True))
    _add_column_if_missing('receipt_documents', sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True))
    _add_column_if_missing('receipt_documents', sa.Column('change_description', sa.String(length=500), nullable=True))
    _add_fk_if_missing('receipt_documents', 'created_by', 'users')
    _add_fk_if_missing('receipt_documents', 'updated_by', 'users')

    _add_column_if_missing('transactions', sa.Column('created_by', sa.Integer(), nullable=True))
    _add_column_if_missing('transactions', sa.Column('updated_by', sa.Integer(), nullable=True))
    _add_column_if_missing('transactions', sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True))
    _add_column_if_missing('transactions', sa.Column('change_description', sa.String(length=500), nullable=True))
    _add_fk_if_missing('transactions', 'created_by', 'users')
    _add_fk_if_missing('transactions', 'updated_by', 'users')

    _add_column_if_missing('writeoff_documents', sa.Column('updated_by', sa.Integer(), nullable=True))
    _add_column_if_missing('writeoff_documents', sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True))
    _add_column_if_missing('writeoff_documents', sa.Column('change_description', sa.String(length=500), nullable=True))
    _add_fk_if_missing('writeoff_documents', 'updated_by', 'users')


def downgrade() -> None:
    """Downgrade schema (idempotent)."""
    bind = op.get_bind()
    insp = inspect(bind)

    def _drop_fk(table: str, col: str) -> None:
        if _fk_exists(table, col):
            op.drop_constraint(None, table, type_='foreignkey')

    def _drop_col(table: str, col: str) -> None:
        if _has_column(table, col):
            op.drop_column(table, col)

    _drop_fk('writeoff_documents', 'updated_by')
    _drop_col('writeoff_documents', 'change_description')
    _drop_col('writeoff_documents', 'updated_at')
    _drop_col('writeoff_documents', 'updated_by')

    for t in ('transactions', 'receipt_documents', 'meter_reading_documents', 'accrual_documents'):
        _drop_fk(t, 'updated_by')
        _drop_fk(t, 'created_by')
        for c in ('change_description', 'updated_at', 'updated_by', 'created_by'):
            _drop_col(t, c)
