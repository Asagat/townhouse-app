"""cash_contractor

Заменяет «Виды услуг» на «Контрагент» в денежных документах.

Убирает `transactions.services_type_id` и `cash_register.services_type_id`
(поле «Виды услуг» из документа «Приход/Расход» и «Регистра денежных средств» —
более не нужно для денежных операций) и добавляет на их место `contractor_id`
(связь на справочник «Контрагенты» = `owners`) как в шапку «Приход/Расход», так и
в регистр (`cash_register`), чтобы регистр фильтровался/отчитывался по контрагенту
без JOIN (зеркалится из шапки при вставке/редактировании).

Оба поля необязательны (NULL — операции без конкретного контрагента).
Идемпотентно: на свежей БД `0002_schema_squash` (create_all по актуальным моделям)
эти объекты создаются из моделей; `0008` лишь подстраховывает уже развёрнутые БД.

Revision ID: 0008_cash_contractor
Revises: 0007_document_create_ts
Create Date: 2026-09-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0008_cash_contractor"
down_revision: Union[str, Sequence[str], None] = "0007_document_create_ts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(op.get_bind()).get_columns(table)]


def _fk_exists(table: str, column: str) -> bool:
    for fk in inspect(op.get_bind()).get_foreign_keys(table):
        if column in fk["constrained_columns"]:
            return True
    return False


def upgrade() -> None:
    # --- контрагент: контрактор_id на owners ---
    for table, col in (("cash_register", "contractor_id"), ("transactions", "contractor_id")):
        if not _has_column(table, col):
            op.add_column(table, sa.Column(col, sa.Integer(), nullable=True))
        if not _fk_exists(table, col):
            op.create_foreign_key(
                f"fk_{table}_{col}", table, "owners", [col], ["id"], ondelete="RESTRICT"
            )

    # --- удаляем «Виды услуг» ---
    for table, col in (("cash_register", "services_type_id"), ("transactions", "services_type_id")):
        if _has_column(table, col):
            if _fk_exists(table, col):
                op.drop_constraint(f"fk_{table}_services_type", table, type_="foreignkey")
            op.drop_column(table, col)


def downgrade() -> None:
    # возвращаем services_type_id (для будущих откатов), убираем contractor_id
    for table in ("transactions", "cash_register"):
        if _has_column(table, "contractor_id"):
            if _fk_exists(table, "contractor_id"):
                op.drop_constraint(f"fk_{table}_contractor_id", table, type_="foreignkey")
            op.drop_column(table, "contractor_id")
        if not _has_column(table, "services_type_id"):
            op.add_column(table, sa.Column("services_type_id", sa.Integer(), nullable=True))
        if not _fk_exists(table, "services_type_id"):
            op.create_foreign_key(
                f"fk_{table}_services_type", table, "services_type",
                ["services_type_id"], ["id"], ondelete="RESTRICT",
            )
