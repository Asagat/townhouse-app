// src/components/accruals/PersonalAccrualModal.test.tsx
// RTL-тесты модалки «Персональное доначисление / корректировка»:
//   — загрузка справочников л/с и видов услуг (useList → dataProvider.getList);
//   — валидации «Добавить строку» (нужны л/с, услуга и ненулевая сумма) и причины;
//   — проверка содержимого документа и отправка POST /accrual_documents/personal
//     (тело: accrual_date, comment, entries[{account_id, services_type_id, amount}]);
//   — успех (сообщение, onSaved, onClose), ошибка с detail, удаление строки.
// Реальной сети нет: Refine-запросы обслуживает мок dataProvider (custom/getList).

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { Refine } from "@refinedev/core";
import { message } from "antd";
import dayjs from "dayjs";

import { PersonalAccrualModal } from "./PersonalAccrualModal";

const ACCOUNTS = [
    { id: 1, account_number: "LS/0001", account_name: "Иванов", apartment: { apartment_number: 1 } },
    { id: 2, account_number: "LS/0002", account_name: "", apartment: { apartment_number: 2 } },
];
const SERVICES = [
    { id: 5, services_type: "Вывоз мусора" },
    { id: 7, services_type: "Электричество" },
];

/** Подпись л/с: `{account_number} — кв.{apartment_number} {account_name}`. */
const ACCOUNT_LABEL = "LS/0001 — кв.1 Иванов";

/** Мок-провайдер Refine: справочники — getList, сохранение — custom (useCustomMutation). */
const makeDataProvider = (customImpl?: (args: any) => any) => {
    const custom = vi.fn(customImpl ?? (async () => ({ data: { created: [{ id: 11 }] } })));
    return {
        custom,
        getList: vi.fn(async ({ resource }: any) => {
            if (resource === "accounts") return { data: ACCOUNTS, total: ACCOUNTS.length };
            if (resource === "services_type") return { data: SERVICES, total: SERVICES.length };
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

const renderModal = (dp: any) => {
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
            <PersonalAccrualModal open onClose={onClose} onSaved={onSaved} />
        </Refine>,
    );
    return { onClose, onSaved };
};

/** Открывает выпадающий список antd, найденный по тексту-плейсхолдеру. */
const openSelectByPlaceholder = (placeholder: string) => {
    const ph = screen
        .getAllByText(placeholder)
        .find((el) => el.classList.contains("ant-select-selection-placeholder"));
    expect(ph, `селект с плейсхолдером «${placeholder}»`).toBeTruthy();
    const selector = (ph as HTMLElement)
        .closest(".ant-select")!
        .querySelector(".ant-select-selector") as Element;
    fireEvent.mouseDown(selector);
};

/** Выбирает значение в конкретном селекте: открывает список и кликает вариант. */
const pickInSelect = async (placeholder: string, optionLabel: string) => {
    openSelectByPlaceholder(placeholder);
    fireEvent.click(await screen.findByText(optionLabel));
};

/** Заполняет и добавляет одну строку начисления (л/с, услуга, сумма). */
const addRow = async (accountLabel: string, serviceLabel: string, amount: string) => {
    await pickInSelect("Лицевой счёт", accountLabel);
    await pickInSelect("Услуга", serviceLabel);
    fireEvent.change(screen.getByPlaceholderText("Сумма ±"), { target: { value: amount } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить строку" }));
};

const reasonInput = () => screen.getByPlaceholderText(/Например/);

beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
});

afterEach(() => {
    vi.unstubAllGlobals();
    // Статические сообщения antd живут вне дерева RTL — чистим вручную между тестами.
    message.destroy();
});

describe("PersonalAccrualModal — справочники и строки", () => {
    it("загружает л/с и виды услуг и показывает их в выпадающих списках", async () => {
        const dp = makeDataProvider();
        renderModal(dp);

        await waitFor(() => expect(dp.getList).toHaveBeenCalled());
        const resources = dp.getList.mock.calls.map((c: any[]) => c[0].resource).sort();
        expect(resources).toEqual(["accounts", "services_type"]);

        openSelectByPlaceholder("Лицевой счёт");
        expect(await screen.findByText(ACCOUNT_LABEL)).toBeTruthy();
        expect(screen.getByText("LS/0002 — кв.2")).toBeTruthy();

        openSelectByPlaceholder("Услуга");
        expect(await screen.findByText("Вывоз мусора")).toBeTruthy();
        expect(screen.getByText("Электричество")).toBeTruthy();
    });

    it("без выбранных л/с, услуги и суммы «Добавить строку» предупреждает", async () => {
        renderModal(makeDataProvider());
        fireEvent.click(screen.getByRole("button", { name: "Добавить строку" }));
        expect(
            await screen.findByText("Выберите л/с, услугу и введите ненулевую сумму"),
        ).toBeTruthy();
    });

    it("добавленная строка попадает в таблицу, отображает сумму и «Итого»", async () => {
        renderModal(makeDataProvider());
        await addRow(ACCOUNT_LABEL, "Вывоз мусора", "1500");

        // Подпись л/с и услуги — и в выбранном значении селекта, и в строке таблицы.
        expect(screen.getAllByText(ACCOUNT_LABEL).length).toBeGreaterThan(1);
        expect(screen.getAllByText("Вывоз мусора").length).toBeGreaterThan(1);
        // Ячейка суммы с денежным форматированием.
        expect(screen.getByText("1 500,00")).toBeTruthy();
        expect(screen.getByText(/Итого:/)).toBeTruthy();
    });

    it("удаление строки убирает её из таблицы и блок «Итого»", async () => {
        renderModal(makeDataProvider());
        await addRow(ACCOUNT_LABEL, "Вывоз мусора", "1500");
        expect(screen.getByText(/Итого:/)).toBeTruthy();

        fireEvent.click(screen.getByRole("button", { name: "Удалить" }));
        await waitFor(() => expect(screen.queryByText(/Итого:/)).toBeNull());
    });
});

describe("PersonalAccrualModal — сохранение", () => {
    it("«Сохранить» шлёт POST /accrual_documents/personal с телом документа", async () => {
        const dp = makeDataProvider();
        const { onClose, onSaved } = renderModal(dp);
        await addRow(ACCOUNT_LABEL, "Вывоз мусора", "1500");

        fireEvent.change(reasonInput(), { target: { value: "  Доначисление площадки  " } });
        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

        await waitFor(() => expect(dp.custom).toHaveBeenCalled());
        const args = dp.custom.mock.calls[0][0];
        expect(String(args.url)).toContain("/accrual_documents/personal");
        expect(args.method).toBe("post");

        const payload = args.payload ?? args.values;
        // Дата начисления — первое число выбранных года/месяца (по умолчанию текущих).
        const now = dayjs();
        expect(payload.accrual_date).toBe(
            `${now.year()}-${String(now.month() + 1).padStart(2, "0")}-01`,
        );
        // Причина обрезается по краям.
        expect(payload.comment).toBe("Доначисление площадки");
        expect(payload.entries).toEqual([
            { account_id: 1, services_type_id: 5, amount: 1500 },
        ]);

        expect(await screen.findByText("Персональное доначисление сохранено")).toBeTruthy();
        await waitFor(() => expect(onSaved).toHaveBeenCalled());
        expect(onClose).toHaveBeenCalled();
    });

    it("без причины «Сохранить» показывает ошибку и не отправляет документ", async () => {
        const dp = makeDataProvider();
        renderModal(dp);
        await addRow(ACCOUNT_LABEL, "Вывоз мусора", "1500");

        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

        expect(
            await screen.findByText("Укажите причину («Примечание») персональной корректировки"),
        ).toBeTruthy();
        expect(dp.custom).not.toHaveBeenCalled();
    });

    it("ошибка сохранения показывает detail из ответа сервера", async () => {
        const dp = makeDataProvider(async () => {
            throw { response: { data: { detail: "Лицевой счёт не найден" } } };
        });
        renderModal(dp);
        await addRow(ACCOUNT_LABEL, "Вывоз мусора", "1500");
        fireEvent.change(reasonInput(), { target: { value: "Причина" } });

        fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

        expect(await screen.findByText("Лицевой счёт не найден")).toBeTruthy();
    });
});
