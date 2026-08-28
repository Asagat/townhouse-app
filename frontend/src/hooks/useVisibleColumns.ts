// frontend/src/hooks/useVisibleColumns.ts
// Настройка отображаемых колонок списка (Вариант A): настройка видимости колонок
// набора с сохранением в localStorage по (ресурс, роль).
//
// Храним МНОЖЕСТВО видимых ключей. Новые колонки (не присутствующие в сохранённом
// наборе) по умолчанию видимы — чтобы автодобавленные колонки не «терялись».

import { useCallback, useEffect, useState } from "react";

const STORAGE_PREFIX = "townhouse_visible_columns";

export interface ColumnMeta {
    key: string;
    label: string;
}

const storageKey = (resource: string, role: string) =>
    `${STORAGE_PREFIX}:${resource}:${role}`;

const load = (key: string): Set<string> | null => {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    try {
        return new Set(JSON.parse(raw) as string[]);
    } catch {
        return null;
    }
};

/**
 * Возвращает настройки видимости колонок для (resource, role).
 * - `visibleKeys` — множество ключей видимых колонок.
 * - `setVisibleKeys` — обновление (с сохранением в localStorage).
 */
export const useVisibleColumns = (resource: string, role: string) => {
    const key = storageKey(resource, role);
    const [visibleKeys, setVisibleKeys] = useState<Set<string>>(() => load(key) ?? null);

    useEffect(() => {
        // При смене ресурса/роли перечитываем сохранённое значение.
        setVisibleKeys(load(key) ?? null);
    }, [key]);

    const save = useCallback(
        (next: Set<string>) => {
            setVisibleKeys(next);
            localStorage.setItem(key, JSON.stringify([...next]));
        },
        [key],
    );

    const toggle = useCallback(
        (columnKey: string, checked: boolean) => {
            setVisibleKeys((prev) => {
                const next = new Set(prev ?? []);
                if (checked) {
                    next.add(columnKey);
                } else {
                    next.delete(columnKey);
                }
                localStorage.setItem(key, JSON.stringify([...next]));
                return next;
            });
        },
        [key],
    );

    return { visibleKeys, setVisibleKeys: save, toggle };
};

/** Отбирает колонки, которые должны показываться (по сохранённой настройке). */
export const filterVisibleColumns = <T extends ColumnMeta>(
    allColumns: T[],
    visibleKeys: Set<string> | null,
): T[] => {
    if (!visibleKeys || visibleKeys.size === 0) return allColumns;
    return allColumns.filter((col) => visibleKeys.has(col.key));
};
