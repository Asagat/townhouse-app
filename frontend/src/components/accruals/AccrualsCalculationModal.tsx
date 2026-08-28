// AccrualsCalculationModal.tsx

import { useEffect, useState } from "react";
import { Modal, Button, Space, Select, InputNumber, Table, Checkbox, Input, message } from "antd";
import dayjs from "dayjs";
import { useApiUrl, useCustom, useCustomMutation } from "@refinedev/core";
import type { AccrualPreviewRow } from "../../types";
import { formatNumber } from "../../config/formatters";

interface AccrualsCalculationModalProps {
    open: boolean;
    onClose: () => void;
    onSaved: () => void;
    /** Если передан, модалка работает в режиме редактирования существующего документа */
    documentId?: number;
}

const monthOptions = [
    { value: 1, label: "Январь" },
    { value: 2, label: "Февраль" },
    { value: 3, label: "Март" },
    { value: 4, label: "Апрель" },
    { value: 5, label: "Май" },
    { value: 6, label: "Июнь" },
    { value: 7, label: "Июль" },
    { value: 8, label: "Август" },
    { value: 9, label: "Сентябрь" },
    { value: 10, label: "Октябрь" },
    { value: 11, label: "Ноябрь" },
    { value: 12, label: "Декабрь" },
];

const monthLabelByValue: Record<number, string> = Object.fromEntries(
    monthOptions.map((m) => [m.value, m.label]),
);

const getDefaultTitle = (year: number, month: number): string =>
    `Начисление за ${monthLabelByValue[month] ?? month} ${year}`;

/**
 * Модальное окно для расчета и начисления коммунальных услуг.
 * Без documentId — режим создания: оператор выбирает месяц/год, система рассчитывает
 * предварительные строки, оператор выбирает строки для сохранения в новый документ.
 * С documentId — режим редактирования: подгружаются месяц/год и ранее выбранные строки
 * существующего документа, при сохранении строки документа полностью пересоздаются.
 */
export const AccrualsCalculationModal = ({
    open,
    onClose,
    onSaved,
    documentId,
}: AccrualsCalculationModalProps) => {
    const apiUrl = useApiUrl();
    const isEditMode = documentId !== undefined;
    const now = dayjs();
    const [year, setYear] = useState<number>(now.year());
    const [month, setMonth] = useState<number>(now.month() + 1);
    const [rows, setRows] = useState<AccrualPreviewRow[]>([]);
    const [selectedKeys, setSelectedKeys] = useState<number[]>([]);
    const [isSaving, setIsSaving] = useState(false);
    const [pendingSelection, setPendingSelection] = useState<
        Array<{ account_id: number; services_type_id: number }> | null
    >(null);

    const { refetch, isFetching } = useCustom<{ rows: AccrualPreviewRow[] }>({
        url: `${apiUrl}/accruals_register/calculate`,
        method: "get",
        config: { query: { year, month } },
        queryOptions: {
            enabled: false,
            onSuccess: (response) => {
                const data = response.data.rows ?? [];
                setRows(data);
                if (pendingSelection) {
                    // Восстанавливаем выбор строк, ранее сохранённых в редактируемом документе
                    const keys = data
                        .filter((row) =>
                            pendingSelection.some(
                                (sel) =>
                                    sel.account_id === row.account_id &&
                                    sel.services_type_id === row.services_type_id,
                            ),
                        )
                        .map((row) => row.row_number);
                    setSelectedKeys(keys);
                    setPendingSelection(null);
                } else {
                    setSelectedKeys(data.map((row) => row.row_number));
                }
            },
            onError: (err: any) =>
                message.error(
                    err?.response?.data?.detail ?? "Не удалось рассчитать начисления",
                ),
        },
    });

    const { refetch: fetchDocumentDetails, isFetching: isLoadingDocument } = useCustom<{
        year: number;
        month: number;
        selections: Array<{ account_id: number; services_type_id: number }>;
        document?: { id: number; title?: string | null };
    }>({
        url: `${apiUrl}/accrual_documents/${documentId}/details`,
        method: "get",
        queryOptions: {
            enabled: false,
            onSuccess: (response) => {
                const { year: docYear, month: docMonth, selections } = response.data;
                setPendingSelection(selections ?? []);
                setYear(docYear);
                setMonth(docMonth);
            },
            onError: (err: any) =>
                message.error(
                    err?.response?.data?.detail ?? "Не удалось загрузить документ начислений",
                ),
        },
    });

    const { mutate: generate, isLoading: saving } = useCustomMutation();

    useEffect(() => {
        if (!open) return;

        if (isEditMode) {
            setRows([]);
            setSelectedKeys([]);
            fetchDocumentDetails();
        } else {
            const n = dayjs();
            setYear(n.year());
            setMonth(n.month() + 1);
            setRows([]);
            setSelectedKeys([]);
            setPendingSelection(null);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, isEditMode, documentId]);

    useEffect(() => {
        if (open) {
            refetch();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, year, month]);

    const handleSave = () => {
        const selectedRows = rows.filter((row) =>
            selectedKeys.includes(row.row_number),
        );
        if (selectedRows.length === 0) {
            message.error("Выберите хотя бы одну строку для начисления");
            return;
        }

        setIsSaving(true);

        // Название документа генерируется на сервере автоматически (1.9 роадмапа).
        const selections = selectedRows.map((row) => ({
            account_id: row.account_id,
            services_type_id: row.services_type_id,
        }));

        // Отправляем только идентификаторы выбранных строк — сумма, потребление, тариф и показания
        // будут пересчитаны на сервере на момент сохранения.
        if (isEditMode) {
            generate(
                {
                    url: `${apiUrl}/accrual_documents/${documentId}/full`,
                    method: "put",
                    values: {
                        accrual_date: `${year}-${String(month).padStart(2, "0")}-01`,
                        selections,
                    },
                },
                {
                    onSuccess: (response) => {
                        const data = response.data as any;
                        const updated = data.updated?.length ?? 0;
                        message.success(`Документ начислений обновлён, записей: ${updated}`);
                        onSaved();
                        onClose();
                        setIsSaving(false);
                    },
                    onError: (err: any) => {
                        message.error(
                            err?.response?.data?.detail ?? "Не удалось обновить начисления",
                        );
                        setIsSaving(false);
                    },
                },
            );
        } else {
            generate(
                {
                    url: `${apiUrl}/accruals_register/generate`,
                    method: "post",
                    values: { year, month, selections },
                },
                {
                    onSuccess: (response) => {
                        const data = response.data as any;
                        const created = data.created?.length ?? 0;
                        const newDocumentId = data.document?.id;
                        message.success(
                            newDocumentId
                                ? `Создан документ начислений №${newDocumentId}, начислено записей: ${created}`
                                : `Начислено записей: ${created}`,
                        );
                        onSaved();
                        onClose();
                        setIsSaving(false);
                    },
                    onError: (err: any) => {
                        message.error(
                            err?.response?.data?.detail ?? "Не удалось сохранить начисления",
                        );
                        setIsSaving(false);
                    },
                },
            );
        }
    };

    const allSelected = rows.length > 0 && selectedKeys.length === rows.length;
    const someSelected = selectedKeys.length > 0 && !allSelected;

    const columns = [
        {
            title: (
                <Checkbox
                    checked={allSelected}
                    indeterminate={someSelected}
                    onChange={(e) =>
                        setSelectedKeys(
                            e.target.checked ? rows.map((row) => row.row_number) : [],
                        )
                    }
                />
            ),
            key: "select",
            width: 50,
            render: (_: unknown, record: AccrualPreviewRow) => (
                <Checkbox
                    checked={selectedKeys.includes(record.row_number)}
                    onChange={(e) =>
                        setSelectedKeys((prev) =>
                            e.target.checked
                                ? [...prev, record.row_number]
                                : prev.filter((key) => key !== record.row_number),
                        )
                    }
                />
            ),
        },
        { title: "№", dataIndex: "row_number", key: "row_number", width: 60 },
        {
            title: "Квартира (Лицевой счёт)",
            dataIndex: "account_id_label",
            key: "account_id_label",
        },
        {
            title: "Вид услуги",
            dataIndex: "services_type_id_label",
            key: "services_type_id_label",
        },
        {
            title: "Показание прошлое",
            dataIndex: "past_reading_value",
            key: "past_reading_value",
            render: formatNumber,
        },
        {
            title: "Показание текущее",
            dataIndex: "current_reading_value",
            key: "current_reading_value",
            render: formatNumber,
        },
        {
            title: "Потребление",
            dataIndex: "consumption",
            key: "consumption",
            render: formatNumber,
        },
        {
            title: "Тариф",
            dataIndex: "tariff_id_label",
            key: "tariff_id_label",
        },
        {
            title: "Сумма",
            dataIndex: "amount",
            key: "amount",
            render: formatNumber,
        },
    ];

    return (
        <Modal
            title={isEditMode ? "Редактирование документа начислений" : "Начисление сумм по коммунальным услугам"}
            open={open}
            onCancel={onClose}
            width={1100}
            destroyOnClose
            footer={[
                <Button key="cancel" onClick={onClose}>
                    Отмена
                </Button>,
                <Button
                    key="save"
                    type="primary"
                    loading={saving || isSaving}
                    disabled={selectedKeys.length === 0}
                    onClick={handleSave}
                >
                    {isEditMode
                        ? `Сохранить изменения (${selectedKeys.length})`
                        : `Начислить выбранные (${selectedKeys.length})`}
                </Button>,
            ]}
        >
            <Space style={{ marginBottom: 16 }} size="large" wrap>
                <div>
                    <div style={{ marginBottom: 4 }}>Название документа</div>
                    <Input
                        style={{ width: 280 }}
                        value={getDefaultTitle(year, month)}
                        readOnly
                    />
                </div>
                <div>
                    <div style={{ marginBottom: 4 }}>Месяц</div>
                    <Select
                        style={{ width: 160 }}
                        value={month}
                        onChange={setMonth}
                        options={monthOptions}
                    />
                </div>
                <div>
                    <div style={{ marginBottom: 4 }}>Год</div>
                    <InputNumber
                        style={{ width: 120 }}
                        value={year}
                        min={2000}
                        max={2100}
                        onChange={(value) => value && setYear(Number(value))}
                    />
                </div>
            </Space>

            <Table
                rowKey="row_number"
                dataSource={rows}
                columns={columns}
                loading={isFetching || isLoadingDocument}
                pagination={false}
                size="small"
                scroll={{ y: 450 }}
            />
        </Modal>
    );
};
