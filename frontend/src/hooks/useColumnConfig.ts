import { useCallback, useEffect, useState } from "react";

/**
 * Ширины колонок для конкретного ресурса.
 * Хранится в localStorage отдельно на ресурс и сохраняется при изменении,
 * чтобы настройки пользователя не терялись при перезагрузке.
 */

const storageKey = (resource: string) => `columnsWidths:${resource}`;

const DEFAULT_WIDTH = 150;
const MIN_WIDTH = 60;
const MAX_WIDTH = 600;

const loadWidths = (key: string): Record<string, number> | null => {
    try {
        const raw = localStorage.getItem(key);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (typeof parsed !== "object" || parsed === null) return null;
        return parsed as Record<string, number>;
    } catch {
        return null;
    }
};

export const useColumnWidths = (resource: string) => {
    const key = storageKey(resource);

    const [widths, setWidths] = useState<Record<string, number>>(() => {
        return loadWidths(key) ?? {};
    });

    useEffect(() => {
        try {
            localStorage.setItem(key, JSON.stringify(widths));
        } catch {
            // localStorage недоступен — настройки просто не сохранятся
        }
    }, [key, widths]);

    const getWidth = useCallback(
        (colKey: string) => {
            const w = widths[colKey];
            return typeof w === "number" && w > 0 ? w : DEFAULT_WIDTH;
        },
        [widths],
    );

    const setColumnWidth = useCallback((colKey: string, width: number) => {
        const clamped = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(width)));
        setWidths((prev) => ({ ...prev, [colKey]: clamped }));
    }, []);

    return { getWidth, setColumnWidth };
};
