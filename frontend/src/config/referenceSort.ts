// src/config/referenceSort.ts
// Порядок по умолчанию для выпадающих списков справочников.
//
// Списки-справочники (ReferenceSelect — поля форм, ReferenceFilterSelect — фильтры)
// грузятся напрямую через authedFetch, без Refine-пагинации, поэтому порядок задаём
// сами: иначе записи идут как их отдаёт БД (по id) и «Квартиры» в формах выглядели
// не по порядку. Сортировка применяется тем же механизмом, что и в списках
// (`backend/sorting.py`, `build_order_clause`); нераспознанные поля безопасно
// игнорируются, поэтому лишний параметр ничего не ломает.

export interface ReferenceSort {
    field: string;
    order: "asc" | "desc";
}

export const REFERENCE_SORT: Record<string, ReferenceSort> = {
    // Квартиры — по номеру (главная «поле Квартиры» в формах).
    apartments: { field: "apartment_number", order: "asc" },
    // Лицевые счета — по номеру (LS-NNNN: совпадает с порядком квартир).
    accounts: { field: "account_number", order: "asc" },
    owners: { field: "full_name", order: "asc" },
    meters: { field: "serial_number", order: "asc" },
    services_type: { field: "services_type", order: "asc" },
    tariff_types: { field: "name", order: "asc" },
    cash_points: { field: "name", order: "asc" },
    analytic_articles: { field: "name", order: "asc" },
};

/**
 * Добавка к query-строке запроса справочника: `&_sort=…&_order=…`
 * (или пустая строка, если порядок для ресурса не задан).
 */
export const referenceSortQuery = (resource: string): string => {
    const sort = REFERENCE_SORT[resource];
    return sort ? `&_sort=${encodeURIComponent(sort.field)}&_order=${sort.order}` : "";
};

/** Тот же порядок, но в виде `sorters` для Refine `useList` (или `undefined`). */
export const referenceSorters = (resource: string): ReferenceSort[] | undefined => {
    const sort = REFERENCE_SORT[resource];
    return sort ? [sort] : undefined;
};
