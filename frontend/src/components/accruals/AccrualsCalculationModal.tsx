// AccrualsCalculationModal.tsx

import { useEffect, useState } from "react";
import { Modal, Button, Space, Select, InputNumber, Table, Checkbox, message } from "antd";
import dayjs from "dayjs";
import { useApiUrl, useCustom, useCustomMutation } from "@refinedev/core";
import type { AccrualPreviewRow } from "../../types";
import { formatNumber } from "../../config/formatters";

interface AccrualsCalculationModalProps {
    open: boolean;
    onClose: () => void;
    onSaved: () => void;
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

/**
 * Модальное окно для расчета и начисления коммунальных услуг
 * Оператор выбирает месяц/год, система рассчитывает предварительные строки
 * Оператор может выбрать строки для сохранения в регистр
 */
export const AccrualsCalculationModal = ({
    open,
    onClose,
    onSaved,
}: AccrualsCalculationModalProps) => {
    const apiUrl = useApiUrl();
    const now = dayjs();
    const [year, setYear] = useState<number>(now.year());
    const [month, setMonth] = useState<number>(now.month() + 1);
    const [rows, setRows] = useState<AccrualPreviewRow[]>([]);
    const [selectedKeys, setSelectedKeys] = useState<number[]>([]);
    const [isSaving, setIsSaving] = useState(false);

    const { refetch, isFetching } = useCustom<{ rows: AccrualPreviewRow[] }>({
        url: `${apiUrl}/accruals_register/calculate`,
        method: "get",
        config: { query: { year, month } },
        queryOptions: {
            enabled: false,
            onSuccess: (response) => {
                const data = response.data.rows ?? [];
                setRows(data);
                setSelectedKeys(data.map((row) => row.row_number));
            },
            onError: (err: any) =>
                message.error(
                    err?.response?.data?.detail ?? "Не удалось рассчитать начисления",
                ),
        },
    });

    const { mutate: generate, isLoading: saving } = useCustomMutation();

    useEffect(() => {
        if (open) {
            const n = dayjs();
            setYear(n.year());
            setMonth(n.month() + 1);
            setRows([]);
            setSelectedKeys([]);
        }
    }, [open]);

    useEffect(() => {
        if (open) {
            refetch();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, year, month]);

    const handleSave = async () => {
        const selectedRows = rows.filter((row) =>
            selectedKeys.includes(row.row_number),
        );
        if (selectedRows.length === 0) {
            message.error("Выберите хотя бы одну строку для начисления");
            return;
        }

        setIsSaving(true);

        try {
            // 1. Создаем документ начислений
            const docResponse = await fetch(`${apiUrl}/accrual_documents`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    accrual_date: `${year}-${String(month).padStart(2, '0')}-01`
                })
            });

            if (!docResponse.ok) {
                throw new Error("Не удалось создать документ начислений");
            }

            const docData = await docResponse.json();
            const documentId = docData.id;
            message.info(`Создан документ начислений №${documentId}`);

            // 2. Сохраняем начисления с document_id
            generate(
                {
                    url: `${apiUrl}/accruals_register/generate`,
                    method: "post",
                    values: {
                        year,
                        month,
                        document_id: documentId,
                        rows: selectedRows,
                    },
                },
                {
                    onSuccess: (response) => {
                        const created = (response.data as any).created?.length ?? 0;
                        message.success(`Начислено записей: ${created}`);
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
        } catch (error) {
            message.error("Не удалось создать документ начислений");
            setIsSaving(false);
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
            title="Начисление сумм по коммунальным услугам"
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
                    Начислить выбранные ({selectedKeys.length})
                </Button>,
            ]}
        >
            <Space style={{ marginBottom: 16 }} size="large" wrap>
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
                loading={isFetching}
                pagination={false}
                size="small"
                scroll={{ y: 450 }}
            />
        </Modal>
    );
};
