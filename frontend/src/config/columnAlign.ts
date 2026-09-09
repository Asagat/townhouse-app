// src/config/columnAlign.ts
// Политика форматирования колонок списков (GenericList): выравнивание значений ячеек
// и заголовков по типу колонки. Правила (08.09.2026):
//
//   - названия столбцов — по центру;
//   - денежные значения — справа, с 2 знаками после запятой и без знака валюты «₸»
//     (сам текст форматирует formatMoney в config/formatters.ts);
//   - текстовые/описательные значения — слева;
//   - прочие (числовые счётчики, даты, булево «Да/Нет» и т.п.) — по центру.

import type { CSSProperties } from "react";

export type CellAlign = "left" | "center" | "right";

/** Денежные колонки: значения этих полей выравниваются вправо. */
const MONEY_KEYS: string[] = [
    "amount",
    "total_amount",
    "price",
    "income",
    "expense",
    "balance_after",
    "debt",
    "overpayment",
    "payable_amount",
    "allocated",
    "total_allocated",
];

/**
 * Текстовые/описательные колонки: выравниваются влево. Сюда входят свободные
 * строковые поля (названия, адреса, примечания), телефон, статусные подписи
 * и человекочитаемые названия связанных справочников.
 */
const TEXT_KEYS: string[] = [
    // свободный текст и описания
    "full_name",
    "owner_name",
    "name",
    "title",
    "address",
    "account_name",
    "notes",
    "comment",
    "unit",
    "phone",
    // подписи enum/выбора, показанные словами
    "status",
    "kind",
    "kind_label",
    "transaction_type",
    "doc_kind",
    "is_active_label",
    // названия услуг и другие человекочитаемые подписи ЛК/движений
    "service_name",
    "service",
    // вложенные человекочитаемые названия справочников
    "owner.full_name",
    "owner.phone",
    "apartment.owner.full_name",
    "cash_point.name",
    "article.name",
    "contractor.full_name",
    "services_type",
    "services_type.services_type",
    "tariff_type.name",
    "meter.serial_number",
    "document.title",
    "document_title",
    "created_by_name",
];

const MONEY_SET = new Set(MONEY_KEYS);
const TEXT_SET = new Set(TEXT_KEYS);

/** Выравнивание значения ячейки по имени колонки. */
export const cellAlign = (columnKey: string): CellAlign => {
    if (MONEY_SET.has(columnKey)) return "right";
    if (TEXT_SET.has(columnKey)) return "left";
    return "center";
};

/** Выравнивание заголовка колонки — всегда по центру. */
export const headerAlign = (): CellAlign => "center";

/** Inline-стиль выравнивания ячейки (используется в render/onCell колонок Table). */
export const cellAlignStyle = (columnKey: string): CSSProperties => ({
    textAlign: cellAlign(columnKey),
});

/** Inline-стиль заголовка колонки (Table onHeaderCell). */
export const headerAlignStyle = (): CSSProperties => ({ textAlign: headerAlign() });
