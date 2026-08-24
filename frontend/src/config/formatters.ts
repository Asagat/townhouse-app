// src/config/formatters.ts

/**
 * Формат даты для отображения в пользовательском интерфейсе
 */
export const DATE_FORMAT = 'DD.MM.YYYY';

/**
 * Форматирует дату в строку формата ДД.ММ.ГГГГ
 * @param v - дата в любом формате (строка, Date, null, undefined)
 * @returns отформатированная дата или "—" если значение отсутствует
 */
export const formatDate = (v: any): string =>
    v ? new Date(v).toLocaleDateString('ru-RU') : '—';

/**
 * Форматирует дату и время в строку формата ДД.ММ.ГГГГ ЧЧ:ММ:СС
 * @param v - дата в любом формате (строка, Date, null, undefined)
 * @returns отформатированная дата и время или "—" если значение отсутствует
 */
export const formatDateTime = (v: any): string =>
    v ? new Date(v).toLocaleString('ru-RU') : '—';

/**
 * Форматирует число с разделителями тысяч
 * @param v - число (string, number, null, undefined)
 * @returns отформатированное число или "—" если значение отсутствует
 */
export const formatNumber = (v: any): string =>
    v != null ? Number(v).toLocaleString('ru-RU') : '—';

/**
 * Форматирует булево значение в "Да" или "Нет"
 * @param v - булево значение или значение, приводимое к boolean
 * @returns "Да" если true, "Нет" если false
 */
export const formatBool = (v: any): string =>
    v ? 'Да' : 'Нет';

/**
 * Форматирует цену с символом ₸
 * @param v - число (string, number, null, undefined)
 * @returns отформатированная цена с символом валюты или "—" если значение отсутствует
 */
export const formatPrice = (v: any): string =>
    v != null ? `${Number(v).toLocaleString('ru-RU')} ₸` : '—';
