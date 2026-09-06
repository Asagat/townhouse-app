// src/config/filters.ts
// Конфигурация общего механизма фильтрации списков (роадмап Б10).
//
// Для каждой колонки определяется «вид» элемента управления фильтром:
//   text     — строка «содержит» (сервер: <field>_like);
//   number   — диапазон «от/до» (<field>_gte / <field>_lte);
//   date     — период по датам (поле только с датой);
//   datetime — период по датам (поле с датой и временем; «по» включает весь день);
//   bool     — выбор Да/Нет (<field>=true|false);
//   select   — выбор из заранее известных значений (<field>=<value>).
//
// Поля, которых нет в карте, считаются text-фильтром «содержит» (сервер молча
// пропускает неразрешимые колонки).

export type FilterKind = "text" | "number" | "date" | "datetime" | "bool" | "select";

const TEXT_KEYS: string[] = [
    "full_name",
    "address",
    "account_name",
    "name",
    "title",
    "notes",
    "comment",
    "phone",
    "serial_number",
    "services_type",
    "owner_name",
    "document_title",
    "unit",
    "status",
    "kind",
    "created_by_name",
    "owner.full_name",
    "owner.phone",
    "apartment.owner.full_name",
    "account.account_number",
    "cash_point.name",
    "article.name",
    "contractor.full_name",
    "meter.serial_number",
    "document.title",
    "tariff_type.name",
    "services_type.services_type",
];

const NUMBER_KEYS: string[] = [
    "id",
    "doc_no",
    "square",
    "amount",
    "consumption",
    "past_reading_value",
    "current_reading_value",
    "income",
    "expense",
    "balance_after",
    "price",
    "readings_count",
    "accruals_count",
    "total_amount",
    "debt",
    "overpayment",
    "payable_amount",
    "items_count",
    "total_allocated",
    "priority",
    "reading",
    "period_month",
    "period_year",
    "apartment_number",
    "apartment.apartment_number",
];

const DATE_KEYS: string[] = [
    "reading_date",
    "accrual_date",
    "valid_from",
    "installed_at",
    "writeoff_date",
];

const DATETIME_KEYS: string[] = [
    "transaction_date",
    "created_at",
    "operation_date",
    "issued_at",
];

const BOOL_KEYS: string[] = ["is_active", "is_oneoff"];

// Значения выбора для enum-колонок. value — как ХРАНИТСЯ в БД (для нативных
// PG-enum это имя члена: in_cash/out_cash/…), label — как показывается в UI
// (сериализатор отдаёт русское значение enum: «Приход в кассу» и т.п.).
export const FILTER_SELECT_OPTIONS: Record<string, { value: string; label: string }[]> = {
    transaction_type: [
        { value: "in_cash", label: "Приход в кассу" },
        { value: "out_cash", label: "Расход из кассы" },
        { value: "in_bank", label: "Приход в банк" },
        { value: "out_bank", label: "Расход из банка" },
    ],
    doc_kind: [
        { value: "monthly", label: "Регулярные" },
        { value: "oneoff", label: "Разовые/персональные" },
    ],
};

const KIND_MAP: Record<string, FilterKind> = {};
for (const k of TEXT_KEYS) KIND_MAP[k] = "text";
for (const k of NUMBER_KEYS) KIND_MAP[k] = "number";
for (const k of DATE_KEYS) KIND_MAP[k] = "date";
for (const k of DATETIME_KEYS) KIND_MAP[k] = "datetime";
for (const k of BOOL_KEYS) KIND_MAP[k] = "bool";
for (const k of Object.keys(FILTER_SELECT_OPTIONS)) KIND_MAP[k] = "select";

export const getFilterKind = (columnKey: string): FilterKind => KIND_MAP[columnKey] ?? "text";

export const isSelectFilter = (columnKey: string): boolean =>
    KIND_MAP[columnKey] === "select";

export const getSelectOptions = (columnKey: string) => FILTER_SELECT_OPTIONS[columnKey] ?? [];
