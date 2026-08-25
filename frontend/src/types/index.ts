// src/types/index.ts

/**
 * Конфигурация колонки для таблицы
 */
export type Column = {
    key: string;
    label: string;
    format?: (value: any) => string;
};

/**
 * Метаданные поля формы, полученные с бэкенда
 */
export type FieldMeta = {
    name: string;
    label: string;
    type:
        | 'string'
        | 'text'
        | 'integer'
        | 'decimal'
        | 'date'
        | 'datetime'
        | 'boolean'
        | 'enum'
        | 'reference';
    required: boolean;
    reference?: string;
    choices?: { value: string; label: string }[];
    default?: string | number | boolean;
};

/**
 * Состояние модального окна для создания/редактирования записи
 */
export type ModalState = {
    mode: 'create' | 'edit';
    record?: Record<string, any>;
};

/**
 * Строка предпросмотра начислений
 */
export type AccrualPreviewRow = {
    row_number: number;
    account_id: number;
    account_id_label: string;
    services_type_id: number;
    services_type_id_label: string;
    tariff_id: number;
    tariff_id_label: string;
    past_reading_value: number | null;
    current_reading_value: number | null;
    consumption: number;
    amount: number;
};

/**
 * Ответ от API для предпросмотра начислений
 */
export type AccrualsPreviewResponse = {
    rows: AccrualPreviewRow[];
};

/**
 * Ответ от API для массового создания показаний
 */
export type BulkReadingsResponse = {
    created?: Array<{ id: number; apartment_id: number }>;
    errors?: Array<{ apartment_id: number; detail: string }>;
};

/**
 * Параметры для генерации начислений
 */
export type GenerateAccrualsPayload = {
    year: number;
    month: number;
    title?: string;
    rows: AccrualPreviewRow[];
};

/**
 * Параметры для массового создания показаний
 */
export type BulkReadingsPayload = {
    services_type_id: number;
    reading_date: string;
    entries: Array<{
        apartment_id: number;
        reading: number;
    }>;
};
