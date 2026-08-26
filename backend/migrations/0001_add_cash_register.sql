-- 0001_add_cash_register.sql
-- Фаза 1 (Шаг 1): регистр денежных средств.
-- Регистр взаиморасчётов (accounts_register) больше НЕ заполняется документом
-- «Приход/Расход» — движение денег фиксируется в cash_register (история денег),
-- а во взаиморасчёты попадает через операцию списания (Фаза 3).

CREATE SEQUENCE IF NOT EXISTS cash_register_id_seq;

CREATE TABLE IF NOT EXISTS cash_register (
    id              integer PRIMARY KEY DEFAULT nextval('cash_register_id_seq'),
    operation_date  timestamp WITHOUT TIME ZONE DEFAULT now(),
    account_id      integer NOT NULL,
    transaction_id  integer NOT NULL,
    income          numeric(15, 2) DEFAULT 0,
    expense         numeric(15, 2) DEFAULT 0,
    balance_after   numeric(15, 2)
);

-- Каскадное удаление cash_register-строк вместе с удаляемым документом «Приход/Расход».
ALTER TABLE cash_register
    ADD CONSTRAINT cash_register_account_id_fkey
    FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE RESTRICT;

ALTER TABLE cash_register
    ADD CONSTRAINT cash_register_transaction_id_fkey
    FOREIGN KEY (transaction_id) REFERENCES transactions (id) ON DELETE CASCADE;

-- Индекс для пересчёта баланса регистра по счёту (ORDER BY operation_date, id).
CREATE INDEX IF NOT EXISTS idx_cash_register_account_date
    ON cash_register (account_id, operation_date, id);
