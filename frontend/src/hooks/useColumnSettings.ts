// frontend/src/hooks/useColumnSettings.ts
// Логика настроек колонок списка (роадмап 2.10/2.1): видимость (вариант A),
// ПОРЯДОК колонок (вариант C) и ШИРИНЫ (ресайз, 2.1).
//
// Хранилище (localStorage-кэш + сервер per-user, роадмап 2.13) находится СНАРУЖИ:
// хук получает текущие настройки (`settings: {order, hidden, widths}`) и колбэк
// `onChange(next)` для сохранения. Новые колонки, добавленные в конфиг позже,
// по умолчанию видимы и дописываются в конец порядка (не «теряются»).

import { useCallback, useMemo } from "react";

export interface StoredColumnSettings {
    order: string[];
    hidden: string[];
    widths: Record<string, number>;
}

/**
 * Логика настроек колонок для (resource, role).
 * - `orderedAll` — все ключи колонок в текущем порядке (сохранённый либо исходный).
 * - `hiddenKeys` — множество скрытых ключей.
 * - `widths` — заданные пользователем ширины колонок (пусто — автоширина).
 * - `toggle(key, checked)` — показать/скрыть колонку.
 * - `move(fromIndex, toIndex)` / `moveKey(fromKey, toKey)` — переставить колонку.
 * - `setWidth(key, px)` — установить ширину колонки (ресайз).
 */
export const useColumnSettings = (
    allKeys: string[],
    settings: StoredColumnSettings | null,
    onChange: (next: StoredColumnSettings) => void,
) => {
    const orderedAll = useMemo(() => {
        const known = (settings?.order ?? []).filter((k) => allKeys.includes(k));
        // Новые колонки (появились после сохранения) — видимы, дописываются в конец.
        const missing = allKeys.filter((k) => !known.includes(k));
        return [...known, ...missing];
    }, [settings, allKeys]);

    const hiddenKeys = useMemo(() => new Set(settings?.hidden ?? []), [settings]);

    const widths = settings?.widths ?? {};

    const save = useCallback(
        (patch: Partial<StoredColumnSettings>) => {
            onChange({
                order: patch.order ?? orderedAll,
                hidden: patch.hidden ?? settings?.hidden ?? [],
                widths: patch.widths ?? settings?.widths ?? {},
            });
        },
        [onChange, orderedAll, settings],
    );

    const toggle = useCallback(
        (columnKey: string, checked: boolean) => {
            const hidden = new Set(settings?.hidden ?? []);
            if (checked) {
                hidden.delete(columnKey);
            } else {
                hidden.add(columnKey);
            }
            save({ hidden: [...hidden] });
        },
        [settings, save],
    );

    const move = useCallback(
        (fromIndex: number, toIndex: number) => {
            if (fromIndex === toIndex) return;
            const order = [...orderedAll];
            const [moved] = order.splice(fromIndex, 1);
            order.splice(toIndex, 0, moved);
            save({ order });
        },
        [orderedAll, save],
    );

    // Перестановка по ключам (drag&drop заголовков колонок, где видимые колонки
    // соседствуют в orderedAll со скрытыми).
    const moveKey = useCallback(
        (fromKey: string, toKey: string) => {
            if (fromKey === toKey) return;
            const order = [...orderedAll];
            const fromIdx = order.indexOf(fromKey);
            const toIdx = order.indexOf(toKey);
            if (fromIdx < 0 || toIdx < 0) return;
            order.splice(fromIdx, 1);
            order.splice(order.indexOf(toKey), 0, fromKey);
            save({ order });
        },
        [orderedAll, save],
    );

    const setWidth = useCallback(
        (columnKey: string, px: number) => {
            save({
                widths: { ...widths, [columnKey]: Math.max(40, Math.round(px)) },
            });
        },
        [widths, save],
    );

    return { orderedAll, hiddenKeys, widths, toggle, move, moveKey, setWidth };
};
