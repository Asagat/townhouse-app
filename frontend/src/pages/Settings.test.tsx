// src/pages/Settings.test.tsx
// RTL-тесты страницы «Префиксы» (Settings): загрузка префикса лицевого счёта
// (http.get), сохранение (http.put), валидация обязательного поля и показ ошибки
// загрузки. Сеть полностью подменяется моком axios-инстанса `auth/http` — реальных
// запросов нет.

import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { Settings } from "./Settings";
import { http } from "../auth/http";

// Axios-инстанс страницы подменяем целиком: Settings ходит только в
// /api/auth/settings (get для чтения, put для сохранения).
vi.mock("../auth/http", () => ({
    apiUrl: "/api",
    http: {
        get: vi.fn(),
        put: vi.fn(),
    },
}));

const getMock = http.get as unknown as Mock;
const putMock = http.put as unknown as Mock;

beforeEach(() => {
    vi.clearAllMocks();
    getMock.mockResolvedValue({
        data: { settings: { account_number_prefix: "LS-" } },
    });
    putMock.mockResolvedValue({ data: {} });
});

describe("Settings — префиксы", () => {
    it("после загрузки показывает префикс лицевого счёта в поле", async () => {
        render(<Settings />);

        // Пока идёт загрузка — крутится Spin, формы ещё нет.
        expect(document.querySelector(".ant-spin")).not.toBeNull();

        expect(await screen.findByDisplayValue("LS-")).toBeTruthy();
        // Значение запрошено именно с эндпоинта настроек.
        expect(getMock).toHaveBeenCalledWith("/api/auth/settings");
    });

    it("показывает карточку «Лицевые счета» и кнопку «Сохранить»", async () => {
        render(<Settings />);
        await screen.findByDisplayValue("LS-");

        expect(screen.getByText("Лицевые счета")).toBeTruthy();
        expect(screen.getByRole("button", { name: "Сохранить" })).toBeTruthy();
    });

    it("сохраняет префикс через http.put с переданными настройками", async () => {
        render(<Settings />);
        const input = await screen.findByDisplayValue("LS-");

        fireEvent.change(input, { target: { value: "LN-" } });
        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

        await waitFor(() =>
            expect(putMock).toHaveBeenCalledWith("/api/auth/settings", {
                settings: { account_number_prefix: "LN-" },
            }),
        );
    });

    it("не отправляет пустой префикс — срабатывает валидация required", async () => {
        render(<Settings />);
        const input = await screen.findByDisplayValue("LS-");

        fireEvent.change(input, { target: { value: "" } });
        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

        expect(await screen.findByText("Укажите префикс")).toBeTruthy();
        expect(putMock).not.toHaveBeenCalled();
    });

    it("показывает ошибку загрузки в Alert с текстом detail", async () => {
        getMock.mockRejectedValueOnce({
            response: { data: { detail: "Нет доступа к настройкам" } },
        });

        render(<Settings />);

        expect(await screen.findByText("Нет доступа к настройкам")).toBeTruthy();
    });
});
