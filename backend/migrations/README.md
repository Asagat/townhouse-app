# Миграции

Начиная с внедрения Alembic, управление схемой БД ведётся через Alembic:

    alembic upgrade head     # применить все миграции
    alembic revision --autogenerate -m "описание"   # новая миграция
    alembic current          # текущая ревизия

Настроено в `backend/alembic/` и `backend/alembic.ini`; URL берётся из окружения
`DATABASE_URL` через `backend/database.py`.

## Перенумерация id (разово, перед финальным прод-развёртыванием — ТД-2)

Приводит автогенерируемые `id` всех таблиц к непрерывной нумерации с 1, сохраняя
содержимое. Выполняется на копии/переносе (dev → прод), НЕ в рабочем режиме.

Два шага (оба — с прогоном без изменений):

```bash
python migrations/renumber_all_entities.py          # отчёт «дыр» (без изменений)
python migrations/renumber_all_entities.py --apply  # перенумеровать id всех таблиц
python migrations/renumber_finalize.py --dry-run     # план финализации
python migrations/renumber_finalize.py               # применить
```

1. `renumber_all_entities.py` — порядок зависимостей «справочники → документы →
   регистры», перепривязка всех FK и `setval` по каждой последовательности;
2. `renumber_finalize.py` — хронология начислений и «Приход/Расход» (`Начальный
   остаток` → id 1), пересборка `accounts_register`, перегенерация квитанций,
   контроль `check_register_integrity`.

Полный порядок переноса на прод-сервер — `DEPLOY.md` §7.6.

> ⚠️ Перенумерация `users` делает недействительными выданные JWT (`sub = user.id`) —
> пользователи войдут заново. Начинать с бэкапа БД.

### Заменённые частные случаи (устарели)

Следующие скрипты ранее делали по отдельности то, что теперь закрыто парой выше.
Оставлены для точечных сценариев, но для полной перенумерации не использовать:

| Устаревший скрипт | Что делал | Теперь |
|---|---|---|
| `migrations/reimport/recreate_and_resync.py` | `RESTART IDENTITY` для начислений/квитанций + хронология | шаг `renumber_finalize.py` |
| `migrations/reimport/renumber_transactions_chronological.py` | перенумерация «Приход/Расход» по хронологии | шаг `renumber_finalize.py` |
| `migrations/reimport/reorder_receipts_by_period_apartment.py` | перенумерация квитанций по (период, кв.) | автоматически через перегенерацию квитанций |

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

## Тарифы: удаление «двойников» после конверсии 2.18 (`fix_duplicate_open_tariffs.py`)

Конверсия `0018_tariff_period_conversion` для каждого исторического разового сбора
создала закрытый тариф-период (с комментарием «Конверсия 2.18…») и оставила
**открытый тариф-двойник** с той же датой начала. Последний такой двойник в услуге
становился её бессрочной базовой ставкой и подставлялся в новые начисления
(`resolve_tariff_for_accrual_period` поле `status` не читает). Реальный случай:
«Фонд развития» — 148 850 ₸/мес с 05.2026 вместо базовых 2 000 ₸; в начисление
за август 2026 попало 17 строк по 148 850.

Скрипт идемпотентно удаляет открытые тарифы, у которых есть закрытый «конверсионный»
тариф (комментарий «Конверсия 2.18…») с **той же** датой начала и на которые **нет
ссылок** в `accruals_register`; флаг `--normalize-status` дополнительно оставляет
«Действующим» ровно один тариф на услугу (применяемый для текущего месяца).

```bash
python migrations/fix_duplicate_open_tariffs.py                          # dry-run
python migrations/fix_duplicate_open_tariffs.py --apply
python migrations/fix_duplicate_open_tariffs.py --apply --normalize-status
```

Правка касается **только справочника тарифов**: строки начислений/регистров не меняются.
После — контроль `migrations/accruals_sum_check.py` и/или `check_register_integrity`.
Если по «двойнику» уже начислен месяц, это начисление надо пересчитать отдельно
(штатно через приложение), иначе в регистре останется завышенная сумма.

Запуск на NAS (без сборки образа):
`docker cp backend/migrations/fix_duplicate_open_tariffs.py <backend-контейнер>:/app/migrations/`.
