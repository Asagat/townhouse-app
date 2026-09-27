// src/config/filters.test.ts
// Юнит-тесты конфигурации фильтров списков (3.2): вид контрола по колонке,
// варианты select, справочные фильтры и фильтры по умолчанию.

import { describe, it, expect } from "vitest";
import {
    getFilterKind,
    isSelectFilter,
    getSelectOptions,
    isResourceSelectFilter,
    getResourceSelectOptions,
    isResourceDynamicSelect,
    isResourceReferenceFilter,
    getReferenceSource,
    getDefaultResourceFilters,
} from "./filters";

describe("getFilterKind — вид контрола по колонке", () => {
    it("текст/число/дата/дата-время/булево/select", () => {
        expect(getFilterKind("full_name")).toBe("text");
        expect(getFilterKind("amount")).toBe("number");
        expect(getFilterKind("accrual_date")).toBe("date");
        expect(getFilterKind("transaction_date")).toBe("datetime");
        expect(getFilterKind("is_active")).toBe("bool");
        expect(getFilterKind("transaction_type")).toBe("select");
        expect(getFilterKind("owner.full_name")).toBe("select"); // справочная колонка
    });

    it("неизвестная колонка → текст", () => {
        expect(getFilterKind("no_such_column")).toBe("text");
    });

    it("isSelectFilter / getSelectOptions для enum-поля", () => {
        expect(isSelectFilter("transaction_type")).toBe(true);
        const opts = getSelectOptions("transaction_type");
        expect(opts.map((o) => o.value)).toContain("in_cash");
        expect(opts.length).toBeGreaterThan(0);
    });
});

describe("ресурсо-зависимые select-фильтры", () => {
    it("«Тип» кассы/счёта — только для cash_points", () => {
        expect(isResourceSelectFilter("cash_points", "kind")).toBe(true);
        expect(getResourceSelectOptions("cash_points", "kind").map((o) => o.value)).toEqual([
            "cash",
            "bank",
        ]);
    });

    it("«Год» квитанций — динамический select с сервера", () => {
        expect(isResourceDynamicSelect("receipt_documents", "period_year")).toBe(true);
        expect(isResourceDynamicSelect("owners", "period_year")).toBe(false);
    });
});

describe("справочные фильтры", () => {
    it("колонки-справочники фильтруются select'ом по справочнику", () => {
        expect(isResourceReferenceFilter("payments", "owner.full_name")).toBe(true);
        // Ресурсо-зависимая: «Лицевой счёт» квитанций — из справочника счетов.
        expect(isResourceReferenceFilter("receipt_documents", "account_number")).toBe(true);
        expect(isResourceReferenceFilter("payments", "amount")).toBe(false);
    });

    it("getReferenceSource отдаёт valueOf/labelOf", () => {
        const src = getReferenceSource("receipt_documents", "account_number");
        expect(src?.resource).toBe("accounts");
        expect(src?.valueOf({ account_number: "LS/0001" })).toBe("LS/0001");

        const owners = getReferenceSource("payments", "owner.full_name");
        expect(owners?.valueOf({ full_name: "Иванов Иван" })).toBe("Иванов Иван");
    });
});

describe("фильтры по умолчанию", () => {
    it("«Тарифы» по умолчанию — только действующие", () => {
        const def = getDefaultResourceFilters("tariffs");
        expect(def?.applied).toEqual([{ field: "status", operator: "eq", value: "active" }]);
    });

    it("для прочих ресурсов — нет", () => {
        expect(getDefaultResourceFilters("owners")).toBeUndefined();
    });
});
