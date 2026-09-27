// src/pages/AdminCabinet.test.tsx
// RTL-тесты страницы «Личный кабинет жителя» для администратора (pages/AdminCabinet):
//   1) загрузка списка лицевых счетов (/accounts) и заглушка до выбора;
//   2) выбор счёта → загрузка сводки/квитанций/движений
//      (/accounts/{id}/statement, /receipts, /movements) и отрисовка общего
//      блока CabinetView (режим account, заголовок «Квитанции жителя»);
//   3) ошибка загрузки списка счетов и ошибка загрузки сводки — в Alert.
//
// Refine — мок dataProvider (getApiUrl → /api); сеть — мок fetch (без реальной сети).

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Refine } from "@refinedev/core";

import { AdminCabinet } from "./AdminCabinet";

const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });

const ACCOUNTS = [
    {
        id: 1,
        account_number: "LS-0001",
        account_name: "Кв.1",
        apartment: { apartment_number: 1, owner: { full_name: "Иванов Иван" } },
    },
    { id: 2, account_number: "LS-0002", account_name: "Кв.2", apartment: null },
];

// Подпись опции формируется в AdminCabinet: «Кв. №1 — Иванов Иван (LS-0001)».
const ACCOUNT_OPTION = "Кв. №1 — Иванов Иван (LS-0001)";

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

const MOVEMENTS = {
    metrics: { accrued: 1000, paid: 500, available: 500, debt: 500 },
    movements: [],
    cash_movements: [],
    closing: 0,
};

const HOUSE_EXPENSES = {
    period: { from: null, to: null },
    articles: [{ name: "Зарплата", expense: 2000 }],
    total: 2000,
};

const makeDataProvider = () =>
    ({
        custom: vi.fn(async () => ({ data: {} })),
        getList: vi.fn(async () => ({ data: [], total: 0 })),
        getOne: vi.fn(async () => ({ data: {} })),
        getMany: vi.fn(async () => ({ data: [] })),
        create: vi.fn(async () => ({ data: {} })),
        update: vi.fn(async () => ({ data: {} })),
        deleteOne: vi.fn(async () => ({ data: {} })),
        getApiUrl: () => "/api",
    }) as any;

const renderCabinet = () =>
    render(
        <Refine dataProvider={makeDataProvider()}>
            <AdminCabinet />
        </Refine>,
    );

/** Открывает выпадающий список счетов и выбирает опцию. */
const selectAccount = async (container: HTMLElement, label: string) => {
    const selector = container.querySelector(".ant-select-selector") as HTMLElement;
    fireEvent.mouseDown(selector);
    fireEvent.click(await screen.findByText(label));
};

beforeEach(() => {
    vi.stubGlobal(
        "fetch",
        vi.fn(async (url: RequestInfo | URL) => {
            const u = String(url);
            if (u.includes("/accounts?")) return json(ACCOUNTS);
            if (u.includes("/statement")) return json(STATEMENT);
            if (u.includes("/receipts")) return json([]);
            if (u.includes("/movements")) return json(MOVEMENTS);
            if (u.includes("/house_expenses")) return json(HOUSE_EXPENSES);
            return json({});
        }),
    );
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("AdminCabinet", () => {
    it("загружает список счетов и показывает заглушку до выбора", async () => {
        renderCabinet();

        expect(await screen.findByText("Личный кабинет жителя")).toBeTruthy();
        expect(
            screen.getByText("Выберите квартиру, чтобы увидеть данные, которые видит житель."),
        ).toBeTruthy();

        // Список счетов запрошен с пагинацией Refine и сортировкой справочника.
        const urls = (fetch as any).mock.calls.map((c: any[]) => String(c[0]));
        const listCall = urls.find((u: string) => u.includes("/accounts?"));
        expect(listCall).toBeTruthy();
        expect(listCall).toContain("_start=0");
        expect(listCall).toContain("_end=1000");
    });

    it("выбор счёта грузит сводку/квитанции/движения и показывает CabinetView", async () => {
        const { container } = renderCabinet();
        await screen.findByText("Личный кабинет жителя");

        await selectAccount(container, ACCOUNT_OPTION);

        // Сводка по выбранному счёту и заголовок квитанций в режиме account.
        expect(await screen.findByText("Лицевой счёт LS-0001")).toBeTruthy();
        expect(await screen.findByText("Квитанции жителя")).toBeTruthy();

        // Данные запрошены именно по выбранному счёту.
        const urls = (fetch as any).mock.calls.map((c: any[]) => String(c[0]));
        for (const frag of [
            "/accounts/1/statement",
            "/accounts/1/receipts",
            "/accounts/1/movements",
        ]) {
            expect(urls.some((u: string) => u.includes(frag))).toBe(true);
        }
    });

    it("ошибка загрузки списка счетов показывается в Alert", async () => {
        vi.stubGlobal(
            "fetch",
            vi.fn(async (url: RequestInfo | URL) => {
                const u = String(url);
                if (u.includes("/accounts?")) return json({ detail: "Нет доступа" }, 403);
                return json({});
            }),
        );
        renderCabinet();

        expect(await screen.findByText("Не удалось загрузить лицевые счета")).toBeTruthy();
    });

    it("ошибка загрузки сводки по выбранному счёту показывается в Alert", async () => {
        vi.stubGlobal(
            "fetch",
            vi.fn(async (url: RequestInfo | URL) => {
                const u = String(url);
                if (u.includes("/accounts?")) return json(ACCOUNTS);
                if (u.includes("/statement")) return json({ detail: "Нет доступа к счёту" }, 403);
                if (u.includes("/receipts")) return json([]);
                if (u.includes("/movements")) return json(MOVEMENTS);
                if (u.includes("/house_expenses")) return json(HOUSE_EXPENSES);
                return json({});
            }),
        );
        const { container } = renderCabinet();
        await screen.findByText("Личный кабинет жителя");

        await selectAccount(container, ACCOUNT_OPTION);

        expect(await screen.findByText("Нет доступа к счёту")).toBeTruthy();
    });
});
