// src/components/common/ReferenceDrillProvider.test.tsx
// RTL: стековое read-only «проваливание» (2.21) — по вызову drill() открывается окно
// просмотра связанной записи с её полями; заголовок — «Просмотр: <ресурс>».

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { ReferenceDrillProvider } from "./ReferenceDrillProvider";
import { useReferenceDrill } from "./referenceDrillContext";
import { clearToken, setIdentity } from "../../auth/token";

const json = (body: unknown) =>
    new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
    });

const stubApi = () =>
    vi.stubGlobal(
        "fetch",
        vi.fn(async (url: RequestInfo | URL) => {
            const u = String(url);
            if (u.includes("/meta/owners")) {
                return json({
                    fields: [
                        { name: "full_name", label: "ФИО", type: "string", required: true },
                        { name: "phone", label: "Телефон", type: "string" },
                    ],
                });
            }
            if (u.includes("/owners/42")) {
                return json({ id: 42, full_name: "Иванов Иван", phone: "7011234567" });
            }
            return json({});
        }),
    );

/** Кнопка-потребитель контекста: вызывает drill при клике. */
const DrillButton = () => {
    const { drill, canDrill } = useReferenceDrill();
    return (
        <>
            <button onClick={() => drill("owners", 42)}>drill-owner</button>
            <span data-testid="can-owners">{String(canDrill("owners"))}</span>
            <span data-testid="can-tariff-types">{String(canDrill("tariff_types"))}</span>
        </>
    );
};

afterEach(() => {
    vi.unstubAllGlobals();
    clearToken();
});

describe("ReferenceDrillProvider", () => {
    it("открывает просмотр связанной записи по drill()", async () => {
        setIdentity({ id: 1, username: "admin", full_name: "Админ", role: "admin", role_name: "Администратор" });
        stubApi();
        render(
            <ReferenceDrillProvider>
                <DrillButton />
            </ReferenceDrillProvider>,
        );

        fireEvent.click(screen.getByText("drill-owner"));

        // Заголовок окна и поле записи из мок-ответа.
        expect(await screen.findByText("Просмотр: Контрагент")).toBeTruthy();
        expect(await screen.findByDisplayValue("Иванов Иван")).toBeTruthy();
    });

    it("canDrill отражает право чтения роли", () => {
        setIdentity({ id: 1, username: "admin", full_name: "Админ", role: "admin", role_name: "Администратор" });
        render(
            <ReferenceDrillProvider>
                <DrillButton />
            </ReferenceDrillProvider>,
        );
        expect(screen.getByTestId("can-owners").textContent).toBe("true");
    });
});
