// src/config/referenceSort.test.ts
// Юнит-тесты порядка справочников (3.2): квартиры/ЛС — по номеру, прочие — по имени.

import { describe, it, expect } from "vitest";
import { REFERENCE_SORT, referenceSortQuery, referenceSorters } from "./referenceSort";

describe("referenceSort", () => {
    it("query-строка для справочника с заданным порядком", () => {
        expect(referenceSortQuery("apartments")).toBe("&_sort=apartment_number&_order=asc");
        expect(referenceSortQuery("accounts")).toBe("&_sort=account_number&_order=asc");
    });

    it("для неизвестного ресурса — пустая строка / undefined", () => {
        expect(referenceSortQuery("nope")).toBe("");
        expect(referenceSorters("nope")).toBeUndefined();
    });

    it("sorters для Refine useList", () => {
        expect(referenceSorters("owners")).toEqual([{ field: "full_name", order: "asc" }]);
    });

    it("все записи карты используют порядок по возрастанию", () => {
        for (const sort of Object.values(REFERENCE_SORT)) {
            expect(sort.order).toBe("asc");
            expect(sort.field).toBeTruthy();
        }
    });
});
