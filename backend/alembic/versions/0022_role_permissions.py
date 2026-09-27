"""role_permissions (задача 2.6: настраиваемая матрица прав)

Создаёт таблицу `role_permissions` (права роли на ресурс/раздел: видимость меню +
чтение/создание/изменение/удаление) и засеивает её **дефолтной матрицей** из
`permissions.default_permissions()` — то есть текущим поведением. До правок админом
поведение не меняется; отсутствующая строка в рантайме тоже означает «дефолт из кода».

Идемпотентно: на свежей БД `0002_schema_squash` (create_all по моделям) уже создаёт
таблицу; сид идёт через `ON CONFLICT DO NOTHING`.

Revision ID: 0022_role_permissions
Revises: 0021_cash_register_cash_point
Create Date: 2026-09-27
"""

import os
import sys
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from models import Base  # noqa: E402
from permissions import PERMISSION_CATALOG, ROLES, default_permissions  # noqa: E402

revision: str = "0022_role_permissions"
down_revision: Union[str, Sequence[str], None] = "0021_cash_register_cash_point"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # Создаёт недостающие таблицы по моделям (здесь — role_permissions).
    Base.metadata.create_all(bind=bind)

    perms = default_permissions()
    rows = []
    for role in ROLES:
        for entry in PERMISSION_CATALOG:
            p = perms[role][entry["key"]]
            rows.append(
                {
                    "role": role,
                    "resource": entry["key"],
                    "menu": p["menu"],
                    "read": p["read"],
                    "create": p["create"],
                    "edit": p["edit"],
                    "delete": p["delete"],
                }
            )
    if rows:
        bind.execute(
            text(
                "INSERT INTO role_permissions "
                "(role, resource, menu, can_read, can_create, can_edit, can_delete) "
                "VALUES (:role, :resource, :menu, :read, :create, :edit, :delete) "
                "ON CONFLICT (role, resource) DO NOTHING"
            ),
            rows,
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS role_permissions")
