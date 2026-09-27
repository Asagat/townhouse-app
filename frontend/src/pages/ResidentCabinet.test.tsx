// src/pages/ResidentCabinet.test.tsx
// RTL-тесты страницы «Личный кабинет жителя» (pages/ResidentCabinet):
//   1) загрузка сводки по своему ЛС (/me/statement) и списка квитанций (/me/receipts),
//      а общий блок CabinetView дополнительно тянет движения (/me/movements) и
//      общедомовые расходы (/me/house_expenses);
//   2) заголовок «Личный кабинет» и наполнение сводки/квитанций;
//   3) нижняя навигация «Главная»/«Настройки»/«Выход» и переход по «Настройки» → /profile
//      (probe-роут через <Routes>);
//   4) выход вызывает Refine authProvider.logout;
//   5) ошибка загрузки сводки показывается в Alert.
//
// Refine — мок dataProvider (getApiUrl → /api) + мок authProvider (logout);
// react-router — MemoryRouter; сеть — мок fetch (без реальной сети).

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { Refine } from "@refinedev/core";
import dayjs from "dayjs";

import { ResidentCabinet } from "./ResidentCabinet";
import { formatPeriod } from "../config/formatters";

const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });

const STATEMENT = {
    account: { id: 1, account_number: "LS-0001", account_name: "Кв.1" },
    apartment: { apartment_number: 1, address: "ул. Тестовая, 1" },
    owner: { full_name: "Иванов Иван", phone: "70000000000" },
    metrics: {
        accrued_total: 1000,
        paid_total: 500,
        available: 500,
        debt_total: 500,
        overpayment: 0,
        balance: 500,
    },
    services: [
        { services_type_id: 1, service_name: "Вывоз мусора", accrued: 1000, paid: 500, debt: 500 },
    ],
};

// Квитанция за прошлый месяц: CabinetView фильтрует квитанции по выбранному периоду,
// который по умолчанию — прошлый месяц. Поэтому дату считаем от текущей, чтобы тест
// не зависел от календаря.
const prevMonth = dayjs().subtract(1, "month");
const RECEIPT = {
    id: 7,
    period_month: prevMonth.month() + 1,
    period_year: prevMonth.year(),
    apartment_number: 1,
    owner_name: "Иванов Иван",
    total_amount: 1000,
    payable_amount: 500,
};
const receiptPeriodText = formatPeriod(
    `${prevMonth.year()}-${String(prevMonth.month() + 1).padStart(2, "0")}`,
);

const MOVEMENTS = {
    metrics: { accrued: 1000, paid: 500, available: 500, debt: 500 },
    movements: [
        {
            date: "2026-03-01",
            kind: "accrual",
            kind_label: "Начисление",
            service: "Вывоз мусора",
            article: null,
            amount: 1000,
            balance_after: 1000,
            document: null,
        },
    ],
    cash_movements: [],
    closing: 0,
};

const HOUSE_EXPENSES = {
    period: { from: null, to: null },
    articles: [{ name: "Зарплата", expense: 2000 }],
    total: 2000,
};

const makeProviders = () => {
    const dataProvider: any = {
        custom: vi.fn(async () => ({ data: {} })),
        getList: vi.fn(async () => ({ data: [], total: 0 })),
        getOne: vi.fn(async () => ({ data: {} })),
        getMany: vi.fn(async () => ({ data: [] })),
        create: vi.fn(async () => ({ data: {} })),
        update: vi.fn(async () => ({ data: {} })),
        deleteOne: vi.fn(async () => ({ data: {} })),
        getApiUrl: () => "/api",
    };
    const authProvider: any = {
        login: vi.fn(async () => ({ success: true })),
        logout: vi.fn(async () => ({ success: true, redirectTo: "/" })),
        check: vi.fn(async () => ({ authenticated: true })),
        getIdentity: vi.fn(async () => ({ id: 1, name: "Тест" })),
        getPermissions: vi.fn(async () => []),
        onError: vi.fn(async () => ({})),
    };
    return { dataProvider, authProvider };
};

const renderCabinet = () => {
    const providers = makeProviders();
    const utils = render(
        <MemoryRouter initialEntries={["/"]}>
            <Refine dataProvider={providers.dataProvider} authProvider={providers.authProvider}>
                <Routes>
                    <Route path="/" element={<ResidentCabinet />} />
                    <Route path="/profile" element={<div>Probe-страница профиля</div>} />
                </Routes>
            </Refine>
        </MemoryRouter>,
    );
    return { ...utils, ...providers };
};

// Все эндпоинты ЛК жителя, которые должны быть замоканы (страница + CabinetView).
beforeEach(() => {
    vi.stubGlobal(
        "fetch",
        vi.fn(async (url: RequestInfo | URL) => {
            const u = String(url);
            if (u.includes("/me/statement")) return json(STATEMENT);
            if (u.includes("/me/receipts")) return json([RECEIPT]);
            if (u.includes("/me/movements")) return json(MOVEMENTS);
            if (u.includes("/house_expenses")) return json(HOUSE_EXPENSES);
            return json({});
        }),
    );
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("ResidentCabinet", () => {
    it("загружает сводку и квитанции и показывает их в блоке ЛК", async () => {
        renderCabinet();

        // Заголовок страницы.
        expect(await screen.findByText("Личный кабинет")).toBeTruthy();

        // Сводка по счёту (шапка CabinetView) и наполнение квитанций.
        expect(await screen.findByText("Лицевой счёт LS-0001")).toBeTruthy();
        expect(await screen.findByText(receiptPeriodText)).toBeTruthy();

        // Движения и общедомовые расходы CabinetView тоже подгрузил.
        expect(await screen.findByText("Движения")).toBeTruthy();
        expect(await screen.findByText("Общедомовые расходы")).toBeTruthy();

        // Запросы ушли на нужные эндпоинты.
        const urls = (fetch as any).mock.calls.map((c: any[]) => String(c[0]));
        for (const frag of ["/me/statement", "/me/receipts", "/me/movements", "/me/house_expenses"]) {
            expect(urls.some((u: string) => u.includes(frag))).toBe(true);
        }
    });

    it("показывает нижнюю навигацию: Главная / Настройки / Выход", async () => {
        renderCabinet();
        await screen.findByText("Личный кабинет");

        // У кнопок-иконок antd есть внутренний role="img", поэтому имя — по подписи.
        expect(screen.getByRole("button", { name: /Главная/ })).toBeTruthy();
        expect(screen.getByRole("button", { name: /Настройки/ })).toBeTruthy();
        expect(screen.getByRole("button", { name: /Выход/ })).toBeTruthy();
    });

    it("переход по «Настройки» открывает /profile", async () => {
        renderCabinet();
        await screen.findByText("Личный кабинет");

        fireEvent.click(screen.getByRole("button", { name: /Настройки/ }));
        expect(await screen.findByText("Probe-страница профиля")).toBeTruthy();
    });

    it("«Выход» вызывает authProvider.logout", async () => {
        const { authProvider } = renderCabinet();
        await screen.findByText("Личный кабинет");

        fireEvent.click(screen.getByRole("button", { name: /Выход/ }));
        await waitFor(() => expect(authProvider.logout).toHaveBeenCalled());
    });

    it("ошибка загрузки сводки показывается в Alert", async () => {
        vi.stubGlobal(
            "fetch",
            vi.fn(async (url: RequestInfo | URL) => {
                const u = String(url);
                if (u.includes("/me/statement")) return json({ detail: "Нет доступа к сводке" }, 403);
                if (u.includes("/me/receipts")) return json([]);
                // CabinetView рендерится даже без сводки и всё равно грузит общедомовые
                // расходы — отдаём валидную форму ответа.
                if (u.includes("/house_expenses")) return json({ articles: [], total: 0 });
                return json({});
            }),
        );
        renderCabinet();

        expect(await screen.findByText("Нет доступа к сводке")).toBeTruthy();
    });
});
