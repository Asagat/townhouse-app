// src/pages/DebtorsReport.test.tsx
// Отчёт по должникам: в таблице НЕ должно быть колонок «Начислено»/«Оплачено»
// (убраны по запросу владельца) — остаются квартира, л/с, собственник, переплата, долг.
// Сеть подменяется мок-функцией fetch (мок-ответ /reports/debtors).

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { DebtorsReport } from "./DebtorsReport";

const okJson = (body: unknown) =>
    Promise.resolve(
        new Response(JSON.stringify(body), {
            status: 200,
            headers: { "Content-Type": "application/json" },
        }),
    );

const DEBTORS = {
    rows: [
        {
            account_id: 3,
            account_number: "LS-0003",
            account_name: "Кв.3",
            apartment_number: 3,
            address: "ул. Тестовая, 3",
            owner_name: "Иванов Иван",
            accrued: 160765,
            paid: 0,
            debt: 160765,
            overpayment: 0,
        },
    ],
    total_debt: 160765,
    count: 1,
};

describe("DebtorsReport", () => {
    beforeEach(() => {
        vi.stubGlobal("fetch", vi.fn(() => okJson(DEBTORS)));
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("без колонок «Начислено» и «Оплачено», с «Долгом» и данными строки", async () => {
        render(<DebtorsReport />);

        // Ждём загрузку строки из мок-ответа.
        expect(await screen.findByText("LS-0003")).toBeTruthy();

        const headers = screen
            .getAllByRole("columnheader")
            .map((h) => (h.textContent ?? "").replace(/\u00a0/g, " "));
        expect(headers.some((h) => h.includes("Начислено"))).toBe(false);
        expect(headers.some((h) => h.includes("Оплачено"))).toBe(false);
        expect(headers.some((h) => h.includes("Долг"))).toBe(true);

        // Долг строки показан в денежном формате (пробелы-разделители, 2 знака).
        expect(screen.getByText(/160\s?765,00/u)).toBeTruthy();
    });
});
