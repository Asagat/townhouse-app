// src/auth/can.test.ts
// Юнит-тесты разрешений на действия по ролям (3.2) — исторический фолбэк `can.ts`
// (когда матрица прав ещё не загружена, права берутся из этих правил).
// Матрица с бэкенда проверяется отдельно в menuAccess.test.ts.

import { describe, it, expect, beforeEach } from "vitest";

import { canCreate, canEdit, canDelete } from "./can";

beforeEach(() => {
    localStorage.clear(); // нет токена → матрица не загружена → действует фолбэк
});

describe("can (фолбэк): системный справочник «Типы тарифов» заперт для всех", () => {
    it("admin не может создавать/править/удалять tariff_types", () => {
        expect(canCreate("admin", "tariff_types")).toBe(false);
        expect(canEdit("admin", "tariff_types")).toBe(false);
        expect(canDelete("admin", "tariff_types")).toBe(false);
    });
});

describe("can (фолбэк): admin", () => {
    it("полный доступ к обычным ресурсам", () => {
        expect(canCreate("admin", "payments")).toBe(true);
        expect(canEdit("admin", "tariffs")).toBe(true);
        expect(canDelete("admin", "accounts")).toBe(true);
    });
});

describe("can (фолбэк): operator", () => {
    it("создание/правка — кроме «настроек» и регистров", () => {
        expect(canCreate("operator", "payments")).toBe(true);
        expect(canCreate("operator", "tariffs")).toBe(false); // «настройки»
        expect(canEdit("operator", "accounts_register")).toBe(false); // регистр
        expect(canCreate("operator", "cash_points")).toBe(false);
    });

    it("удаление — только операционные документы/справочники", () => {
        expect(canDelete("operator", "payments")).toBe(true);
        expect(canDelete("operator", "accounts")).toBe(true);
        expect(canDelete("operator", "services_type")).toBe(false);
    });
});

describe("can (фолбэк): cashier", () => {
    it("создаёт Приход/Расход и справочники учёта, но не правит Приход/Расход", () => {
        expect(canCreate("cashier", "payments")).toBe(true);
        expect(canCreate("cashier", "apartments")).toBe(true);
        expect(canCreate("cashier", "accrual_documents")).toBe(false);
        expect(canEdit("cashier", "payments")).toBe(false);
        expect(canEdit("cashier", "owners")).toBe(true);
        expect(canDelete("cashier", "payments")).toBe(false);
    });
});

describe("can (фолбэк): controller", () => {
    it("только показания и счётчики", () => {
        expect(canCreate("controller", "meter_reading_documents")).toBe(true);
        expect(canCreate("controller", "meters")).toBe(true);
        expect(canCreate("controller", "payments")).toBe(false);
        expect(canDelete("controller", "meters")).toBe(false);
    });
});

describe("can (фолбэк): resident", () => {
    it("ничего не может", () => {
        for (const resource of ["payments", "apartments", "meters"]) {
            expect(canCreate("resident", resource)).toBe(false);
            expect(canEdit("resident", resource)).toBe(false);
            expect(canDelete("resident", resource)).toBe(false);
        }
    });
});
