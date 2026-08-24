// src/config/columns.ts

import type { Column } from '../types';
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
 * Ключ - имя ресурса, значение - массив колонок для отображения в таблице
 */
export const columnsConfig: Record<string, Column[]> = {
    apartments: [
        { key: 'apartment_number', label: '№ квартиры' },
        { key: 'address', label: 'Адрес' },
        { key: 'square', label: 'Площадь, м²', format: formatNumber },
        { key: 'owner_id_label', label: 'Собственник' },
    ],

    accounts: [
        { key: 'account_number', label: '№ счёта' },
        { key: 'account_name', label: 'Наименование' },
        { key: 'is_active', label: 'Активен', format: formatBool },
        { key: 'apartment_id_label', label: 'Квартира' },
    ],

    cash_points: [
        { key: 'name', label: 'Наименование' },
        { key: 'is_active', label: 'Активен', format: formatBool },
    ],

    payments: [
        { key: 'transaction_date', label: 'Дата', format: formatDateTime },
        { key: 'apartment_id_label', label: 'Квартира' },
        { key: 'amount', label: 'Сумма', format: formatNumber },
        { key: 'transaction_type', label: 'Тип операции' },
        { key: 'account_label', label: 'Лицевой счёт' },
        { key: 'cash_point_id_label', label: 'Касса/Счёт' },
        { key: 'notes', label: 'Примечание' },
    ],

    accruals_register: [
        { key: 'accrual_date', label: 'Дата начисления', format: formatDate },
        { key: 'account_id_label', label: 'Лицевой счёт' },
        { key: 'services_type_id_label', label: 'Вид услуги' },
        { key: 'past_reading_value', label: 'Показание прошлое', format: formatNumber },
        { key: 'current_reading_value', label: 'Показание текущее', format: formatNumber },
        { key: 'consumption', label: 'Потребление', format: formatNumber },
        { key: 'amount', label: 'Сумма', format: formatNumber },
    ],

    accounts_register: [
        { key: 'operation_date', label: 'Дата операции', format: formatDateTime },
        { key: 'income', label: 'Приход', format: formatNumber },
        { key: 'expense', label: 'Расход', format: formatNumber },
        { key: 'balance_after', label: 'Баланс', format: formatNumber },
        { key: 'account_id_label', label: 'Лицевой счёт' },
    ],

    service_types: [
        { key: 'services_type', label: 'Вид услуги' },
    ],

    tariff_types: [
        { key: 'name', label: 'Наименование' },
    ],

    tariffs: [
        { key: 'price', label: 'Цена', format: formatNumber },
        { key: 'unit', label: 'Ед. изм.' },
        { key: 'valid_from', label: 'Действует с', format: formatDate },
        { key: 'services_type_id_label', label: 'Вид услуги' },
        { key: 'tariff_type_id_label', label: 'Тип тарифа' },
    ],

    meters: [
        { key: 'serial_number', label: 'Серийный номер' },
        { key: 'installed_at', label: 'Дата установки', format: formatDate },
        { key: 'apartment_id_label', label: 'Квартира' },
        { key: 'services_type_id_label', label: 'Вид услуги' },
    ],

    meter_readings: [
        { key: 'apartment_id_label', label: 'Квартира' },
        { key: 'services_type_id_label', label: 'Вид услуги' },
        { key: 'reading', label: 'Показание', format: formatNumber },
        { key: 'reading_date', label: 'Дата показания', format: formatDate },
        { key: 'meter_label', label: 'Счётчик' },
    ],
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
