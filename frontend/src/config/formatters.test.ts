// src/config/formatters.test.ts
// Юнит-тесты форматтеров (3.2): даты/период, деньги, телефон, числа, булево.
// Особое внимание — разбор дат БЕЗ сдвига по часовому поясу (строки YYYY-MM-DD).

import { describe, it, expect } from "vitest";
import {
    formatDate,
    formatDateTime,
    formatNumber,
    formatBool,
    formatPrice,
    formatMoney,
    isMoneyFieldName,
    normalizePhone,
    formatPhone,
    formatPhoneInput,
    moneyInputFormatter,
    moneyInputParser,
    formatDateLong,
    formatPeriod,
    formatMonth,
} from "./formatters";

// ru-RU разделяет разряды неразрывным пробелом — приводим к обычному для сравнения.
const sp = (s: string) => s.replace(/\u00a0/g, " ");

describe("formatDate (ДД.ММ.ГГГГ без сдвига по TZ)", () => {
    it("дата-строка разбирается по компонентам", () => {
        expect(formatDate("2026-08-24")).toBe("24.08.2026");
        expect(formatDate("2026-08-24T10:00:00")).toBe("24.08.2026");
        expect(formatDate("2026-01-05")).toBe("05.01.2026");
    });

    it("пустое/некорректное → «—»", () => {
        expect(formatDate(null)).toBe("—");
        expect(formatDate(undefined)).toBe("—");
        expect(formatDate("")).toBe("—");
        expect(formatDate("не-дата")).toBe("—");
    });
});

describe("formatDateTime", () => {
    it("для значения возвращает строку, для пустого — «—»", () => {
        expect(formatDateTime(null)).toBe("—");
        expect(formatDateTime("")).toBe("—");
        expect(formatDateTime("2026-08-24T10:00:00")).not.toBe("—");
    });
});

describe("formatNumber / formatBool / formatPrice", () => {
    it("число с разделителями разрядов", () => {
        expect(sp(formatNumber(1234.5))).toBe("1 234,5");
        expect(formatNumber(null)).toBe("—");
    });

    it("булево «Да»/«Нет»", () => {
        expect(formatBool(true)).toBe("Да");
        expect(formatBool(false)).toBe("Нет");
        expect(formatBool(0)).toBe("Нет");
    });

    it("цена с символом ₸, пусто → «—»", () => {
        expect(sp(formatPrice(1234.5))).toBe("1 234,5 ₸");
        expect(formatPrice(null)).toBe("—");
    });
});

describe("formatMoney (разряды + 2 знака, без ₸)", () => {
    it("ровно 2 знака после запятой", () => {
        expect(sp(formatMoney(1234.5))).toBe("1 234,50");
        expect(sp(formatMoney(0))).toBe("0,00");
        expect(sp(formatMoney("1500"))).toBe("1 500,00");
    });

    it("пустое/некорректное → «—»", () => {
        expect(formatMoney(null)).toBe("—");
        expect(formatMoney("")).toBe("—");
        expect(formatMoney("abc")).toBe("—");
    });

    it("isMoneyFieldName распознаёт денежные поля", () => {
        expect(isMoneyFieldName("amount")).toBe(true);
        expect(isMoneyFieldName("balance_after")).toBe(true);
        expect(isMoneyFieldName("full_name")).toBe(false);
    });
});

describe("телефон", () => {
    it("normalizePhone убирает +7/8 и оставляет 10 цифр", () => {
        expect(normalizePhone("+7(701)123-45-67")).toBe("7011234567");
        expect(normalizePhone("87011234567")).toBe("7011234567");
        expect(normalizePhone("7011234567")).toBe("7011234567");
        expect(normalizePhone("701")).toBe("701");
        expect(normalizePhone("")).toBe("");
    });

    it("formatPhone — маска, пусто → «—»", () => {
        expect(formatPhone("7011234567")).toBe("+7(701)123-45-67");
        expect(formatPhone("")).toBe("—");
        expect(formatPhone(null)).toBe("—");
    });

    it("formatPhoneInput — маска, пусто → пустая строка", () => {
        expect(formatPhoneInput("7011234567")).toBe("+7(701)123-45-67");
        expect(formatPhoneInput("")).toBe("");
    });
});

describe("денежный InputNumber (formatter/parser)", () => {
    it("formatter даёт «1 234,50»", () => {
        expect(sp(moneyInputFormatter(1234.5))).toBe("1 234,50");
        expect(sp(moneyInputFormatter("1,5"))).toBe("1,50");
        expect(moneyInputFormatter("")).toBe("");
    });

    it("parser возвращает числовую строку с точкой", () => {
        expect(moneyInputParser("1 234,50")).toBe("1234.50");
        expect(moneyInputParser(undefined)).toBe("");
    });
});

describe("периоды и месяцы", () => {
    it("formatDateLong — «31 марта 2026»", () => {
        expect(formatDateLong("2026-03-31")).toBe("31 марта 2026");
        expect(formatDateLong(null)).toBe("—");
    });

    it("formatPeriod — «Август, 2026 г.»", () => {
        expect(formatPeriod("2026-08-24")).toBe("Август, 2026 г.");
        expect(formatPeriod("2026-08")).toBe("Август, 2026 г.");
        expect(formatPeriod(null)).toBe("—");
    });

    it("formatMonth по номеру 1–12", () => {
        expect(formatMonth(8)).toBe("Август");
        expect(formatMonth("3")).toBe("Март");
        expect(formatMonth(0)).toBe("—");
        expect(formatMonth(13)).toBe("—");
        expect(formatMonth(null)).toBe("—");
    });
});
