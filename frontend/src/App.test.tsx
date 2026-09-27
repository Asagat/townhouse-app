// src/App.test.tsx
// RTL-тесты маршрутизации приложения (deep-link):
//   1) прямая ссылка на /dashboard при валидной сессии (admin) рендерит Дашборд —
//      маршрут ресурса зарегистрирован, catch-all `*` его не перехватывает;
//   2) без токена /dashboard уводит на /login (штатный гейт авторизации).
//
// Сеть замокана (fetch); localStorage готовит «сессию» перед рендером.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";

import App from "./App";

const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("App — маршрутизация по прямым ссылкам", () => {
    beforeEach(() => {
        window.history.pushState({}, "", "/dashboard");
        vi.stubGlobal(
            "fetch",
            vi.fn(async (url: RequestInfo | URL) => {
                const u = String(url);
                if (u.includes("/auth/permissions/me")) return json({ role: "admin", keys: {} });
                if (u.includes("/dashboard")) {
                    return json({
                        metrics: { accrued: 0, received: 0, written_off: 0, debt: 0, cash_balance: 0, debtors_count: 0 },
                        top_debtors: [],
                        debt_dynamics: [],
                        expenses: { total: 0, articles: [], count: 0 },
                        window_days: 30,
                    });
                }
                return json({}, 401);
            }),
        );
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        localStorage.clear();
    });

    it("валидная сессия: /dashboard рендерит Дашборд и не уводит на другой маршрут", async () => {
        localStorage.setItem("townhouse_token", "t");
        localStorage.setItem(
            "townhouse_user",
            JSON.stringify({ id: 1, username: "admin", full_name: "Admin", role: "admin", role_name: "Администратор" }),
        );

        render(<App />);

        expect(await screen.findByText("Дашборд")).toBeTruthy();
        expect(window.location.pathname).toBe("/dashboard");
    });

    it("без токена: /dashboard уводит на форму входа (/login)", async () => {
        localStorage.clear();

        render(<App />);

        // Страница входа.
        expect(await screen.findByText("Вход в систему")).toBeTruthy();
        expect(window.location.pathname).toBe("/login");
    });
});
