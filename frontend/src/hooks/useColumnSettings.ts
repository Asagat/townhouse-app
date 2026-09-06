// frontend/src/hooks/useColumnSettings.ts
// Настройка отображаемых колонок списка (роадмап 2.10): видимость (вариант A)
// и ПОРЯДОК колонок (вариант C) с сохранением в localStorage по (ресурс, роль).
//
// Храним объект { order, hidden }:
//   - order  — порядок ВСЕХ ключей колонок (перетаскивание в панели «Колонки»);
//   - hidden — скрытые ключи.
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
}

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
            return { order: allKeys, hidden: allKeys.filter((k) => !visible.has(k)) };
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
 * - `toggle(key, checked)` — показать/скрыть колонку.
 * - `move(fromIndex, toIndex)` — переставить колонку (drag&drop).
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
            save({ order: orderedAll, hidden: [...hidden] });
        },
        [settings, orderedAll, save],
    );

    const move = useCallback(
        (fromIndex: number, toIndex: number) => {
            if (fromIndex === toIndex) return;
            const order = [...orderedAll];
            const [moved] = order.splice(fromIndex, 1);
            order.splice(toIndex, 0, moved);
            save({ order, hidden: settings?.hidden ?? [] });
        },
        [orderedAll, settings, save],
    );

    return { orderedAll, hiddenKeys, toggle, move };
};
