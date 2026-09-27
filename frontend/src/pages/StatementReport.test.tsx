// src/pages/StatementReport.test.tsx
// RTL-тесты «Выписки по лицевому счёту» (3.2): до выбора счёта — подсказка без запроса;
// выбор счёта → шапка/метрики/движения; знаковая сумма; PDF.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { Refine } from "@refinedev/core";

import { StatementReport } from "./StatementReport";

const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });

const STMT = {
    account: {
        id: 9,
        account_number: "LS/0001",
        account_name: "",
        apartment_number: 1,
        owner_name: "Иванов Иван",
    },
    metrics: { accrued: 1000, paid: 500, available: 500, debt: 500 },
    movements: [
        {
            date: "2026-08-15",
            kind: "accrual",
            kind_label: "Начисление",
            service: "Электроэнергия",
            document: "Начисление №1",
            amount: 1000,
            balance_after: 1000,
        },
        {
            date: "2026-08-20",
            kind: "payment",
            kind_label: "Оплата",
            service: "Электроэнергия",
            document: "Приход в кассу №1",
            amount: -500,
            balance_after: 500,
        },
    ],
    closing: 500,
};

const dataProvider: any = {
    custom: vi.fn(async () => ({ data: { fields: [] } })),
    getList: vi.fn(async ({ resource }: any) => {
        if (resource === "accounts")
            return {
                data: [
                    {
                        id: 9,
                        account_number: "LS/0001",
                        account_name: "",
                        apartment: { apartment_number: 1 },
                    },
                ],
                total: 1,
            };
        return { data: [], total: 0 };
    }),
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
            <StatementReport />
        </Refine>,
    );

const selectAccount = async () => {
    const selector = document.querySelector(".ant-select-selector") as Element;
    fireEvent.mouseDown(selector);
    fireEvent.click(await screen.findByText("LS/0001 — кв.1"));
};

beforeEach(() => {
    vi.stubGlobal(
        "fetch",
        vi.fn(async (url: RequestInfo | URL) => {
            const u = String(url);
            if (u.includes("/reports/statement/pdf"))
                return new Response(new Blob(["pdf"]), {
                    status: 200,
                    headers: { "Content-Type": "application/pdf" },
                });
            return json(STMT);
        }),
    );
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("StatementReport", () => {
    it("до выбора счёта показывает подсказку и не запрашивает выписку", () => {
        renderReport();
        expect(screen.getByText("Выберите лицевой счёт для построения выписки")).toBeTruthy();
        expect((fetch as any).mock.calls.length).toBe(0);
    });

    it("после выбора счёта — шапка, метрики и движения (знаковая сумма)", async () => {
        renderReport();
        await selectAccount();

        expect(await screen.findByText(/Л\/с LS\/0001/u)).toBeTruthy();
        const url = String((fetch as any).mock.calls[0][0]);
        expect(url).toContain("/accounts/9/movements");

        // Метрики периода.
        expect(screen.getByText("Начислено (период)")).toBeTruthy();
        expect(screen.getByText("Списано (период)")).toBeTruthy();
        expect(screen.getAllByText("Долг").length).toBeGreaterThan(0);

        // Движения: даты DD.MM.YYYY и знаковые суммы «глазами счёта» (amount инвертируется).
        const accrual = (await screen.findByText("Начисление №1")).closest("tr") as HTMLElement;
        expect(within(accrual).getByText("15.08.2026")).toBeTruthy();
        expect(within(accrual).getByText(/−1 000,00/u)).toBeTruthy(); // начисление → минус

        const payment = screen.getByText("Приход в кассу №1").closest("tr") as HTMLElement;
        expect(within(payment).getByText("20.08.2026")).toBeTruthy();
        expect(within(payment).getByText(/\+500,00/u)).toBeTruthy(); // оплата → плюс
    });

    it("PDF доступен после выбора счёта и запрашивает /reports/statement/pdf", async () => {
        const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
        (URL as any).createObjectURL = vi.fn(() => "blob:test");
        (URL as any).revokeObjectURL = vi.fn();
        try {
            renderReport();
            // До выбора счёта кнопка PDF отключена.
            expect((screen.getByRole("button", { name: /PDF/u }) as HTMLButtonElement).disabled).toBe(true);

            await selectAccount();
            await screen.findByText(/Л\/с LS\/0001/u);

            await waitFor(() =>
                expect(
                    (screen.getByRole("button", { name: /PDF/u }) as HTMLButtonElement).disabled,
                ).toBe(false),
            );
            screen.getByRole("button", { name: /PDF/u }).click();
            const pdfCall = (fetch as any).mock.calls.find((c: any[]) =>
                String(c[0]).includes("/reports/statement/pdf"),
            );
            expect(pdfCall).toBeTruthy();
            expect(String(pdfCall[0])).toContain("account_id=9");
        } finally {
            anchorClick.mockRestore();
        }
    });
});
