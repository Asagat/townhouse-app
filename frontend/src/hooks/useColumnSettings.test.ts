// src/hooks/useColumnSettings.test.ts
// Совместимость настроек колонок: ID раньше был захардкожен и не попадал в сохранённый
// порядок — у старых настроек его надо вернуть В НАЧАЛО, а не в конец.

import { describe, it, expect } from "vitest";
import { withLeadingColumn, type StoredColumnSettings } from "./useColumnSettings";

const settings = (order: string[]): StoredColumnSettings => ({
    order,
    hidden: ["notes"],
    widths: { amount: 120 },
});

describe("withLeadingColumn", () => {
    it("null остаётся null", () => {
        expect(withLeadingColumn(null, "id")).toBeNull();
    });

    it("пустой порядок не трогаем (новые колонки и так пойдут в исходном порядке)", () => {
        const s = settings([]);
        expect(withLeadingColumn(s, "id")).toBe(s);
    });

    it("если ключ уже есть в порядке — объект не меняется", () => {
        const s = settings(["id", "amount"]);
        expect(withLeadingColumn(s, "id")).toBe(s);
    });

    it("старые настройки без ID — ID добавляется первым, остальное сохраняется", () => {
        const s = settings(["amount", "notes"]);
        const result = withLeadingColumn(s, "id");
        expect(result?.order).toEqual(["id", "amount", "notes"]);
        // Видимость и ширины не теряются.
        expect(result?.hidden).toEqual(["notes"]);
        expect(result?.widths).toEqual({ amount: 120 });
    });
});
