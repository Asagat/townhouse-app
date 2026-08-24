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

interface GenericListProps {
    resourceName: string;
}

export const GenericList = ({ resourceName }: GenericListProps) => {
    const apiUrl = useApiUrl();
    const { tableQuery, current, setCurrent, pageSize, setPageSize } = useTable({
        resource: resourceName,
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
    const isReadOnly = resourceName === "accounts_register";

    const columns = getColumnsForResource(resourceName);
    const meta = allResources.find((r) => r.key === resourceName);

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
        { title: "ID", dataIndex: "id", key: "id", width: 70 },
        ...columns.map((col) => ({
            title: col.label,
            dataIndex: col.key,
            key: col.key,
            render: (value: any) => (col.format ? col.format(value) : value ?? "—"),
        })),
        {
            title: "Действия",
            key: "actions",
            width: 200,
            render: (_: unknown, record: any) =>
                !isReadOnly ? (
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
                ) : (
                    <span style={{ color: "#999", fontSize: "12px" }}>Только чтение</span>
                ),
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
                    {!isReadOnly && isAccrualsRegister && (
                        <Button
                            type="primary"
                            onClick={() => setAccrualsModalOpen(true)}
                        >
                            Добавить
                        </Button>
                    )}
                    {!isReadOnly && !isAccrualsRegister && (
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
                pagination={{
                    current,
                    pageSize,
                    total,
                    showSizeChanger: true,
                    onChange: (page, size) => {
                        setCurrent(page);
                        if (size) setPageSize(size);
                    },
                }}
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
                />
            )}

            {resourceName === "meter_readings" && (
                <BulkReadingsModal
                    open={bulkModalOpen}
                    onClose={() => setBulkModalOpen(false)}
                    onSaved={() => tableQuery.refetch()}
                />
            )}

            {isAccrualsRegister && (
                <AccrualsCalculationModal
                    open={accrualsModalOpen}
                    onClose={() => setAccrualsModalOpen(false)}
                    onSaved={() => tableQuery.refetch()}
                />
            )}
        </div>
    );
};
