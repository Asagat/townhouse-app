// src/components/common/ReferenceFilterSelect.tsx
// Фильтр-список со значениями из справочника (для колонок-справочников в Б10).
// Значение фильтра — отображаемое значение записи (сервер: eq по display-полю),
// label — расширенная подпись. Ресурс справочника грузится один раз (кэш на модуль),
// чтобы повторные открытия панели фильтров не дёргали API.

import { useEffect, useState } from "react";
import { Select } from "antd";
import { authedFetch, apiUrl } from "../../auth/http";
import type { ReferenceFilterSource } from "../../config/filters";

// Кэш загруженных справочников на уровне модуля (ключ — resource).
const cache = new Map<string, any[]>();

export const ReferenceFilterSelect = ({
    source,
    value,
    onChange,
}: {
    source: ReferenceFilterSource;
    value?: string;
    onChange?: (value: string | undefined) => void;
}) => {
    const [items, setItems] = useState<any[]>(() => cache.get(source.resource) ?? []);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        let cancelled = false;
        const cached = cache.get(source.resource);
        if (cached) {
            setItems(cached);
            return;
        }
        setLoading(true);
        authedFetch(`${apiUrl}/${source.resource}?_end=100000`)
            .then(async (r) => {
                if (!r.ok) return [] as any[];
                const data = await r.json();
                return Array.isArray(data) ? data : (data?.data ?? []);
            })
            .then((data) => {
                if (cancelled) return;
                const list = data ?? [];
                cache.set(source.resource, list);
                setItems(list);
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [source.resource]);

    // Уникальные значения (в справочнике могут быть дубли отображаемого поля —
    // для фильтра достаточно одного варианта).
    const seen = new Set<string>();
    const options: { value: string; label: string }[] = [];
    for (const item of items) {
        const value = source.valueOf(item);
        if (!value || seen.has(value)) continue;
        seen.add(value);
        options.push({ value, label: source.labelOf(item) });
    }

    return (
        <Select
            showSearch
            allowClear
            loading={loading}
            placeholder="Выбрать…"
            style={{ width: "100%" }}
            value={value ?? undefined}
            onChange={onChange}
            filterOption={(input, option) =>
                (option?.label ?? "").toString().toLowerCase().includes(input.toLowerCase())
            }
            options={options}
        />
    );
};
