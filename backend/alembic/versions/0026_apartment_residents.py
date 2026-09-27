"""apartment_residents — сведения о жильцах квартир (Б8, фаза 1)

Создаёт таблицу `apartment_residents` (состав жителей квартиры по периодам) и
гарантирует наличие системного типа тарифа «На человека» (фаза 2 — расчёт по числу
жильцов в `services.calculate_accrual_for_account_service`).

Revision ID: 0026_apartment_residents
Revises: 0025_app_settings
Create Date: 2026-09-27
"""

import os
import sys
from typing import Sequence, Union

from alembic import op

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from models import Base  # noqa: E402

revision: str = "0026_apartment_residents"
down_revision: Union[str, Sequence[str], None] = "0025_app_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Идемпотентно: создаёт недостающие таблицы по моделям (здесь — apartment_residents).
    Base.metadata.create_all(bind=op.get_bind())
    # Системный тип тарифа «На человека» (используется формулой начисления, Б8).
    op.execute(
        "INSERT INTO tariff_types (name) SELECT 'На человека' "
        "WHERE NOT EXISTS (SELECT 1 FROM tariff_types WHERE name = 'На человека')"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS apartment_residents")
