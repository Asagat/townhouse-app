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
    Input,
    message,
} from "antd";
import dayjs, { Dayjs } from "dayjs";
import { useList, useApiUrl, useCustom, useCustomMutation } from "@refinedev/core";
import { DATE_FORMAT } from "../../config/formatters";

interface BulkReadingsModalProps {
    open: boolean;
    onClose: () => void;
    onSaved: () => void;
    /** Если передан, модалка работает в режиме редактирования существующего документа показаний */
    documentId?: number;
}

const MONTH_NAMES_NOMINATIVE = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
];

const getDefaultTitle = (date: Dayjs): string =>
    `Снятие показаний за ${MONTH_NAMES_NOMINATIVE[date.month()]} ${date.year()}`;

const DEFAULT_SERVICE_TYPE_LABEL = "Электричество";

/**
 * Модальное окно для массового ввода показаний счетчиков.
 * Без documentId — режим создания: оператор задаёт название документа, вид услуги и дату,
 * затем вводит показания для каждой квартиры, создаётся новый документ.
 * С documentId — режим редактирования: подгружаются данные существующего документа
 * и его показания, при сохранении документ и его показания полностью пересоздаются.
 */
export const BulkReadingsModal = ({
    open,
    onClose,
    onSaved,
    documentId,
}: BulkReadingsModalProps) => {
    const apiUrl = useApiUrl();
    const isEditMode = documentId !== undefined;
    const { data: apartmentsData, isLoading: apartmentsLoading } = useList({
        resource: "apartments",
        pagination: { mode: "off" },
        sorters: [{ field: "apartment_number", order: "asc" }],
    });
    const { data: serviceTypesData } = useList({
        resource: "services_type",
        pagination: { mode: "off" },
    });

    const apartments = apartmentsData?.data ?? [];
    const serviceTypes = serviceTypesData?.data ?? [];

    const [title, setTitle] = useState<string>("");
    const [serviceTypeId, setServiceTypeId] = useState<number | undefined>();
    const [readingDate, setReadingDate] = useState<Dayjs>(dayjs());
    const [readings, setReadings] = useState<Record<number, string>>({});
    const [rowErrors, setRowErrors] = useState<Record<number, string>>({});

    const { mutate: bulkCreate, isLoading: saving } = useCustomMutation();

    const { refetch: fetchDocument, isFetching: isLoadingDocument } = useCustom<{
        document: any;
        readings: any[];
    }>({
        url: `${apiUrl}/meter_reading_documents/${documentId}/readings`,
        method: "get",
        queryOptions: {
            enabled: false,
            onSuccess: (response) => {
                const { document, readings: existingReadings } = response.data;
                setTitle(document.title ?? "");
                setReadingDate(document.reading_date ? dayjs(document.reading_date) : dayjs());
                setServiceTypeId(document.services_type_id ?? undefined);

                const readingsMap: Record<number, string> = {};
                (existingReadings ?? []).forEach((r: any) => {
                    if (r.apartment_id != null) {
                        readingsMap[r.apartment_id] = String(r.reading);
                    }
                });
                setReadings(readingsMap);
                setRowErrors({});
            },
            onError: (err: any) =>
                message.error(
                    err?.response?.data?.detail ?? "Не удалось загрузить документ показаний",
                ),
        },
    });

    useEffect(() => {
        if (!open) return;

        if (isEditMode) {
            fetchDocument();
        } else {
            const now = dayjs();
            setTitle(getDefaultTitle(now));
            setServiceTypeId(undefined);
            setReadingDate(now);
            setReadings({});
            setRowErrors({});
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, isEditMode, documentId]);

    // Подставляем вид услуги по умолчанию (Электричество) в режиме создания, как только справочник загрузится
    useEffect(() => {
        if (open && !isEditMode && serviceTypeId === undefined && serviceTypes.length > 0) {
            const defaultServiceType = serviceTypes.find(
                (s: any) => s.services_type === DEFAULT_SERVICE_TYPE_LABEL,
            );
            if (defaultServiceType) {
                setServiceTypeId(Number(defaultServiceType.id));
            }
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, isEditMode, serviceTypes]);

    const handleSave = () => {
        if (!title.trim()) {
            message.error("Введите название документа");
            return;
        }
        if (!serviceTypeId) {
            message.error("Выберите вид услуги");
            return;
        }

        const readingsPayload = Object.entries(readings)
            .filter(([, value]) => value !== "" && value != null)
            .map(([apartmentId, value]) => ({
                apartment_id: Number(apartmentId),
                reading: Number(value),
            }));

        if (readingsPayload.length === 0) {
            message.error("Заполните хотя бы одно показание");
            return;
        }

        const url = isEditMode
            ? `${apiUrl}/meter_reading_documents/${documentId}/full`
            : `${apiUrl}/meter_readings/bulk`;

        bulkCreate(
            {
                url,
                method: isEditMode ? "put" : "post",
                values: {
                    title,
                    services_type_id: serviceTypeId,
                    reading_date: readingDate.format("YYYY-MM-DD"),
                    readings: readingsPayload,
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

                    const savedCount = (result.created ?? result.updated)?.length ?? 0;
                    const errorCount = result.errors?.length ?? 0;

                    if (savedCount > 0) {
                        message.success(
                            isEditMode
                                ? `Документ обновлён, показаний: ${savedCount}`
                                : `Сохранено показаний: ${savedCount}`,
                        );
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
            title={isEditMode ? "Редактирование документа показаний" : "Массовый ввод показаний"}
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
                    <div style={{ marginBottom: 4 }}>Название документа</div>
                    <Input
                        style={{ width: 260 }}
                        placeholder="Показания за август 2026 г."
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                    />
                </div>
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
                loading={apartmentsLoading || isLoadingDocument}
                pagination={false}
                size="small"
                scroll={{ y: 400 }}
            />
        </Modal>
    );
};
