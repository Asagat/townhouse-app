// src/config/referenceDrill.ts
// «Проваливание» по ссылочным полям (роадмап 2.21): карта «колонка списка → ссылка»
// и разрешение id связанной записи из строки/формы.
//
// В строках списков сериализаторы уже отдают вложенные объекты справочников с id
// (account{id}, owner{id}, cash_point{id}, services_type{id} и т.п.). Здесь описано,
// какая колонка куда ведёт и где в строке лежит id целевой записи. Колонки без id
// (например денормализованные `apartment_number`/`owner_name` квитанций или текстовый
// `document_title` регистров) в карту не входят — для них «проваливание» недоступно.

export interface ReferenceTarget {
    /** Ресурс-цель (generic CRUD, `/api/{resource}/{id}`). */
    resource: string;
    /** Путь к id связанной записи в строке/объекте (например `owner.id`). */
    idPath: string;
}

// Карта по ключу колонки (ключи общие для списков — см. `config/columns.ts`).
export const COLUMN_REFERENCE: Record<string, ReferenceTarget> = {
    "owner.full_name": { resource: "owners", idPath: "owner.id" },
    "owner.phone": { resource: "owners", idPath: "owner.id" },
    "apartment.owner.full_name": { resource: "owners", idPath: "apartment.owner.id" },
    "apartment.apartment_number": { resource: "apartments", idPath: "apartment.id" },
    "account.account_number": { resource: "accounts", idPath: "account.id" },
    "services_type.services_type": { resource: "services_type", idPath: "services_type.id" },
    "tariff_type.name": { resource: "tariff_types", idPath: "tariff_type.id" },
    "cash_point.name": { resource: "cash_points", idPath: "cash_point.id" },
    "article.name": { resource: "analytic_articles", idPath: "article.id" },
    "contractor.full_name": { resource: "owners", idPath: "contractor.id" },
    "meter.serial_number": { resource: "meters", idPath: "meter.id" },
    "document.title": { resource: "meter_reading_documents", idPath: "document.id" },
    "tariff": { resource: "tariffs", idPath: "tariff.id" },
};

// Человекочитаемые подписи ресурсов-целей (для заголовка окна). Для остальных —
// подпись берётся из меню, иначе сам ключ ресурса.
export const RESOURCE_LABELS: Record<string, string> = {
    owners: "Контрагент",
    apartments: "Квартира",
    accounts: "Лицевой счёт",
    services_type: "Вид услуги",
    tariff_types: "Тип тарифа",
    tariffs: "Тариф",
    cash_points: "Касса/Счёт",
    analytic_articles: "Статья доходов и расходов",
    meters: "Счётчик",
    meter_reading_documents: "Документ показаний",
};

/** Ссылка для колонки списка (или null, если проваливание не поддерживается). */
export const referenceForColumn = (columnKey: string): ReferenceTarget | null =>
    COLUMN_REFERENCE[columnKey] ?? null;

/** Значение по пути `a.b.c` во вложенном объекте строки. */
export const resolveIdByPath = (record: any, path: string): number | null => {
    let current: any = record;
    for (const part of path.split(".")) {
        if (current == null || typeof current !== "object") return null;
        current = current[part];
    }
    // id допустим числовой; null/undefined/пусто — нет ссылки.
    if (current === null || current === undefined || current === "") return null;
    const num = Number(current);
    return Number.isFinite(num) ? num : null;
};

/** Ссылка для колонки списка с готовым id из конкретной строки. */
export const referenceFromRow = (
    columnKey: string,
    record: any,
): { resource: string; id: number } | null => {
    const target = referenceForColumn(columnKey);
    if (!target) return null;
    const id = resolveIdByPath(record, target.idPath);
    return id === null ? null : { resource: target.resource, id };
};
