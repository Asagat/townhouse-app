// src/auth/menuAccess.ts
// Видимость разделов меню по ролям (см. ролевую матрицу в ROADMAP).

import type { Category, ResourceItem } from "../config/menu";

export const ROLE_OPTIONS_LABELS: Record<string, string> = {
    admin: "Администратор",
    operator: "Оператор",
    cashier: "Кассир",
    controller: "Контролер",
    resident: "Житель",
};

// Роли, которым доступен каждый раздел меню (по ключу ресурса).
// Кассир (Вариант A — строгий): только Приход/Расход, Квартиры/Лицевые счета/
// Контрагенты, и Регистры (чтение). Показания/Счетчики/Настройки/Начисления/
// Квитанции/Кассы кассиру НЕ показываем.
// Контролер — только показания (+ квартиры/счета/контрагенты/счетчики для выбора).
export const resourceRoles: Record<string, string[]> = {
    // Документы
    payments: ["admin", "operator", "cashier"],
    accrual_documents: ["admin", "operator"],
    meter_reading_documents: ["admin", "operator", "controller"],
    receipt_documents: ["admin", "operator"],
    writeoff_documents: ["admin", "operator"],

    // Справочники
    tariffs: ["admin", "operator"],
    cash_points: ["admin", "operator"],
    owners: ["admin", "operator", "cashier", "controller"],
    apartments: ["admin", "operator", "cashier", "controller"],
    accounts: ["admin", "operator", "cashier", "controller"],

    // Регистры
    meter_readings: ["admin", "operator", "controller"],
    accounts_register: ["admin", "operator", "cashier"],
    accruals_register: ["admin", "operator", "cashier"],
    cash_register: ["admin", "operator", "cashier"],

    // Настройки
    tariff_types: ["admin", "operator"],
    services_type: ["admin", "operator"],
    analytic_articles: ["admin", "operator"],
    meters: ["admin", "operator", "controller"],

    // Администрирование
    users: ["admin"],
    // Просмотр личного кабинета жителя (только админ)
    cabinet_admin: ["admin"],

    // Личный кабинет (только житель)
    cabinet: ["resident"],

    // Отчёты (бухгалтерские роли)
    cash_report: ["admin", "operator", "cashier"],
};

export const hasResourceAccess = (role: string, key: string): boolean => {
    const allowed = resourceRoles[key];
    if (!allowed) return true; // неизвестные ресурсы показываем всем
    return allowed.includes(role);
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
