// src/components/accruals/OneOffAccrualsEditModal.tsx

import { useEffect, useState } from "react";
import { Modal, Button, Table, Input, InputNumber, Space, message, Typography } from "antd";
import { useApiUrl, useCustom, useCustomMutation } from "@refinedev/core";
import { formatNumber } from "../../config/formatters";

interface CopyRow {
    id: number;
    account_id: number;
    account_label: string;
    service_label: string;
    amount: number;
}

interface Props {
    open: boolean;
    documentId: number | undefined;
    onClose: () => void;
    onSaved: () => void;
}

export const OneOffAccrualsEditModal = ({ open, documentId, onClose, onSaved }: Props) => {
    const apiUrl = useApiUrl();
    const [comment, setComment] = useState("");
    const [rows, setRows] = useState<CopyRow[]>([]);
    const [saving, setSaving] = useState(false);

    const { data: detailsData, refetch, isFetching } = useCustom<any>({
        url: documentId ? `${apiUrl}/accrual_documents/${documentId}/details` : "",
        method: "get",
        queryOptions: { enabled: false },
    });

    const { mutate: save } = useCustomMutation();

    useEffect(() => {
        if (open && documentId) {
            setRows([]);
            setComment("");
            refetch();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, documentId]);

    useEffect(() => {
        if (!detailsData?.data) return;
        const { document, accruals } = detailsData.data;
        setComment(document?.comment ?? "");
        setRows(
            (accruals ?? []).map((a: any) => ({
                id: a.id,
                account_id: a.account_id,
                account_label:
                    a.apartment && a.account
                        ? `№ ${a.apartment.apartment_number} (${a.account.account_number})`
                        : `счёт #${a.account_id}`,
                service_label: a.services_type?.services_type ?? `услуга #${a.services_type_id}`,
                amount: Number(a.amount) || 0,
            })),
        );
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [detailsData]);

    const setAmount = (id: number, value: number | null) => {
        setRows((prev) => prev.map((r) => (r.id === id ? { ...r, amount: value ?? 0 } : r)));
    };

    const handleSave = () => {
        setSaving(true);
        save(
            {
                url: `${apiUrl}/accrual_documents/${documentId}/amounts`,
                method: "put",
                values: {
                    rows: rows.map((r) => ({ id: r.id, amount: r.amount })),
                    comment: comment.trim() || null,
                },
            },
            {
                onSuccess: () => {
                    message.success("Изменения сохранены");
                    setSaving(false);
                    onSaved();
                    onClose();
                },
                onError: (err: any) => {
                    message.error(
                        err?.response?.data?.detail ?? "Не удалось сохранить правки разовых сборов",
                    );
                    setSaving(false);
                },
            },
        );
    };

    const columns = [
        { title: "Квартира / Лицевой счёт", dataIndex: "account_label", key: "account_label" },
        { title: "Вид услуги", dataIndex: "service_label", key: "service_label" },
        {
            title: "Сумма (₸)",
            dataIndex: "amount",
            key: "amount",
            width: 220,
            render: (_: unknown, rec: CopyRow) => (
                <InputNumber
                    min={0}
                    precision={2}
                    style={{ width: "100%" }}
                    value={rec.amount}
                    onChange={(v) => setAmount(rec.id, typeof v === "number" ? v : null)}
                />
            ),
        },
    ];

    const totalAmount = rows.reduce((s, r) => s + (Number(r.amount) || 0), 0);

    return (
        <Modal
            title="Редактирование разовых/персональных начислений"
            open={open}
            onCancel={onClose}
            width={820}
            destroyOnClose
            footer={[
                <Button key="cancel" onClick={onClose}>
                    Отмена
                </Button>,
                <Button
                    key="save"
                    type="primary"
                    loading={saving}
                    onClick={handleSave}
                    disabled={rows.length === 0}
                >
                    Сохранить
                </Button>,
            ]}
        >
            <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
                Разовые сборы начисляются фиксированными суммами (без показаний/потребления) —
                здесь правится только сумма строки.
            </Typography.Paragraph>
            <Table
                rowKey="id"
                size="small"
                loading={isFetching}
                columns={columns}
                dataSource={rows}
                pagination={false}
                scroll={{ y: 360 }}
                locale={{ emptyText: "Нет строк" }}
            />
            <div style={{ marginTop: 12 }}>
                <div style={{ marginBottom: 4 }}>Примечание к документу</div>
                <Input.TextArea
                    rows={2}
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="Комментарий бухгалтера (необязательно)"
                />
            </div>
            <Space style={{ marginTop: 8 }} size="small">
                <span>
                    Итог: <b>{formatNumber(totalAmount)}</b> ₸
                </span>
            </Space>
        </Modal>
    );
};
