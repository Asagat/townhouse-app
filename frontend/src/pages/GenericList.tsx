// src/pages/GenericList.tsx

import { useState } from "react";
import {
    Table,
    Button,
    Space,
    Popconfirm,
    message,
} from "antd";
import {
    useTable,
    useCreate,
    useUpdate,
    useDelete,
    useCustom,
    useApiUrl,
} from "@refinedev/core";
import type { FieldMeta, ModalState } from "../types";
import { getColumnsForResource } from "../config/columns";
import { allResources } from "../config/menu";
import { RecordFormModal } from "../components/common/RecordFormModal";
import { BulkReadingsModal } from "../components/meter-readings/BulkReadingsModal";
import { AccrualsCalculationModal } from "../components/accruals/AccrualsCalculationModal";
import type { SortOrder } from "antd/es/table/interface";

interface GenericListProps {
    resourceName: string;
}

// Конфигурация сортировки для всех полей
const sortMapping: Record<string, string> = {
    'id': 'id',
    'apartment_number': 'apartment_number',
    'address': 'address',
    'square': 'square',
    'account_number': 'account_number',
    'account_name': 'account_name',
    'is_active': 'is_active',
    'name': 'name',
    'transaction_date': 'transaction_date',
    'amount': 'amount',
    'transaction_type': 'transaction_type',
    'notes': 'notes',
    'past_reading_value': 'past_reading_value',
    'current_reading_value': 'current_reading_value',
    'consumption': 'consumption',
    'operation_date': 'operation_date',
    'income': 'income',
    'expense': 'expense',
    'balance_after': 'balance_after',
    'price': 'price',
    'unit': 'unit',
    'valid_from': 'valid_from',
    'serial_number': 'serial_number',
    'installed_at': 'installed_at',
    'full_name': 'full_name',
    'phone': 'phone',

    // Вложенные поля
    'owner.full_name': 'owner.full_name',
    'owner_id_label': 'owner.full_name',
    'apartment.apartment_number': 'apartment.apartment_number',
    'apartment_id_label': 'apartment.apartment_number',
    'services_type.services_type': 'services_type.services_type',
    'services_type_id_label': 'services_type.services_type',
    'meter.serial_number': 'meter.serial_number',
    'meter_label': 'meter.serial_number',
    'account.account_number': 'account.account_number',
    'account_label': 'account.account_number',
    'account_id_label': 'account.account_number',
    'cash_point.name': 'cash_point.name',
    'cash_point_id_label': 'cash_point.name',
    'tariff_type.name': 'tariff_type.name',
    'tariff_type_id_label': 'tariff_type.name',

    // Поля начислений и документов
    'accrual_date': 'accrual_date',
    'accrual_document_id': 'accrual_document_id',
    'created_at': 'created_at',
    'accruals_count': 'accruals_count',
    'total_amount': 'total_amount',
};

const isSortableField = (dataIndex: string): boolean => {
    if (dataIndex === 'id') return true;
    return !!sortMapping[dataIndex];
};

const getSortField = (dataIndex: string): string => {
    if (sortMapping[dataIndex]) {
        return sortMapping[dataIndex];
    }
    return dataIndex;
};

const getValueByPath = (obj: any, path: string): any => {
    if (!obj || !path) return undefined;
    const keys = path.split('.');
    let result = obj;
    for (const key of keys) {
        if (result === null || result === undefined) return undefined;
        result = result[key];
    }
    return result;
};

export const GenericList = ({ resourceName }: GenericListProps) => {
    const apiUrl = useApiUrl();

    const {
        tableQuery,
        current,
        setCurrent,
        pageSize,
        setPageSize,
        sorters,
        setSorters,
    } = useTable({
        resource: resourceName,
        pagination: {
            current: 1,
            pageSize: 10,
        },
        sorters: {
            initial: [
                {
                    field: "id",
                    order: "desc",
                },
            ],
        },
    });

    const data = tableQuery?.data?.data ?? [];
    const total = tableQuery?.data?.total ?? 0;

    const { data: metaResponse, isLoading: metaLoading } = useCustom<{
        fields: FieldMeta[];
    }>({
        url: `${apiUrl}/meta/${resourceName}`,
        method: "get",
    });
    const fields = metaResponse?.data?.fields ?? [];

    const { mutate: createRecord, isLoading: creating } = useCreate();
    const { mutate: updateRecord, isLoading: updating } = useUpdate();
    const { mutate: deleteRecord } = useDelete();

    const [modalState, setModalState] = useState<ModalState | null>(null);
    const [bulkModalOpen, setBulkModalOpen] = useState(false);
    const [accrualsModalOpen, setAccrualsModalOpen] = useState(false);

    const isAccrualsRegister = resourceName === "accruals_register";
    const isAccrualDocuments = resourceName === "accrual_documents";
    const isReadOnly = resourceName === "accounts_register";

    const columns = getColumnsForResource(resourceName);
    const meta = allResources.find((r) => r.key === resourceName);

    const getColumnSortOrder = (dataIndex: string): SortOrder | undefined => {
        if (!isSortableField(dataIndex)) return undefined;
        const sortField = getSortField(dataIndex);
        const sorter = sorters?.find(s => s.field === sortField || s.field === dataIndex);
        if (!sorter) return undefined;
        return sorter.order === 'asc' ? 'ascend' : 'descend';
    };

    const handleTableChange = (_pagination: any, _filters: any, sorter: any) => {
        if (!sorter || !sorter.field) {
            setSorters([]);
            return;
        }
        if (!isSortableField(sorter.field)) {
            setSorters([]);
            return;
        }
        const order = sorter.order === 'ascend' ? 'asc' : 'desc';
        const sortField = getSortField(sorter.field);
        setSorters([{
            field: sortField,
            order: order,
        }]);
    };

    const handleSubmit = (values: Record<string, any>) => {
        if (modalState?.mode === "create") {
            createRecord(
                { resource: resourceName, values },
                {
                    onSuccess: () => {
                        message.success("Запись добавлена");
                        setModalState(null);
                    },
                    onError: (err: any) =>
                        message.error(
                            err?.response?.data?.detail ?? "Не удалось создать запись",
                        ),
                },
            );
        } else if (modalState?.mode === "edit" && modalState.record) {
            updateRecord(
                { resource: resourceName, id: modalState.record.id, values },
                {
                    onSuccess: () => {
                        message.success("Запись обновлена");
                        setModalState(null);
                    },
                    onError: (err: any) =>
                        message.error(
                            err?.response?.data?.detail ?? "Не удалось обновить запись",
                        ),
                },
            );
        }
    };

    const tableColumns = [
        {
            title: "ID",
            dataIndex: "id",
            key: "id",
            width: 70,
            sorter: true,
            sortOrder: getColumnSortOrder('id'),
            defaultSortOrder: 'descend' as const,
        },
        ...columns.map((col) => {
            const sortable = isSortableField(col.key);
            const isNested = col.key.includes('.');
            return {
                title: col.label,
                dataIndex: col.key,
                key: col.key,
                render: (value: any, record: any) => {
                    try {
                        const val = isNested ? getValueByPath(record, col.key) : value;
                        return col.format ? col.format(val) : val ?? "—";
                    } catch {
                        return "—";
                    }
                },
                sorter: sortable,
                sortOrder: getColumnSortOrder(col.key),
                ...(sortable && {
                    onHeaderCell: () => ({
                        style: { cursor: 'pointer' },
                        title: 'Кликните для сортировки',
                    }),
                }),
            };
        }),
        {
            title: "Действия",
            key: "actions",
            width: 200,
            fixed: 'right' as const,
            render: (_: unknown, record: any) => {
                if (isAccrualsRegister) {
                    return (
                        <Space>
                            <Button
                                size="small"
                                onClick={() => setModalState({ mode: "edit", record })}
                            >
                                Редактировать
                            </Button>
                            <Popconfirm
                                title="Удалить запись?"
                                okText="Удалить"
                                cancelText="Отмена"
                                onConfirm={() =>
                                    deleteRecord(
                                        { resource: resourceName, id: record.id },
                                        {
                                            onSuccess: () => message.success("Запись удалена"),
                                            onError: (err: any) =>
                                                message.error(
                                                    err?.response?.data?.detail ??
                                                        "Не удалось удалить запись",
                                                ),
                                        },
                                    )
                                }
                            >
                                <Button size="small" danger>
                                    Удалить
                                </Button>
                            </Popconfirm>
                        </Space>
                    );
                }

                if (isAccrualDocuments) {
                    return (
                        <Space>
                            <Button
                                size="small"
                                onClick={() => setModalState({ mode: "edit", record })}
                            >
                                Редактировать
                            </Button>
                            <Popconfirm
                                title="Удалить документ начислений? Все связанные записи в регистре начислений также будут удалены."
                                okText="Удалить"
                                cancelText="Отмена"
                                onConfirm={() =>
                                    deleteRecord(
                                        { resource: resourceName, id: record.id },
                                        {
                                            onSuccess: () => {
                                                message.success("Документ начислений удален");
                                                tableQuery.refetch();
                                            },
                                            onError: (err: any) =>
                                                message.error(
                                                    err?.response?.data?.detail ??
                                                        "Не удалось удалить документ",
                                                ),
                                        },
                                    )
                                }
                            >
                                <Button size="small" danger>
                                    Удалить
                                </Button>
                            </Popconfirm>
                        </Space>
                    );
                }

                if (!isReadOnly) {
                    return (
                        <Space>
                            <Button
                                size="small"
                                onClick={() => setModalState({ mode: "edit", record })}
                            >
                                Редактировать
                            </Button>
                            <Popconfirm
                                title="Удалить запись?"
                                okText="Удалить"
                                cancelText="Отмена"
                                onConfirm={() =>
                                    deleteRecord(
                                        { resource: resourceName, id: record.id },
                                        {
                                            onSuccess: () => message.success("Запись удалена"),
                                            onError: (err: any) =>
                                                message.error(
                                                    err?.response?.data?.detail ??
                                                        "Не удалось удалить запись",
                                                ),
                                        },
                                    )
                                }
                            >
                                <Button size="small" danger>
                                    Удалить
                                </Button>
                            </Popconfirm>
                        </Space>
                    );
                }
                return (
                    <span style={{ color: "#999", fontSize: "12px" }}>Только чтение</span>
                );
            },
        },
    ];

    return (
        <div
            style={{
                background: "#fff",
                padding: "30px",
                borderRadius: "12px",
                width: "100%",
                boxSizing: "border-box",
            }}
        >
            <div
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: 20,
                }}
            >
                <h1 style={{ color: "#1f1f1f", margin: 0 }}>
                    {meta?.label ?? resourceName}
                </h1>
                <Space>
                    {resourceName === "meter_readings" && (
                        <Button onClick={() => setBulkModalOpen(true)}>
                            Массовый ввод показаний
                        </Button>
                    )}

                    {isAccrualDocuments && (
                        <Button
                            type="primary"
                            onClick={() => setAccrualsModalOpen(true)}
                        >
                            Добавить
                        </Button>
                    )}

                    {!isReadOnly && !isAccrualsRegister && !isAccrualDocuments && (
                        <Button
                            type="primary"
                            disabled={metaLoading}
                            onClick={() => setModalState({ mode: "create" })}
                        >
                            Добавить
                        </Button>
                    )}
                </Space>
            </div>

            <Table
                rowKey="id"
                dataSource={data}
                columns={tableColumns}
                loading={tableQuery.isLoading}
                onChange={handleTableChange}
                pagination={{
                    current,
                    pageSize,
                    total,
                    showSizeChanger: true,
                    showTotal: (total) => `Всего ${total} записей`,
                    onChange: (page, size) => {
                        setCurrent(page);
                        if (size) setPageSize(size);
                    },
                }}
                scroll={{ x: 'max-content' }}
            />

            {modalState && (
                <RecordFormModal
                    open={!!modalState}
                    title={
                        modalState.mode === "create" ? "Новая запись" : "Редактирование записи"
                    }
                    fields={fields}
                    initialValues={modalState.record}
                    confirmLoading={creating || updating}
                    onCancel={() => setModalState(null)}
                    onSubmit={handleSubmit}
                    resourceName={resourceName}
                />
            )}

            {resourceName === "meter_readings" && (
                <BulkReadingsModal
                    open={bulkModalOpen}
                    onClose={() => setBulkModalOpen(false)}
                    onSaved={() => tableQuery.refetch()}
                />
            )}

            {isAccrualDocuments && (
                <AccrualsCalculationModal
                    open={accrualsModalOpen}
                    onClose={() => setAccrualsModalOpen(false)}
                    onSaved={() => tableQuery.refetch()}
                />
            )}
        </div>
    );
};
