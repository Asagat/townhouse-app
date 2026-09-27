// src/config/export.test.ts
// Юнит-тесты построения параметров экспорта списков (роадмап 2.2).

import { describe, it, expect } from "vitest";
import { buildExportParams } from "./export";

describe("buildExportParams", () => {
    it("переводит операторы фильтров в суффиксы серверного фильтра", () => {
        const params = buildExportParams(
            [
                { field: "full_name", operator: "contains", value: "Иван" },
                { field: "amount", operator: "gte", value: 100 },
                { field: "amount", operator: "lte", value: 500 },
                { field: "is_active", operator: "eq", value: true },
            ],
            undefined,
            [{ key: "full_name", label: "ФИО" }],
            "csv",
        );
        expect(params.get("full_name_like")).toBe("Иван");
        expect(params.get("amount_gte")).toBe("100");
        expect(params.get("amount_lte")).toBe("500");
        expect(params.get("is_active")).toBe("true");
        expect(params.get("_export")).toBe("csv");
    });

    it("пропускает пустые значения и неподдерживаемые операторы", () => {
        const params = buildExportParams(
            [
                { field: "title", operator: "contains", value: "" },
                { field: "title", operator: "startswith", value: "x" },
            ],
            undefined,
            [],
            "xlsx",
        );
        expect(params.toString()).not.toContain("title");
        expect(params.get("_export")).toBe("xlsx");
    });

    it("передаёт сортировку и колонки", () => {
        const params = buildExportParams(
            [],
            [{ field: "operation_date", order: "asc" }],
            [
                { key: "operation_date", label: "Дата операции" },
                { key: "balance_after", label: "Остаток по кассе" },
            ],
            "xlsx",
        );
        expect(params.get("_sort")).toBe("operation_date");
        expect(params.get("_order")).toBe("asc");
        expect(JSON.parse(params.get("_columns") as string)).toEqual([
            { key: "operation_date", label: "Дата операции" },
            { key: "balance_after", label: "Остаток по кассе" },
        ]);
    });
});
