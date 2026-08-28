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
 * - `allKeys` — все доступные ключи колонок (для корректной инициализации).
 * - `visibleKeys` — множество ключей видимых колонок; `null` = настройка не задана (все видны).
 * - `toggle` — показать/скрыть колонку с сохранением в localStorage.
 */
export const useVisibleColumns = (resource: string, role: string, allKeys: string[]) => {
    const key = storageKey(resource, role);
    const [visibleKeys, setVisibleKeys] = useState<Set<string> | null>(() => load(key));

    useEffect(() => {
        // При смене ресурса/роли перечитываем сохранённое значение.
        setVisibleKeys(load(key));
    }, [key]);

    const toggle = useCallback(
        (columnKey: string, checked: boolean) => {
            setVisibleKeys((prev) => {
                // Если настройки ещё нет (null = все видны) — строим базис из всех колонок,
                // чтобы снятие одной колонки оставило остальные видимыми.
                const next = new Set(prev && prev.size > 0 ? prev : allKeys);
                if (checked) {
                    next.add(columnKey);
                } else {
                    next.delete(columnKey);
                }
                localStorage.setItem(key, JSON.stringify([...next]));
                return next;
            });
        },
        [key, allKeys],
    );

    return { visibleKeys, toggle };
};

/** Отбирает колонки, которые должны показываться (по сохранённой настройке).
 * `null` (настройка не задана) — показать все; пустое множество — скрыть все. */
export const filterVisibleColumns = <T extends ColumnMeta>(
    allColumns: T[],
    visibleKeys: Set<string> | null,
): T[] => {
    if (!visibleKeys) return allColumns;
    return allColumns.filter((col) => visibleKeys.has(col.key));
};
