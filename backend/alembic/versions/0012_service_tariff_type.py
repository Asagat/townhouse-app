"""service_tariff_type

Перенос привязки «Тип тарифа» с тарифа на вид услуги (09.2026):

* `services_type.tariff_type_id` (NOT NULL, FK -> tariff_types) — тип задаётся
  один раз на виде услуги и наследуется всеми его тарифами. Это исключает ошибку
  пользователя «на тарифе указан не тот тип» (начисление не проходило), а тарифы
  вводятся чаще, чем виды услуг.
* `tariffs.tariff_type_id` удаляется.

Бэкафилл для существующих данных (идемпотентно, работает и на «свежей» БД, где
шаг 0002 create_all уже создал схему по актуальным моделям — все операции под
гвардами _has_column):
  1) тип услуги = тип её ПОСЛЕДНЕГО регулярного тарифа (valid_from DESC, id DESC);
  2) если регулярных нет — тип любого тарифа;
  3) если тарифов нет вовсе — системный «Фиксированный» (создаётся при отсутствии).

Начисление и метры после переноса читают тип с вида услуги (services.py /
serializers.py), регистры и документы не меняются: они ссылаются на services_type
и tariffs по своим id, а tariff_type_id в accruals_register не хранился.

Revision ID: 0012_service_tariff_type
Revises: 0011_opening_balance_and_doc_no
Create Date: 2026-09-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0012_service_tariff_type"
down_revision: Union[str, Sequence[str], None] = "0011_opening_balance_and_doc_no"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(op.get_bind()).get_columns(table)]


def upgrade() -> None:
    if not _has_column("services_type", "tariff_type_id"):
        # 0) Гарантируем наличие системного «Фиксированного» (фолбэк для услуг без тарифов).
        op.execute(
            "INSERT INTO tariff_types (name) "
            "SELECT 'Фиксированный' WHERE NOT EXISTS "
            "(SELECT 1 FROM tariff_types WHERE name = 'Фиксированный')"
        )

        op.add_column(
            "services_type",
            sa.Column("tariff_type_id", sa.Integer(), nullable=True),
        )
        # 1) тип из последнего регулярного тарифа услуги (что реально считает начисление)
        op.execute(
            """
            UPDATE services_type st
            SET tariff_type_id = (
                SELECT t.tariff_type_id FROM tariffs t
                WHERE t.services_type_id = st.id AND t.is_oneoff = false
                ORDER BY t.valid_from DESC, t.id DESC LIMIT 1
            )
            WHERE st.tariff_type_id IS NULL
            """
        )
        # 2) если регулярных нет — берём любой тариф (разовые тоже задают тип услуги)
        op.execute(
            """
            UPDATE services_type st
            SET tariff_type_id = (
                SELECT t.tariff_type_id FROM tariffs t
                WHERE t.services_type_id = st.id
                ORDER BY t.valid_from DESC, t.id DESC LIMIT 1
            )
            WHERE st.tariff_type_id IS NULL
            """
        )
        # 3) фолбэк — «Фиксированный»
        op.execute(
            """
            UPDATE services_type st
            SET tariff_type_id = (SELECT id FROM tariff_types WHERE name = 'Фиксированный' LIMIT 1)
            WHERE st.tariff_type_id IS NULL
            """
        )
        with op.batch_alter_table("services_type") as batch:
            batch.alter_column("tariff_type_id", existing_type=sa.Integer(), nullable=False)
            batch.create_foreign_key(
                "fk_services_type_tariff_type_id",
                "tariff_types",
                ["tariff_type_id"],
                ["id"],
                ondelete="RESTRICT",
            )

    if _has_column("tariffs", "tariff_type_id"):
        with op.batch_alter_table("tariffs") as batch:
            batch.drop_column("tariff_type_id")


def downgrade() -> None:
    # Возвращаем tariffs.tariff_type_id из типа вида услуги.
    if not _has_column("tariffs", "tariff_type_id"):
        op.add_column("tariffs", sa.Column("tariff_type_id", sa.Integer(), nullable=True))
        op.execute(
            """
            UPDATE tariffs t
            SET tariff_type_id = (
                SELECT st.tariff_type_id FROM services_type st WHERE st.id = t.services_type_id
            )
            """
        )
        with op.batch_alter_table("tariffs") as batch:
            batch.alter_column("tariff_type_id", existing_type=sa.Integer(), nullable=False)
            batch.create_foreign_key(
                "tariffs_tariff_type_id_fkey",
                "tariff_types",
                ["tariff_type_id"],
                ["id"],
                ondelete="RESTRICT",
            )

    if _has_column("services_type", "tariff_type_id"):
        with op.batch_alter_table("services_type") as batch:
            batch.drop_column("tariff_type_id")
