// src/components/meter-readings/BulkReadingsModal.test.tsx
// RTL-тесты модалки массового ввода показаний (3.2): авто-выбор вида услуги,
// валидации, сбор payload (только заполненные строки), режим редактирования.
// Refine — мок dataProvider; сеть напрямую не используется (authedFetch не задействован).

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { Refine } from "@refinedev/core";

import { BulkReadingsModal } from "./BulkReadingsModal";

const APARTMENTS = [{ id: 1, apartment_number: 1, address: "ул. Тестовая, 1" }];

const makeDataProvider = (opts: { services: any[]; customImpl?: (args: any) => any }) => {
    const custom = vi.fn(
        opts.customImpl ??
            (async () => ({ data: { created: [{ id: 1 }], errors: [] } })),
    );
    return {
        custom,
        getList: vi.fn(async ({ resource }: any) => {
            if (resource === "apartments") return { data: APARTMENTS, total: APARTMENTS.length };
            if (resource === "services_type") return { data: opts.services, total: opts.services.length };
            return { data: [], total: 0 };
        }),
        getOne: vi.fn(async () => ({ data: {} })),
        getMany: vi.fn(async () => ({ data: [] })),
        create: vi.fn(async () => ({ data: {} })),
        update: vi.fn(async () => ({ data: {} })),
        deleteOne: vi.fn(async () => ({ data: {} })),
        getApiUrl: () => "http://localhost:8000/api",
    } as any;
};

const renderModal = (dp: any, props: Partial<{ documentId: number; readonly: boolean }> = {}) => {
    const onClose = vi.fn();
    const onSaved = vi.fn();
    render(
        <Refine dataProvider={dp}>
            <BulkReadingsModal open onClose={onClose} onSaved={onSaved} {...props} />
        </Refine>,
    );
    return { onClose, onSaved };
};

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("BulkReadingsModal — создание", () => {
    it("без видов услуг «Сохранить» просит выбрать услугу", async () => {
        const dp = makeDataProvider({ services: [] });
        renderModal(dp);
        await screen.findByText(/ул\. Тестовая, 1/u);
        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
        expect(await screen.findByText("Выберите вид услуги")).toBeTruthy();
    });

    it("вид услуги по умолчанию «Электричество»; без показаний — подсказка", async () => {
        const dp = makeDataProvider({ services: [{ id: 7, services_type: "Электричество" }] });
        renderModal(dp);
        // Авто-выбор услуги по умолчанию.
        expect(await screen.findByText("Электричество")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
        expect(await screen.findByText("Заполните хотя бы одно показание")).toBeTruthy();
    });

    it("сохраняет только заполненные показания (POST /meter_readings/bulk)", async () => {
        const dp = makeDataProvider({ services: [{ id: 7, services_type: "Электричество" }] });
        renderModal(dp);
        await screen.findByText(/ул\. Тестовая, 1/u);
        await screen.findByText("Электричество");

        const input = document.querySelector(".ant-input-number-input") as HTMLInputElement;
        fireEvent.change(input, { target: { value: "15" } });

        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
        await waitFor(() => expect(dp.custom).toHaveBeenCalled());
        const args = dp.custom.mock.calls[0][0];
        expect(String(args.url)).toContain("/meter_readings/bulk");
        expect(args.method).toBe("post");
        const payload = args.payload ?? args.values;
        expect(payload.services_type_id).toBe(7);
        expect(payload.readings).toEqual([{ apartment_id: 1, reading: 15 }]);
    });
});

describe("BulkReadingsModal — редактирование", () => {
    it("подгружает документ, показывает показания и сохраняет PUT /full", async () => {
        const dp = makeDataProvider({
            services: [{ id: 7, services_type: "Электричество" }],
            customImpl: async (args: any) => {
                if (String(args.url).includes("/readings")) {
                    return {
                        data: {
                            document: { reading_date: "2026-08-01", services_type_id: 7 },
                            readings: [{ apartment_id: 1, reading: 15 }],
                        },
                    };
                }
                return { data: { updated: [{ id: 1 }], errors: [] } };
            },
        });
        renderModal(dp, { documentId: 99 });

        expect(await screen.findByText("Редактирование документа показаний")).toBeTruthy();
        await waitFor(() => expect(dp.custom).toHaveBeenCalled());
        // Показание из документа подставлено в строку (InputNumber со step=0.001 — «15.000»).
        expect(await screen.findByDisplayValue("15.000")).toBeTruthy();

        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
        await waitFor(() => {
            const put = dp.custom.mock.calls.find((c: any[]) => String(c[0].url).includes("/full"));
            expect(put).toBeTruthy();
            expect(put![0].method).toBe("put");
            expect(String(put![0].url)).toContain("/meter_reading_documents/99/full");
        });
    });
});
