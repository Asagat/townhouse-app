// WriteoffViewModal.tsx
// Просмотр документа «Списание задолженностей» со строками распределения.

import { useEffect, useState } from "react";
import { Modal, Button, Spin, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useApiUrl } from "@refinedev/core";
import { authedFetch } from "../../auth/http";

interface WriteoffItemData {
    id: number;
    account_id: number;
    account_number: string | null;
    account_name: string | null;
    services_type_id: number;
    services_type: string | null;
    allocated: number;
    balance_after: number | null;
}

interface WriteoffDocumentData {
    id: number;
    writeoff_date: string | null;
    title: string | null;
    status: string;
    created_by: number | null;
    created_at: string | null;
    items_count: number;
    total_allocated: number;
}

interface WriteoffViewModalProps {
    open: boolean;
    documentId: number | undefined;
    onClose: () => void;
}

const fmtAmount2 = (value: number | null | undefined): string => {
    const v = Number(value ?? 0);
    let num = v;
    let prefix = "";
    if (num < 0) {
        prefix = "-";
        num = Math.abs(num);
    }
    const rounded = num.toFixed(2);
    const [intPart, frac] = rounded.split(".");
    const withSpaces = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    return `${prefix}${withSpaces},${frac}`;
};

const statusLabel: Record<string, { text: string; color: string }> = {
    new: { text: "Активен", color: "green" },
    cancelled: { text: "Отменён", color: "red" },
};

export const WriteoffViewModal = ({
    open,
    documentId,
    onClose,
}: WriteoffViewModalProps) => {
    const apiUrl = useApiUrl();
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [doc, setDoc] = useState<WriteoffDocumentData | null>(null);
    const [items, setItems] = useState<WriteoffItemData[]>([]);

    useEffect(() => {
        if (!open || documentId === undefined) return;
        let cancelled = false;
        setLoading(true);
        setError(null);
        setDoc(null);
        setItems([]);
        authedFetch(`${apiUrl}/writeoff_documents/${documentId}/items`)
            .then(async (resp) => {
                if (!resp.ok) {
                    let detail = "Не удалось загрузить документ списания";
                    try {
                        const body = await resp.json();
                        detail = body?.detail ?? detail;
                    } catch {
                        /* ignore */
                    }
                    throw new Error(detail);
                }
                return resp.json();
            })
            .then((data) => {
                if (cancelled) return;
                setDoc(data?.document ?? null);
                setItems((data?.items ?? []).slice().sort((a: WriteoffItemData, b: WriteoffItemData) => a.id - b.id));
            })
            .catch((err: Error) => {
                if (cancelled) return;
                setError(err.message);
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [open, documentId, apiUrl]);

    const columns: ColumnsType<WriteoffItemData> = [
        { title: "Лицевой счёт", dataIndex: "account_number", key: "account_number",
          render: (v, r) => v ? `${v} (${r.account_name ?? ""})`.trim() : String(r.account_id) },
        { title: "Услуга", dataIndex: "services_type", key: "services_type",
          render: (v) => v ?? "—" },
        { title: "Списано", dataIndex: "allocated", key: "allocated", align: "right",
          render: (v: number) => fmtAmount2(v) },
        { title: "Баланс после", dataIndex: "balance_after", key: "balance_after", align: "right",
          render: (v: number | null) => v === null ? "—" : fmtAmount2(v) },
    ];

    const st = (doc?.status ?? "new");
    const status = statusLabel[st] ?? { text: st, color: "default" };

    return (
        <Modal
            title={`Списание задолженностей № ${doc?.id ?? (documentId ?? "")}`}
            open={open}
            onCancel={onClose}
            width={760}
            footer={[
                <Button key="close" onClick={onClose}>
                    Закрыть
                </Button>,
            ]}
        >
            {loading && (
                <div style={{ textAlign: "center", padding: 40 }}>
                    <Spin />
                </div>
            )}

            {error && !loading && (
                <div style={{ textAlign: "center", padding: 24, color: "#cf1322" }}>
                    {error}
                </div>
            )}

            {!loading && !error && doc && (
                <>
                    <div style={{ marginBottom: 16 }}>
                        <Typography.Text>
                            Дата: <b>{doc.writeoff_date ?? "—"}</b>; Создан: {doc.created_at ?? "—"}
                        </Typography.Text>
                        <br />
                        <Tag color={status.color}>{status.text}</Tag>
                        <div style={{ marginTop: 8 }}>
                            <Typography.Text strong>
                                Распределено: {fmtAmount2(doc.total_allocated)} по {doc.items_count} запись(ям).
                            </Typography.Text>
                        </div>
                    </div>
                    <Table<WriteoffItemData>
                        rowKey="id"
                        size="small"
                        pagination={false}
                        dataSource={items}
                        columns={columns}
                    />
                </>
            )}

            {!loading && !error && !items.length && (
                <Typography.Text type="secondary">
                    По документу нет строк распределения (задолженность отсутствовала).
                </Typography.Text>
            )}
        </Modal>
    );
};

export default WriteoffViewModal;
