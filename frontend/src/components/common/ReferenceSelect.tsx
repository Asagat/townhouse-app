// src/components/common/ReferenceSelect.tsx

import { Select } from "antd";
import { useList } from "@refinedev/core";

/**
 * Форматтеры для отображения записей справочников в выпадающих списках
 * Ключ - имя ресурса, значение - функция форматирования
 */
const referenceLabelFormatters: Record<string, (item: any) => string> = {
    owners: (item) => item.full_name ?? `#${item.id}`,
    apartments: (item) => `№ ${item.apartment_number} — ${item.owner?.full_name || "Без собственника"}`,
    accounts: (item) => `${item.account_number} (${item.account_name})`,
    cash_points: (item) => item.name,
    service_types: (item) => item.services_type,
    tariff_types: (item) => item.name,
    tariffs: (item) => `${item.price} ₸${item.unit ? " / " + item.unit : ""}`,
    meters: (item) => item.serial_number,
};

/**
 * Компонент для выбора записи из справочника (Foreign Key)
 * Автоматически загружает данные и форматирует отображение
 */
export const ReferenceSelect = ({
    resource,
    value,
    onChange,
    placeholder,
    allowClear = true,
}: {
    /** Название ресурса (справочника) */
    resource: string;
    /** Текущее выбранное значение (ID записи) */
    value?: number;
    /** Обработчик изменения значения */
    onChange?: (value: number | undefined) => void;
    /** Плейсхолдер для Select */
    placeholder?: string;
    /** Разрешить очистку значения */
    allowClear?: boolean;
}) => {
    const { data, isLoading } = useList({
        resource,
        pagination: { mode: "off" },
    });

    const items = data?.data ?? [];

    // Получаем форматтер для конкретного ресурса или используем стандартный
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
            placeholder={placeholder || `Выберите ${resource}`}
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
