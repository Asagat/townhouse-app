// src/pages/Dashboard.test.tsx
// RTL-тесты дашборда главной страницы (2.19): запрос /api/dashboard, KPI-метрики
// («Начислено», «Внесено в кассу», «Списано», «Долг (л/с с долгом: N)», «Остаток в кассе»),
// таблица должников (квартира, л/с, собственник, долг в денежном формате), строка
// «Итого расходов» в расходах по кассе, переход по кнопке «Отчёт по должникам» и
// обработка ошибки загрузки (Alert с detail). Компонент использует useNavigate — поэтому
// рендерим внутри MemoryRouter с Routes. Refine не нужен: данные идут через authedFetch/apiUrl.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import { Dashboard } from "./Dashboard";

const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });

const DASHBOARD = {
    metrics: {
        accrued: 1234.5,
        received: 500,
        written_off: 200,
        debt: 160765,
        cash_balance: 2034.5,
        debtors_count: 2,
    },
    top_debtors: [
        {
            account_id: 3,
            account_number: "LS-0003",
            apartment_number: 3,
            owner_name: "Иванов Иван",
            accrued: 160765,
            paid: 0,
            debt: 160765,
        },
        {
            account_id: 5,
            account_number: "LS-0005",
            apartment_number: 5,
            owner_name: "Петров Пётр",
            accrued: 2000,
            paid: 0,
            debt: 2000,
        },
    ],
    debt_dynamics: [{ month: "2026-08", debt: 160765, label: "Август 2026" }],
    expenses: {
        total: 700,
        articles: [
            { name: "Электроэнергия", expense: 500 },
            { name: "Вывоз мусора", expense: 200 },
        ],
        count: 2,
    },
    window_days: 30,
};

const renderDashboard = () =>
    render(
        <MemoryRouter initialEntries={["/"]}>
            <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/debtors_report" element={<div>Страница отчёта по должникам</div>} />
            </Routes>
        </MemoryRouter>,
    );

beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json(DASHBOARD))));
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("Dashboard", () => {
    it("запрашивает /api/dashboard при загрузке", async () => {
        renderDashboard();
        await screen.findByText("Иванов Иван");

        expect((fetch as any).mock.calls.length).toBeGreaterThan(0);
        expect(String((fetch as any).mock.calls[0][0])).toContain("/api/dashboard");
    });

    it("показывает KPI-метрики и окно периода", async () => {
        renderDashboard();
        await screen.findByText("Иванов Иван");

        for (const title of [
            "Начислено",
            "Внесено в кассу",
            "Списано",
            "Долг (л/с с долгом: 2)",
            "Остаток в кассе",
        ]) {
            expect(screen.getByText(title)).toBeTruthy();
        }
        // Заголовки секций с окном периода.
        expect(screen.getByText("Движение за последние 30 дней")).toBeTruthy();
        expect(screen.getByText("Состояние на сейчас")).toBeTruthy();
    });

    it("в таблице должников — квартира, л/с, собственник и долг в денежном формате", async () => {
        renderDashboard();

        const owner = await screen.findByText("Иванов Иван");
        const row = owner.closest("tr") as HTMLElement;
        expect(row).not.toBeNull();

        expect(within(row).getByText("3")).toBeTruthy();
        expect(within(row).getByText("LS-0003")).toBeTruthy();
        // Долг строки — денежный формат «160 765,00» (пробел-разделитель и 2 знака).
        expect(within(row).getByText(/160\s?765,00/u)).toBeTruthy();
    });

    it("в расходах по кассе показывает статьи и строку «Итого расходов»", async () => {
        renderDashboard();
        await screen.findByText("Иванов Иван");

        expect(screen.getByText("Расходы по кассе (за последние 30 дней)")).toBeTruthy();
        expect(screen.getByText("Электроэнергия")).toBeTruthy();
        expect(screen.getByText("Вывоз мусора")).toBeTruthy();

        const totalRow = screen.getByText("Итого расходов").closest("tr") as HTMLElement;
        expect(totalRow).not.toBeNull();
        expect(within(totalRow).getByText(/700,00/u)).toBeTruthy();
    });

    it("кнопка «Отчёт по должникам» уводит на /debtors_report", async () => {
        renderDashboard();
        await screen.findByText("Иванов Иван");

        fireEvent.click(screen.getByRole("button", { name: /Отчёт по должникам/u }));

        expect(await screen.findByText("Страница отчёта по должникам")).toBeTruthy();
    });

    it("ошибка загрузки показывается в Alert с detail", async () => {
        vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ detail: "Нет доступа к дашборду" }, 403))));
        renderDashboard();

        expect(await screen.findByText("Нет доступа к дашборду")).toBeTruthy();
    });
});
