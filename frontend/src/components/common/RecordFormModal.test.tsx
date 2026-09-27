// src/components/common/RecordFormModal.test.tsx
// RTL RecordFormModal (3.2/2.21): режим просмотра — форматирование значений и кнопка
// «…» у ссылочных полей (открывает связанную запись); в режиме редактирования кнопки нет.

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { RecordFormModal } from "./RecordFormModal";
import { ReferenceDrillProvider } from "./ReferenceDrillProvider";
import { clearToken, setIdentity } from "../../auth/token";
import type { FieldMeta } from "../../types";

const json = (body: unknown) =>
    new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
    });

const FIELDS: FieldMeta[] = [
    { name: "apartment_id", label: "Квартира", type: "reference", reference: "apartments", required: true },
    { name: "price", label: "Цена", type: "decimal", required: false },
    { name: "is_active", label: "Активен", type: "boolean", required: false },
    { name: "installed_at", label: "Дата установки", type: "date", required: false },
];

const VALUES = {
    apartment_id: 5,
    apartment: { id: 5, apartment_number: 5 },
    price: 1234.5,
    is_active: true,
    installed_at: "2026-01-15",
};

const stubFetch = () =>
    vi.stubGlobal(
        "fetch",
        vi.fn(async (url: RequestInfo | URL) => {
            const u = String(url);
            if (u.includes("/meta/apartments")) {
                return json({ fields: [{ name: "apartment_number", label: "№ квартиры", type: "number" }] });
            }
            if (u.includes("/apartments/5")) {
                return json({ id: 5, apartment_number: 5 });
            }
            return json([]);
        }),
    );

const renderModal = (readonly: boolean) => {
    setIdentity({ id: 1, username: "admin", full_name: "Админ", role: "admin", role_name: "Администратор" });
    return render(
        <ReferenceDrillProvider>
            <RecordFormModal
                open
                title="Просмотр записи"
                fields={FIELDS}
                initialValues={VALUES}
                confirmLoading={false}
                readonly={readonly}
                resourceName="meters"
                onCancel={() => {}}
                onSubmit={() => {}}
            />
        </ReferenceDrillProvider>,
    );
};

afterEach(() => {
    vi.unstubAllGlobals();
    clearToken();
});

describe("RecordFormModal — режим просмотра", () => {
    it("форматирует значения (деньги/булево/дата) и показывает ссылку", () => {
        stubFetch();
        renderModal(true);
        expect(screen.getByDisplayValue("1 234,50")).toBeTruthy(); // money
        expect(screen.getByDisplayValue("Да")).toBeTruthy(); // boolean
        expect(screen.getByDisplayValue("15.01.2026")).toBeTruthy(); // date
        expect(screen.getByDisplayValue("5")).toBeTruthy(); // reference (label из вложенного)
    });

    it("кнопка «…» у ссылочного поля открывает связанную запись", async () => {
        stubFetch();
        renderModal(true);
        const drillButton = document.querySelector(".anticon-ellipsis")?.closest("button");
        expect(drillButton).not.toBeNull();
        fireEvent.click(drillButton as HTMLElement);
        expect(await screen.findByText("Просмотр: Квартира")).toBeTruthy();
    });
});

describe("RecordFormModal — редактирование", () => {
    it("кнопки «…» нет, поля привязаны к форме", () => {
        stubFetch();
        renderModal(false);
        expect(document.querySelector(".anticon-ellipsis")).toBeNull();
        // Поле ввода квартиры — селект справочника (ReferenceSelect).
        expect(document.querySelector(".ant-select")).not.toBeNull();
    });
});
