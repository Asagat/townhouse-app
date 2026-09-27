// src/pages/Users.test.tsx
// RTL-проверки страницы «Пользователи и права» (вкладка «Пользователи»):
// загрузка списка через `http.get("/api/auth/users")`, отрисовка строк (логин/имя/
// роль-тег/активность), выделение записи и появление действий «Редактировать/Удалить»,
// модалка создания (POST), редактирование (PATCH) и удаление через Popconfirm (DELETE).
//
// Сеть не используется: модуль `../auth/http` замокан фабрикой vi.mock (axios-инстанс
// заменён на vi.fn-заглушки). Вкладка «Права доступа» (RolePermissions) в antd Tabs по
// умолчанию не рендерится, поэтому здесь она не задействована — см. отдельный
// RolePermissions.test.tsx.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { http } from "../auth/http";
import { Users } from "./Users";

vi.mock("../auth/http", () => ({
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

const USERS = [
    {
        id: 1,
        username: "admin",
        full_name: "Админ Админович",
        role: "admin",
        role_name: "Администратор",
        is_active: true,
    },
    {
        id: 2,
        username: "cashier1",
        full_name: null,
        role: "cashier",
        role_name: "Кассир",
        is_active: false,
    },
];

/** Кнопка-иконка действия по классу иконки (EditOutlined/DeleteOutlined). */
const iconButton = (icon: "edit" | "delete"): HTMLButtonElement | null =>
    (document.querySelector(`.anticon-${icon}`)?.closest("button") as HTMLButtonElement) ?? null;

/** Клик по строке таблицы выбранного логина (выделяет запись). */
const selectRow = (username: string) => {
    const cell = screen.getByText(username);
    fireEvent.click(cell.closest("tr") as HTMLElement);
};

beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(http.get).mockResolvedValue({ data: USERS } as any);
    vi.mocked(http.post).mockResolvedValue({ data: { id: 3 } } as any);
    vi.mocked(http.patch).mockResolvedValue({ data: {} } as any);
    vi.mocked(http.delete).mockResolvedValue({ data: {} } as any);
    vi.mocked(http.put).mockResolvedValue({ data: {} } as any);
});

afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
});

describe("Users — список пользователей", () => {
    it("загружает список с /api/auth/users и отображает логин, имя, роль-тег и активность", async () => {
        render(<Users />);

        expect(await screen.findByText("admin")).toBeTruthy();
        expect(vi.mocked(http.get)).toHaveBeenCalledWith("/api/auth/users");

        expect(screen.getByText("cashier1")).toBeTruthy();
        expect(screen.getByText("Админ Админович")).toBeTruthy();
        // Пустое имя (null) отображается прочерком.
        expect(screen.getByText("—")).toBeTruthy();
        // Роль — тег с подписью из role_name.
        expect(screen.getByText("Администратор")).toBeTruthy();
        expect(screen.getByText("Кассир")).toBeTruthy();
        // Активность текстом.
        expect(screen.getByText("Да")).toBeTruthy();
        expect(screen.getByText("Нет")).toBeTruthy();
    });

    it("до выделения строки кнопки действий отключены", async () => {
        render(<Users />);
        await screen.findByText("admin");

        expect(iconButton("edit")?.disabled).toBe(true);
        expect(iconButton("delete")?.disabled).toBe(true);
    });
});

describe("Users — выделение записи", () => {
    it("выделение строки включает действия «Редактировать/Удалить» и показывает номер записи", async () => {
        render(<Users />);
        await screen.findByText("admin");

        selectRow("admin");

        expect(await screen.findByText(/Запись № 1/u)).toBeTruthy();
        await waitFor(() => {
            expect(iconButton("edit")?.disabled).toBe(false);
            expect(iconButton("delete")?.disabled).toBe(false);
        });
    });
});

describe("Users — создание пользователя", () => {
    it("«Создать пользователя» открывает модалку, а «Сохранить» шлёт POST /api/auth/users", async () => {
        render(<Users />);
        await screen.findByText("admin");

        fireEvent.click(screen.getByRole("button", { name: /Создать пользователя/u }));
        expect(await screen.findByText("Новый пользователь")).toBeTruthy();

        fireEvent.change(screen.getByLabelText("Логин"), { target: { value: "newbie" } });
        fireEvent.change(screen.getByLabelText("Пароль"), { target: { value: "секрет123" } });

        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

        await waitFor(() =>
            expect(vi.mocked(http.post)).toHaveBeenCalledWith(
                "/api/auth/users",
                expect.objectContaining({
                    username: "newbie",
                    password: "секрет123",
                    role: "cashier",
                    is_active: true,
                }),
            ),
        );
    });
});

describe("Users — редактирование пользователя", () => {
    it("модалка заполнена, логин заблокирован, «Сохранить» шлёт PATCH /api/auth/users/1", async () => {
        render(<Users />);
        await screen.findByText("admin");

        selectRow("admin");
        await screen.findByText(/Запись № 1/u);

        fireEvent.click(iconButton("edit") as HTMLButtonElement);
        expect(await screen.findByText("Редактировать: admin")).toBeTruthy();

        const login = screen.getByLabelText("Логин") as HTMLInputElement;
        expect(login.disabled).toBe(true);
        expect(login.value).toBe("admin");

        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

        await waitFor(() =>
            expect(vi.mocked(http.patch)).toHaveBeenCalledWith(
                "/api/auth/users/1",
                expect.objectContaining({ username: "admin", role: "admin" }),
            ),
        );
    });
});

describe("Users — удаление пользователя", () => {
    it("Popconfirm подтверждает удаление и шлёт DELETE /api/auth/users/1", async () => {
        render(<Users />);
        await screen.findByText("admin");

        selectRow("admin");
        await screen.findByText(/Запись № 1/u);

        fireEvent.click(iconButton("delete") as HTMLButtonElement);
        // Popconfirm с текстом подтверждения (antd, локаль по умолчанию).
        expect(await screen.findByText("Удалить пользователя?")).toBeTruthy();

        fireEvent.click(screen.getByRole("button", { name: "OK" }));

        await waitFor(() =>
            expect(vi.mocked(http.delete)).toHaveBeenCalledWith("/api/auth/users/1"),
        );
    });
});
