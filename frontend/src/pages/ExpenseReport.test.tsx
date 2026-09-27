// src/pages/ExpenseReport.test.tsx
// RTL-тесты отчёта «По расходам» (3.2): KPI, «По статьям», движения, ошибка, PDF.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { Refine } from "@refinedev/core";

import { ExpenseReport } from "./ExpenseReport";

const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });

const REPORT = {
    period: { from: "2026-08-01", to: "2026-08-31" },
    total_expense: 5200,
    count: 2,
    articles: [
        { name: "Электроэнергия", expense: 5000 },
        { name: "Водоснабжение", expense: 200 },
    ],
    movements: [
        {
            operation_date: "2026-08-10",
            document_title: "Расход из кассы №5",
            transaction_id: 5,
            account_number: null,
            article_name: "Электроэнергия",
            contractor_name: "ТОО Ромашка",
            amount: 5000,
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
            <ExpenseReport />
        </Refine>,
    );

beforeEach(() => {
    vi.stubGlobal(
        "fetch",
        vi.fn(async (url: RequestInfo | URL) => {
            const u = String(url);
            if (u.includes("/reports/expenses/pdf"))
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

describe("ExpenseReport", () => {
    it("загружает отчёт и показывает KPI и статью расходов", async () => {
        renderReport();
        expect((await screen.findAllByText("Электроэнергия")).length).toBeGreaterThan(0);

        const url = String((fetch as any).mock.calls[0][0]);
        expect(url).toContain("/reports/expenses?");
        expect(url).toContain("from_date=");
        expect(url).toContain("to_date=");

        expect(screen.getByText("Расходы за период")).toBeTruthy();
        expect(screen.getByText("Количество операций")).toBeTruthy();

        // Статья и её сумма в денежном формате.
        const articleCell = screen.getAllByText("Электроэнергия")[0].closest("tr") as HTMLElement;
        expect(within(articleCell).getByText(/5\s?000,00/u)).toBeTruthy();
    });

    it("движения: документ, дата DD.MM.YYYY, сумма; пустой л/с — «—»", async () => {
        renderReport();
        const doc = await screen.findByText("Расход из кассы №5");
        const row = doc.closest("tr") as HTMLElement;
        expect(within(row).getByText(/10\.08\.2026/u)).toBeTruthy();
        expect(within(row).getByText(/5\s?000,00/u)).toBeTruthy();
        expect(within(row).getAllByText("—").length).toBeGreaterThan(0); // account_number = null
    });

    it("ошибка загрузки показывается в Alert", async () => {
        vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "Нет доступа" }, 403)));
        renderReport();
        expect(await screen.findByText("Нет доступа")).toBeTruthy();
    });

    it("кнопка PDF запрашивает /reports/expenses/pdf", async () => {
        const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
        (URL as any).createObjectURL = vi.fn(() => "blob:test");
        (URL as any).revokeObjectURL = vi.fn();
        try {
            renderReport();
            await screen.findAllByText("Электроэнергия");
            screen.getByRole("button", { name: "PDF" }).click();
            const pdfCall = (fetch as any).mock.calls.find((c: any[]) =>
                String(c[0]).includes("/reports/expenses/pdf"),
            );
            expect(pdfCall).toBeTruthy();
        } finally {
            anchorClick.mockRestore();
        }
    });
});
