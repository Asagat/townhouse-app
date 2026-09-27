// src/auth/menuAccess.ts
// Видимость разделов меню. Источник — матрица прав с бэкенда (задача 2.6, поле
// `menu`); пока права не загружены — откат к исторической карте `resourceRoles`
// (ниже). Разделы, которых нет в матрице (`users`, `cabinet`), всегда по фолбэку.

import type { Category, ResourceItem } from "../config/menu";
import { getPermissions, getPermissionsRole } from "./permissions";

export const ROLE_OPTIONS_LABELS: Record<string, string> = {
    admin: "Администратор",
    operator: "Оператор",
    cashier: "Кассир",
    controller: "Контролер",
    resident: "Житель",
    auditor: "Аудитор",
};

// Историческая карта видимости разделов меню по ролям (фолбэк).
export const resourceRoles: Record<string, string[]> = {
    dashboard: ["admin", "operator", "cashier", "auditor"],
    payments: ["admin", "operator", "cashier"],
    accrual_documents: ["admin", "operator"],
    meter_reading_documents: ["admin", "operator", "controller"],
    receipt_documents: ["admin", "operator"],
    writeoff_documents: ["admin", "operator"],
    tariffs: ["admin", "operator"],
    cash_points: ["admin", "operator"],
    owners: ["admin", "operator", "cashier", "controller"],
    apartments: ["admin", "operator", "cashier", "controller"],
    accounts: ["admin", "operator", "cashier", "controller"],
    meter_readings: ["admin", "operator", "controller"],
    accounts_register: ["admin", "operator", "cashier"],
    accruals_register: ["admin", "operator", "cashier"],
    cash_register: ["admin", "operator", "cashier"],
    tariff_types: ["admin", "operator"],
    services_type: ["admin", "operator"],
    analytic_articles: ["admin", "operator"],
    meters: ["admin", "operator", "controller"],
    users: ["admin"],
    prefixes: ["admin"],
    cabinet_admin: ["admin"],
    cabinet: ["resident"],
    cash_report: ["admin", "operator", "cashier"],
    expense_report: ["admin", "operator", "cashier"],
    debtors_report: ["admin", "operator", "cashier"],
    statement_report: ["admin", "operator", "cashier"],
};

const fallbackAccess = (role: string, key: string): boolean => {
    // Аудитор видит все разделы (только чтение), кроме «Пользователи и права», «Префиксы» и ЛК жителя.
    if (role === "auditor") return key !== "users" && key !== "prefixes" && key !== "cabinet";
    const allowed = resourceRoles[key];
    if (!allowed) return true; // неизвестные ресурсы показываем всем
    return allowed.includes(role);
};

export const hasResourceAccess = (role: string, key: string): boolean => {
    const perms = getPermissions();
    if (perms && getPermissionsRole() === role && key in perms) {
        return perms[key].menu;
    }
    return fallbackAccess(role, key);
};

export const filterCategoriesByRole = (role: string, cats: Category[]): Category[] => {
    if (!role) return cats; // роль ещё не известна — не скрываем (избегаем мигания пустого меню)
    return cats
        .map((cat) => ({
            ...cat,
            items: cat.items.filter((item: ResourceItem) => hasResourceAccess(role, item.key)),
        }))
        .filter((cat) => cat.items.length > 0);
};
