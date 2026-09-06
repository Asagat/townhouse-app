// frontend/src/hooks/useColumnSettings.ts
// Настройка отображаемых колонок списка (роадмап 2.10/2.1): видимость (вариант A),
// ПОРЯДОК колонок (вариант C) и ШИРИНЫ (ресайз, 2.1) с сохранением в localStorage
// по (ресурс, роль).
//
// Храним объект { order, hidden, widths }:
//   - order  — порядок ВСЕХ ключей колонок (перетаскивание заголовков/в панели «Колонки»);
//   - hidden — скрытые ключи;
//   - widths — заданные пользователем ширины колонок (ключ -> px).
// Новые колонки, добавленные в конфиг позже сохранения, по умолчанию видимы и
// дописываются в конец порядка (не «теряются»).
//
// Обратная совместимость: старый формат (массив видимых ключей) при чтении
// мигрируется в { order: исходный порядок, hidden: все остальные }.

import { useCallback, useEffect, useMemo, useState } from "react";

const STORAGE_PREFIX = "townhouse_visible_columns";

export interface StoredColumnSettings {
    order: string[];
    hidden: string[];
    widths: Record<string, number>;
}

const EMPTY_WIDTHS: Record<string, number> = {};

const storageKey = (resource: string, role: string) =>
    `${STORAGE_PREFIX}:${resource}:${role}`;

const load = (key: string, allKeys: string[]): StoredColumnSettings | null => {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    try {
        const parsed = JSON.parse(raw) as unknown;
        if (Array.isArray(parsed)) {
            // Старый формат (2.10-A): массив видимых ключей. Скрытые — остальные.
            const visible = new Set(parsed as string[]);
            return {
                order: allKeys,
                hidden: allKeys.filter((k) => !visible.has(k)),
                widths: EMPTY_WIDTHS,
            };
        }
        if (
            parsed &&
            typeof parsed === "object" &&
            Array.isArray((parsed as StoredColumnSettings).order)
        ) {
            const p = parsed as StoredColumnSettings;
            return {
                order: p.order,
                hidden: Array.isArray(p.hidden) ? p.hidden : [],
                widths:
                    p.widths && typeof p.widths === "object" ? p.widths : EMPTY_WIDTHS,
            };
        }
        return null;
    } catch {
        return null;
    }
};

/**
 * Настройки колонок списка для (resource, role).
 * - `orderedAll` — все ключи колонок в текущем порядке (сохранённый либо исходный).
 * - `hiddenKeys` — множество скрытых ключей.
 * - `widths` — заданные пользователем ширины колонок (пусто — автоширина).
 * - `toggle(key, checked)` — показать/скрыть колонку.
 * - `move(fromIndex, toIndex)` / `moveKey(fromKey, toKey)` — переставить колонку.
 * - `setWidth(key, px)` — установить ширину колонки (ресайз).
 */
export const useColumnSettings = (
    resource: string,
    role: string,
    allKeys: string[],
) => {
    const key = storageKey(resource, role);
    const [settings, setSettings] = useState<StoredColumnSettings | null>(() =>
        load(key, allKeys),
    );

    useEffect(() => {
        // При смене ресурса/роли перечитываем сохранённое значение.
        setSettings(load(key, allKeys));
    }, [key, allKeys]);

    const orderedAll = useMemo(() => {
        const known = (settings?.order ?? []).filter((k) => allKeys.includes(k));
        // Новые колонки (появились после сохранения) — видимы, дописываются в конец.
        const missing = allKeys.filter((k) => !known.includes(k));
        return [...known, ...missing];
    }, [settings, allKeys]);

    const hiddenKeys = useMemo(
        () => new Set(settings?.hidden ?? []),
        [settings],
    );

    const widths = settings?.widths ?? EMPTY_WIDTHS;

    const save = useCallback(
        (next: StoredColumnSettings) => {
            localStorage.setItem(key, JSON.stringify(next));
            setSettings(next);
        },
        [key],
    );

    const toggle = useCallback(
        (columnKey: string, checked: boolean) => {
            const hidden = new Set(settings?.hidden ?? []);
            if (checked) {
                hidden.delete(columnKey);
            } else {
                hidden.add(columnKey);
            }
            save({ order: orderedAll, hidden: [...hidden], widths });
        },
        [settings, orderedAll, widths, save],
    );

    const move = useCallback(
        (fromIndex: number, toIndex: number) => {
            if (fromIndex === toIndex) return;
            const order = [...orderedAll];
            const [moved] = order.splice(fromIndex, 1);
            order.splice(toIndex, 0, moved);
            save({ order, hidden: settings?.hidden ?? [], widths });
        },
        [orderedAll, settings, widths, save],
    );

    // Перестановка по ключам (используется при drag&drop заголовков колонок, где
    // видимые колонки соседствуют в orderedAll со скрытыми).
    const moveKey = useCallback(
        (fromKey: string, toKey: string) => {
            if (fromKey === toKey) return;
            const order = [...orderedAll];
            const fromIdx = order.indexOf(fromKey);
            const toIdx = order.indexOf(toKey);
            if (fromIdx < 0 || toIdx < 0) return;
            order.splice(fromIdx, 1);
            order.splice(order.indexOf(toKey), 0, fromKey);
            save({ order, hidden: settings?.hidden ?? [], widths });
        },
        [orderedAll, settings, widths, save],
    );

    const setWidth = useCallback(
        (columnKey: string, px: number) => {
            const nextWidths = { ...widths, [columnKey]: Math.max(40, Math.round(px)) };
            save({
                order: orderedAll,
                hidden: settings?.hidden ?? [],
                widths: nextWidths,
            });
        },
        [orderedAll, settings, widths, save],
    );

    return { orderedAll, hiddenKeys, widths, toggle, move, moveKey, setWidth };
};
