// src/components/common/ReferenceSelect.test.tsx
// RTL-тесты выпадающего справочника (3.2): загрузка через authedFetch (мок fetch),
// форматирование подписи, выбор значения (id), пункт «— пусто —» и filterFn.

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { ReferenceSelect } from "./ReferenceSelect";

const stubList = (items: unknown[]) => {
    vi.stubGlobal(
        "fetch",
        vi.fn(async () =>
            new Response(JSON.stringify(items), {
                status: 200,
                headers: { "Content-Type": "application/json" },
            }),
        ),
    );
};

/** Открывает выпадающий список antd (mousedown по селектору). */
const openSelect = (container: HTMLElement) => {
    const selector = container.querySelector(".ant-select-selector");
    expect(selector).not.toBeNull();
    fireEvent.mouseDown(selector as Element);
};

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("ReferenceSelect", () => {
    it("загружает список и показывает подпись ресурса — «№ 5 — Иванов Иван»", async () => {
        stubList([{ id: 5, apartment_number: 5, owner: { full_name: "Иванов Иван" } }]);
        const { container } = render(<ReferenceSelect resource="apartments" />);

        openSelect(container);
        expect(await screen.findByText("№ 5 — Иванов Иван")).toBeTruthy();
    });

    it("выбор варианта отдаёт числовой id", async () => {
        stubList([{ id: 5, apartment_number: 5, owner: { full_name: "Иванов Иван" } }]);
        const onChange = vi.fn();
        const { container } = render(<ReferenceSelect resource="apartments" onChange={onChange} />);

        openSelect(container);
        fireEvent.click(await screen.findByText("№ 5 — Иванов Иван"));
        await waitFor(() => expect(onChange).toHaveBeenCalledWith(5));
    });

    it("optional: пункт «— пусто —» очищает значение (undefined)", async () => {
        stubList([{ id: 5, name: "Касса" }]);
        const onChange = vi.fn();
        const { container } = render(
            <ReferenceSelect resource="cash_points" optional value={5} onChange={onChange} />,
        );

        openSelect(container);
        fireEvent.click(await screen.findByText("— пусто —"));
        await waitFor(() => expect(onChange).toHaveBeenCalledWith(undefined));
    });

    it("filterFn отсеивает варианты", async () => {
        stubList([
            { id: 1, name: "Касса" },
            { id: 2, name: "Счёт" },
        ]);
        const { container } = render(
            <ReferenceSelect resource="cash_points" filterFn={(i: any) => i.id === 2} />,
        );

        openSelect(container);
        expect(await screen.findByText("Счёт")).toBeTruthy();
        expect(screen.queryByText("Касса")).toBeNull();
    });

    it("ошибка сети не роняет компонент (пустой список)", async () => {
        vi.stubGlobal("fetch", vi.fn(async () => new Response("boom", { status: 500 })));
        const { container } = render(<ReferenceSelect resource="cash_points" />);
        openSelect(container);
        // Ничего не выбрано и нет вариантов — просто нет исключений.
        await waitFor(() => expect(container.querySelector(".ant-select")).not.toBeNull());
    });
});
