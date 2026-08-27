// src/config/columns.ts

import type { Column, FieldMeta } from '../types';
import { formatDate, formatDateTime, formatNumber, formatBool } from './formatters';

/**
 * Базовые колонки по умолчанию, если для ресурса не задана своя конфигурация
 */
export const defaultColumns: Column[] = [
    { key: 'full_name', label: 'ФИО' },
    { key: 'phone', label: 'Телефон' },
];

/**
 * Конфигурация колонок для каждого ресурса
 * Используем вложенные поля (apartment.number, owner.full_name и т.д.)
 */
export const columnsConfig: Record<string, Column[]> = {
    apartments: [
        { key: 'apartment_number', label: '№ квартиры' },
        { key: 'address', label: 'Адрес' },
        { key: 'square', label: 'Площадь, м²', format: formatNumber },
        { key: 'owner.full_name', label: 'Собственник' },
        { key: 'owner.phone', label: 'Телефон собственника' },
    ],

    accounts: [
        { key: 'account_number', label: '№ счёта' },
        { key: 'account_name', label: 'Наименование' },
        { key: 'is_active', label: 'Активен', format: formatBool },
        { key: 'apartment.apartment_number', label: '№ квартиры' },
        { key: 'apartment.owner.full_name', label: 'Собственник' },
    ],

    cash_points: [
        { key: 'name', label: 'Наименование' },
        { key: 'is_active', label: 'Активен', format: formatBool },
    ],

    payments: [
        { key: 'title', label: 'Название' },
        { key: 'transaction_date', label: 'Дата', format: formatDateTime },
        { key: 'cash_point.name', label: 'Касса/Счёт' },
        { key: 'apartment.apartment_number', label: '№ квартиры' },
        { key: 'account.account_number', label: 'Лицевой счёт' },
        { key: 'owner.full_name', label: 'Собственник' },
        { key: 'transaction_type', label: 'Тип операции' },
        { key: 'amount', label: 'Сумма', format: formatNumber },
        { key: 'notes', label: 'Примечание' },
        { key: 'created_by_name', label: 'Автор' },
    ],

    transactions: [
        { key: 'title', label: 'Название' },
        { key: 'transaction_date', label: 'Дата', format: formatDateTime },
        { key: 'cash_point.name', label: 'Касса/Счёт' },
        { key: 'apartment.apartment_number', label: '№ квартиры' },
        { key: 'account.account_number', label: 'Лицевой счёт' },
        { key: 'owner.full_name', label: 'Собственник' },
        { key: 'transaction_type', label: 'Тип операции' },
        { key: 'amount', label: 'Сумма', format: formatNumber },
        { key: 'notes', label: 'Примечание' },
        { key: 'created_by_name', label: 'Автор' },
    ],

    accrual_documents: [
        { key: 'title', label: 'Название' },
        { key: 'accrual_date', label: 'Дата начисления', format: formatDate },
        { key: 'accruals_count', label: 'Количество записей' },
        { key: 'total_amount', label: 'Общая сумма', format: formatNumber },
        { key: 'created_at', label: 'Дата создания', format: formatDateTime },
        { key: 'created_by_name', label: 'Автор' },
    ],

    accruals_register: [
        { key: 'apartment.apartment_number', label: '№ квартиры' },
        { key: 'account.account_number', label: 'Лицевой счёт' },
        { key: 'services_type.services_type', label: 'Вид услуги' },
        { key: 'accrual_date', label: 'Дата начисления', format: formatDate },
        { key: 'past_reading_value', label: 'Показание прошлое', format: formatNumber },
        { key: 'current_reading_value', label: 'Показание текущее', format: formatNumber },
        { key: 'consumption', label: 'Потребление', format: formatNumber },
        { key: 'amount', label: 'Сумма', format: formatNumber },
        { key: 'document_title', label: 'Документ' },
    ],

    accounts_register: [
        { key: 'apartment.apartment_number', label: '№ квартиры' },
        { key: 'account.account_number', label: 'Лицевой счёт' },
        { key: 'services_type.services_type', label: 'Вид услуги' },
        { key: 'operation_date', label: 'Дата операции', format: formatDateTime },
        { key: 'income', label: 'Приход', format: formatNumber },
        { key: 'expense', label: 'Расход', format: formatNumber },
        { key: 'balance_after', label: 'Баланс', format: formatNumber },
        { key: 'document_title', label: 'Документ' },
    ],

    cash_register: [
        { key: 'apartment.apartment_number', label: '№ квартиры' },
        { key: 'account.account_number', label: 'Лицевой счёт' },
        { key: 'operation_date', label: 'Дата операции', format: formatDateTime },
        { key: 'income', label: 'Приход', format: formatNumber },
        { key: 'expense', label: 'Расход', format: formatNumber },
        { key: 'balance_after', label: 'Баланс', format: formatNumber },
        { key: 'document_title', label: 'Документ' },
    ],

    services_type: [
        { key: 'services_type', label: 'Вид услуги' },
        { key: 'priority', label: 'Приоритет списания' },
    ],

    tariff_types: [
        { key: 'name', label: 'Наименование' },
    ],

    tariffs: [
        { key: 'price', label: 'Цена', format: formatNumber },
        { key: 'unit', label: 'Ед. изм.' },
        { key: 'valid_from', label: 'Действует с', format: formatDate },
        { key: 'services_type.services_type', label: 'Вид услуги' },
        { key: 'tariff_type.name', label: 'Тип тарифа' },
    ],

    meters: [
        { key: 'serial_number', label: 'Серийный номер' },
        { key: 'installed_at', label: 'Дата установки', format: formatDate },
        { key: 'apartment.apartment_number', label: '№ квартиры' },
        { key: 'services_type.services_type', label: 'Вид услуги' },
    ],

    meter_readings: [
        { key: 'apartment.apartment_number', label: '№ квартиры' },
        { key: 'services_type.services_type', label: 'Вид услуги' },
        { key: 'reading_date', label: 'Дата показания', format: formatDate },
        { key: 'reading', label: 'Показание', format: formatNumber },
        { key: 'meter.serial_number', label: 'Счётчик' },
        { key: 'document.title', label: 'Документ' },
    ],

    meter_reading_documents: [
        { key: 'title', label: 'Название' },
        { key: 'reading_date', label: 'Дата показаний', format: formatDate },
        { key: 'services_type.services_type', label: 'Вид услуги' },
        { key: 'readings_count', label: 'Количество записей' },
        { key: 'created_at', label: 'Дата создания', format: formatDateTime },
        { key: 'created_by_name', label: 'Автор' },
    ],

    receipt_documents: [
        { key: 'apartment_number', label: '№ квартиры' },
        { key: 'owner_name', label: 'Собственник' },
        { key: 'account_number', label: 'Лицевой счёт' },
        { key: 'period_month', label: 'Месяц' },
        { key: 'period_year', label: 'Год' },
        { key: 'total_amount', label: 'Начислено', format: formatNumber },
        { key: 'debt', label: 'Долг', format: formatNumber },
        { key: 'overpayment', label: 'Переплата', format: formatNumber },
        { key: 'payable_amount', label: 'К оплате', format: formatNumber },
        { key: 'created_by_name', label: 'Автор' },
    ],

    writeoff_documents: [
        { key: 'writeoff_date', label: 'Дата', format: formatDate },
        { key: 'status', label: 'Статус' },
        { key: 'items_count', label: 'Записей' },
        { key: 'total_allocated', label: 'Распределено', format: formatNumber },
        { key: 'title', label: 'Название' },
        { key: 'created_at', label: 'Создан', format: formatDateTime },
        { key: 'created_by_name', label: 'Автор' },
    ],
};

/**
 * Конфигурация полей для форм
 */
export const formFieldConfig: Record<string, string[]> = {
    apartments: ['apartment_number', 'address', 'square', 'owner_id'],
    accounts: ['account_number', 'account_name', 'is_active', 'apartment_id'],
    cash_points: ['name', 'is_active'],
    payments: ['title', 'apartment_id', 'cash_point_id', 'transaction_type', 'amount', 'transaction_date', 'notes'],
    transactions: ['title', 'apartment_id', 'cash_point_id', 'transaction_type', 'amount', 'transaction_date', 'notes'],
    accruals_register: ['accrual_date', 'account_id', 'services_type_id', 'past_reading_value', 'current_reading_value', 'consumption', 'amount'],
    accounts_register: ['account_id', 'services_type_id', 'income', 'expense', 'balance_after'],
    services_type: ['services_type', 'priority'],
    tariff_types: ['name'],
    tariffs: ['services_type_id', 'tariff_type_id', 'price', 'unit', 'valid_from'],
    meters: ['serial_number', 'apartment_id', 'services_type_id', 'installed_at'],
    meter_readings: ['apartment_id', 'services_type_id', 'reading', 'reading_date'],
    meter_reading_documents: ['title', 'reading_date', 'services_type_id'],
    accrual_documents: ['accrual_date'],
};

/**
 * Сортирует поля формы в соответствии с конфигурацией
 */
export const sortFieldsForForm = (fields: FieldMeta[], resourceName: string): FieldMeta[] => {
    const order = formFieldConfig[resourceName];
    if (!order) {
        return fields;
    }

    const fieldMap = new Map(fields.map(field => [field.name, field]));
    const sortedFields: FieldMeta[] = [];
    const addedFields = new Set<string>();

    order.forEach(fieldName => {
        const field = fieldMap.get(fieldName);
        if (field) {
            sortedFields.push(field);
            addedFields.add(fieldName);
        }
    });

    fields.forEach(field => {
        if (!addedFields.has(field.name)) {
            sortedFields.push(field);
        }
    });

    return sortedFields;
};

/**
 * Проверяет, есть ли конфигурация для указанного ресурса
 */
export const hasColumnsConfig = (resourceName: string): boolean =>
    resourceName in columnsConfig;

/**
 * Получает конфигурацию колонок для ресурса или возвращает стандартные колонки
 */
export const getColumnsForResource = (resourceName: string): Column[] =>
    columnsConfig[resourceName] ?? defaultColumns;

/**
 * Проверяет, есть ли конфигурация порядка полей для ресурса
 */
export const hasFieldOrder = (resourceName: string): boolean =>
    resourceName in formFieldConfig;

/**
 * Получает порядок полей для ресурса или возвращает undefined
 */
export const getFieldOrder = (resourceName: string): string[] | undefined =>
    formFieldConfig[resourceName];
