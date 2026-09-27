// src/pages/ResidentSettings.test.tsx
// RTL-тесты страницы «Настройки жителя» (Б2): загрузка контактных данных в форму
// (ФИО/телефон/e-mail/доп. контакты), логин только для чтения, сохранение через
// PATCH /me/contacts с телом формы, валидация (обязательное ФИО и формат e-mail),
// показ ошибок загрузки/сохранения в Alert и переход к смене пароля.
//
// Refine обёрнут мок-провайдерами (страница использует useApiUrl/useLogout) —
// реальной сети нет: глобальный fetch подменён vi.stubGlobal.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { Refine } from "@refinedev/core";

import { ResidentSettings } from "./ResidentSettings";

const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });

// Телефон приходит локальным номером (10 цифр) и в форме показывается в маске.
const CONTACTS = {
    full_name: "Иванов Иван",
    phone: "9001234567",
    email: "ivan@example.com",
    contact_info: "Доп. контакт: 8-900-000-00-00",
    login: "resident1",
};

// Подмена сети: GET/PATCH /me/contacts. Прочие пути — пустой ok-ответ.
const defaultFetch = (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/me/contacts")) {
        if ((init?.method ?? "GET").toUpperCase() === "PATCH") {
            return Promise.resolve(json({ ...CONTACTS }));
        }
        return Promise.resolve(json(CONTACTS));
    }
    return Promise.resolve(json({}));
};

const fetchMock = vi.fn(defaultFetch);

// Минимальный провайдер данных: useApiUrl вызывает getApiUrl().
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

// useLogout обращается к authProvider.logout — держим мок, чтобы никуда не ходить.
const mockAuthProvider: any = {
    login: vi.fn(),
    logout: vi.fn(async () => ({ success: true })),
    check: vi.fn(async () => ({ authenticated: true })),
    getIdentity: vi.fn(async () => ({ id: 1, name: "Житель" })),
    getPermissions: vi.fn(async () => []),
    onError: vi.fn(async () => ({})),
};

const renderSettings = () =>
    render(
        <MemoryRouter initialEntries={["/"]}>
            <Refine dataProvider={mockDataProvider} authProvider={mockAuthProvider}>
                <Routes>
                    <Route path="/" element={<ResidentSettings />} />
                    <Route path="/change-password" element={<div>Страница смены пароля</div>} />
                </Routes>
            </Refine>
        </MemoryRouter>,
    );

/** Находит первый вызов fetch с указанным HTTP-методом (без метода — GET). */
const callByMethod = (method: string) =>
    fetchMock.mock.calls.find(
        (c) => (c[1]?.method ?? "GET").toUpperCase() === method,
    );

beforeEach(() => {
    vi.clearAllMocks();
    fetchMock.mockReset();
    fetchMock.mockImplementation(defaultFetch);
    vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("ResidentSettings — контактные данные", () => {
    it("загружает контакты в форму: ФИО, телефон, e-mail и доп. контакты", async () => {
        renderSettings();

        // Пока идёт загрузка — крутится Spin, формы ещё нет.
        expect(document.querySelector(".ant-spin")).not.toBeNull();

        expect(await screen.findByDisplayValue("Иванов Иван")).toBeTruthy();
        // Телефон показан в маске «+7(XXX)XXX-XX-XX».
        expect(screen.getByDisplayValue("+7(900)123-45-67")).toBeTruthy();
        expect(screen.getByDisplayValue("ivan@example.com")).toBeTruthy();
        expect(screen.getByDisplayValue("Доп. контакт: 8-900-000-00-00")).toBeTruthy();

        // Данные запрошены именно с /me/contacts.
        expect(callByMethod("GET")?.[0]).toBe("/api/me/contacts");
    });

    it("логин показывается только для чтения (disabled)", async () => {
        renderSettings();

        const login = (await screen.findByDisplayValue("resident1")) as HTMLInputElement;
        expect(login.disabled).toBe(true);
    });

    it("сохранение отправляет PATCH /me/contacts с телом формы", async () => {
        renderSettings();
        await screen.findByDisplayValue("Иванов Иван");

        fireEvent.change(screen.getByLabelText("ФИО"), { target: { value: "Петров Пётр" } });
        // У кастомного PhoneField нет связи label↔input — берём поле по placeholder.
        fireEvent.change(screen.getByPlaceholderText("+7 (___) ___-__-__"), {
            target: { value: "79011112233" },
        });
        fireEvent.change(screen.getByLabelText("E-mail"), { target: { value: "petr@example.com" } });
        fireEvent.change(screen.getByLabelText("Доп. контакты"), { target: { value: "Тел. 2" } });

        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

        await waitFor(() => expect(callByMethod("PATCH")).toBeTruthy());
        const patch = callByMethod("PATCH")!;

        expect(patch[0]).toBe("/api/me/contacts");
        expect(JSON.parse((patch[1] as RequestInit).body as string)).toEqual({
            full_name: "Петров Пётр",
            // Телефон нормализован до 10 цифр (без кода страны) — так хранит форма.
            phone: "9011112233",
            email: "petr@example.com",
            contact_info: "Тел. 2",
        });
        // Успех подтверждается сообщением.
        expect(await screen.findByText("Контактные данные сохранены")).toBeTruthy();
    });

    it("пустое ФИО не отправляется — срабатывает валидация required", async () => {
        renderSettings();
        const name = await screen.findByLabelText("ФИО");

        fireEvent.change(name, { target: { value: "" } });
        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

        expect(await screen.findByText("Укажите ФИО")).toBeTruthy();
        expect(callByMethod("PATCH")).toBeUndefined();
    });

    it("некорректный e-mail не отправляется — срабатывает валидация формата", async () => {
        renderSettings();
        const email = await screen.findByLabelText("E-mail");

        fireEvent.change(email, { target: { value: "не-почта" } });
        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

        expect(await screen.findByText("Некорректный e-mail")).toBeTruthy();
        expect(callByMethod("PATCH")).toBeUndefined();
    });

    it("ошибка загрузки показывается в Alert с текстом detail", async () => {
        fetchMock.mockResolvedValueOnce(json({ detail: "Нет доступа к контактам" }, 403));

        renderSettings();

        expect(await screen.findByText("Нет доступа к контактам")).toBeTruthy();
    });

    it("ошибка сохранения показывается в Alert с текстом detail", async () => {
        renderSettings();
        await screen.findByDisplayValue("Иванов Иван");

        fetchMock.mockResolvedValueOnce(json({ detail: "ФИО обязательно" }, 400));
        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

        expect(await screen.findByText("ФИО обязательно")).toBeTruthy();
    });

    it("кнопка «Сменить пароль» уводит на /change-password", async () => {
        renderSettings();
        await screen.findByDisplayValue("Иванов Иван");

        fireEvent.click(screen.getByRole("button", { name: /Сменить пароль/u }));

        expect(await screen.findByText("Страница смены пароля")).toBeTruthy();
    });
});
