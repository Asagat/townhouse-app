// src/components/writeoffs/WriteOffsModal.test.tsx
// RTL-тесты модалки «Списание задолженностей»: запуск списания через
// useCustomMutation (POST {apiUrl}/writeoff_documents/run), отображение итоговой
// таблицы распределения по счетам, вариант «нет задолженности», обработка ошибки
// (detail из ответа) и закрытие окна. Реальной сети нет — dataProvider Refine
// подменён мок-функцией custom; сообщения antd message проверяются шпионами.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { Refine } from "@refinedev/core";
import { message } from "antd";

import { WriteOffsModal } from "./WriteOffsModal";
import { formatMoney } from "../../config/formatters";

/** Мок-провайдер Refine: списание идёт через dataProvider.custom (useCustomMutation). */
const makeDataProvider = (customImpl: (args: any) => any) => {
    const custom = vi.fn(customImpl);
    return {
        custom,
        getList: vi.fn(async () => ({ data: [], total: 0 })),
        getOne: vi.fn(async () => ({ data: {} })),
        getMany: vi.fn(async () => ({ data: [] })),
        create: vi.fn(async () => ({ data: {} })),
        update: vi.fn(async () => ({ data: {} })),
        deleteOne: vi.fn(async () => ({ data: {} })),
        getApiUrl: () => "http://localhost:8000/api",
    } as any;
};

const renderModal = (dataProvider: any, onClose = vi.fn(), onSaved = vi.fn()) => {
    render(
        <Refine dataProvider={dataProvider}>
            <WriteOffsModal open onClose={onClose} onSaved={onSaved} />
        </Refine>,
    );
    return { onClose, onSaved };
};

beforeEach(() => {
    vi.spyOn(message, "success").mockImplementation(() => undefined as any);
    vi.spyOn(message, "error").mockImplementation(() => undefined as any);
});

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
});

describe("WriteOffsModal", () => {
    it("«Выполнить списание» шлёт POST /writeoff_documents/run и показывает распределение", async () => {
        const dp = makeDataProvider(async () => ({
            data: {
                document: { id: 42, status: "new", total_allocated: 600 },
                processed: [
                    { account_id: 1, accrued: 900, available: 300, written_off: 400 },
                    { account_id: 2, accrued: 500, available: 250, written_off: 200 },
                ],
            },
        }));
        const { onSaved } = renderModal(dp);

        fireEvent.click(screen.getByRole("button", { name: "Выполнить списание" }));

        await waitFor(() => expect(dp.custom).toHaveBeenCalledTimes(1));
        const args = dp.custom.mock.calls[0][0];
        expect(String(args.url)).toContain("/writeoff_documents/run");
        expect(args.method).toBe("post");

        // Итоговая строка с номером документа и суммой распределения.
        expect(
            await screen.findByText(/Документ «Списание задолженностей» №42 \(new\)\./u),
        ).toBeTruthy();
        expect(screen.getByText(/Итог: списано 600,00 по 2 счетам\./u)).toBeTruthy();

        // Таблица распределения: ровно 2 строки счёта.
        const bodyRows = document.querySelectorAll(".ant-table-tbody tr.ant-table-row");
        expect(bodyRows.length).toBe(2);
        const first = bodyRows[0] as HTMLElement;
        expect(first.textContent).toContain("1");
        expect(first.textContent).toContain(formatMoney(900));
        expect(first.textContent).toContain(formatMoney(400));

        // Успех: сообщение и колбэк сохранения.
        expect(message.success).toHaveBeenCalledWith(
            `Списание выполнено (документ №42): распределено ${formatMoney(600)} по 2 счетам`,
        );
        expect(onSaved).toHaveBeenCalled();
    });

    it("нет задолженности: processed пустой — показывает подсказку и сообщение", async () => {
        const dp = makeDataProvider(async () => ({
            data: {
                document: { id: 7, status: "new", total_allocated: 0 },
                processed: [],
            },
        }));
        const { onSaved } = renderModal(dp);

        fireEvent.click(screen.getByRole("button", { name: "Выполнить списание" }));

        expect(
            await screen.findByText(
                "Активных лицевых счетов, по которым нужно распределить средства, нет.",
            ),
        ).toBeTruthy();
        expect(screen.getByText(/Итог: списано 0,00 по 0 счетам\./u)).toBeTruthy();
        expect(message.success).toHaveBeenCalledWith(
            "Списание выполнено: нет задолженности для распределения",
        );
        expect(onSaved).toHaveBeenCalled();
    });

    it("ошибка списания: показывает detail из ответа и не вызывает onSaved", async () => {
        const dp = makeDataProvider(async () => {
            throw { response: { data: { detail: "Списание уже выполняется" } } };
        });
        const { onSaved } = renderModal(dp);

        fireEvent.click(screen.getByRole("button", { name: "Выполнить списание" }));

        expect(await screen.findByText("Списание уже выполняется")).toBeTruthy();
        expect(message.error).toHaveBeenCalledWith("Списание уже выполняется");
        expect(onSaved).not.toHaveBeenCalled();
    });

    it("ошибка без detail: используется текст по умолчанию", async () => {
        const dp = makeDataProvider(async () => {
            throw {};
        });
        renderModal(dp);

        fireEvent.click(screen.getByRole("button", { name: "Выполнить списание" }));

        expect(await screen.findByText("Не удалось выполнить списание")).toBeTruthy();
        expect(message.error).toHaveBeenCalledWith("Не удалось выполнить списание");
    });

    it("кнопка «Закрыть» вызывает onClose и не запускает списание", () => {
        const dp = makeDataProvider(async () => ({ data: {} }));
        const { onClose } = renderModal(dp);

        fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));

        expect(onClose).toHaveBeenCalled();
        expect(dp.custom).not.toHaveBeenCalled();
    });
});
