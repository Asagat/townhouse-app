// src/components/receipts/ReceiptsModal.test.tsx
// RTL-тесты модалки «Квитанции за период» (3.2): счётчик квитанций под удаление
// (X-Total-Count), формирование (POST /generate), удаление (DELETE /bulk_delete),
// скачивание ZIP (POST /bulk_pdf). Сеть — мок fetch; Refine — мок dataProvider.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { Refine } from "@refinedev/core";

import { ReceiptsModal } from "./ReceiptsModal";

const json = (body: unknown, total?: number) =>
    new Response(JSON.stringify(body), {
        status: 200,
        headers: {
            "Content-Type": "application/json",
            ...(total != null ? { "X-Total-Count": String(total) } : {}),
        },
    });

/** Мок-провайдер Refine: custom используется useCustomMutation (generate/delete/download). */
const makeDataProvider = (customImpl?: (args: any) => any) => {
    const custom = vi.fn(customImpl ?? (async () => ({ data: { created: [{ id: 1 }, { id: 2 }] } })));
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
            <ReceiptsModal open onClose={onClose} onSaved={onSaved} />
        </Refine>,
    );
    return { onClose, onSaved };
};

beforeEach(() => {
    vi.stubGlobal(
        "fetch",
        vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => {
            const u = String(url);
            if (u.includes("bulk_delete")) return json({ deleted: 3 });
            if (u.includes("bulk_pdf"))
                return new Response(new Blob(["zip"]), { status: 200, headers: { "Content-Type": "application/zip" } });
            // Запрос счётчика квитанций под удаление.
            return json([], 5);
        }),
    );
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("ReceiptsModal", () => {
    it("показывает число квитанций под удаление из X-Total-Count", async () => {
        renderModal(makeDataProvider());
        expect(await screen.findByText("Будет удалено квитанций: 5")).toBeTruthy();
        const firstUrl = String((fetch as any).mock.calls[0][0]);
        expect(firstUrl).toContain("/receipt_documents?");
        expect(firstUrl).toContain("period_month=");
    });

    it("«Сформировать» вызывает POST /receipt_documents/generate и закрывает окно", async () => {
        const dp = makeDataProvider();
        const { onClose, onSaved } = renderModal(dp);
        await screen.findByText("Будет удалено квитанций: 5");

        fireEvent.click(screen.getByRole("button", { name: "Сформировать" }));

        await waitFor(() => expect(dp.custom).toHaveBeenCalled());
        const args = dp.custom.mock.calls[0][0];
        expect(String(args.url)).toContain("/receipt_documents/generate");
        expect(args.method).toBe("post");
        // Refine передаёт тело как payload (в компоненте — values).
        expect(args.payload ?? args.values).toMatchObject({ comment: "" });
        await waitFor(() => expect(onSaved).toHaveBeenCalled());
        expect(onClose).toHaveBeenCalled();
    });

    it("ошибка генерации (409) показывает detail", async () => {
        const dp = makeDataProvider(async () => {
            throw { response: { data: { detail: "За данный период уже имеется аналогичный документ" } } };
        });
        renderModal(dp);
        await screen.findByText("Будет удалено квитанций: 5");

        fireEvent.click(screen.getByRole("button", { name: "Сформировать" }));
        expect(
            await screen.findByText("За данный период уже имеется аналогичный документ"),
        ).toBeTruthy();
    });

    it("«Удалить» после подтверждения шлёт DELETE с годом и месяцем", async () => {
        const dp = makeDataProvider();
        const { onSaved } = renderModal(dp);
        await screen.findByText("Будет удалено квитанций: 5");

        // Кнопка-триггер удаления в футере, затем подтверждение в Popconfirm.
        fireEvent.click(screen.getByRole("button", { name: "Удалить" }));
        const confirm = await waitFor(() => {
            const btn = document.querySelector(".ant-popover .ant-btn-primary") as HTMLElement | null;
            expect(btn).not.toBeNull();
            return btn as HTMLElement;
        });
        fireEvent.click(confirm);

        await waitFor(() => {
            const del = (fetch as any).mock.calls.find((c: any[]) => String(c[0]).includes("bulk_delete"));
            expect(del).toBeTruthy();
            const url = String(del[0]);
            expect(url).toContain("year=");
            expect(url).toContain("&month=");
        });
        await waitFor(() => expect(onSaved).toHaveBeenCalled());
    });
});
