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

## Синтез данных из старой БД (раздел 4 роадмапа)

Перенос истории из `templates/Миграция данных FTH.xlsx` (подготовлены CSV в
`templates/clean/`) в ЧИСТУЮ схему (после `alembic upgrade head`, до seed/демо).

* **Подготовка** (локально, нужен `openpyxl`):
  `python backend/migrations/migrate_prepare_sources.py --src templates/Миграция данных FTH.xlsx --out templates/clean`
  → `templates/clean/{apartments,meters,readings,accruals,cash,services}.csv`.
* CSV передаю контейнеру: `docker cp templates/clean <backend>:/app/_migration_src`.

Синтез — в backend-контейнере (`./backend` смонтирован в `/app`), в указанном
порядке (не идемпотентно; выполняется на чистой БД):

| # | Цель | Команда |
|---|------|---------|
| 1 | Справочники+метры | `python migrations/migrate_import.py --csv /app/_migration_src --stage ref,meters` |
| 2 | Месячные Tariff | `python migrations/migrate_synthetic/tariffs.py --csv /app/_migration_src --commit` |
| 3 | Документы показаний | `python migrations/migrate_synthetic/readings.py --csv /app/_migration_src` |
| 4 | Документы начислений | `python migrations/migrate_synthetic/accruals.py --csv /app/_migration_src` |
| 5 | Входящие остатки (старт) | `python migrations/migrate_synthetic/initial_balance.py --csv /app/_migration_src` |
| 6 | Касса (Приход/Расход) | `python migrations/migrate_synthetic/cash.py --csv /app/_migration_src` |
| 7 | Пересборка регистра | `python migrations/migrate_synthetic/rebuild.py` |

Замечания:
- `migrate_import.py`: этап ref+meters + миграционный пользователь/справочники;
- шаг 4 начислений НЕ вносит `enter`; их добавляет шаг 5 как первичные строки
  2017-10 (стартовое сальдо л/с);
- шаг 6 кассы использует прямой SQL (без ORM-событий) во избежание дублей/O(n^2);
- контрольные числа каждого шага печатаются в stdout; сверялись на этапе
  разработки (см. итоги в роадмапе, раздел 4).
