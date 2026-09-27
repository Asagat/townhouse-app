// src/components/common/ReferenceFilterSelect.test.tsx
// RTL-тесты фильтра-списка со значениями из справочника (Б10): загрузка опций через
// authedFetch (мок fetch) с сортировкой referenceSort, выбор значения → onChange с
// display-значением (label — расширенная подпись), очистка (allowClear) → undefined,
// устойчивость к ошибке сети и кэш справочника на уровне модуля.
//
// Кэш ReferenceFilterSelect — модульный (Map по resource), поэтому в каждом тесте
// используется свой ресурс справочника, чтобы тесты не влияли друг на друга.

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { ReferenceFilterSelect } from "./ReferenceFilterSelect";
import { getReferenceSource } from "../../config/filters";

const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });

/** Мок authedFetch, отдающий готовый список записей справочника. */
const stubList = (body: unknown) => {
    const mock = vi.fn(async (_url: RequestInfo | URL) => json(body));
    vi.stubGlobal("fetch", mock);
    return mock;
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

describe("ReferenceFilterSelect", () => {
    it("загружает опции справочника (с сортировкой referenceSort)", async () => {
        const fetchMock = stubList([
            { id: 1, name: "Касса" },
            { id: 2, name: "Счёт" },
        ]);
        const source = getReferenceSource("transactions", "cash_point.name")!;
        const { container } = render(<ReferenceFilterSelect source={source} />);

        openSelect(container);
        // Опция ищется по title: rc-select дублирует текст в скрытом listbox для a11y.
        expect(await screen.findByTitle("Касса")).toBeTruthy();
        expect(await screen.findByTitle("Счёт")).toBeTruthy();

        const calledUrl = String(fetchMock.mock.calls[0][0]);
        expect(calledUrl).toContain("/api/cash_points?_end=100000");
        expect(calledUrl).toContain("_sort=name&_order=asc");
    });

    it("выбор значения отдаёт onChange display-значение, label — отдельно", async () => {
        stubList([
            { id: 1, name: "Аренда", kind: "Доход" },
            { id: 2, name: "Ремонт", kind: "Расход" },
        ]);
        const onChange = vi.fn();
        const source = getReferenceSource("transactions", "article.name")!;
        const { container } = render(
            <ReferenceFilterSelect source={source} onChange={onChange} />,
        );

        openSelect(container);
        // В подписи — расширенный label, а значением уходит само display-имя.
        fireEvent.click(await screen.findByTitle("Ремонт (расход)"));

        await waitFor(() => expect(onChange).toHaveBeenCalled());
        expect(onChange.mock.calls.at(-1)?.[0]).toBe("Ремонт");
    });

    it("очистка значения (allowClear) отдаёт onChange(undefined)", async () => {
        stubList([{ id: 5, full_name: "Иванов Иван" }]);
        const onChange = vi.fn();
        const source = getReferenceSource("transactions", "owner.full_name")!;
        const { container } = render(
            <ReferenceFilterSelect source={source} value="Иванов Иван" onChange={onChange} />,
        );

        await waitFor(() => expect(container.querySelector(".ant-select-clear")).not.toBeNull());
        fireEvent.mouseDown(container.querySelector(".ant-select-clear") as Element);

        await waitFor(() => expect(onChange).toHaveBeenCalled());
        expect(onChange.mock.calls.at(-1)?.[0]).toBeUndefined();
    });

    it("ошибка сети не роняет компонент (пустой список)", async () => {
        vi.stubGlobal("fetch", vi.fn(async () => new Response("boom", { status: 500 })));
        const source = getReferenceSource("transactions", "tariff_type.name")!;
        const { container } = render(<ReferenceFilterSelect source={source} />);

        openSelect(container);
        // Список остаётся пустым, но селект отрисован без исключений.
        await waitFor(() => expect(container.querySelector(".ant-select")).not.toBeNull());
    });

    it("кэширует справочник: повторный рендер не дёргает API", async () => {
        const fetchMock = stubList([{ id: 1, services_type: "Вода" }]);
        const source = getReferenceSource("accounts", "services_type.services_type")!;

        const first = render(<ReferenceFilterSelect source={source} />);
        openSelect(first.container);
        expect(await screen.findByTitle("Вода")).toBeTruthy();
        first.unmount();

        // Кэш на уровне модуля — второй рендер берёт опции без нового запроса.
        const second = render(<ReferenceFilterSelect source={source} />);
        openSelect(second.container);
        expect(await screen.findByTitle("Вода")).toBeTruthy();

        expect(fetchMock).toHaveBeenCalledTimes(1);
    });
});
