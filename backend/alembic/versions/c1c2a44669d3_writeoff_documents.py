"""writeoff_documents

Revision ID: c1c2a44669d3
Revises: 0002_schema_squash
Create Date: 2026-08-27 10:46:09.543154

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'c1c2a44669d3'
down_revision: Union[str, Sequence[str], None] = '0002_schema_squash'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return table in inspect(bind).get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return column in [c["name"] for c in inspect(bind).get_columns(table)]


def _fk_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    for fk in inspect(bind).get_foreign_keys(table):
        if column in fk["constrained_columns"]:
            return True
    return False


def _has_check_on_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    for ck in insp.get_check_constraints(table):
        if column in ck["columns"]:
            return True
    return False


def upgrade() -> None:
    """Idempotent: 0002_schema_squash already creates these via create_all()."""
    if not _has_table('writeoff_documents'):
        op.create_table('writeoff_documents',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('writeoff_date', sa.Date(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
        )
    if not _has_table('writeoff_items'):
        op.create_table('writeoff_items',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('services_type_id', sa.Integer(), nullable=False),
        sa.Column('allocated', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('balance_after', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['document_id'], ['writeoff_documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['services_type_id'], ['services_type.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
        )
    if not _has_column('accounts_register', 'writeoff_id'):
        op.add_column('accounts_register', sa.Column('writeoff_id', sa.Integer(), nullable=True))
    if not _fk_exists('accounts_register', 'writeoff_id'):
        op.create_foreign_key(None, 'accounts_register', 'writeoff_documents', ['writeoff_id'], ['id'], ondelete='CASCADE')

    # Приводим users.role к Enum(native_enum=False) по модели (0001 создаёт VARCHAR).
    # Идемпотентно: пропускаем, если CHECK-ограничение роли уже есть.
    if not _has_check_on_column('users', 'role'):
        op.alter_column('users', 'role',
               existing_type=sa.VARCHAR(length=50),
               type_=sa.Enum('admin', 'operator', 'cashier', 'controller', 'resident', name='userrole', native_enum=False),
               existing_nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    insp = inspect(bind)
    if _fk_exists('accounts_register', 'writeoff_id'):
        op.drop_constraint(None, 'accounts_register', type_='foreignkey')
    if _has_column('accounts_register', 'writeoff_id'):
        op.drop_column('accounts_register', 'writeoff_id')
    if _has_table('writeoff_items'):
        op.drop_table('writeoff_items')
    if _has_table('writeoff_documents'):
        op.drop_table('writeoff_documents')
