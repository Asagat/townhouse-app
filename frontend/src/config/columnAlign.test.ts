// src/config/columnAlign.test.ts
// Юнит-тесты правил форматирования колонок списков (GenericList):
//   - денежные значения -> справа; текстовые -> слева; остальные -> по центру;
//   - заголовок любой колонки -> по центру.

import { describe, it, expect } from "vitest";
import {
    cellAlign,
    headerAlign,
    cellAlignStyle,
    headerAlignStyle,
    type CellAlign,
} from "./columnAlign";

describe("cellAlign — правила выравнивания значения, названия, знака", () => {
    it("денежные поля выравниваются вправо", () => {
        const moneyKeys = [
            "amount",
            "total_amount",
            "price",
            "income",
            "expense",
            "balance_after",
            "debt",
            "overpayment",
            "payable_amount",
            "total_allocated",
        ];
        for (const key of moneyKeys) {
            expect([cellAlign(key), key]).toEqual(["right", key]);
        }
    });

    it("текстовые/описательные поля выравниваются влево", () => {
        const textKeys = [
            "full_name",
            "address",
            "notes",
            "comment",
            "article.name",
            "contractor.full_name",
            "owner.full_name",
            "cash_point.name",
            "document.title",
            "created_by_name",
        ];
        for (const key of textKeys) {
            expect([cellAlign(key), key]).toEqual(["left", key]);
        }
    });

    it("прочие поля (id, счётчики, даты, bool) — по центру", () => {
        const centerKeys = [
            "id",
            "readings_count",
            "accruals_count",
            "square",
            "transaction_date",
            "created_at",
            "reading_date",
            "is_active",
            "item.description",
        ];
        for (const key of centerKeys) {
            expect([cellAlign(key), key]).toEqual(["center", key]);
        }
    });

    it("все возвращаемые значения — корректный набор выравниваний", () => {
        const values = new Set<CellAlign>(["left", "center", "right"]);
        expect(values.has(cellAlign("amount"))).toBe(true);
        expect(values.has(cellAlign("full_name"))).toBe(true);
        expect(values.has(cellAlign("id"))).toBe(true);
    });

    it("значение вправо и текстовое влево отличаются от центра", () => {
        expect(cellAlign("amount")).not.toBe(cellAlign("id"));
        expect(cellAlign("full_name")).not.toBe(cellAlign("id"));
    });
});

describe("headerAlign — заголовки всегда по центру", () => {
    it("возвращает center", () => {
        expect(headerAlign()).toBe("center");
    });
});

describe("style-хелперы соответствуют правилам", () => {
    it("cellAlignStyle отображает правило в textAlign", () => {
        expect(cellAlignStyle("amount").textAlign).toBe("right");
        expect(cellAlignStyle("full_name").textAlign).toBe("left");
        expect(cellAlignStyle("id").textAlign).toBe("center");
    });

    it("headerAlignStyle центрирует", () => {
        expect(headerAlignStyle().textAlign).toBe("center");
    });
});
