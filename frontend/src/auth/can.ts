// src/auth/can.ts
// Разрешения на действия (кнопки) по ролям — согласовано с backend/permissions.py
// и целевой моделью (см. ролевую матрицу). Используется в GenericList для
// скрытия кнопок «Добавить/Редактировать/Удалить» по роли.

const SETTINGS_RESOURCES = ["tariffs", "services_type", "tariff_types", "cash_points"];
const REGISTER_RESOURCES = ["accounts_register", "accruals_register", "cash_register", "meter_readings"];
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

// Контролер вносит показания (создаёт/правит документ показаний) и правит счетчики;
// квартиры/счета/контрагенты — только чтение (для выбора).
const CONTROLLER_CREATE = ["meter_reading_documents", "meters"];

export const canCreate = (role: string, resource: string): boolean => {
    if (role === "admin") return true;
    if (role === "operator") return !SETTINGS_RESOURCES.includes(resource) && !REGISTER_RESOURCES.includes(resource);
    if (role === "cashier") return CASHIER_CREATE.includes(resource) && !REGISTER_RESOURCES.includes(resource);
    if (role === "controller") return CONTROLLER_CREATE.includes(resource);
    return false; // resident
};

export const canEdit = (role: string, resource: string): boolean => {
    if (role === "admin") return true;
    if (role === "operator") return !SETTINGS_RESOURCES.includes(resource) && !REGISTER_RESOURCES.includes(resource);
    if (role === "cashier") return CASHIER_EDIT.includes(resource);
    if (role === "controller") return CONTROLLER_CREATE.includes(resource);
    return false; // resident
};

export const canDelete = (role: string, resource: string): boolean => {
    if (role === "admin") return true;
    if (role === "operator") return OPERATION_WRITE_DELETE.includes(resource);
    return false; // cashier / controller / resident
};
