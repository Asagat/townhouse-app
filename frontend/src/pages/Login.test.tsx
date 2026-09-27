// src/pages/Login.test.tsx
// RTL-тесты страницы входа: отрисовка формы, обязательные поля, успешный вход
// (вызов authProvider.login через useLogin), показ ошибки входа и предупреждение
// об истёкшей сессии (пометка в sessionStorage, см. auth/http). Refine обёрнут
// моками dataProvider/authProvider — реальной сети нет.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Refine } from "@refinedev/core";

import { Login } from "./Login";
import { SESSION_EXPIRED_MESSAGE } from "../auth/http";

// Ключ пометки «сессия истекла» — как в auth/http.
const SESSION_EXPIRED_FLAG = "townhouse:session-expired";

const loginMock = vi.fn();

const mockAuthProvider: any = {
    login: loginMock,
    logout: vi.fn(async () => ({ success: true })),
    check: vi.fn(async () => ({ authenticated: false })),
    getIdentity: vi.fn(async () => ({ id: 1, name: "Тестовый пользователь" })),
    getPermissions: vi.fn(async () => []),
    onError: vi.fn(async () => ({})),
};

// Минимальный провайдер данных: страница входа списков не грузит, но Refine
// требует корректный объект (getList/getOne/.../getApiUrl).
const mockDataProvider: any = {
    getList: vi.fn(async () => ({ data: [], total: 0 })),
    getOne: vi.fn(async () => ({ data: {} })),
    getMany: vi.fn(async () => ({ data: [] })),
    create: vi.fn(async () => ({ data: {} })),
    update: vi.fn(async () => ({ data: {} })),
    deleteOne: vi.fn(async () => ({ data: {} })),
    custom: vi.fn(async () => ({ data: {} })),
    getApiUrl: () => "/api",
};

const renderLogin = () =>
    render(
        <MemoryRouter>
            <Refine dataProvider={mockDataProvider} authProvider={mockAuthProvider}>
                <Login />
            </Refine>
        </MemoryRouter>,
    );

beforeEach(() => {
    vi.clearAllMocks();
    loginMock.mockResolvedValue({ success: true, redirectTo: "/" });
});

afterEach(() => {
    sessionStorage.clear();
});

describe("Login — форма входа", () => {
    it("отображает поля «Логин»/«Пароль» и кнопку «Войти»", () => {
        renderLogin();

        expect(screen.getByText("Логин")).toBeTruthy();
        expect(screen.getByText("Пароль")).toBeTruthy();
        expect(screen.getByRole("button", { name: "Войти" })).toBeTruthy();
        expect(screen.getByText("Family Townhouse")).toBeTruthy();
    });

    it("при пустой отправке показывает ошибки обязательных полей и не вызывает login", async () => {
        renderLogin();

        fireEvent.click(screen.getByRole("button", { name: "Войти" }));

        expect(await screen.findByText("Введите логин")).toBeTruthy();
        expect(await screen.findByText("Введите пароль")).toBeTruthy();
        expect(loginMock).not.toHaveBeenCalled();
    });

    it("успешный вход вызывает login с введёнными логином и паролем", async () => {
        renderLogin();

        fireEvent.change(screen.getByPlaceholderText("Логин"), {
            target: { value: "admin" },
        });
        fireEvent.change(screen.getByPlaceholderText("Пароль"), {
            target: { value: "secret" },
        });
        fireEvent.click(screen.getByRole("button", { name: "Войти" }));

        await waitFor(() =>
            expect(loginMock).toHaveBeenCalledWith({
                username: "admin",
                password: "secret",
            }),
        );
    });

    it("при ошибке входа показывает сообщение из authProvider", async () => {
        loginMock.mockResolvedValueOnce({
            success: false,
            error: { message: "Неверный логин или пароль" },
        });
        renderLogin();

        fireEvent.change(screen.getByPlaceholderText("Логин"), {
            target: { value: "admin" },
        });
        fireEvent.change(screen.getByPlaceholderText("Пароль"), {
            target: { value: "bad-password" },
        });
        fireEvent.click(screen.getByRole("button", { name: "Войти" }));

        expect(await screen.findByText("Неверный логин или пароль")).toBeTruthy();
    });

    it("показывает предупреждение об истёкшей сессии и очищает пометку", async () => {
        sessionStorage.setItem(SESSION_EXPIRED_FLAG, "1");

        renderLogin();

        expect(await screen.findByText(SESSION_EXPIRED_MESSAGE)).toBeTruthy();
        // Пометка одноразовая — после показа она удаляется.
        expect(sessionStorage.getItem(SESSION_EXPIRED_FLAG)).toBeNull();
    });
});
