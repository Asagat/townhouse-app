// src/components/common/ReferenceSelect.tsx

import { Select } from "antd";
import { useList } from "@refinedev/core";

/**
 * Форматтеры для отображения записей справочников в выпадающих списках
 */
const referenceLabelFormatters: Record<string, (item: any) => string> = {
    owners: (item) => item.full_name ?? `#${item.id}`,
    apartments: (item) => {
        const apt = item.apartment_number || item.apartment?.apartment_number;
        const owner = item.owner?.full_name || item.full_name || 'Без собственника';
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
    owners: 'Выберите собственника',
    apartments: 'Выберите квартиру',
    accounts: 'Выберите лицевой счёт',
    cash_points: 'Выберите кассу/счёт',
    service_types: 'Выберите вид услуги',
    services_type: 'Выберите вид услуги',
    tariff_types: 'Выберите тип тарифа',
    tariffs: 'Выберите тариф',
    meters: 'Выберите счётчик',
    meter_readings: 'Выберите показание',
    meter_reading_documents: 'Выберите документ показаний',
    analytic_articles: 'Выберите статью',
};

/**
 * Компонент для выбора записи из справочника (Foreign Key)
 */
export const ReferenceSelect = ({
    resource,
    value,
    onChange,
    placeholder,
    allowClear = true,
    filterFn,
}: {
    resource: string;
    value?: number;
    onChange?: (value: number | undefined) => void;
    placeholder?: string;
    allowClear?: boolean;
    filterFn?: (item: any) => boolean;
}) => {
    const { data, isLoading } = useList({
        resource,
        pagination: { mode: "off" },
    });

    const items = (data?.data ?? []).filter((item: any) =>
        filterFn ? filterFn(item) : true,
    );

    const formatter =
        referenceLabelFormatters[resource] ??
        ((item: any) => item.full_name ?? item.name ?? item.label ?? `#${item.id}`);

    return (
        <Select
            showSearch
            allowClear={allowClear}
            loading={isLoading}
            value={value}
            onChange={onChange}
            placeholder={placeholder || resourcePlaceholders[resource] || `Выберите ${resource}`}
            filterOption={(input, option) =>
                (option?.label ?? "")
                    .toString()
                    .toLowerCase()
                    .includes(input.toLowerCase())
            }
            options={items.map((item: any) => ({
                value: item.id,
                label: formatter(item),
            }))}
        />
    );
};
