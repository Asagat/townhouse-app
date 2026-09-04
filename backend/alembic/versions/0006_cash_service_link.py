"""cash_service_link

Связь денежных документов с «Видами услуг» (services_type).

Добавляет «Виды услуг» в документ «Приход/Расход» (`transactions.services_type_id`) и
дублирует услугу в «Регистр денежных средств» (`cash_register.services_type_id`), чтобы
каждая денежная запись несла одновременно и «Статью» доходов/расходов
(`analytic_articles.article_id`), и «Вид услуги» — для более детальных отчётов по
статьям и видам услуг.

Оба поля необязательные (NULL = операции без привязки к услуге: остатки, общие взносы).
Идемпотентно: на свежей БД `0002_schema_squash` (create_all по актуальным моделям) эти
колонки уже создаются моделями; `0006` лишь подстраховывает уже развёрнутые БД.

Revision ID: 0006_cash_service_link
Revises: 1e9f7c2a5b6d
Create Date: 2026-09-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0006_cash_service_link"
down_revision: Union[str, Sequence[str], None] = "1e9f7c2a5b6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    return table in inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(op.get_bind()).get_columns(table)]


def _fk_exists(table: str, column: str) -> bool:
    for fk in inspect(op.get_bind()).get_foreign_keys(table):
        if column in fk["constrained_columns"]:
            return True
    return False


def _add_service_fk(table: str, column: str, fk_name: str) -> None:
    """Добавляет nullable-колонку (если нет) и внешний ключ на services_type."""
    if not _has_table("services_type"):
        return
    if not _has_column(table, column):
        op.add_column(table, sa.Column(column, sa.Integer(), nullable=True))
    if not _fk_exists(table, column):
        op.create_foreign_key(
            fk_name, table, "services_type", [column], ["id"], ondelete="RESTRICT"
        )


def upgrade() -> None:
    """Добавляет services_type_id в transactions и cash_register."""
    _add_service_fk("transactions", "services_type_id", "fk_transactions_services_type")
    _add_service_fk("cash_register", "services_type_id", "fk_cash_register_services_type")


def downgrade() -> None:
    """Downgrade schema (идемпотентно, не трогаем данные)."""
    for table, column, fk_name in (
        ("cash_register", "services_type_id", "fk_cash_register_services_type"),
        ("transactions", "services_type_id", "fk_transactions_services_type"),
    ):
        if _has_column(table, column):
            if _fk_exists(table, column):
                op.drop_constraint(fk_name, table, type_="foreignkey")
            op.drop_column(table, column)
