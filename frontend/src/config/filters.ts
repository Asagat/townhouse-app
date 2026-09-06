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

export type SelectOption = { value: string | number; label: string };

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
    // «Автор» в журналах документов: список зарегистрированных пользователей
    // (эндпоинт /creators; жители не создают документы). Значение — как показывается
    // в колонке «Автор» (ФИО, а если не заполнено — логин).
    creators: {
        resource: "creators",
        valueOf: (i: any) => (i.full_name ?? i.username ?? "").toString(),
        labelOf: (i: any) => i.full_name ?? i.username ?? `#${i.id}`,
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
    "created_by_name": "creators",
};

// Ресурсо-зависимые справочные колонки: колонка с одним и тем же именем в разных
// списках фильтруется по-разному. Например «Лицевой счёт» (account_number) в списке
// квитанций — выбором из справочника лицевых счетов, а не текстом «содержит».
const RESOURCE_REFERENCE_COLUMNS: Record<string, Record<string, string>> = {
    receipt_documents: { account_number: "accounts" },
};

export const isResourceReferenceFilter = (resourceName: string, columnKey: string): boolean =>
    columnKey in FILTER_REFERENCE_COLUMNS || !!RESOURCE_REFERENCE_COLUMNS[resourceName]?.[columnKey];

export const getReferenceSource = (
    resourceName: string,
    columnKey: string,
): ReferenceFilterSource | undefined => {
    const resource =
        RESOURCE_REFERENCE_COLUMNS[resourceName]?.[columnKey] ?? FILTER_REFERENCE_COLUMNS[columnKey];
    return resource ? REFERENCE_SOURCES[resource] : undefined;
};

// --- Ресурсо-зависимые select-фильтры ---
// Отдельные поля одного имени в разных списках фильтруются по-разному. Например
// колонка «Статус»: у тарифов это «Действующий/Архивный», а не текстовый «содержит».

/** Варианты «Месяц» списка квитанций (значение — номер месяца). */
const MONTH_SELECT_OPTIONS: SelectOption[] = [
    { value: 1, label: "Январь" },
    { value: 2, label: "Февраль" },
    { value: 3, label: "Март" },
    { value: 4, label: "Апрель" },
    { value: 5, label: "Май" },
    { value: 6, label: "Июнь" },
    { value: 7, label: "Июль" },
    { value: 8, label: "Август" },
    { value: 9, label: "Сентябрь" },
    { value: 10, label: "Октябрь" },
    { value: 11, label: "Ноябрь" },
    { value: 12, label: "Декабрь" },
];

const RESOURCE_SELECT_OPTIONS: Record<string, Record<string, SelectOption[]>> = {
    tariffs: {
        status: [
            { value: "active", label: "Действующий" },
            { value: "archived", label: "Архивный" },
        ],
    },
    receipt_documents: {
        period_month: MONTH_SELECT_OPTIONS,
    },
};

export const isResourceSelectFilter = (resourceName: string, columnKey: string): boolean =>
    !!RESOURCE_SELECT_OPTIONS[resourceName]?.[columnKey];

export const getResourceSelectOptions = (
    resourceName: string,
    columnKey: string,
): SelectOption[] => RESOURCE_SELECT_OPTIONS[resourceName]?.[columnKey] ?? [];

// --- Select-фильтры, значения которых подтягиваются с сервера (диапазон данных) ---
// «Год» в списке квитанций: от самого раннего года записей (квитанции/начисления —
// входящие остатки) до текущего года; значения берутся из /receipt_documents/periods.
const RESOURCE_DYNAMIC_SELECT_FIELDS: Record<string, string[]> = {
    receipt_documents: ["period_year"],
};

export const isResourceDynamicSelect = (resourceName: string, columnKey: string): boolean =>
    !!RESOURCE_DYNAMIC_SELECT_FIELDS[resourceName]?.includes(columnKey);

// --- Фильтры по умолчанию для списка ---
// Применяются при открытии раздела (например «Тарифы» по умолчанию показывают только
// Действующие). `draft` — значения для панели фильтров, `applied` — CrudFilter-запросы.
export interface DefaultResourceFilters {
    draft: Record<string, any>;
    applied: Array<{ field: string; operator: "eq"; value: any }>;
}

const DEFAULT_RESOURCE_FILTERS: Record<string, DefaultResourceFilters> = {
    tariffs: {
        draft: { status: { sel: "active" } },
        applied: [{ field: "status", operator: "eq", value: "active" }],
    },
};

export const getDefaultResourceFilters = (
    resourceName: string,
): DefaultResourceFilters | undefined => DEFAULT_RESOURCE_FILTERS[resourceName];

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
