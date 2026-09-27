// src/pages/CashReport.test.tsx
// RTL-тесты отчёта «По кассе» (3.2): загрузка с периодом, KPI, таблицы «Итоги по типам»/
// «По кассам»/движения, ошибка и PDF. Refine — мок dataProvider; сеть — мок fetch.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { Refine } from "@refinedev/core";

import { CashReport } from "./CashReport";

const sp = (s: string) => s.replace(/\u00a0/g, " ");

const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });

const REPORT = {
    period: { from: "2026-08-01", to: "2026-08-31" },
    totals: { opening: 1000, income: 1234.5, expense: 200, closing: 2034.5 },
    totals_by_kind: {
        cash: { opening: 1000, income: 1234.5, expense: 200, closing: 2034.5 },
        bank: { opening: 0, income: 0, expense: 0, closing: 0 },
    },
    cash_points: [
        {
            cash_point_id: 1,
            cash_point_name: "Касса городка",
            kind: "Касса",
            kind_code: "cash",
            is_active: true,
            opening: 1000,
            income: 1234.5,
            expense: 200,
            closing: 2034.5,
        },
    ],
    movements: [
        {
            operation_date: "2026-08-24",
            document_title: "Приход в кассу №1",
            transaction_id: 11,
            account_number: "LS/0001",
            account_name: "Кв.1",
            article_name: "Поступления от жителей",
            contractor_name: "Иванов Иван",
            income: 1234.5,
            expense: 0,
            amount: 1234.5,
        },
    ],
};

const dataProvider: any = {
    custom: vi.fn(async () => ({ data: { fields: [] } })),
    getList: vi.fn(async () => ({ data: [{ id: 1, name: "Касса городка" }], total: 1 })),
    getOne: vi.fn(async () => ({ data: {} })),
    getMany: vi.fn(async () => ({ data: [] })),
    create: vi.fn(async () => ({ data: {} })),
    update: vi.fn(async () => ({ data: {} })),
    deleteOne: vi.fn(async () => ({ data: {} })),
    getApiUrl: () => "http://localhost:8000/api",
};

const renderReport = () =>
    render(
        <Refine dataProvider={dataProvider}>
            <CashReport />
        </Refine>,
    );

beforeEach(() => {
    vi.stubGlobal(
        "fetch",
        vi.fn(async (url: RequestInfo | URL) => {
            const u = String(url);
            if (u.includes("/reports/cash_register/pdf"))
                return new Response(new Blob(["pdf"]), {
                    status: 200,
                    headers: { "Content-Type": "application/pdf" },
                });
            return json(REPORT);
        }),
    );
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("CashReport", () => {
    it("загружает отчёт за период и показывает KPI и таблицы", async () => {
        renderReport();
        // Строка кассы появилась после загрузки.
        expect(await screen.findByText("Касса городка")).toBeTruthy();

        // Запрос сформирован с границами периода (по умолчанию — текущий месяц).
        const url = String((fetch as any).mock.calls[0][0]);
        expect(url).toContain("/reports/cash_register?");
        expect(url).toContain("from_date=");
        expect(url).toContain("to_date=");

        // KPI-заголовки.
        for (const title of ["Остаток на начало", "Приход", "Расход", "Остаток на конец"]) {
            expect(screen.getAllByText(title).length).toBeGreaterThan(0);
        }
        // Раздельные итоги по типу (2.15).
        expect(screen.getByText("Наличные (касса)")).toBeTruthy();
        expect(screen.getByText("Безналичные (счёт)")).toBeTruthy();
        expect(screen.getAllByText("Касса").length).toBeGreaterThan(0);
    });

    it("в движениях — документ, дата DD.MM.YYYY и сумма в денежном формате", async () => {
        renderReport();
        const doc = await screen.findByText("Приход в кассу №1");
        const row = doc.closest("tr") as HTMLElement;
        expect(row).not.toBeNull();
        expect(within(row).getByText(/24\.08\.2026/u)).toBeTruthy();
        const moneyCell = Array.from(row.querySelectorAll("td")).find((c) =>
            /1\s?234,50/u.test(sp(c.textContent ?? "")),
        );
        expect(moneyCell).toBeDefined();
    });

    it("ошибка загрузки показывается в Alert", async () => {
        vi.stubGlobal(
            "fetch",
            vi.fn(async () => json({ detail: "Нет доступа к отчёту" }, 403)),
        );
        renderReport();
        expect(await screen.findByText("Нет доступа к отчёту")).toBeTruthy();
    });

    it("кнопка PDF запрашивает /reports/cash_register/pdf", async () => {
        const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
        (URL as any).createObjectURL = vi.fn(() => "blob:test");
        (URL as any).revokeObjectURL = vi.fn();
        try {
            renderReport();
            await screen.findByText("Касса городка");
            const pdfBtn = screen.getByRole("button", { name: "PDF" });
            pdfBtn.click();
            const pdfCall = (fetch as any).mock.calls.find((c: any[]) =>
                String(c[0]).includes("/reports/cash_register/pdf"),
            );
            expect(pdfCall).toBeTruthy();
        } finally {
            anchorClick.mockRestore();
        }
    });
});
