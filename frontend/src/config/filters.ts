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

// --- Справочные фильтры (select по справочнику) ---
// Колонки, которые на формах заполняются из справочников (reference), в списках тоже
// фильтруются выбором из того же справочника (а не свободным текстом «содержит»).
// Значение фильтра — отображаемое значение записи (сервер: eq по display-полю),
// label — расширенная подпись для выпадающего списка.
export interface ReferenceFilterSource {
    resource: string;
    valueOf: (item: any) => string;
    labelOf: (item: any) => string;
}

const _v = (x: any) => (x == null ? "" : String(x));

const REFERENCE_SOURCES: Record<string, ReferenceFilterSource> = {
    owners: {
        resource: "owners",
        valueOf: (i: any) => i.full_name ?? "",
        labelOf: (i: any) => i.full_name ?? `#${i.id}`,
    },
    apartments: {
        resource: "apartments",
        valueOf: (i: any) => _v(i.apartment_number ?? i.apartment?.apartment_number),
        labelOf: (i: any) => {
            const apt = i.apartment_number ?? i.apartment?.apartment_number;
            const owner = i.owner?.full_name;
            return owner ? `№ ${apt} — ${owner}` : `№ ${apt}`;
        },
    },
    accounts: {
        resource: "accounts",
        valueOf: (i: any) => i.account_number ?? "",
        labelOf: (i: any) =>
            `${i.account_number ?? ""}${i.account_name ? ` (${i.account_name})` : ""}`,
    },
    cash_points: {
        resource: "cash_points",
        valueOf: (i: any) => i.name ?? "",
        labelOf: (i: any) => i.name ?? `#${i.id}`,
    },
    analytic_articles: {
        resource: "analytic_articles",
        valueOf: (i: any) => i.name ?? "",
        labelOf: (i: any) =>
            i.name
                ? `${i.name}${i.kind ? ` (${i.kind === "Доход" ? "доход" : "расход"})` : ""}`
                : `#${i.id}`,
    },
    services_type: {
        resource: "services_type",
        valueOf: (i: any) => i.services_type ?? "",
        labelOf: (i: any) => i.services_type ?? `#${i.id}`,
    },
    meters: {
        resource: "meters",
        valueOf: (i: any) => i.serial_number ?? "",
        labelOf: (i: any) => i.serial_number ?? `#${i.id}`,
    },
    tariff_types: {
        resource: "tariff_types",
        valueOf: (i: any) => i.name ?? "",
        labelOf: (i: any) => i.name ?? `#${i.id}`,
    },
};

// Какие display-колонки списков фильтровать как справочник (select), а не «содержит».
export const FILTER_REFERENCE_COLUMNS: Record<string, string> = {
    "cash_point.name": "cash_points",
    "article.name": "analytic_articles",
    "contractor.full_name": "owners",
    "owner.full_name": "owners",
    "apartment.owner.full_name": "owners",
    "account.account_number": "accounts",
    "apartment.apartment_number": "apartments",
    "services_type.services_type": "services_type",
    "meter.serial_number": "meters",
    "tariff_type.name": "tariff_types",
};

export const isReferenceFilter = (columnKey: string): boolean =>
    columnKey in FILTER_REFERENCE_COLUMNS;

export const getReferenceSource = (
    columnKey: string,
): ReferenceFilterSource | undefined => {
    const resource = FILTER_REFERENCE_COLUMNS[columnKey];
    return resource ? REFERENCE_SOURCES[resource] : undefined;
};

const KIND_MAP: Record<string, FilterKind> = {};
for (const k of TEXT_KEYS) KIND_MAP[k] = "text";
for (const k of NUMBER_KEYS) KIND_MAP[k] = "number";
for (const k of DATE_KEYS) KIND_MAP[k] = "date";
for (const k of DATETIME_KEYS) KIND_MAP[k] = "datetime";
for (const k of BOOL_KEYS) KIND_MAP[k] = "bool";
for (const k of Object.keys(FILTER_SELECT_OPTIONS)) KIND_MAP[k] = "select";
for (const k of Object.keys(FILTER_REFERENCE_COLUMNS)) KIND_MAP[k] = "select";

export const getFilterKind = (columnKey: string): FilterKind => KIND_MAP[columnKey] ?? "text";

export const isSelectFilter = (columnKey: string): boolean =>
    KIND_MAP[columnKey] === "select";

export const getSelectOptions = (columnKey: string) => FILTER_SELECT_OPTIONS[columnKey] ?? [];
