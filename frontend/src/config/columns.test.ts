// src/config/columns.test.ts
// Юнит-тесты конфигурации колонок списков и порядка полей форм (3.2).

import { describe, it, expect } from "vitest";
import {
    defaultColumns,
    getColumnsForResource,
    hasColumnsConfig,
    sortFieldsForForm,
    hasFieldOrder,
    getFieldOrder,
} from "./columns";
import type { FieldMeta } from "../types";

const field = (name: string): FieldMeta => ({
    name,
    label: name,
    type: "string",
    required: false,
});

describe("getColumnsForResource", () => {
    it("известный ресурс — своя конфигурация колонок", () => {
        expect(getColumnsForResource("cash_points").map((c) => c.key)).toEqual([
            "name",
            "kind",
            "is_active",
        ]);
    });

    it("неизвестный ресурс — колонки по умолчанию", () => {
        expect(getColumnsForResource("no_such")).toBe(defaultColumns);
        expect(hasColumnsConfig("no_such")).toBe(false);
        expect(hasColumnsConfig("owners")).toBe(true);
    });
});

describe("sortFieldsForForm — порядок полей формы", () => {
    it("сначала настроенные поля (в заданном порядке), затем остальные без потерь", () => {
        const fields = [field("owner_id"), field("address"), field("apartment_number")];
        const out = sortFieldsForForm(fields, "apartments").map((f) => f.name);
        // apartments: ['apartment_number', 'address', 'square', 'owner_id']
        expect(out).toEqual(["apartment_number", "address", "owner_id"]);
    });

    it("для ресурса без настройки порядок сохраняется как есть", () => {
        const fields = [field("b"), field("a")];
        expect(sortFieldsForForm(fields, "no_such").map((f) => f.name)).toEqual(["b", "a"]);
    });

    it("getFieldOrder/hasFieldOrder", () => {
        expect(hasFieldOrder("apartments")).toBe(true);
        expect(getFieldOrder("apartments")?.[0]).toBe("apartment_number");
        expect(hasFieldOrder("no_such")).toBe(false);
        expect(getFieldOrder("no_such")).toBeUndefined();
    });
});
