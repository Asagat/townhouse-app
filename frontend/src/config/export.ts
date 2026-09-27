// src/config/export.ts
// Построение параметров экспорта списка в Excel/CSV (роадмап 2.2).
//
// Экспорт использует тот же эндпоинт, что и список (GET /api/{resource}), поэтому
// параметры фильтрации/сортировки переводятся в тот же формат, что шлёт dataProvider
// (@refinedev/simple-rest): <field>[_like|_ne|_gte|_lte] + _sort/_order. Дополнительно
// передаются _columns (колонки таблицы: ключ + подпись) и _export (формат).
//
// Логика вынесена из компонента, чтобы её можно было покрыть юнит-тестами.

import type { CrudFilter, CrudSort } from "@refinedev/core";

// Соответствие операторов Refine суффиксам серверного фильтра (см. backend/filtering.py).
export const EXPORT_OPERATOR_SUFFIX: Record<string, string> = {
    eq: "",
    contains: "_like",
    ne: "_ne",
    gte: "_gte",
    lte: "_lte",
};

export type ExportColumn = { key: string; label: string };

/**
 * Собирает query-параметры выгрузки из применённых фильтров/сортировки и колонок.
 *
 * - учитываются только поддерживаемые сервером операторы (прочие игнорируются);
 * - пустые значения фильтров пропускаются;
 * - сортировка берётся из первого сортировщика списка;
 * - колонки передаются как JSON `[{key,label}]`.
 */
export function buildExportParams(
    filters: CrudFilter[] | undefined,
    sorters: CrudSort[] | undefined,
    columns: ExportColumn[],
    fmt: "xlsx" | "csv",
): URLSearchParams {
    const params = new URLSearchParams();

    for (const f of filters ?? []) {
        if (!f || typeof f !== "object" || !("field" in f) || !("value" in f)) continue;
        const op = String((f as { operator?: string }).operator ?? "eq");
        if (!(op in EXPORT_OPERATOR_SUFFIX)) continue;
        const value = (f as { value?: unknown }).value;
        if (value === undefined || value === null || value === "") continue;
        params.append(
            `${(f as unknown as { field: string }).field}${EXPORT_OPERATOR_SUFFIX[op]}`,
            String(value),
        );
    }

    const sorter = sorters?.[0];
    if (sorter?.field) {
        params.append("_sort", sorter.field);
        params.append("_order", sorter.order === "asc" ? "asc" : "desc");
    }

    params.append("_columns", JSON.stringify(columns.map((c) => ({ key: c.key, label: c.label }))));
    params.append("_export", fmt);
    return params;
}
