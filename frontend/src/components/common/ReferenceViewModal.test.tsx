// src/components/common/ReferenceViewModal.test.tsx
// RTL-тесты read-only просмотра связанной записи (2.21): загрузка метаданных
// (`/api/meta/{resource}`) и самой записи (`/api/{resource}/{id}`) через authedFetch
// (мок fetch), отрисовка полей в режиме просмотра (disabled), закрытие окна и
// обработка ошибки загрузки (message.error + onClose).

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { message } from "antd";

import { ReferenceViewModal } from "./ReferenceViewModal";

const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });

// Метаданные полей ресурса owners и сама запись (id=42).
const FIELDS = [
    { name: "full_name", label: "ФИО", type: "string", required: true },
    { name: "phone", label: "Телефон", type: "string", required: false },
];

const RECORD = { id: 42, full_name: "Иванов Иван", phone: "7011234567" };

/** Мок authedFetch: отдаёт метаданные и запись; фиксирует все URL. */
const stubApi = () =>
    vi.fn(async (url: RequestInfo | URL) => {
        const u = String(url);
        if (u.includes("/meta/owners")) return json({ fields: FIELDS });
        if (u.includes("/owners/42")) return json(RECORD);
        return json({});
    });

beforeEach(() => {
    // Гасим статический message (иначе предупреждения antd о контексте) и проверяем вызовы.
    vi.spyOn(message, "error").mockImplementation(() => undefined as any);
});

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
});

describe("ReferenceViewModal", () => {
    it("загружает метаданные и запись, показывает заголовок с подписью ресурса", async () => {
        const fetchMock = stubApi();
        vi.stubGlobal("fetch", fetchMock);
        render(<ReferenceViewModal resource="owners" id={42} onClose={vi.fn()} />);

        // Подпись ресурса «owners» — «Контрагент» (RESOURCE_LABELS).
        expect(await screen.findByText("Просмотр: Контрагент")).toBeTruthy();

        const urls = fetchMock.mock.calls.map((call) => String(call[0]));
        expect(urls.some((u) => u.includes("/api/meta/owners"))).toBe(true);
        expect(urls.some((u) => u.includes("/api/owners/42"))).toBe(true);
    });

    it("отрисовывает поля записи в режиме просмотра (disabled)", async () => {
        vi.stubGlobal("fetch", stubApi());
        render(<ReferenceViewModal resource="owners" id={42} onClose={vi.fn()} />);

        // Текстовое поле — как есть; телефон — с маской «+7(XXX)XXX-XX-XX».
        const nameInput = (await screen.findByDisplayValue("Иванов Иван")) as HTMLInputElement;
        expect(nameInput.disabled).toBe(true);

        const phoneInput = screen.getByDisplayValue("+7(701)123-45-67") as HTMLInputElement;
        expect(phoneInput.disabled).toBe(true);

        // Подписи полей формы присутствуют.
        expect(screen.getByText("ФИО")).toBeTruthy();
        expect(screen.getByText("Телефон")).toBeTruthy();
    });

    it("кнопка «Закрыть» вызывает onClose", async () => {
        vi.stubGlobal("fetch", stubApi());
        const onClose = vi.fn();
        render(<ReferenceViewModal resource="owners" id={42} onClose={onClose} />);

        const closeButton = await screen.findByRole("button", { name: "Закрыть" });
        fireEvent.click(closeButton);

        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("ошибка загрузки: показывает detail из ответа и закрывает окно", async () => {
        vi.stubGlobal(
            "fetch",
            vi.fn(async () => json({ detail: "Нет доступа к ресурсу" }, 500)),
        );
        const onClose = vi.fn();
        render(<ReferenceViewModal resource="owners" id={42} onClose={onClose} />);

        await waitFor(() =>
            expect(message.error).toHaveBeenCalledWith("Нет доступа к ресурсу"),
        );
        expect(onClose).toHaveBeenCalled();
    });

    it("до получения ответа показывает индикатор загрузки", async () => {
        // Управляемые промисы: запросы «висят» до нашего сигнала.
        const resolvers: Array<(response: Response) => void> = [];
        vi.stubGlobal(
            "fetch",
            vi.fn(() => new Promise<Response>((resolve) => resolvers.push(resolve))),
        );

        render(<ReferenceViewModal resource="owners" id={42} onClose={vi.fn()} />);

        expect(document.querySelector(".ant-spin")).not.toBeNull();

        // Завершаем запросы, чтобы не оставлять висящих промисов.
        await act(async () => {
            resolvers.forEach((resolve) => resolve(json({ fields: [] })));
        });
    });
});
