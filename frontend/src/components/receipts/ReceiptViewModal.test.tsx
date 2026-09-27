// src/components/receipts/ReceiptViewModal.test.tsx
// RTL-тесты модалки просмотра квитанции ReceiptViewModal:
//   1) загрузка квитанции (GET /receipt_documents/:id/items) — шапка, строки услуг,
//      строка «Итого»; индикатор загрузки до ответа и текст ошибки при неудаче;
//   2) два режима отрисовки: мобильный (компактная сводка + примечание) и десктопный
//      («PDF-подобная» таблица) — режим задаётся сочетанием matchMedia;
//   3) сохранение примечания при editable (PATCH .../comment — URL, метод и тело) и
//      ошибка сохранения;
//   4) скачивание PDF (fetch .../pdf + подмена <a>.click и URL.createObjectURL).
//
// Сети нет: fetch подменяется vi.stubGlobal; Refine — мок dataProvider.
// matchMedia в setup.ts всегда «не совпало» → по умолчанию компонент в мобильном
// режиме; для десктопных проверок matchMedia мокается под широкий вьюпорт (>= md).

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { Refine } from "@refinedev/core";
import { message } from "antd";

import { ReceiptViewModal } from "./ReceiptViewModal";

const API = "http://localhost:8000/api";

const dataProvider: any = {
    getApiUrl: () => API,
    getList: vi.fn(async () => ({ data: [], total: 0 })),
    getOne: vi.fn(async () => ({ data: {} })),
    getMany: vi.fn(async () => ({ data: [] })),
    create: vi.fn(async () => ({ data: {} })),
    update: vi.fn(async () => ({ data: {} })),
    deleteOne: vi.fn(async () => ({ data: {} })),
};

const DOC = {
    id: 42,
    period_month: 5,
    period_year: 2026,
    apartment_number: 13,
    owner_name: "Иванов Иван Иванович",
    total_amount: 1525,
    debt: 300,
    overpayment: 0,
    payable_amount: 1225,
    issued_at: "2026-06-14T12:30:00",
    comment: "Проверено бухгалтерией",
};

const ITEMS = [
    {
        id: 1,
        service_name: "Вывоз мусора",
        reading_prev: null,
        reading_curr: null,
        quantity: 1,
        tariff: 152.5,
        amount: 152.5,
        debt: 0,
        overpayment: 0,
        payable: 152.5,
    },
    {
        id: 2,
        service_name: "Вода",
        reading_prev: 10,
        reading_curr: 25,
        quantity: 15,
        tariff: 91.5,
        amount: 1372.5,
        debt: 300,
        overpayment: 0,
        payable: 1072.5,
    },
];

const jsonOf = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });

type FetchHandler = (url: string, init?: RequestInit) => Response;

/** Маршрутизатор мок-fetch по эндпоинтам компонента. */
const defaultFetch = (
    overrides: { items?: FetchHandler; comment?: FetchHandler; pdf?: FetchHandler } = {},
): FetchHandler => (url, init) => {
    if (url.endsWith("/comment")) {
        return (overrides.comment ?? (() => jsonOf({ comment: "" })))(url, init);
    }
    if (url.endsWith("/pdf")) {
        return (
            overrides.pdf ??
            (() =>
                new Response(new Blob(["pdf"], { type: "application/pdf" }), {
                    status: 200,
                    headers: { "Content-Type": "application/pdf" },
                }))
        )(url, init);
    }
    if (url.endsWith("/items")) {
        return (overrides.items ?? (() => jsonOf({ document: DOC, items: ITEMS })))(url, init);
    }
    return jsonOf({});
};

const stubFetch = (handler: FetchHandler) =>
    vi.stubGlobal(
        "fetch",
        vi.fn((input: RequestInfo | URL, init?: RequestInit) => handler(String(input), init)),
    );

/**
 * Мок matchMedia под заданную ширину вьюпорта: antd Grid.useBreakpoint читает
 * `(min-width/max-width)`, поэтому подмена определяет мобильный/десктопный режим.
 */
const stubViewport = (width: number) =>
    vi.stubGlobal("matchMedia", (query: string) => {
        const min = /min-width:\s*(\d+)px/.exec(query);
        const max = /max-width:\s*(\d+)px/.exec(query);
        let matches = true;
        if (min) matches = matches && width >= Number(min[1]);
        if (max) matches = matches && width <= Number(max[1]);
        return {
            matches,
            media: query,
            onchange: null,
            addListener: () => {},
            removeListener: () => {},
            addEventListener: () => {},
            removeEventListener: () => {},
            dispatchEvent: () => false,
        } as unknown as MediaQueryList;
    });

const renderModal = (props: { editable?: boolean; onClose?: () => void } = {}) => {
    const onClose = props.onClose ?? vi.fn();
    const view = render(
        <Refine dataProvider={dataProvider}>
            <ReceiptViewModal
                open
                receiptId={42}
                onClose={onClose}
                editable={props.editable ?? false}
            />
        </Refine>,
    );
    return { ...view, onClose };
};

const ROWS_MSG = /Услуг в квитанции: 2/u;

let successSpy: any;
let errorSpy: any;

beforeEach(() => {
    // Не даём antd рисовать тосты: проверяем вызовы message, а не DOM уведомлений.
    successSpy = vi.spyOn(message, "success").mockImplementation(() => ({} as any));
    errorSpy = vi.spyOn(message, "error").mockImplementation(() => ({} as any));
});

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
});

describe("ReceiptViewModal", () => {
    it("мобильный режим: компактная сводка, итоги и примечание без правки", async () => {
        stubFetch(defaultFetch());
        renderModal();

        // Заголовок окна — номер квитанции из документа после загрузки.
        expect(await screen.findByText("Квитанция № 42")).toBeTruthy();

        // Сводка: период + квартира/собственник.
        expect(screen.getByText("Май 2026")).toBeTruthy();
        expect(screen.getByText(/Квартира № 13/u)).toBeTruthy();
        expect(screen.getByText(/Иванов Иван Иванович/u)).toBeTruthy();

        // Строки итогов (суммы в русском формате «1 525,00»).
        expect(screen.getByText("Начислено")).toBeTruthy();
        expect(screen.getByText("1 525,00")).toBeTruthy();
        expect(screen.getByText("Долг")).toBeTruthy();
        expect(screen.getByText("300,00")).toBeTruthy();
        expect(screen.getByText("Переплата")).toBeTruthy();
        expect(screen.getByText("К оплате")).toBeTruthy();
        expect(screen.getByText("1 225,00")).toBeTruthy();

        expect(screen.getByText(ROWS_MSG)).toBeTruthy();
        expect(screen.getByText("Сформирована: 14.06.2026 12:30:00")).toBeTruthy();

        // Примечание в режиме только чтения — текстом, без кнопки «Сохранить».
        // Комментарий подставляется эффектом после загрузки документа — ждём его.
        expect(await screen.findByText("Проверено бухгалтерией")).toBeTruthy();
        expect(screen.queryByRole("button", { name: "Сохранить" })).toBeNull();

        // Широкая таблица в мобильном режиме не рисуется (контент Modal — в портале,
        // поэтому ищем по document, а не по корню render).
        expect(document.querySelector(".receipt-mobile-summary")).toBeTruthy();
        expect(document.querySelector(".ant-table")).toBeNull();

        // Кнопка скачивания PDF присутствует.
        expect(screen.getByRole("button", { name: "PDF" })).toBeTruthy();
    });

    it("десктопный режим: шапка, таблица услуг, строка «Итого» и запрос items", async () => {
        stubViewport(1280);
        stubFetch(defaultFetch());
        const { onClose } = renderModal();

        // Десктопная «PDF-подобная» вёрстка.
        expect(await screen.findByText("Family Townhouse")).toBeTruthy();
        expect(screen.getByText("Квитанция")).toBeTruthy();
        expect(screen.getByText("Май 2026")).toBeTruthy();
        expect(screen.getByText("Квартира № 13 Иванов Иван Иванович")).toBeTruthy();

        // Строки услуг и строка-итог.
        expect(screen.getByText("Вывоз мусора")).toBeTruthy();
        expect(screen.getByText("Вода")).toBeTruthy();
        expect(screen.getByText("Итого")).toBeTruthy();

        // Суммы строк и итогов.
        expect(screen.getByText("1 372,50")).toBeTruthy();
        expect(screen.getByText("1 525,00")).toBeTruthy();
        expect(screen.getByText("1 225,00")).toBeTruthy();
        // Долг 300,00 — в строке «Вода» и в итоговой строке.
        expect(screen.getAllByText("300,00").length).toBeGreaterThanOrEqual(2);
        expect(screen.getByText("14.06.2026 12:30:00")).toBeTruthy();

        // Примечание — readOnly-поле с загруженным комментарием, без кнопки сохранения.
        const textarea = screen.getByPlaceholderText(
            "Дополнительная пометка по квитанции (не влияет на суммы)",
        ) as HTMLTextAreaElement;
        await waitFor(() => expect(textarea.value).toBe("Проверено бухгалтерией"));
        expect(textarea.readOnly).toBe(true);
        expect(screen.queryByRole("button", { name: "Сохранить" })).toBeNull();

        // Таблица есть, мобильной сводки нет (контент Modal — в портале).
        expect(document.querySelector(".ant-table")).toBeTruthy();
        expect(document.querySelector(".receipt-mobile-summary")).toBeNull();

        // Запрос за детализацией — с id квитанции.
        const itemsCall = (fetch as any).mock.calls.find((c: any[]) =>
            String(c[0]).endsWith("/receipt_documents/42/items"),
        );
        expect(itemsCall).toBeTruthy();

        // «Закрыть» вызывает onClose.
        fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
        expect(onClose).toHaveBeenCalled();
    });

    it("показывает индикатор загрузки, пока квитанция не получена", async () => {
        let resolveItems!: (resp: Response) => void;
        vi.stubGlobal(
            "fetch",
            vi.fn(() => new Promise<Response>((resolve) => (resolveItems = resolve))),
        );
        renderModal();

        // Контент Modal рендерится в портал — ищем индикатор в document.
        expect(document.querySelector(".ant-spin")).toBeTruthy();
        expect(screen.queryByText("Май 2026")).toBeNull();

        await act(async () => {
            resolveItems(jsonOf({ document: DOC, items: ITEMS }));
        });

        expect(await screen.findByText("Май 2026")).toBeTruthy();
    });

    it("ошибка загрузки квитанции: показывает detail с бэкенда", async () => {
        stubFetch(defaultFetch({ items: () => jsonOf({ detail: "Квитанция не найдена" }, 404) }));
        renderModal();

        expect(await screen.findByText("Квитанция не найдена")).toBeTruthy();
    });

    it("editable: сохранение примечания шлёт PATCH с URL и телом и обновляет поле", async () => {
        stubViewport(1280);
        const commentHandler: FetchHandler = (_url, init) => {
            const body = JSON.parse(String(init?.body ?? "{}"));
            return jsonOf({ comment: `${body.comment} (сервер)` });
        };
        stubFetch(defaultFetch({ comment: commentHandler }));
        renderModal({ editable: true });

        const textarea = (await screen.findByPlaceholderText(
            "Дополнительная пометка по квитанции (не влияет на суммы)",
        )) as HTMLTextAreaElement;
        fireEvent.change(textarea, { target: { value: "Новый комментарий" } });

        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

        await waitFor(() => {
            const call = (fetch as any).mock.calls.find((c: any[]) =>
                String(c[0]).endsWith("/receipt_documents/42/comment"),
            );
            expect(call).toBeTruthy();
            expect(call[1]?.method).toBe("PATCH");
            expect(JSON.parse(String(call[1]?.body))).toEqual({ comment: "Новый комментарий" });
        });

        // Ответ сервера применился к полю, и показано сообщение об успехе.
        await waitFor(() => expect(textarea.value).toBe("Новый комментарий (сервер)"));
        expect(successSpy).toHaveBeenCalledWith("Примечание сохранено");
    });

    it("editable: ошибка сохранения примечания показывается через message.error", async () => {
        stubViewport(1280);
        stubFetch(
            defaultFetch({ comment: () => jsonOf({ detail: "Комментарий слишком длинный" }, 400) }),
        );
        renderModal({ editable: true });

        fireEvent.click(await screen.findByRole("button", { name: "Сохранить" }));

        await waitFor(() =>
            expect(errorSpy).toHaveBeenCalledWith("Комментарий слишком длинный"),
        );
    });

    it("кнопка PDF запрашивает /receipt_documents/:id/pdf и скачивает файл", async () => {
        const anchorClick = vi
            .spyOn(HTMLAnchorElement.prototype, "click")
            .mockImplementation(() => {});
        const createObjectURL = vi.fn(() => "blob:test");
        (URL as any).createObjectURL = createObjectURL;
        (URL as any).revokeObjectURL = vi.fn();

        stubFetch(defaultFetch());
        renderModal();
        await screen.findByText("Квитанция № 42");

        fireEvent.click(screen.getByRole("button", { name: "PDF" }));

        await waitFor(() => {
            const pdfCall = (fetch as any).mock.calls.find((c: any[]) =>
                String(c[0]).endsWith("/receipt_documents/42/pdf"),
            );
            expect(pdfCall).toBeTruthy();
        });
        await waitFor(() => expect(createObjectURL).toHaveBeenCalled());
        expect(anchorClick).toHaveBeenCalled();
    });
});
