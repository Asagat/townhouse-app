"""regular_oneoff_kinds

Разделение «регулярных» и «разовых» (одноразовых) сущностей без потери истории:

  * `tariffs.is_oneoff` — у тарифа появляется признак «разового/одноразового» сбора.
    Регулярные тарифы участвуют в ежемесячном пересчёте; разовые — нет, но строки
    начислений продолжают на них ссылаться (история сохраняется).
  * `accrual_documents.doc_kind` — тип документа начислений: 'monthly' (регулярный,
    «Начисление за …») или 'oneoff' («Разовые сборы …», «Персональное доначисление …»,
    «Входящие остатки …» и т.п.). Месячный (пере-)расчёт работает только с monthly.

Идемпотентно: шаг 0002 (create_all по актуальным моделям) уже мог создать колонки
на свежей БД — здесь гарантируем их наличие и разметку только при отсутствии.

Revision ID: 9a4d2c01e6f0
Revises: 0005_drop_analytic_code
Create Date: 2026-09-03 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect, text
import sqlalchemy as sa

revision: str = '9a4d2c01e6f0'
down_revision: Union[str, Sequence[str], None] = '0005_drop_analytic_code'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return column in [c["name"] for c in inspect(bind).get_columns(table)]


def oneoff_title_like() -> str:
    """Условия на `accrual_documents.title`, по которым документ — разовый/внеш.
    Классифицируем по устойчивым префиксам авто-названий миграции."""
    return (
        "lower(title) LIKE 'разовые сборы%'"
        " OR lower(title) LIKE 'разовый%'"
        " OR lower(title) LIKE '%разовые%'"
        " OR lower(title) LIKE 'персональное доначисление%'"
        " OR lower(title) LIKE 'входящие остатки%'"
    )


def upgrade() -> None:
    if not _has_column("tariffs", "is_oneoff"):
        op.add_column(
            'tariffs',
            sa.Column('is_oneoff', sa.Boolean(), nullable=False,
                      server_default=sa.text('false')),
        )
    if not _has_column("accrual_documents", "doc_kind"):
        op.add_column(
            'accrual_documents',
            sa.Column('doc_kind', sa.String(20), nullable=False,
                      server_default="'monthly'"),
        )
    op.execute(
        "UPDATE accrual_documents SET doc_kind='oneoff' "
        "WHERE (title IS NULL OR " + oneoff_title_like() + ") AND doc_kind='monthly'"
    )


def downgrade() -> None:
    if _has_column("accrual_documents", "doc_kind"):
        op.drop_column('accrual_documents', 'doc_kind')
    if _has_column("tariffs", "is_oneoff"):
        op.drop_column('tariffs', 'is_oneoff')
