// src/components/permissions/RolePermissions.test.tsx
// RTL-проверки вкладки «Права доступа» (задача 2.6): загрузка матрицы
// «ресурс × роль» с /api/auth/permissions, отрисовка строк каталога и заголовков ролей,
// блокировка чекбоксов фиксированных ролей и «запертых» действий, переключение чекбокса
// с последующим сохранением (PUT с items) и сброс к умолчаниям (POST /reset).
//
// Сеть не используется: модуль `../../auth/http` замокан фабрикой vi.mock.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";

import { http } from "../../auth/http";
import { RolePermissions } from "./RolePermissions";

vi.mock("../../auth/http", () => ({
    apiUrl: "/api",
    http: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        patch: vi.fn(),
        delete: vi.fn(),
    },
    authedFetch: vi.fn(),
    handleUnauthorized: vi.fn(),
    consumeSessionExpiredNotice: vi.fn(() => false),
    downloadAuthorizedFile: vi.fn(),
    downloadAuthorizedPdf: vi.fn(),
    openAuthorizedPdf: vi.fn(),
    SESSION_EXPIRED_MESSAGE: "Сессия истекла. Выйдите из системы и войдите заново.",
}));

// Раздел (section) — только Р и, при read_enforced, Ч; ресурс — все пять действий.
const PERMISSIONS = {
    catalog: [
        { key: "dashboard", label: "Дашборд", group: "Обзор", kind: "section", read_enforced: true },
        { key: "payments", label: "Платежи", group: "Финансы", kind: "resource", read_enforced: false },
    ],
    roles: ["admin", "operator", "cashier", "resident"],
    fixed_roles: ["admin", "resident"],
    locked_actions: { payments: ["delete"] },
    matrix: {
        admin: {
            dashboard: { menu: true, read: true, create: false, edit: false, delete: false },
            payments: { menu: true, read: true, create: true, edit: true, delete: true },
        },
        operator: {
            dashboard: { menu: true, read: true, create: false, edit: false, delete: false },
            payments: { menu: true, read: false, create: true, edit: true, delete: true },
        },
        cashier: {
            dashboard: { menu: true, read: true, create: false, edit: false, delete: false },
            payments: { menu: true, read: true, create: false, edit: false, delete: false },
        },
        resident: {
            dashboard: { menu: true, read: false, create: false, edit: false, delete: false },
            payments: { menu: true, read: false, create: false, edit: false, delete: false },
        },
    },
};

// Порядок столбцов-ролей совпадает с `roles`: admin, operator, cashier, resident.
const ROLE_INDEX = { admin: 0, operator: 1, cashier: 2, resident: 3 };

/** Чекбоксы строки таблицы по подписи ресурса, в порядке DOM (5 действий на роль). */
const checkboxesOfRow = (label: string): HTMLInputElement[] => {
    const row = screen.getByText(label).closest("tr") as HTMLElement;
    return within(row).getAllByRole("checkbox") as HTMLInputElement[];
};

/** Чекбокс конкретной роли и действия в строке-ресурсе (у ресурса 5 действий). */
const checkboxAt = (label: string, role: keyof typeof ROLE_INDEX, actionIndex: number): HTMLInputElement =>
    checkboxesOfRow(label)[ROLE_INDEX[role] * 5 + actionIndex];

beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(http.get).mockResolvedValue({ data: PERMISSIONS } as any);
    vi.mocked(http.put).mockResolvedValue({ data: {} } as any);
    vi.mocked(http.post).mockResolvedValue({ data: {} } as any);
    vi.mocked(http.patch).mockResolvedValue({ data: {} } as any);
    vi.mocked(http.delete).mockResolvedValue({ data: {} } as any);
});

afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
});

describe("RolePermissions — загрузка матрицы", () => {
    it("загружает /api/auth/permissions и рисует строки каталога и заголовки ролей", async () => {
        render(<RolePermissions />);

        expect(await screen.findByText("Дашборд")).toBeTruthy();
        expect(vi.mocked(http.get)).toHaveBeenCalledWith("/api/auth/permissions");

        // Строки каталога.
        expect(screen.getByText("Платежи")).toBeTruthy();

        // Заголовки столбцов: базовые и роли (подписи из ROLE_OPTIONS_LABELS).
        const headers = screen
            .getAllByRole("columnheader")
            .map((h) => (h.textContent ?? "").trim());
        expect(headers).toEqual(
            expect.arrayContaining([
                "Группа",
                "Ресурс / раздел",
                "Администратор",
                "Оператор",
                "Кассир",
                "Житель",
            ]),
        );
    });
});

describe("RolePermissions — блокировка чекбоксов", () => {
    it("у фиксированных ролей (admin/resident) все чекбоксы disabled", async () => {
        render(<RolePermissions />);
        await screen.findByText("Платежи");

        const checkboxes = checkboxesOfRow("Платежи");
        // admin — индексы 0..4, resident — 15..19.
        for (const i of [0, 1, 2, 3, 4, 15, 16, 17, 18, 19]) {
            expect(checkboxes[i].disabled).toBe(true);
        }
    });

    it("«запертое» действие (payments.delete) недоступно и у нефиксированных ролей", async () => {
        render(<RolePermissions />);
        await screen.findByText("Платежи");

        // operator: menu/read/create/edit доступны, delete (индекс 4) — заблокирован.
        expect(checkboxAt("Платежи", "operator", 0).disabled).toBe(false);
        expect(checkboxAt("Платежи", "operator", 1).disabled).toBe(false);
        expect(checkboxAt("Платежи", "operator", 4).disabled).toBe(true);

        // cashier — так же delete заблокирован.
        expect(checkboxAt("Платежи", "cashier", 0).disabled).toBe(false);
        expect(checkboxAt("Платежи", "cashier", 4).disabled).toBe(true);
    });
});

describe("RolePermissions — сохранение", () => {
    it("переключение чекбокса и «Сохранить» шлют PUT /api/auth/permissions с items", async () => {
        render(<RolePermissions />);
        await screen.findByText("Платежи");

        // operator.read для «Платежи» изначально false → включаем.
        const read = checkboxAt("Платежи", "operator", 1);
        expect(read.checked).toBe(false);
        fireEvent.click(read);

        await waitFor(() => expect(checkboxAt("Платежи", "operator", 1).checked).toBe(true));

        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

        await waitFor(() => expect(vi.mocked(http.put)).toHaveBeenCalledTimes(1));
        const [url, body] = vi.mocked(http.put).mock.calls[0];
        expect(url).toBe("/api/auth/permissions");

        const items = (body as { items: Array<Record<string, unknown>> }).items;
        const operatorPayments = items.find((i) => i.role === "operator" && i.resource === "payments");
        expect(operatorPayments).toMatchObject({
            role: "operator",
            resource: "payments",
            read: true,
        });
        // Фиксированные роли в сохранение не попадают.
        expect(items.some((i) => i.role === "admin" || i.role === "resident")).toBe(false);
    });
});

describe("RolePermissions — сброс к умолчаниям", () => {
    it("«Сбросить к умолчаниям» шлёт POST /api/auth/permissions/reset", async () => {
        render(<RolePermissions />);
        await screen.findByText("Платежи");

        fireEvent.click(screen.getByRole("button", { name: "Сбросить к умолчаниям" }));

        await waitFor(() =>
            expect(vi.mocked(http.post)).toHaveBeenCalledWith("/api/auth/permissions/reset"),
        );
    });
});
