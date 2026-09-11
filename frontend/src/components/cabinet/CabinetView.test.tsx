// src/components/cabinet/CabinetView.test.tsx
// RTL-проверки ЛК: единый стиль строк внутри блоков и наполнение блока «Движения».
//
//   1) Подписи строк (услуги, движения, квитанции, статьи расходов) имеют один
//      и тот же вид — 17px и обычный вес, как в отчёте «Общедомовые расходы».
//   2) Блок «Движения»: крупно — вид услуги (и у начисления, и у оплаты),
//      мелко — вид/название документа («Начисление» / «Приход в кассу №10»);
//      знаки — «глазами жителя» (начисление с минусом, оплата/списание с плюсом).
//
// Сеть подменяется мок-функцией fetch: /me/movements отдаёт заранее заданный
// набор движений и кассовых операций.

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { CabinetView } from "./CabinetView";
import type { StatementData } from "./CabinetView";
import { formatMoney } from "../../config/formatters";

const STATEMENT: StatementData = {
    account: { id: 1, account_number: "LS-0001", account_name: "Кв.1" },
    apartment: { apartment_number: 1, address: "ул. Тестовая, 1" },
    owner: { full_name: "Иванов Иван", phone: "70000000000" },
    metrics: {
        accrued_total: 1000,
        paid_total: 500,
        available: 500,
        debt_total: 500,
        overpayment: 0,
        balance: 500,
    },
    services: [
        { services_type_id: 1, service_name: "Вывоз мусора", accrued: 1000, paid: 500, debt: 500 },
    ],
};

const MOVEMENTS_RESPONSE = {
    metrics: { accrued: 1000, paid: 500, available: 500, debt: 500 },
    movements: [
        {
            date: "2026-03-01",
            kind: "accrual",
            kind_label: "Начисление",
            service: "Вывоз мусора",
            amount: 1000,
            balance_after: 1000,
            document: null,
        },
        {
            date: "2026-03-10",
            kind: "payment",
            kind_label: "Оплата",
            service: "Фонд развития",
            amount: -500,
            balance_after: 500,
            document: "Приход в кассу №10",
        },
    ],
    cash_movements: [{ date: "2026-03-10", cash_point: "Касса", amount: 500 }],
    closing: 500,
};

const okJson = (body: unknown) =>
    Promise.resolve(
        new Response(JSON.stringify(body), {
            status: 200,
            headers: { "Content-Type": "application/json" },
        }),
    );

describe("CabinetView", () => {
    beforeEach(() => {
        vi.stubGlobal(
            "fetch",
            vi.fn((input: RequestInfo | URL) => {
                const url = String(input);
                if (url.includes("/me/movements") || url.includes("/movements")) {
                    return okJson(MOVEMENTS_RESPONSE);
                }
                if (url.includes("/house_expenses")) {
                    return okJson({
                        period: { from: null, to: null },
                        articles: [{ name: "Зарплата", expense: 2000 }],
                        total: 2000,
                    });
                }
                return okJson({});
            }),
        );
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    const renderView = () =>
        render(
            <CabinetView
                statement={STATEMENT}
                receipts={[
                    {
                        id: 7,
                        period_month: 3,
                        period_year: 2026,
                        apartment_number: 1,
                        owner_name: "Иванов Иван",
                        total_amount: 1000,
                        payable_amount: 500,
                    },
                ]}
                apiUrl="/api"
                houseExpenses={true}
            />,
        );

    /** Приводит текст к виду без узких/неразрывных пробелов (формат чисел ru-RU). */
    const norm = (s: string) => s.replace(/[\u00a0\u202f\u2009]/g, " ");
    const plain = (el: Element | null) => norm(el?.textContent ?? "");

    it("блок «Движения»: крупно — вид услуги, мелко — вид документа", async () => {
        renderView();

        // Заголовок и содержимое загруженного ответа /me/movements.
        expect(await screen.findByText("Движения")).toBeTruthy();

        // Начисление: крупно — вид услуги, мелко — подпись документа.
        expect(await screen.findByText(/01\.03\.2026 — Вывоз мусора/u)).toBeTruthy();
        expect(await screen.findByText("Начисление")).toBeTruthy();

        // Оплата: крупно — тоже вид услуги, мелко — вид денежного документа
        // (а не «Оплата» и не услуга вместо документа).
        expect(await screen.findByText(/10\.03\.2026 — Фонд развития/u)).toBeTruthy();
        expect(await screen.findByText("Приход в кассу №10")).toBeTruthy();

        // Итог кассы — отдельная строка.
        expect(await screen.findByText("Внесено в кассу за период")).toBeTruthy();
        expect(screen.getByText(/10\.03\.2026 — Касса/u)).toBeTruthy();
    });

    it("знаки — «глазами жителя»: начисление с минусом, оплата с плюсом", async () => {
        renderView();

        // Дожидаемся загрузки движений (иначе карточка ещё без строк).
        await screen.findByText(/01\.03\.2026 — Вывоз мусора/u);
        const card = screen.getByText("Движения").closest(".ant-card") as HTMLElement;
        const text = plain(card);

        // Начисление 1000 → «−1 000,00», оплата 500 → «+500,00» (в API знаки обратные).
        expect(text).toContain(norm("−" + formatMoney(1000)));
        expect(text).toContain(norm("+" + formatMoney(500)));
    });

    it("подписи строк одного вида: 17px и обычный вес (как «Общедомовые расходы»)", async () => {
        const { container } = renderView();

        // Ждём, пока данные движений отрисуются (иначе карточки ещё нет).
        await screen.findByText(/01\.03\.2026 — Вывоз мусора/u);

        // Подписи-строки, которые должны выглядеть одинаково, — из разных блоков.
        const service = (await screen.findAllByText("Вывоз мусора"))[0];
        const article = await screen.findByText("Зарплата");
        expect(container.querySelectorAll(".ant-card").length).toBeGreaterThan(5);

        const styleOf = (el: Element) => (el as HTMLElement).style;
        expect(styleOf(service).fontSize).toBe("17px");
        expect(styleOf(service).fontWeight).toBe("400");
        expect(styleOf(article).fontSize).toBe("17px");
        expect(styleOf(article).fontWeight).toBe("400");
        // Единый вид: базовые «типографские» свойства одинаковы во всех блоках.
        expect(styleOf(service).fontSize).toBe(styleOf(article).fontSize);
        expect(styleOf(service).fontWeight).toBe(styleOf(article).fontWeight);
    });

    it("суммы — с 2 знаками и без знака валюты, прижаты вправо", async () => {
        renderView();

        // Дожидаемся загрузки кассовых операций (иначе итог ещё 0,00).
        await screen.findByText(/10\.03\.2026 — Касса/u);
        const cashTotal = screen.getByText("Внесено в кассу за период");
        const row = cashTotal.parentElement as HTMLElement;
        const value = row.lastElementChild as HTMLElement;

        expect(plain(value)).toMatch(/500,00/u);
        expect(plain(value)).not.toContain("₸");
        expect(value.style.textAlign).toBe("right");
    });
});
