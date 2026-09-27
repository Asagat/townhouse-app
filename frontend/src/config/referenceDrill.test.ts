// src/config/referenceDrill.test.ts
// Юнит-тесты карты «проваливания» по ссылкам (2.21).

import { describe, it, expect } from "vitest";
import {
    referenceForColumn,
    resolveIdByPath,
    referenceFromRow,
} from "./referenceDrill";

describe("referenceForColumn", () => {
    it("известные ссылочные колонки → ресурс+путь к id", () => {
        expect(referenceForColumn("owner.full_name")).toEqual({
            resource: "owners",
            idPath: "owner.id",
        });
        expect(referenceForColumn("account.account_number")).toEqual({
            resource: "accounts",
            idPath: "account.id",
        });
    });

    it("скалярные/текстовые колонки → null (проваливание недоступно)", () => {
        expect(referenceForColumn("doc_no")).toBeNull();
        expect(referenceForColumn("apartment_number")).toBeNull(); // квитанции: денорм. текст
        expect(referenceForColumn("document_title")).toBeNull();
    });
});

describe("resolveIdByPath", () => {
    it("достаёт id по вложенному пути", () => {
        const row = { owner: { id: 42, full_name: "Иванов" } };
        expect(resolveIdByPath(row, "owner.id")).toBe(42);
    });

    it("глубокий путь и отсутствие значения", () => {
        const row = { apartment: { owner: { id: 7 } } };
        expect(resolveIdByPath(row, "apartment.owner.id")).toBe(7);
        expect(resolveIdByPath(row, "apartment.missing.id")).toBeNull();
        expect(resolveIdByPath(row, "owner.id")).toBeNull();
    });

    it("пустая строка/нечисло → null", () => {
        expect(resolveIdByPath({ owner: { id: "" } }, "owner.id")).toBeNull();
        expect(resolveIdByPath({ owner: { id: "abc" } }, "owner.id")).toBeNull();
    });
});

describe("referenceFromRow", () => {
    it("отдаёт ресурс и id для ссылочной колонки строки", () => {
        const row = { cash_point: { id: 2, name: "Касса" } };
        expect(referenceFromRow("cash_point.name", row)).toEqual({
            resource: "cash_points",
            id: 2,
        });
    });

    it("колонка без id или без карты → null", () => {
        expect(referenceFromRow("owner.full_name", { owner: { full_name: "X" } })).toBeNull();
        expect(referenceFromRow("doc_no", { id: 1 })).toBeNull();
    });
});
