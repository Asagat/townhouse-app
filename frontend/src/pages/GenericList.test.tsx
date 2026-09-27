// src/pages/GenericList.test.tsx
// RTL-проверка правил форматирования на реальной таблице GenericList (список
// «Приход/Расход» = resource `transactions`):
//   - заголовки любых колонок — по центру;
//   - денежные значения — справа, с запятой как десятичным разделителем и без «₸»;
//   - текстовые значения — слева; прочие (даты/id) — по центру.
// Данные подменяются моковым Refine dataProvider (без сети), чтобы проверить
// именно форматирование таблицы.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Refine } from "@refinedev/core";
import { GenericList } from "./GenericList";
import { ReferenceDrillProvider } from "../components/common/ReferenceDrillProvider";
import { clearToken, setIdentity } from "../auth/token";

// Одинокая запись «Приход/Расход» со всеми типами значений для проверки колонок.
// У вложенных справочников есть id — для «проваливания» в связанные записи (2.21).
const TRANSACTION = {
    id: 1,
    title: "Приход в кассу",
    transaction_date: "2026-08-24T10:00:00",
    cash_point: { id: 2, name: "Основная касса" },
    apartment: { id: 5, apartment_number: "5" },
    account: { id: 9, account_number: "LS/0001" },
    article: { id: 3, name: "Поступления от жителей" },
    contractor: { id: 7, full_name: "Иванов Иван" },
    owner: { id: 42, full_name: "Петров Пётр" },
    transaction_type: "in_cash",
    amount: 1234.5,
    notes: "Комментарий А",
    created_by_name: "Оператор",
};

/** Провайдер Refine, не ходящий в сеть, на одну запись. */
const mockDataProvider: any = {
    getList: vi.fn(async () => ({
        data: [TRANSACTION],
        total: 1,
    })),
    getOne: vi.fn(async () => ({ data: TRANSACTION })),
    getMany: vi.fn(async () => ({ data: [TRANSACTION] })),
    create: vi.fn(async () => ({ data: TRANSACTION })),
    update: vi.fn(async () => ({ data: TRANSACTION })),
    deleteOne: vi.fn(async () => ({ data: TRANSACTION })),
    custom: vi.fn(async () => ({ data: { fields: [] } })),
    // useApiUrl в GenericList вызывает getApiUrl() провайдера — без него ошибка.
    getApiUrl: () => "http://localhost:8000/api",
};

const renderTransactionsList = () =>
    render(
        <Refine dataProvider={mockDataProvider}>
            <GenericList resourceName="transactions" />
        </Refine>,
    );

/** Ищет ячейку строки, содержащую фрагмент текста (для сравнения по подстроке). */
const rowCellByText = (row: HTMLElement, text: RegExp): HTMLElement => {
    const td = Array.from(row.querySelectorAll("td")).find((c) => {
        const t = (c.textContent ?? "").replace(/\u00a0/g, " ");
        return text.test(t);
    });
    expect(td, `ячейка со значением ${text} в строке найдена`).toBeDefined();
    return td as HTMLElement;
};

describe("GenericList — форматирование колонок списка", () => {
    beforeEach(async () => {
        renderTransactionsList();
        // Ждём загрузку строки из мок-провайдера (форматируемый ряд появляется async).
        await screen.findByText(/Комментарий А/u);
    });

    it("отображает запись с денежным значением — 2 знака, запятая, без ₸, справа", async () => {
        const row = screen.getByText(/Комментарий А/u).closest("tr");
        expect(row).not.toBeNull();

        const moneyCell = rowCellByText(row as HTMLElement, /1\s*234[,]50/u);
        // Без знака валюты «₸».
        expect(moneyCell.textContent).not.toContain("₸");
        // Запятая — десятичный разделитель, ровно два знака после запятой.
        expect(moneyCell.textContent).toMatch(/[,]50$/u);
        // Денежное значение — выравнивание вправо.
        expect((moneyCell as HTMLElement).style.textAlign).toBe("right");
    });

    it("текстовые колонки выравниваются влево (пример — Статья и Собственник)", async () => {
        const row = screen.getByText(/Комментарий А/u).closest("tr");
        expect(row).not.toBeNull();

        const article = rowCellByText(row as HTMLElement, /Поступления от жителей/u);
        const owner = rowCellByText(row as HTMLElement, /Петров Пётр/u);
        expect((article as HTMLElement).style.textAlign).toBe("left");
        expect((owner as HTMLElement).style.textAlign).toBe("left");

        // И примечание (свободный текст) — тоже слева.
        const notes = rowCellByText(row as HTMLElement, /Комментарий А/u);
        expect((notes as HTMLElement).style.textAlign).toBe("left");
    });

    it("прочие значения (id и дата операции) выравниваются по центру", async () => {
        const row = screen.getByText(/Комментарий А/u).closest("tr");
        expect(row).not.toBeNull();

        const id = rowCellByText(row as HTMLElement, /^1$/u);
        const date = rowCellByText(row as HTMLElement, /24\.08\.2026/u);
        expect((id as HTMLElement).style.textAlign).toBe("center");
        expect((date as HTMLElement).style.textAlign).toBe("center");
    });

    it("заголовки всех колонок расположены по центру", async () => {
        const headers = screen.getAllByRole("columnheader");
        const sumHeader = headers.find((h) =>
            (h.textContent ?? "").replace(/\u00a0/g, " ").includes("Сумма"),
        );
        const notesHeader = headers.find((h) =>
            (h.textContent ?? "").replace(/\u00a0/g, " ").includes("Примечание"),
        );
        expect(sumHeader).toBeDefined();
        expect(notesHeader).toBeDefined();
        expect((sumHeader as HTMLElement).style.textAlign).toBe("center");
        expect((notesHeader as HTMLElement).style.textAlign).toBe("center");
    });

    it("дата в колонке операций показана в формате DD.MM.YYYY", async () => {
        const row = screen.getByText(/Комментарий А/u).closest("tr");
        const date = within(row as HTMLElement).getByText(/24\.08\.2026/u);
        expect(date.textContent).toMatch(/^24\.08\.2026/);
    });

    it("колонка ID доступна в панели «Отображаемые колонки» (её можно скрыть)", async () => {
        // Панель открывается кнопкой с иконкой таблицы (TableOutlined → .anticon-table).
        const colsButton = document.querySelector(".anticon-table")?.closest("button");
        expect(colsButton).not.toBeNull();
        fireEvent.click(colsButton as HTMLElement);

        await screen.findByText(/Отображаемые колонки/u);
        // getByLabelText бросает, если чек-бокса нет; по умолчанию колонка видима.
        const idCheckbox = screen.getByLabelText("ID") as HTMLInputElement;
        expect(idCheckbox.checked).toBe(true);
    });
});

describe("GenericList — экспорт списка (2.2)", () => {
    it("кнопка «Экспорт → Excel» запрашивает файл с _export=xlsx и колонками", async () => {
        // Перехватываем fetch (его использует authedFetch скачивания) и не даём
        // браузеру реально создавать/скачивать объектный URL.
        const fetchMock = vi.fn(
            async (_url: RequestInfo | URL) =>
                new Response(new Blob(["data"]), {
                    status: 200,
                    headers: {
                        "Content-Type":
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    },
                }),
        );
        vi.stubGlobal("fetch", fetchMock);
        const createUrl = vi.fn(() => "blob:test");
        const revokeUrl = vi.fn();
        (URL as any).createObjectURL = createUrl;
        (URL as any).revokeObjectURL = revokeUrl;
        // Скачивание в jsdom иначе даёт «Not implemented: navigation» — гасим клик <a>.
        const anchorClick = vi
            .spyOn(HTMLAnchorElement.prototype, "click")
            .mockImplementation(() => {});

        try {
            renderTransactionsList();
            await screen.findByText(/Комментарий А/u);

            // Кнопка экспорта — иконка «скачать» (DownloadOutlined).
            const exportBtn = document.querySelector(".anticon-download")?.closest("button");
            expect(exportBtn).not.toBeNull();
            fireEvent.click(exportBtn as HTMLElement);

            fireEvent.click(await screen.findByText("Excel (.xlsx)"));

            await waitFor(() => expect(fetchMock).toHaveBeenCalled());
            const calledUrl = String(fetchMock.mock.calls[0][0]);
            expect(calledUrl).toContain("/api/transactions?");
            expect(calledUrl).toContain("_export=xlsx");
            expect(calledUrl).toContain("_columns=");
            // Колонки передаются JSON-ом (с ключом и подписью).
            expect(decodeURIComponent(calledUrl)).toContain('"label":"Сумма"');
        } finally {
            anchorClick.mockRestore();
            vi.unstubAllGlobals();
        }
    });
});

describe("GenericList — проваливание по ссылке (2.21)", () => {
    it("кнопка «…» в ссылочной колонке открывает связанную запись", async () => {
        setIdentity({
            id: 1,
            username: "admin",
            full_name: "Админ",
            role: "admin",
            role_name: "Администратор",
        });
        vi.stubGlobal(
            "fetch",
            vi.fn(async (url: RequestInfo | URL) => {
                const u = String(url);
                const body = u.includes("/meta/owners")
                    ? { fields: [{ name: "full_name", label: "ФИО", type: "string", required: true }] }
                    : { id: 42, full_name: "Петров Пётр" };
                return new Response(JSON.stringify(body), {
                    status: 200,
                    headers: { "Content-Type": "application/json" },
                });
            }),
        );

        try {
            render(
                <ReferenceDrillProvider>
                    <Refine dataProvider={mockDataProvider}>
                        <GenericList resourceName="transactions" />
                    </Refine>
                </ReferenceDrillProvider>,
            );
            await screen.findByText(/Комментарий А/u);

            // Кнопка «…» в ячейке собственника («Петров Пётр»).
            const ownerCell = rowCellByText(
                screen.getByText(/Комментарий А/u).closest("tr") as HTMLElement,
                /Петров Пётр/u,
            );
            const drillButton = ownerCell.querySelector(".anticon-ellipsis")?.closest("button");
            expect(drillButton).not.toBeNull();
            fireEvent.click(drillButton as HTMLElement);

            expect(await screen.findByText("Просмотр: Контрагент")).toBeTruthy();
            expect(await screen.findByDisplayValue("Петров Пётр")).toBeTruthy();
        } finally {
            clearToken();
            vi.unstubAllGlobals();
        }
    });
});
