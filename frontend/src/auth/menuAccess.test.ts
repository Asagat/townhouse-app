// src/auth/menuAccess.test.ts
// Права роли (задача 2.6): меню и кнопки берутся из матрицы с бэкенда
// (/api/auth/permissions/me); пока права не загружены — действуют исторические
// правила (фолбэк). Здесь проверяется реальный модуль permissions с подменой fetch.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import { hasResourceAccess, filterCategoriesByRole } from "./menuAccess";
import { canCreate } from "./can";
import { loadPermissions } from "./permissions";
import { clearToken, setToken } from "./token";

const TOKEN_KEY = "townhouse_token";

const stubPermissions = (role: string, keys: Record<string, unknown>) => {
    vi.stubGlobal(
        "fetch",
        vi.fn(async () =>
            new Response(JSON.stringify({ role, keys }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
            }),
        ),
    );
};

beforeEach(() => {
    localStorage.clear();
});

afterEach(() => {
    clearToken();
    vi.unstubAllGlobals();
});

describe("menuAccess/can: фолбэк без матрицы", () => {
    it("использует исторические правила", () => {
        localStorage.removeItem(TOKEN_KEY);
        // Кассир: справочники видны, «Статьи» в меню скрыты (но читаются формой).
        expect(hasResourceAccess("cashier", "owners")).toBe(true);
        expect(hasResourceAccess("cashier", "analytic_articles")).toBe(false);
        expect(canCreate("cashier", "payments")).toBe(true);
        expect(canCreate("cashier", "tariffs")).toBe(false);
    });
});

describe("menuAccess/can: с матрицей прав", () => {
    it("меню и кнопки берутся из матрицы", async () => {
        stubPermissions("cashier", {
            // «Статьи»: чтение есть, раздел в меню включён вручную.
            analytic_articles: { menu: true, read: true, create: false, edit: false, delete: false },
            payments: { menu: false, read: true, create: true, edit: false, delete: false },
        });
        setToken("t");
        await loadPermissions();

        expect(hasResourceAccess("cashier", "analytic_articles")).toBe(true);
        expect(hasResourceAccess("cashier", "payments")).toBe(false); // пункт меню скрыт
        expect(canCreate("cashier", "payments")).toBe(true);
        // Ключа нет в матрице → историческое правило.
        expect(hasResourceAccess("cashier", "owners")).toBe(true);
    });

    it("filterCategoriesByRole скрывает пустые разделы", async () => {
        stubPermissions("cashier", {
            owners: { menu: true, read: true, create: false, edit: false, delete: false },
            apartments: { menu: false, read: true, create: false, edit: false, delete: false },
        });
        setToken("t");
        await loadPermissions();

        const cats = [
            { title: "Справочники", items: [
                { key: "owners", label: "Контрагенты", icon: "" },
                { key: "apartments", label: "Квартиры", icon: "" },
            ] },
            { title: "Пустой", items: [{ key: "apartments", label: "Квартиры", icon: "" }] },
        ];
        const out = filterCategoriesByRole("cashier", cats);
        expect(out).toHaveLength(1);
        expect(out[0].items.map((i) => i.key)).toEqual(["owners"]);
    });
});
