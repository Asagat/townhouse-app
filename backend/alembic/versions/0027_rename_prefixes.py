"""rename settings resource -> prefixes

Переименование раздела «Настройки» → «Префиксы» (пункт меню «5. Администрирование»).
В `permissions.PERMISSION_CATALOG` ключ ресурса изменён `settings` → `prefixes`.

На БД, где матрица `role_permissions` уже засеяна старым ключом (локальная dev-БД),
строки переименовываем, чтобы сохранённые администратором права не «осиротели».
Свежие БД (и прод, где миграции ещё не применялись) на 0022 сразу сидят с новым
ключом — для них UPDATE ничего не меняет.

Revision ID: 0027_rename_prefixes
Revises: 0026_apartment_residents
Create Date: 2026-09-27
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0027_rename_prefixes"
down_revision: Union[str, Sequence[str], None] = "0026_apartment_residents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE role_permissions SET resource = 'prefixes' WHERE resource = 'settings'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE role_permissions SET resource = 'settings' WHERE resource = 'prefixes'"
    )
