// src/config/formatters.ts

/**
 * Формат даты для отображения в пользовательском интерфейсе
 */
export const DATE_FORMAT = 'DD.MM.YYYY';

/**
 * Форматирует дату в строку формата ДД.ММ.ГГГГ
 * (без сдвига по часовому поясу: дата вида YYYY-MM-DD разбирается по компонентам).
 * @param v - дата в любом формате (строка, Date, null, undefined)
 * @returns отформатированная дата или "—" если значение отсутствует
 */
export const formatDate = (v: any): string => {
    if (v == null || v === '') return '—';
    const s = String(v);
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) {
        return `${m[3]}.${m[2]}.${m[1]}`;
    }
    const d = new Date(s);
    if (Number.isNaN(d.getTime())) return '—';
    const p = (n: number) => String(n).padStart(2, '0');
    return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}`;
};

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

/**
 * Денежный формат: разделители разрядов и ровно 2 знака после запятой
 * (например, «1 234,50»). Для пустого/некорректного значения — «—».
 */
export const formatMoney = (v: any): string => {
    if (v == null || v === '') return '—';
    const n = Number(v);
    if (!Number.isFinite(n)) return '—';
    return n.toLocaleString('ru-RU', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
};

/** Имена полей, являющихся деньгами (для форматирования в формах). */
const MONEY_FIELD_NAMES = new Set([
    'amount',
    'total_amount',
    'price',
    'income',
    'expense',
    'balance_after',
    'debt',
    'overpayment',
    'payable_amount',
    'allocated',
    'total_allocated',
]);

export const isMoneyFieldName = (name: string): boolean => MONEY_FIELD_NAMES.has(name);

/**
 * Приводит телефон к локальному номеру (10 цифр, без кода страны):
 * убирает «+7»/«8» в начале, если номер набран в национальном/международном формате.
 * Для неполного ввода возвращает набранные цифры как есть (до 10).
 */
export const normalizePhone = (value: any): string => {
    const d = String(value ?? '').replace(/\D/g, '');
    if (!d) return '';
    if (d.length === 11 && (d[0] === '7' || d[0] === '8')) return d.slice(1, 11);
    return d.slice(0, 10);
};

/** Накладывает маску «+7(XXX)XXX-XX-XX» на локальный номер (10 цифр). */
const maskLocalPhone = (local: string): string => {
    let out = '+7';
    if (local.length > 0) out += '(' + local.slice(0, 3);
    if (local.length > 3) out += ')' + local.slice(3, 6);
    if (local.length > 6) out += '-' + local.slice(6, 8);
    if (local.length > 8) out += '-' + local.slice(8, 10);
    return out;
};

/**
 * Телефон в виде «+7(XXX)XXX-XX-XX»; для пустого/некорректного значения — «—».
 * Используется в режиме просмотра форм.
 */
export const formatPhone = (value: any): string => {
    const local = normalizePhone(value);
    if (!local) return '—';
    return maskLocalPhone(local);
};

/**
 * Маска «+7(XXX)XXX-XX-XX» для отображения значения (пустое значение — пустая строка).
 */
export const formatPhoneInput = (value: any): string => {
    const local = normalizePhone(value);
    if (!local) return '';
    return maskLocalPhone(local);
};

/**
 * formatter для денежного InputNumber: «1 234,50».
 * (пробелы — разделители разрядов, запятая — десятичный разделитель)
 */
export const moneyInputFormatter = (value?: number | string): string => {
    if (value === undefined || value === null || value === '') return '';
    const cleaned = String(value).replace(/[^\d.,-]/g, '').replace(',', '.');
    const n = Number(cleaned);
    if (!Number.isFinite(n)) return '';
    return n.toLocaleString('ru-RU', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
};

/** parser для денежного InputNumber: убирает пробелы/разделители, запятую → точку. */
export const moneyInputParser = (text?: string): string => {
    if (text === undefined || text === null) return '';
    return String(text).replace(/[^\d.,-]/g, '').replace(',', '.');
};

/** Названия месяцев (именительный падеж, как в «Январь, 2025 г.»). */
const MONTH_NAMES = [
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];

/** Названия месяцев в родительном падеже (как в «31 марта 2026»). */
const MONTH_NAMES_GENITIVE = [
    'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
];

/**
 * Дата прописью «31 марта 2026» (без «г.»).
 * Разбор по компонентам без сдвига по часовому поясу (дата вида YYYY-MM-DD).
 */
export const formatDateLong = (v: any): string => {
    if (v == null || v === '') return '—';
    const s = String(v);
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) {
        const day = parseInt(m[3], 10);
        const month = parseInt(m[2], 10);
        const year = parseInt(m[1], 10);
        if (month >= 1 && month <= 12) {
            return `${day} ${MONTH_NAMES_GENITIVE[month - 1]} ${year}`;
        }
    }
    const d = new Date(s);
    if (Number.isNaN(d.getTime())) return '—';
    return `${d.getDate()} ${MONTH_NAMES_GENITIVE[d.getMonth()]} ${d.getFullYear()}`;
};

/**
 * Форматирует дату-период в «Январь, 2025 г.»
 * (без сдвига по часовому поясу: дата вида YYYY-MM-DD разбирается по компонентам).
 */
export const formatPeriod = (v: any): string => {
    if (v == null || v === '') return '—';
    const s = String(v);
    const m = s.match(/^(\d{4})-(\d{2})/);
    if (m) {
        const month = parseInt(m[2], 10);
        const year = parseInt(m[1], 10);
        if (month >= 1 && month <= 12) {
            return `${MONTH_NAMES[month - 1]}, ${year} г.`;
        }
    }
    const d = new Date(s);
    if (Number.isNaN(d.getTime())) return '—';
    return `${MONTH_NAMES[d.getMonth()]}, ${d.getFullYear()} г.`;
};

/**
 * Название месяца по его номеру 1–12 («Январь»…«Декабрь»);
 * для пустого/некорректного значения — «—».
 */
export const formatMonth = (v: any): string => {
    const n = Number(v);
    if (!Number.isInteger(n) || n < 1 || n > 12) return '—';
    return MONTH_NAMES[n - 1];
};
