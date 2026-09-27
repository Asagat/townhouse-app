// src/components/writeoffs/WriteoffViewModal.test.tsx
// RTL-тесты модалки просмотра документа «Списание задолженностей»: загрузка шапки
// и строк распределения через authedFetch (GET {apiUrl}/writeoff_documents/{id}/items),
// сортировка строк по id, статус (Активен/Отменён), пустой документ, ошибка загрузки
// (с детализацией и без), передача JWT и отсутствие запроса без documentId.
// Реальной сети нет — глобальный fetch подменён мок-функцией.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { Refine } from "@refinedev/core";

import { WriteoffViewModal } from "./WriteoffViewModal";

const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });

const dataProvider: any = {
    custom: vi.fn(async () => ({ data: {} })),
    getList: vi.fn(async () => ({ data: [], total: 0 })),
    getOne: vi.fn(async () => ({ data: {} })),
    getMany: vi.fn(async () => ({ data: [] })),
    create: vi.fn(async () => ({ data: {} })),
    update: vi.fn(async () => ({ data: {} })),
    deleteOne: vi.fn(async () => ({ data: {} })),
    getApiUrl: () => "http://localhost:8000/api",
};

// Строки намеренно не по порядку id: компонент должен отсортировать по id по возрастанию.
const DOC = {
    document: {
        id: 55,
        writeoff_date: "2026-03-31",
        title: null,
        status: "new",
        created_by: 1,
        created_at: "2026-03-31T10:00:00",
        items_count: 2,
        total_allocated: 600,
    },
    items: [
        {
            id: 2,
            account_id: 20,
            account_number: "LS-0020",
            account_name: "Кв.20",
            services_type_id: 5,
            services_type: "Вывоз мусора",
            allocated: 400,
            balance_after: 100,
        },
        {
            id: 1,
            account_id: 10,
            account_number: null,
            account_name: null,
            services_type_id: 3,
            services_type: null,
            allocated: 200,
            balance_after: null,
        },
    ],
};

const renderModal = (documentId: number | undefined) =>
    render(
        <Refine dataProvider={dataProvider}>
            <WriteoffViewModal open documentId={documentId} onClose={vi.fn()} />
        </Refine>,
    );

beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn(async () => json(DOC)));
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("WriteoffViewModal", () => {
    it("загружает документ и строки распределения, сортируя их по id", async () => {
        renderModal(55);

        // Запрос к детализации строк документа.
        await screen.findByText(/Списание задолженностей № 55/u);
        const url = String((fetch as any).mock.calls[0][0]);
        expect(url).toContain("/writeoff_documents/55/items");

        // Шапка: дата, статус-плашка, итог.
        expect(screen.getByText("2026-03-31")).toBeTruthy();
        expect(screen.getByText("Активен")).toBeTruthy();
        expect(screen.getByText(/Распределено: 600,00 по 2 запись/u)).toBeTruthy();

        // Строки отсортированы по id (1 → 2), а не по порядку ответа.
        const bodyRows = document.querySelectorAll(".ant-table-tbody tr.ant-table-row");
        expect(bodyRows.length).toBe(2);
        const first = bodyRows[0] as HTMLElement;
        const second = bodyRows[1] as HTMLElement;
        // id=1: нет лицевого счёта → показывается account_id.
        expect(first.textContent).toContain("10");
        expect(first.textContent).toContain("200,00");
        // id=2: лицевой счёт с именем и услугой.
        expect(second.textContent).toContain("LS-0020 (Кв.20)");
        expect(second.textContent).toContain("Вывоз мусора");
        expect(second.textContent).toContain("400,00");
    });

    it("отменённый документ показывается плашкой «Отменён»", async () => {
        vi.stubGlobal(
            "fetch",
            vi.fn(async () =>
                json({ document: { ...DOC.document, status: "cancelled" }, items: DOC.items }),
            ),
        );
        renderModal(55);

        expect(await screen.findByText("Отменён")).toBeTruthy();
    });

    it("документ без строк распределения показывает пояснение", async () => {
        vi.stubGlobal(
            "fetch",
            vi.fn(async () =>
                json({
                    document: { ...DOC.document, items_count: 0, total_allocated: 0 },
                    items: [],
                }),
            ),
        );
        renderModal(55);

        expect(
            await screen.findByText(
                "По документу нет строк распределения (задолженность отсутствовала).",
            ),
        ).toBeTruthy();
        expect(screen.getByText(/Распределено: 0,00 по 0 запись/u)).toBeTruthy();
    });

    it("ошибка загрузки: показывает detail из ответа", async () => {
        vi.stubGlobal(
            "fetch",
            vi.fn(async () => json({ detail: "Документ списания не найден" }, 404)),
        );
        renderModal(55);

        expect(await screen.findByText("Документ списания не найден")).toBeTruthy();
    });

    it("некорректный ответ без JSON: показывает текст по умолчанию", async () => {
        vi.stubGlobal(
            "fetch",
            vi.fn(async () => new Response("oops", { status: 500 })),
        );
        renderModal(55);

        expect(await screen.findByText("Не удалось загрузить документ списания")).toBeTruthy();
    });

    it("без documentId запрос не выполняется", async () => {
        renderModal(undefined);

        // Модалка открыта (заголовок без номера), но детализацию не запрашиваем.
        expect(await screen.findByText(/Списание задолженностей/u)).toBeTruthy();
        expect((fetch as any).mock.calls.length).toBe(0);
    });

    it("передаёт JWT из localStorage в заголовке Authorization", async () => {
        localStorage.setItem("townhouse_token", "jwt-123");
        renderModal(55);

        await screen.findByText(/Списание задолженностей № 55/u);
        const init = (fetch as any).mock.calls[0][1] as RequestInit;
        expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer jwt-123");
    });
});
