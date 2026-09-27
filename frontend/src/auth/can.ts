// src/auth/can.ts
// Разрешения на действия (кнопки) по ролям. Источник — матрица прав с бэкенда
// (`/api/auth/permissions/me`, задача 2.6); пока права не загружены — откат к
// историческим захардкоженным правилам (ниже). Используется в GenericList для
// скрытия кнопок «Добавить/Редактировать/Удалить» по роли.

import { getPermissions, getPermissionsRole } from "./permissions";

// --- ИСТОРИЧЕСКИЕ ПРАВИЛА (фолбэк до загрузки матрицы) ---

const SETTINGS_RESOURCES = ["tariffs", "services_type", "tariff_types", "cash_points"];
const REGISTER_RESOURCES = ["accounts_register", "accruals_register", "cash_register", "meter_readings"];

// Типы тарифов — системный справочник, «зашит»: не редактируется/не удаляется даже админом.
const LOCKED_RESOURCES = ["tariff_types"];
const OPERATION_WRITE_DELETE = [
    "payments",
    "transactions",
    "accrual_documents",
    "receipt_documents",
    "meter_reading_documents",
    "owners",
    "apartments",
    "accounts",
    "meters",
];

// Какие ресурсы Кассир может создавать (Вариант A): только Приход/Расход + справочники учёта.
const CASHIER_CREATE = ["payments", "apartments", "accounts", "owners"];
// Какие ресурсы Кассир может РЕДАКТИРОВАТЬ: справочники учёта (но не Приход/Расход).
const CASHIER_EDIT = ["apartments", "accounts", "owners"];

// Контролер вносит показания (создаёт/правит документ показаний) и правит счетчики.
const CONTROLLER_CREATE = ["meter_reading_documents", "meters"];

// Что контролер может ЧИТАТЬ (показания + справочники для выбора) — как в бэкенде.
const CONTROLLER_ALLOWED = [
    "meter_reading_documents",
    "meter_readings",
    "meters",
    "apartments",
    "apartment_residents",
    "accounts",
    "owners",
];

const fallbackCreate = (role: string, resource: string): boolean => {
    if (LOCKED_RESOURCES.includes(resource)) return false;
    if (role === "admin") return true;
    if (role === "operator") return !SETTINGS_RESOURCES.includes(resource) && !REGISTER_RESOURCES.includes(resource);
    if (role === "cashier") return CASHIER_CREATE.includes(resource) && !REGISTER_RESOURCES.includes(resource);
    if (role === "controller") return CONTROLLER_CREATE.includes(resource);
    return false; // resident
};

const fallbackEdit = (role: string, resource: string): boolean => {
    if (LOCKED_RESOURCES.includes(resource)) return false;
    if (role === "admin") return true;
    if (role === "operator") return !SETTINGS_RESOURCES.includes(resource) && !REGISTER_RESOURCES.includes(resource);
    if (role === "cashier") return CASHIER_EDIT.includes(resource);
    if (role === "controller") return CONTROLLER_CREATE.includes(resource);
    return false; // resident
};

const fallbackDelete = (role: string, resource: string): boolean => {
    if (LOCKED_RESOURCES.includes(resource)) return false;
    if (role === "admin") return true;
    if (role === "operator") return OPERATION_WRITE_DELETE.includes(resource);
    return false; // cashier / controller / resident
};

// Право чтения (ось `read` матрицы, НЕ видимость меню): нужно для гейта
// «проваливания» по ссылкам (2.21). Фолбэк — исторические правила бэкенда.
const fallbackRead = (role: string, resource: string): boolean => {
    if (role === "admin" || role === "auditor") return true;
    if (role === "controller") return CONTROLLER_ALLOWED.includes(resource);
    if (role === "operator" || role === "cashier") return true;
    return false; // resident
};

/** Права ресурса из матрицы (если она загружена для этой роли), иначе null. */
const storedPerm = (role: string, resource: string) => {
    const perms = getPermissions();
    if (perms && getPermissionsRole() === role) return perms[resource] ?? null;
    return null;
};

export const canCreate = (role: string, resource: string): boolean =>
    storedPerm(role, resource)?.create ?? fallbackCreate(role, resource);

export const canEdit = (role: string, resource: string): boolean =>
    storedPerm(role, resource)?.edit ?? fallbackEdit(role, resource);

export const canDelete = (role: string, resource: string): boolean =>
    storedPerm(role, resource)?.delete ?? fallbackDelete(role, resource);

export const canRead = (role: string, resource: string): boolean =>
    storedPerm(role, resource)?.read ?? fallbackRead(role, resource);
