// src/components/accruals/AccrualsCalculationModal.test.tsx
// RTL-тесты модалки расчёта/начисления коммунальных услуг (AccrualsCalculationModal):
// — создание: предпросмотр (GET /accruals_register/calculate) и начисление
//   (POST /accruals_register/generate) — клиент шлёт только идентификаторы строк
//   (account_id + services_type_id), сумма/тариф/потребление считаются на сервере;
// — блокировка кнопки при снятом выделении, проверка тарифов по услугам;
// — редактирование: загрузка документа (GET /accrual_documents/:id/details)
//   и пересоздание строк (PUT /accrual_documents/:id/full);
// — режим «только просмотр» (readonly) и обработка ошибок расчёта.
// Refine — мок dataProvider (custom); прямых сетевых вызовов компонент не делает,
// fetch заглушён «на всякий случай».

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { Refine } from "@refinedev/core";
import { MemoryRouter } from "react-router-dom";
import { message } from "antd";

import { AccrualsCalculationModal } from "./AccrualsCalculationModal";
import type { AccrualPreviewRow } from "../../types";

/** Строки предпросмотра: одна услуга («Вывоз мусора») на две квартиры. */
const PREVIEW_ROWS: AccrualPreviewRow[] = [
    {
        row_number: 1,
        account_id: 10,
        account_id_label: "Кв.1 (LS/0001)",
        services_type_id: 5,
        services_type_id_label: "Вывоз мусора",
        tariff_id: 3,
        tariff_id_label: "Тариф №3",
        past_reading_value: null,
        current_reading_value: null,
        consumption: 0,
        amount: 1145,
    },
    {
        row_number: 2,
        account_id: 11,
        account_id_label: "Кв.2 (LS/0002)",
        services_type_id: 5,
        services_type_id_label: "Вывоз мусора",
        tariff_id: 3,
        tariff_id_label: "Тариф №3",
        past_reading_value: 10,
        current_reading_value: 15,
        consumption: 5,
        amount: 5725,
    },
];

/**
 * Мок-провайдер Refine: компонент использует useApiUrl/useCustom/useCustomMutation,
 * все три идут в dataProvider (custom/getApiUrl). Реальные запросы не выполняются.
 */
const makeDataProvider = (impl?: (args: any) => any) => {
    const custom = vi.fn(
        impl ??
            (async (args: any) => {
                const url = String(args.url);
                if (url.includes("/accruals_register/calculate")) {
                    return { data: { rows: PREVIEW_ROWS } };
                }
                if (url.includes("/accruals_register/generate")) {
                    return { data: { created: [1, 2], document: { id: 42 } } };
                }
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

/** Аргументы, с которыми вызывался dataProvider.custom (url содержит подстроку). */
const customCallTo = (dp: any, needle: string): any | undefined =>
    dp.custom.mock.calls
        .map((c: any[]) => c[0])
        .find((a: any) => String(a.url).includes(needle));

const renderModal = (
    dp: any,
    props: Partial<{ documentId: number; readonly: boolean }> = {},
) => {
    const onClose = vi.fn();
    const onSaved = vi.fn();
    // retry:false — иначе react-query ретраит неудачный запрос ~7с и onError не успевает
    // до таймаута findByText (Refine сам retry не отключает).
    render(
        <MemoryRouter>
            <Refine
                dataProvider={dp}
                options={{
                    reactQuery: {
                        clientConfig: { defaultOptions: { queries: { retry: false } } },
                    },
                }}
            >
                <AccrualsCalculationModal
                    open
                    onClose={onClose}
                    onSaved={onSaved}
                    {...props}
                />
            </Refine>
        </MemoryRouter>,
    );
    return { onClose, onSaved };
};

beforeEach(() => {
    vi.stubGlobal(
        "fetch",
        vi.fn(
            async () =>
                new Response(JSON.stringify({}), {
                    status: 200,
                    headers: { "Content-Type": "application/json" },
                }),
        ),
    );
});

afterEach(() => {
    vi.unstubAllGlobals();
    // Статические сообщения antd живут вне дерева RTL — чистим вручную между тестами.
    message.destroy();
});

describe("AccrualsCalculationModal — создание", () => {
    it("загружает предпросмотр: строки, суммы и счётчик выбранных", async () => {
        const dp = makeDataProvider();
        renderModal(dp);

        expect(await screen.findByText("Кв.1 (LS/0001)")).toBeTruthy();
        expect(screen.getByText("Кв.2 (LS/0002)")).toBeTruthy();
        // Сумма в денежном формате (неразрывный пробел нормализуется RTL).
        expect(screen.getByText("1 145,00")).toBeTruthy();

        const calc = customCallTo(dp, "/accruals_register/calculate");
        expect(calc).toBeTruthy();
        expect(calc.method).toBe("get");
        expect(typeof calc.query?.year).toBe("number");
        expect(typeof calc.query?.month).toBe("number");

        // По умолчанию выбраны все строки.
        expect(
            screen.getByRole("button", { name: "Начислить выбранные (2)" }),
        ).toBeTruthy();
    });

    it("начисление шлёт POST /generate только с id строк (сумма считается на сервере)", async () => {
        const dp = makeDataProvider();
        const { onClose, onSaved } = renderModal(dp);
        await screen.findByText("Кв.1 (LS/0001)");

        fireEvent.click(
            screen.getByRole("button", { name: "Начислить выбранные (2)" }),
        );

        await waitFor(() => {
            const gen = customCallTo(dp, "/accruals_register/generate");
            expect(gen).toBeTruthy();
            expect(gen.method).toBe("post");
            // В подборке только идентификаторы: без суммы, тарифа, потребления и показаний.
            expect(gen.payload.selections).toEqual([
                { account_id: 10, services_type_id: 5 },
                { account_id: 11, services_type_id: 5 },
            ]);
            for (const sel of gen.payload.selections) {
                expect(Object.keys(sel).sort()).toEqual([
                    "account_id",
                    "services_type_id",
                ]);
            }
            expect(gen.payload.draft_tariffs).toEqual([]);
            expect(typeof gen.payload.year).toBe("number");
            expect(typeof gen.payload.month).toBe("number");
        });

        expect(await screen.findByText(/Создан документ начислений №42/)).toBeTruthy();
        await waitFor(() => expect(onSaved).toHaveBeenCalled());
        expect(onClose).toHaveBeenCalled();
    });

    it("снятие выделения всех строк блокирует кнопку начисления", async () => {
        const dp = makeDataProvider();
        renderModal(dp);
        await screen.findByText("Кв.1 (LS/0001)");

        // Заголовочный чекбокс «выбрать все» — первый в таблице.
        const headerCheckbox = screen.getAllByRole("checkbox")[0] as HTMLInputElement;
        fireEvent.click(headerCheckbox);

        const btn = (await screen.findByRole("button", {
            name: "Начислить выбранные (0)",
        })) as HTMLButtonElement;
        expect(btn.disabled).toBe(true);
    });

    it("«Проверить тарифы» показывает применяемый тариф по услугам", async () => {
        const dp = makeDataProvider();
        renderModal(dp);
        await screen.findByText("Кв.1 (LS/0001)");

        fireEvent.click(screen.getByRole("button", { name: "Проверить тарифы" }));

        await waitFor(() =>
            expect(screen.getAllByText("Применяется тариф").length).toBeGreaterThan(0),
        );
        expect(screen.getAllByText("Вывоз мусора").length).toBeGreaterThan(0);
    });

    it("ошибка расчёта показывается сообщением с текстом detail", async () => {
        const dp = makeDataProvider(async () => {
            throw { response: { data: { detail: "Нет доступа к расчёту начислений" } } };
        });
        renderModal(dp);

        expect(
            await screen.findByText("Нет доступа к расчёту начислений"),
        ).toBeTruthy();
    });
});

describe("AccrualsCalculationModal — редактирование", () => {
    it("подгружает документ и сохраняет PUT /full, пересоздавая строки по id", async () => {
        const dp = makeDataProvider(async (args: any) => {
            const url = String(args.url);
            if (url.includes("/details")) {
                return {
                    data: {
                        year: 2026,
                        month: 3,
                        selections: [{ account_id: 11, services_type_id: 5 }],
                        document: { id: 99, comment: "Комментарий бухгалтера" },
                    },
                };
            }
            if (url.includes("/accruals_register/calculate")) {
                return { data: { rows: PREVIEW_ROWS } };
            }
            if (url.includes("/accrual_documents/99/full")) {
                return { data: { updated: [{ id: 1 }] } };
            }
            return { data: {} };
        });
        const { onClose, onSaved } = renderModal(dp, { documentId: 99 });

        expect(await screen.findByText("Редактирование документа начислений")).toBeTruthy();
        // Комментарий документа подставлен в поле «Примечание».
        expect(await screen.findByDisplayValue("Комментарий бухгалтера")).toBeTruthy();
        // Восстановлен выбор строк: только строка квартиры 11.
        const saveBtn = await screen.findByRole("button", {
            name: "Сохранить изменения (1)",
        });

        fireEvent.click(saveBtn);

        await waitFor(() => {
            const put = customCallTo(dp, "/accrual_documents/99/full");
            expect(put).toBeTruthy();
            expect(put.method).toBe("put");
            expect(put.payload.selections).toEqual([
                { account_id: 11, services_type_id: 5 },
            ]);
            expect(put.payload.comment).toBe("Комментарий бухгалтера");
            expect(put.payload.draft_tariffs).toEqual([]);
            // Дата начисления — первое число выбранных года/месяца документа.
            expect(put.payload.accrual_date).toBe("2026-03-01");
        });

        await waitFor(() => expect(onSaved).toHaveBeenCalled());
        expect(onClose).toHaveBeenCalled();
    });
});

describe("AccrualsCalculationModal — просмотр (readonly)", () => {
    it("нет выбора строк и сохранения, доступна только кнопка «Закрыть»", async () => {
        const dp = makeDataProvider(async (args: any) => {
            const url = String(args.url);
            if (url.includes("/details")) {
                return {
                    data: {
                        year: 2026,
                        month: 3,
                        selections: [{ account_id: 10, services_type_id: 5 }],
                        document: { id: 99, comment: "" },
                    },
                };
            }
            if (url.includes("/accruals_register/calculate")) {
                return { data: { rows: PREVIEW_ROWS } };
            }
            return { data: {} };
        });
        const { onClose } = renderModal(dp, { documentId: 99, readonly: true });

        expect(await screen.findByText("Просмотр документа начислений")).toBeTruthy();
        expect(await screen.findByText("Кв.1 (LS/0001)")).toBeTruthy();

        expect(screen.queryByRole("button", { name: /Сохранить изменения/ })).toBeNull();
        expect(screen.queryByRole("button", { name: /Начислить/ })).toBeNull();
        expect(screen.queryByRole("button", { name: "Проверить тарифы" })).toBeNull();
        // Колонки выбора строк нет — чекбоксов в модалке не должно быть.
        expect(document.querySelector(".ant-checkbox")).toBeNull();

        fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
        expect(onClose).toHaveBeenCalled();
    });
});
