// src/pages/ChangePassword.test.tsx
// RTL-тесты смены пароля (Б9): отрисовка формы, валидация (обязательные поля,
// минимальная длина нового пароля, совпадение нового пароля и подтверждения),
// успешная отправка POST /auth/change-password (URL/метод/тело) с последующим
// GET /auth/me, обновлением личности и переходом на главную, а также показ ошибки
// сервера (detail) с возвратом на форму.
//
// Компонент использует useNavigate — рендерим внутри MemoryRouter с Routes.
// Сеть подменяется моком глобального fetch (authedFetch) — реальных запросов нет.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import { ChangePassword } from "./ChangePassword";

const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });

const ME = {
    id: 1,
    username: "resident1",
    full_name: "Иванов Иван",
    role: "resident",
    role_name: "Житель",
    must_change_password: false,
};

// Подмена сети: смена пароля и обновление личности после успеха.
// Второй параметр (init) нужен только чтобы вызовы fetch в моке были двойкой
// (в тесте проверяем их через `c[1]`) — сам обработчик его не использует.
const defaultFetch = (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/auth/change-password")) return Promise.resolve(json({ ok: true }));
    if (url.endsWith("/auth/me")) return Promise.resolve(json(ME));
    return Promise.resolve(json({}));
};

const fetchMock = vi.fn(defaultFetch);

const renderChangePassword = () =>
    render(
        <MemoryRouter initialEntries={["/change-password"]}>
            <Routes>
                <Route path="/change-password" element={<ChangePassword />} />
                <Route path="/" element={<div>Главная страница</div>} />
            </Routes>
        </MemoryRouter>,
    );

/** Находит первый вызов fetch с указанным HTTP-методом. */
const callByMethod = (method: string) =>
    fetchMock.mock.calls.find((c) => c[1]?.method === method);

const submitButton = () => screen.getByRole("button", { name: "Сменить пароль" });

const fill = (current: string, next: string, confirm: string) => {
    fireEvent.change(screen.getByLabelText("Текущий пароль"), { target: { value: current } });
    fireEvent.change(screen.getByLabelText("Новый пароль"), { target: { value: next } });
    fireEvent.change(screen.getByLabelText("Повторите новый пароль"), { target: { value: confirm } });
};

beforeEach(() => {
    vi.clearAllMocks();
    fetchMock.mockReset();
    fetchMock.mockImplementation(defaultFetch);
    vi.stubGlobal("fetch", fetchMock);
    localStorage.clear();
});

afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
});

describe("ChangePassword — смена пароля", () => {
    it("отображает форму с полями и кнопкой", () => {
        renderChangePassword();

        expect(screen.getByText("Смена пароля")).toBeTruthy();
        expect(screen.getByLabelText("Текущий пароль")).toBeTruthy();
        expect(screen.getByLabelText("Новый пароль")).toBeTruthy();
        expect(screen.getByLabelText("Повторите новый пароль")).toBeTruthy();
        expect(submitButton()).toBeTruthy();
    });

    it("пустая отправка показывает ошибки обязательных полей и не делает запрос", async () => {
        renderChangePassword();

        fireEvent.click(submitButton());

        expect(await screen.findByText("Введите текущий пароль")).toBeTruthy();
        expect(await screen.findByText("Введите новый пароль")).toBeTruthy();
        // Текст ошибки подтверждения совпадает с текстом метки — ищем именно сообщение.
        expect(
            await screen.findByText("Повторите новый пароль", {
                selector: ".ant-form-item-explain-error",
            }),
        ).toBeTruthy();
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it("слишком короткий новый пароль не отправляется — минимум 6 символов", async () => {
        renderChangePassword();

        fill("oldpass", "123", "123");
        fireEvent.click(submitButton());

        expect(await screen.findByText("Минимум 6 символов")).toBeTruthy();
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it("несовпадение нового пароля и подтверждения не отправляется", async () => {
        renderChangePassword();

        fill("oldpass", "newpass1", "newpass2");
        fireEvent.click(submitButton());

        expect(await screen.findByText("Новый пароль и подтверждение не совпадают")).toBeTruthy();
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it("успешная смена: POST /auth/change-password, GET /auth/me и переход на главную", async () => {
        renderChangePassword();

        fill("oldpass", "newpass1", "newpass1");
        fireEvent.click(submitButton());

        await waitFor(() => expect(callByMethod("POST")).toBeTruthy());
        const post = callByMethod("POST")!;
        expect(post[0]).toBe("/api/auth/change-password");
        expect(JSON.parse((post[1] as RequestInit).body as string)).toEqual({
            current_password: "oldpass",
            new_password: "newpass1",
        });

        // После успеха личность обновляется (флаг must_change_password снят)...
        await waitFor(() =>
            expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith("/auth/me"))).toBe(true),
        );
        expect(localStorage.getItem("townhouse_user")).toContain("resident1");

        // ...и происходит переход на главную.
        expect(await screen.findByText("Главная страница")).toBeTruthy();
    });

    it("ошибка смены пароля показывается сообщением detail и остаётся на форме", async () => {
        fetchMock.mockResolvedValueOnce(json({ detail: "Неверный текущий пароль" }, 400));

        renderChangePassword();

        fill("wrong", "newpass1", "newpass1");
        fireEvent.click(submitButton());

        expect(await screen.findByText("Неверный текущий пароль")).toBeTruthy();
        expect(screen.queryByText("Главная страница")).toBeNull();
    });
});
