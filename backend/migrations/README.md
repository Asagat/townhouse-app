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

### Починка лишних «Приход в кассу» (`migrate_group_cash_by_day.py`)

Идемпотентный скрипт-починка для уже импортированной кассы (шумы до добавления
группировки в `migrate_synthetic/cash.py`): сворачивает жительские приходы одной
квартиры/даты в один документ `Transaction` и пересоздаёт производный срез
`accounts_register` (`rebuild_accounts_register`). По умолчанию — сухой прогон
(ничего не меняет); применение — флагом `--apply`:

    python migrations/migrate_group_cash_by_day.py          # что будет сделано
    python migrations/migrate_group_cash_by_day.py --apply   # применить

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
  жительские приходы одной квартиры/даты сливаются в один документ «Приход в кассу»
  (по договорённости миграции); сторно/входящее сальдо/расходы не сливаются;
- контрольные числа каждого шага печатаются в stdout; сверялись на этапе
  разработки (см. итоги в роадмапе, раздел 4).

Синтез помечает документы: обычные («Начисление за …») — `doc_kind='monthly'`,
разовые/персональные («Разовые сборы …», «Персональное доначисление …») —
`doc_kind='oneoff'`; авто-тариф для разовых строк создаётся с `is_oneoff=true`
(не участвует в месячном пересчёте). Месячный (пере-)расчёт начислений работает
только с `doc_kind='monthly'` и только по регулярным тарифам (`is_oneoff=false`).
Прошлые строки (история) при этом сохраняются.

Справочные поля: у тарифов и документов начислений есть необязательное поле
«Примечание» (`comment`) — ревизия `1e9f7c2a5b6d`.
