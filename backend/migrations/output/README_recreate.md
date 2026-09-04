# Накат «пересоздать начисления (хронологические id) + перегенерировать квитанции»

Этот накат выполняет обе доработки после обновления прода:

1. **Начисления** — документы и строки `accruals_register` пересозданы так, что
   «Входящие остатки (старт)» имеет наименьший `id`, далее месячные по возрастанию
   периода (журнал «Начисления» читается хронологически).
2. **Квитанции** — `receipt_documents`(+строки) пересозданы генератором по формуле
   `К оплате = начислено за период + долг на начало периода − переплата`
   (оплаты распределены по своим месяцам).

Вся логика расчёта продублирована из приложения, поэтому численный результат совпадает
с тем, что вернёт сам генератор в рантайме.

## Что лежит в этой папке

| Файл | Назначение |
|---|---|
| `apply_variant_B.sql` | **Шаг 1. Накат «начисления (хроно-ид) + квитанции»** (Вариант Б), валидирован end-to-end |
| `recreate_accruals_receipts_data.sql` | Данные 5 таблиц для шага 1 (встроены в apply_variant_B.sql; отдельно не нужны) |
| `apply_tx_chronological.sql` | **Шаг 2. «Приход/Расход/касса: хроно-ид, Начальный остаток = id 1»**, валидирован end-to-end |
| `recreate_tx_chronological_data.sql` | Данные 3 таблиц для шага 2 (встроены в apply_tx_chronological.sql; отдельно не нужны) |
| `apply_receipts_order.sql` | **Шаг 3. Квитанции: пере-перенумерация по «Дата документа + № квартиры»**, валидирован end-to-end |
| `recreate_receipts_order_data.sql` | Данные квитанций/строк для шага 3 (встроены в apply_receipts_order.sql; отдельно не нужны) |
| `apply_income_group.sql` | **Шаг 4. Приход жителей свёрнут в один документ на квартиру/день**, валидирован end-to-end |
| `recreate_income_group_data.sql` | Данные 3 таблиц для шага 4 (встроены в apply_income_group.sql; отдельно не нужны) |
| `../reimport/recreate_and_resync.py` | Вариант А (скрипт) для шага 1 |
| `../reimport/renumber_transactions_chronological.py` | Вариант А (скрипт) для шага 2 |
| `../reimport/reorder_receipts_by_period_apartment.py` | Вариант А (скрипт) для шага 3 |
| `../reimport/group_resident_income_by_day.py` | Вариант А (скрипт) для шага 4 |
| этот `README_recreate.md` | Инструкция |

> Оба apply-файла имеют встроенную защиту: база должна называться `townhouse`, целевые
> таблицы должны существовать (схема на `head`). Всё выполняется в своих транзакциях —
> при любой ошибке соответствующий файл откатывается целиком.

Накат выполняется **четырьмя последовательными SQL-приката** (каждый в своей
транзакции, при ошибке — полный откат этого файла):

1. `apply_variant_B.sql` — начисления хроно + перегенерируются квитанции;
2. `apply_tx_chronological.sql` — вся «Приход/Расход» по хронологии
   (первая запись = «Начальный остаток», id/doc_no = 1);
3. `apply_receipts_order.sql` — квитанции по «Дата документа» + № квартиры;
4. `apply_income_group.sql` — жительские «Поступления от жителей» одного дня/счёта
   сворачиваются в один документ (убераются сотни построчек).

```bash
# 0) полный бэкап прода — ОБЯЗАТЕЛЬНО
for f in apply_variant_B.sql apply_tx_chronological.sql apply_receipts_order.sql apply_income_group.sql; do
  docker exec -i townhouse-postgres sh -c 'PGPASSWORD=... psql -U townhouse_user -d townhouse -v ON_ERROR_STOP=1' < "$f" || break
done
```

После всех шагов выполнить HOT-reload/restart backend и frontend.

## Вариант А (скрипты) — когда на прод уже добавлялись записи поверх импорта

Если на проде после перезаливки могли появиться новые начисления/транзакции/квитанции,
используйте скрипты (они пересчитают из текущих данных и НЕ перезапишут свежие записи
снимками):

```bash
docker exec townhouse-backend sh -c 'cd /app && python migrations/reimport/recreate_and_resync.py'
docker exec townhouse-backend sh -c 'cd /app && python migrations/reimport/renumber_transactions_chronological.py'
docker exec townhouse-backend sh -c 'cd /app && python migrations/reimport/reorder_receipts_by_period_apartment.py'
docker exec townhouse-backend sh -c 'cd /app && python migrations/reimport/group_resident_income_by_day.py'
```

## После наката — контрольные SQL

```sql
-- 1) старт первым, id хронологичны
SELECT id, accrual_date, doc_kind, title
FROM accrual_documents ORDER BY id ASC LIMIT 5;

-- 2) целостность регистра взаиморасчётов: краткая сверка по всем счетам
SELECT (SELECT count(*) FROM accruals_register) AS строк_начислений,
       (SELECT count(*) FROM accounts_register) AS строк_взаиморасчётов;

-- 3) заголовки квитанций согласованы: К оплате = начислено + долг − переплата
SELECT count(*) AS расхождений
FROM receipt_documents
WHERE abs(total_amount + COALESCE(debt,0) - COALESCE(overpayment,0) - payable_amount) > 0.01;

-- 4) Шаг 2: «Начальный остаток» — первая запись Приход/Расход (id/doc_no = 1)
SELECT id, doc_no, transaction_date, COALESCE(t.notes,'') notes, t.amount
FROM transactions t ORDER BY id ASC LIMIT 3;

-- 5) нет нарушений хронологии (даты монотонны по id)
SELECT count(*) AS нарушений FROM (
  SELECT transaction_date, lag(transaction_date) OVER (ORDER BY id) prev
  FROM transactions) t WHERE transaction_date < prev;

-- 6) Шаг 3: квитанции по (период, № квартиры).
SELECT id, period_year, period_month, apartment_number, account_number
FROM receipt_documents ORDER BY id ASC LIMIT 5;

-- контроль: период не убывает по id
SELECT count(*) AS нарушений FROM (
  SELECT 100*period_year+period_month p,
         lag(100*period_year+period_month) OVER (ORDER BY id) prev
  FROM receipt_documents) t WHERE p < prev;

-- 7) привести последовательности в соответствие с max(id) (если что-то правилось вручную)
SELECT setval('accrual_documents_id_seq',  (SELECT max(id) FROM accrual_documents));
SELECT setval('accruals_register_id_seq',  (SELECT max(id) FROM accruals_register));
SELECT setval('receipt_documents_id_seq',  (SELECT max(id) FROM receipt_documents));
SELECT setval('receipt_items_id_seq',      (SELECT max(id) FROM receipt_items));
SELECT setval('accounts_register_id_seq',  (SELECT max(id) FROM accounts_register));
SELECT setval('transactions_id_seq',       (SELECT max(id) FROM transactions));
SELECT setval('cash_register_id_seq',      (SELECT max(id) FROM cash_register));
```
