import { useCallback, useEffect, useMemo, useState } from "react";

/**
 * Состояние настройки колонок (порядок + ширины) для конкретного ресурса.
 * Хранится в localStorage отдельно на каждый ресурс и сохраняется при изменении,
 * чтобы пользовательские настройки не терялись при перезагрузке.
 */

const storageKey = (resource: string) => `columnsConfig:${resource}`;

type ColumnConfigState = {
    order: string[];
    widths: Record<string, number>;
};

const DEFAULT_WIDTH = 150;
const MIN_WIDTH = 60;
const MAX_WIDTH = 600;

const loadState = (key: string): ColumnConfigState | null => {
    try {
        const raw = localStorage.getItem(key);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (
            !parsed ||
            typeof parsed !== "object" ||
            !Array.isArray(parsed.order) ||
            typeof parsed.widths !== "object" ||
            parsed.widths === null
        ) {
            return null;
        }
        return { order: parsed.order.filter((k: unknown) => typeof k === "string"), widths: parsed.widths };
    } catch {
        return null;
    }
};

export const useColumnConfig = (resource: string, columnKeys: string[]) => {
    const key = storageKey(resource);

    // Инициализация из localStorage либо порядок по умолчанию из конфига.
    const [order, setOrder] = useState<string[]>(() => {
        const saved = loadState(key);
        if (saved?.order && saved.order.length) return saved.order;
        return columnKeys;
    });
    const [widths, setWidths] = useState<Record<string, number>>(() => {
        const saved = loadState(key);
        return saved?.widths ?? {};
    });

    // Если порядок хранится, но не перекрывает текущий набор ключей — дополняем новыми справа.
    useEffect(() => {
        const known = new Set(columnKeys);
        setOrder((prev) => {
            const kept = prev.filter((k) => known.has(k));
            const missing = columnKeys.filter((k) => !kept.includes(k));
            return [...kept, ...missing];
        });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [resource, columnKeys.join(",")]);

    // Сохранение в localStorage.
    useEffect(() => {
        try {
            localStorage.setItem(key, JSON.stringify({ order, widths }));
        } catch {
            // localStorage недоступен — игнорируем, настройки просто не сохранятся
        }
    }, [key, order, widths]);

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

    const moveColumn = useCallback((fromKey: string, toKey: string) => {
        setOrder((prev) => {
            const from = prev.indexOf(fromKey);
            const to = prev.indexOf(toKey);
            if (from < 0 || to < 0 || from === to) return prev;
            const next = [...prev];
            next.splice(from, 1);
            next.splice(to, 0, fromKey);
            return next;
        });
    }, []);

    // Порядок, ограниченный только существующими колонками.
    const effectiveOrder = useMemo(() => {
        const known = new Set(columnKeys);
        const kept = order.filter((k) => known.has(k));
        const missing = columnKeys.filter((k) => !kept.includes(k));
        return [...kept, ...missing];
    }, [order, columnKeys]);

    const reset = useCallback(() => {
        setOrder(columnKeys);
        setWidths({});
    }, [columnKeys]);

    return { order: effectiveOrder, getWidth, setColumnWidth, moveColumn, reset };
};
