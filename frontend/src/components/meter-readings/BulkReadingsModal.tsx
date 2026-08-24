// src/components/meter-readings/BulkReadingsModal.tsx

import { useEffect, useState } from "react";
import {
    Modal,
    Button,
    Space,
    Select,
    DatePicker,
    Table,
    InputNumber,
    message,
} from "antd";
import dayjs, { Dayjs } from "dayjs";
import { useList, useApiUrl, useCustomMutation } from "@refinedev/core";
import { DATE_FORMAT } from "../../config/formatters";

interface BulkReadingsModalProps {
    open: boolean;
    onClose: () => void;
    onSaved: () => void;
}

/**
 * Модальное окно для массового ввода показаний счетчиков
 * Оператор выбирает вид услуги и дату, затем вводит показания для каждой квартиры
 */
export const BulkReadingsModal = ({
    open,
    onClose,
    onSaved,
}: BulkReadingsModalProps) => {
    const apiUrl = useApiUrl();
    const { data: apartmentsData, isLoading: apartmentsLoading } = useList({
        resource: "apartments",
        pagination: { mode: "off" },
        sorters: [{ field: "apartment_number", order: "asc" }],
    });
    const { data: serviceTypesData } = useList({
        resource: "service_types",
        pagination: { mode: "off" },
    });

    const apartments = apartmentsData?.data ?? [];
    const serviceTypes = serviceTypesData?.data ?? [];

    const [serviceTypeId, setServiceTypeId] = useState<number | undefined>();
    const [readingDate, setReadingDate] = useState<Dayjs>(dayjs());
    const [readings, setReadings] = useState<Record<number, string>>({});
    const [rowErrors, setRowErrors] = useState<Record<number, string>>({});

    const { mutate: bulkCreate, isLoading: saving } = useCustomMutation();

    useEffect(() => {
        if (open) {
            setServiceTypeId(undefined);
            setReadingDate(dayjs());
            setReadings({});
            setRowErrors({});
        }
    }, [open]);

    const handleSave = () => {
        if (!serviceTypeId) {
            message.error("Выберите вид услуги");
            return;
        }

        const entries = Object.entries(readings)
            .filter(([, value]) => value !== "" && value != null)
            .map(([apartmentId, value]) => ({
                apartment_id: Number(apartmentId),
                reading: Number(value),
            }));

        if (entries.length === 0) {
            message.error("Заполните хотя бы одно показание");
            return;
        }

        bulkCreate(
            {
                url: `${apiUrl}/meter_readings/bulk`,
                method: "post",
                values: {
                    services_type_id: serviceTypeId,
                    reading_date: readingDate.format("YYYY-MM-DD"),
                    entries,
                },
            },
            {
                onSuccess: (response) => {
                    const result: any = response.data;
                    const newRowErrors: Record<number, string> = {};
                    (result.errors ?? []).forEach((err: any) => {
                        newRowErrors[err.apartment_id] = err.detail;
                    });
                    setRowErrors(newRowErrors);

                    const createdCount = result.created?.length ?? 0;
                    const errorCount = result.errors?.length ?? 0;

                    if (createdCount > 0) {
                        message.success(`Сохранено показаний: ${createdCount}`);
                        onSaved();
                    }
                    if (errorCount > 0) {
                        message.warning(
                            `Не удалось сохранить: ${errorCount}. Ошибки показаны в таблице.`,
                        );
                    } else {
                        onClose();
                    }
                },
                onError: (err: any) =>
                    message.error(
                        err?.response?.data?.detail ?? "Не удалось сохранить показания",
                    ),
            },
        );
    };

    const columns = [
        {
            title: "№ квартиры",
            dataIndex: "apartment_number",
            key: "apartment_number",
            width: 110,
        },
        { title: "Адрес", dataIndex: "address", key: "address" },
        {
            title: "Показание",
            key: "reading",
            width: 220,
            render: (_: unknown, record: any) => (
                <div>
                    <InputNumber
                        style={{ width: "100%" }}
                        step={0.001}
                        value={
                            readings[record.id] !== undefined && readings[record.id] !== ""
                                ? Number(readings[record.id])
                                : undefined
                        }
                        status={rowErrors[record.id] ? "error" : undefined}
                        onChange={(value) => {
                            setReadings((prev) => ({
                                ...prev,
                                [record.id]: value === null ? "" : String(value),
                            }));
                            setRowErrors((prev) => {
                                if (!prev[record.id]) return prev;
                                const next = { ...prev };
                                delete next[record.id];
                                return next;
                            });
                        }}
                    />
                    {rowErrors[record.id] && (
                        <div style={{ color: "#ff4d4f", fontSize: 12, marginTop: 4 }}>
                            {rowErrors[record.id]}
                        </div>
                    )}
                </div>
            ),
        },
    ];

    return (
        <Modal
            title="Массовый ввод показаний"
            open={open}
            onCancel={onClose}
            width={800}
            destroyOnClose
            footer={[
                <Button key="cancel" onClick={onClose}>
                    Отмена
                </Button>,
                <Button key="save" type="primary" loading={saving} onClick={handleSave}>
                    Сохранить
                </Button>,
            ]}
        >
            <Space style={{ marginBottom: 16 }} size="large" wrap>
                <div>
                    <div style={{ marginBottom: 4 }}>Вид услуги</div>
                    <Select
                        style={{ width: 220 }}
                        placeholder="Выберите вид услуги"
                        value={serviceTypeId}
                        onChange={setServiceTypeId}
                        options={serviceTypes.map((s: any) => ({
                            value: s.id,
                            label: s.services_type,
                        }))}
                    />
                </div>
                <div>
                    <div style={{ marginBottom: 4 }}>Дата показания</div>
                    <DatePicker
                        value={readingDate}
                        format={DATE_FORMAT}
                        onChange={(value) => value && setReadingDate(value)}
                        allowClear={false}
                    />
                </div>
            </Space>

            <Table
                rowKey="id"
                dataSource={apartments}
                columns={columns}
                loading={apartmentsLoading}
                pagination={false}
                size="small"
                scroll={{ y: 400 }}
            />
        </Modal>
    );
};
