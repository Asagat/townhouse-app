// src/components/common/ReferenceSelect.tsx

import { useEffect, useState } from "react";
import { Select } from "antd";
import { authedFetch, apiUrl } from "../../auth/http";

/**
 * Форматтеры для отображения записей справочников в выпадающих списках
 */
const referenceLabelFormatters: Record<string, (item: any) => string> = {
    owners: (item) => item.full_name ?? `#${item.id}`,
    apartments: (item) => {
        const apt = item.apartment_number || item.apartment?.apartment_number;
        const owner = item.owner?.full_name || item.full_name || "Без собственника";
        return `№ ${apt} — ${owner}`;
    },
    accounts: (item) => `${item.account_number} (${item.account_name})`,
    cash_points: (item) => item.name,
    service_types: (item) => item.services_type,
    services_type: (item) => item.services_type,
    tariff_types: (item) => item.name,
    tariffs: (item) => `${item.price} ₸${item.unit ? " / " + item.unit : ""}`,
    meters: (item) => item.serial_number,
    analytic_articles: (item) => `${item.name} (${item.kind === "Доход" ? "доход" : "расход"})`,
};

/**
 * Правильные плейсхолдеры для каждого ресурса (в винительном падеже)
 */
const resourcePlaceholders: Record<string, string> = {
    owners: "Выберите собственника",
    apartments: "Выберите квартиру",
    accounts: "Выберите лицевой счёт",
    cash_points: "Выберите кассу/счёт",
    service_types: "Выберите вид услуги",
    services_type: "Выберите вид услуги",
    tariff_types: "Выберите тип тарифа",
    tariffs: "Выберите тариф",
    meters: "Выберите счётчик",
    meter_readings: "Выберите показание",
    meter_reading_documents: "Выберите документ показаний",
    analytic_articles: "Выберите статью",
};

// Символ-разделитель для пункта «— пусто —» (для опциональных полей).
const EMPTY = "__ref_empty__";

/**
 * Компонент для выбора записи из справочника (Foreign Key).
 *
 * - Загружает ВСЕ записи ресурса напрямую (authedFetch, без Refine-пагинации,
 *   чтобы в списке были все квартиры, а не первые 10).
 * - Значение всегда управляемое: используем строковый sentinel ("" — пусто),
 *   чтобы allowClear корректно очищал поле (без глюка controlled/uncontrolled).
 * - Для опциональных полей (optional=true) в списке есть пункт «— пусто —»,
 *   дающий гарантированный способ выбрать пустое значение.
 */
export const ReferenceSelect = ({
    resource,
    value,
    onChange,
    placeholder,
    allowClear = true,
    filterFn,
    optional = false,
}: {
    resource: string;
    value?: number;
    onChange?: (value: number | undefined) => void;
    placeholder?: string;
    allowClear?: boolean;
    filterFn?: (item: any) => boolean;
    optional?: boolean;
}) => {
    const [items, setItems] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        // direct fetch: no Refine pagination -> all records (все квартиры и т.п.).
        authedFetch(`${apiUrl}/${resource}?_end=100000`)
            .then(async (r) => {
                if (!r.ok) return [] as any[];
                const data = await r.json();
                return Array.isArray(data) ? data : (data?.data ?? []);
            })
            .then((data) => {
                if (!cancelled) setItems(data ?? []);
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [resource]);

    const filtered = items.filter((item: any) => (filterFn ? filterFn(item) : true));

    const formatter =
        referenceLabelFormatters[resource] ??
        ((item: any) => item.full_name ?? item.name ?? item.label ?? `#${item.id}`);

    const controlledValue =
        typeof value === "undefined" || value === null ? "" : String(value);

    const options = [
        ...(optional ? [{ value: EMPTY, label: "— пусто —" }] : []),
        ...filtered.map((item: any) => ({
            value: String(item.id),
            label: formatter(item),
        })),
    ];

    return (
        <Select
            showSearch
            allowClear={allowClear}
            loading={loading}
            value={controlledValue}
            onChange={(v: any) => {
                if (v === EMPTY || v === undefined || v === null || v === "") {
                    onChange?.(undefined);
                } else {
                    onChange?.(Number(v));
                }
            }}
            onClear={() => onChange?.(undefined)}
            placeholder={placeholder || resourcePlaceholders[resource] || `Выберите ${resource}`}
            filterOption={(input, option) =>
                (option?.label ?? "").toString().toLowerCase().includes(input.toLowerCase())
            }
            options={options}
        />
    );
};
