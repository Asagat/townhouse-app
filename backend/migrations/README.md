# Миграции

Начиная с внедрения Alembic, управление схемой БД ведётся через Alembic:

    alembic upgrade head     # применить все миграции
    alembic revision --autogenerate -m "описание"   # новая миграция
    alembic current          # текущая ревизия

Настроено в `backend/alembic/` и `backend/alembic.ini`; URL берётся из окружения
`DATABASE_URL` через `backend/database.py`.

## Базовая ревизия `0000_baseline`
No-op-ревизия: фиксирует текущее состояние «уже развёрнутой» схемы как точку
отсчёта Alembic. Существующие legacy-таблицы (users, invoices, counterparties,
debts, invoice_items, debtors, payments, payment_allocations) намеренно НЕ удалены —
решение об их судьбе вынесено за рамки этой ревизии.

## Свежая БД
Для быстрой инициализации схемы с нуля используется `backend/bootstrap_db.py`
(`Base.metadata.create_all()` из моделей) — создаёт только отсутствующие таблицы
идемпотентно, а `0000_baseline` затем ставит версию Alembic.

## Исторические ручные SQL-миграции (`0001_*.sql`, `0002_*.sql`)
Применены вручную до внедрения Alembic (`cash_register`, `services_type.priority`).
Их результат уже включён в текущую схему (и в модели), поэтому в составе Alembic
они не дублируются. Скрипты `flip_accounts_register_signs.py` и
`migrate_old_payments_to_cash_register.py` — данные-миграции, запускаются
однократно при необходимости.
