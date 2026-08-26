"""baseline

Устанавливает точку отсчёта миграций Alembic для текущей (уже существующей) схемы.

ВАЖНО. Ревизия намеренно «пустая» (no-op): схема базы уже развёрнута (ручными
миграциями и ранее). Здесь мы только фиксируем, что текущее состояние БД является
базовым, чтобы Alembic начал вести дальнейшие изменения схемы.

Существующие, но не описанные в моделях таблицы (users, invoices, counterparties,
debts, invoice_items, debtors, payments, payment_allocations) — legacy-хвост из
ранней схемы — намеренно НЕ удаляются (решение о деструктивных изменениях —
отдельная задача, вне этой ревизии). Индексы/именование FK задаются вручную и
уже существуют в БД.

Revision ID: 0000_baseline
Revises:
Create Date: 2026-08-26
"""

from typing import Sequence, Union

revision: str = "0000_baseline"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Базовое состояние схемы уже существует — ничего не меняем."""
    pass


def downgrade() -> None:
    """Ничего не откатываем — baseline не создавал схемы."""

    pass
