"""service_unit

Перенос «Единицы измерения» с тарифа на вид услуги (09.2026) — по той же логике,
что и «Тип тарифа» (0012): единица задаётся один раз на виде услуги и наследуется
всеми её тарифами, чтобы пользователь не вводил её (и не ошибался) в каждом тарифе.

* `services_type.unit` (nullable) добавляется;
* `tariffs.unit` удаляется.

Бэкафилл для существующих данных (идемпотентно, под гвардами _has_column — на
«свежей» БД create_all по актуальным моделям уже создал services_type.unit и не
создал tariffs.unit):
  1) ед. изм. услуги = ед. изм. её ПОСЛЕДНЕГО регулярного тарифа, где она задана;
  2) иначе — любого тарифа услуги;
  3) иначе остаётся NULL (ед. изм. необязательна).

Revision ID: 0013_service_unit
Revises: 0012_service_tariff_type
Create Date: 2026-09-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0013_service_unit"
down_revision: Union[str, Sequence[str], None] = "0012_service_tariff_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(op.get_bind()).get_columns(table)]


def upgrade() -> None:
    if not _has_column("services_type", "unit"):
        op.add_column(
            "services_type",
            sa.Column("unit", sa.String(50), nullable=True),
        )
        # 1) ед. изм. из последнего регулярного тарифа, где она задана
        op.execute(
            """
            UPDATE services_type st
            SET unit = (
                SELECT t.unit FROM tariffs t
                WHERE t.services_type_id = st.id AND t.is_oneoff = false AND t.unit IS NOT NULL
                ORDER BY t.valid_from DESC, t.id DESC LIMIT 1
            )
            WHERE st.unit IS NULL
            """
        )
        # 2) из любого тарифа услуги (регулярных с ед. изм. нет)
        op.execute(
            """
            UPDATE services_type st
            SET unit = (
                SELECT t.unit FROM tariffs t
                WHERE t.services_type_id = st.id AND t.unit IS NOT NULL
                ORDER BY t.valid_from DESC, t.id DESC LIMIT 1
            )
            WHERE st.unit IS NULL
            """
        )

    if _has_column("tariffs", "unit"):
        with op.batch_alter_table("tariffs") as batch:
            batch.drop_column("unit")


def downgrade() -> None:
    # Возвращаем tariffs.unit из единицы вида услуги.
    if not _has_column("tariffs", "unit"):
        op.add_column("tariffs", sa.Column("unit", sa.String(50), nullable=True))
        op.execute(
            """
            UPDATE tariffs t
            SET unit = (SELECT st.unit FROM services_type st WHERE st.id = t.services_type_id)
            """
        )

    if _has_column("services_type", "unit"):
        with op.batch_alter_table("services_type") as batch:
            batch.drop_column("unit")
