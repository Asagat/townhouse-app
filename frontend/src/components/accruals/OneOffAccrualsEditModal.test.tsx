// src/components/accruals/OneOffAccrualsEditModal.test.tsx
// RTL-тесты модалки «Персональное начисление» (документ oneoff):
//   — загрузка строк документа (useCustom GET /accrual_documents/:id/details),
//     подписи строк и подписи-фолбэки, комментарий шапки и «Итог»;
//   — правка суммы и сохранение PUT /accrual_documents/:id/amounts
//     (тело: rows[{id, amount}], comment — trim или null);
//   — успех (сообщение, onSaved, onClose) и ошибка с detail;
//   — режим «только просмотр» (readonly): поля заблокированы, доступно лишь «Закрыть».
// Реальной сети нет: Refine-запросы обслуживает мок dataProvider (custom).

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { Refine } from "@refinedev/core";
import { message } from "antd";

import { OneOffAccrualsEditModal } from "./OneOffAccrualsEditModal";

/** Две строки: обычная (с подписями) и «сырая» (без вложенных account/apartment/services_type). */
const DETAILS = {
    document: { id: 10, comment: "Комментарий бухгалтера" },
    accruals: [
        {
            id: 101,
            account_id: 1,
            account: { account_number: "LS/0001" },
            apartment: { apartment_number: 13 },
            services_type: { services_type: "Вывоз мусора" },
            amount: 114500,
        },
        {
            id: 102,
            account_id: 2,
            account: null,
            apartment: null,
            services_type: null,
            services_type_id: 7,
            amount: 200,
        },
    ],
};

/** Мок-провайдер Refine: детали и сохранение идут через dataProvider.custom. */
const makeDataProvider = (customImpl?: (args: any) => any) => {
    const custom = vi.fn(
        customImpl ??
            (async (args: any) => {
                const url = String(args.url);
                if (url.includes("/details")) return { data: DETAILS };
                if (url.includes("/amounts")) return { data: { updated: 2 } };
                return { data: {} };
            }),
    );
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

const renderModal = (
    dp: any,
    props: Partial<{ documentId: number; readonly: boolean }> = {},
) => {
    const onClose = vi.fn();
    const onSaved = vi.fn();
    // retry:false — иначе react-query ретраит неудачный запрос и onError не успевает.
    render(
        <Refine
            dataProvider={dp}
            options={{
                reactQuery: { clientConfig: { defaultOptions: { queries: { retry: false } } } },
            }}
        >
            <OneOffAccrualsEditModal
                open
                documentId={10}
                onClose={onClose}
                onSaved={onSaved}
                {...props}
            />
        </Refine>,
    );
    return { onClose, onSaved };
};

/** Аргументы, с которыми вызывался dataProvider.custom (url содержит подстроку). */
const customCallTo = (dp: any, needle: string): any | undefined =>
    dp.custom.mock.calls.map((c: any[]) => c[0]).find((a: any) => String(a.url).includes(needle));

/** Инпуты InputNumber в порядке строк (по одному на строку). */
const amountInputs = () =>
    Array.from(document.querySelectorAll(".ant-input-number-input")) as HTMLInputElement[];

beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
});

afterEach(() => {
    vi.unstubAllGlobals();
    // Статические сообщения antd живут вне дерева RTL — чистим вручную между тестами.
    message.destroy();
});

describe("OneOffAccrualsEditModal — загрузка", () => {
    it("грузит детали документа: строки, подписи, фолбэки, комментарий и итог", async () => {
        const dp = makeDataProvider();
        renderModal(dp);

        expect(await screen.findByText("Редактирование персонального начисления")).toBeTruthy();
        expect(await screen.findByText("№ 13 (LS/0001)")).toBeTruthy();
        expect(screen.getByText("Вывоз мусора")).toBeTruthy();
        // Строка без связанных apartment/account и services_type → подписи-фолбэки.
        expect(screen.getByText("счёт #2")).toBeTruthy();
        expect(screen.getByText("услуга #7")).toBeTruthy();
        // Комментарий шапки подставлен в поле «Примечание».
        expect(await screen.findByDisplayValue("Комментарий бухгалтера")).toBeTruthy();
        // Итог = 114 500 + 200.
        expect(screen.getByText("114 700,00")).toBeTruthy();

        const details = customCallTo(dp, "/details");
        expect(details).toBeTruthy();
        expect(details.method).toBe("get");
        expect(String(details.url)).toContain("/accrual_documents/10/details");
    });
});

describe("OneOffAccrualsEditModal — сохранение", () => {
    it("правит сумму и шлёт PUT /accrual_documents/10/amounts с комментарием", async () => {
        const dp = makeDataProvider();
        const { onClose, onSaved } = renderModal(dp);
        await screen.findByText("№ 13 (LS/0001)");

        // Меняем сумму первой строки и примечание (с лишними пробелами — обрезаются).
        fireEvent.change(amountInputs()[0], { target: { value: "200000" } });
        fireEvent.change(screen.getByDisplayValue("Комментарий бухгалтера"), {
            target: { value: "  Обновлённый комментарий  " },
        });
        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

        await waitFor(() => expect(customCallTo(dp, "/amounts")).toBeTruthy());
        const put = customCallTo(dp, "/amounts");
        expect(put.method).toBe("put");
        expect(String(put.url)).toContain("/accrual_documents/10/amounts");

        const payload = put.payload ?? put.values;
        expect(payload.rows).toEqual([
            { id: 101, amount: 200000 },
            { id: 102, amount: 200 },
        ]);
        expect(payload.comment).toBe("Обновлённый комментарий");

        expect(await screen.findByText("Изменения сохранены")).toBeTruthy();
        await waitFor(() => expect(onSaved).toHaveBeenCalled());
        expect(onClose).toHaveBeenCalled();
    });

    it("пустое примечание отправляется как null", async () => {
        const dp = makeDataProvider();
        renderModal(dp);
        const comment = await screen.findByDisplayValue("Комментарий бухгалтера");

        fireEvent.change(comment, { target: { value: "   " } });
        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

        await waitFor(() => expect(customCallTo(dp, "/amounts")).toBeTruthy());
        const put = customCallTo(dp, "/amounts");
        const payload = put.payload ?? put.values;
        expect(payload.comment).toBeNull();
    });

    it("ошибка сохранения показывает detail из ответа сервера", async () => {
        const dp = makeDataProvider(async (args: any) => {
            if (String(args.url).includes("/details")) return { data: DETAILS };
            throw { response: { data: { detail: "Нет прав на изменение сумм" } } };
        });
        renderModal(dp);
        await screen.findByText("№ 13 (LS/0001)");

        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

        expect(await screen.findByText("Нет прав на изменение сумм")).toBeTruthy();
    });
});

describe("OneOffAccrualsEditModal — просмотр (readonly)", () => {
    it("поля заблокированы, доступна только кнопка «Закрыть»", async () => {
        const dp = makeDataProvider();
        const { onClose } = renderModal(dp, { readonly: true });

        expect(await screen.findByText("Просмотр персонального начисления")).toBeTruthy();
        expect(await screen.findByText("№ 13 (LS/0001)")).toBeTruthy();
        expect(screen.queryByRole("button", { name: "Сохранить" })).toBeNull();
        expect(screen.queryByRole("button", { name: "Отмена" })).toBeNull();

        expect(amountInputs()[0].disabled).toBe(true);
        const textarea = screen.getByDisplayValue(
            "Комментарий бухгалтера",
        ) as HTMLTextAreaElement;
        expect(textarea.disabled).toBe(true);

        fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
        expect(onClose).toHaveBeenCalled();
    });
});
