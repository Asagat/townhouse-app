// src/components/common/referenceDrillContext.ts
// Контекст «проваливания» по ссылкам (2.21). Разделён от провайдера, чтобы
// `RecordFormModal` мог пользоваться хуком, а провайдер — импортировать модалку
// (без циклических импортов).

import { createContext, useContext } from "react";

export interface ReferenceDrillApi {
    /** Открыть read-only просмотр записи связанного ресурса поверх текущего. */
    drill: (resource: string, id: number) => void;
    /** Есть ли у текущей роли право чтения этого ресурса (гейт для кнопки «…»). */
    canDrill: (resource: string) => boolean;
}

// По умолчанию — «проваливание» недоступно (когда провайдера нет, напр. в юнит-тестах).
const NOOP: ReferenceDrillApi = { drill: () => {}, canDrill: () => false };

export const ReferenceDrillContext = createContext<ReferenceDrillApi>(NOOP);

export const useReferenceDrill = (): ReferenceDrillApi => useContext(ReferenceDrillContext);
