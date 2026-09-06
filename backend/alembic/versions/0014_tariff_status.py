"""tariff status

Статус тарифа: «Действующий» / «Архивный» (роадмап, тарифы).

* В `tariffs` добавляется колонка `status` (varchar(20), default 'active'):
    active   — Действующий (последний по дате тариф в своей группе);
    archived — Архивный (предыдущие тарифы той же группы).
* Группа = (вид услуги, признак разовости is_oneoff), чтобы разовые тарифы
  (спец-сборы) не «затирались» регулярными и наоборот.
* Бэкафилл: действующим становится последний тариф группы по
  (valid_from DESC, id DESC), остальные помечаются архивными. Статус
  информационный — расчёт начислений идёт по valid_from/is_oneoff, поэтому
  архивация безопасна для созданных начислений и исторических периодов.
* При создании нового тарифа предыдущие действующие той же группы помечаются
  архивными автоматически (см. services.retire_tariff_predecessors / app.py).

Revision ID: 0014_tariff_status
Revises: 0013_service_unit
Create Date: 2026-09-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0014_tariff_status"
down_revision: Union[str, Sequence[str], None] = "0013_service_unit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(op.get_bind()).get_columns(table)]


def upgrade() -> None:
    if not _has_column("tariffs", "status"):
        op.add_column(
            "tariffs",
            sa.Column(
                "status",
                sa.String(20),
                nullable=False,
                server_default="active",
            ),
        )
        # Бэкафилл: действующий — последний тариф группы (вид услуги, разовость).
        op.execute(
            """
            UPDATE tariffs
            SET status = 'archived'
            WHERE id NOT IN (
                SELECT DISTINCT ON (services_type_id, is_oneoff) id
                FROM tariffs
                ORDER BY services_type_id, is_oneoff, valid_from DESC, id DESC
            )
            """
        )


def downgrade() -> None:
    if _has_column("tariffs", "status"):
        with op.batch_alter_table("tariffs") as batch:
            batch.drop_column("status")
