// WriteOffsModal.tsx

import { useState } from "react";
import { Modal, Button, message, Typography, Table } from "antd";
import { useApiUrl, useCustomMutation } from "@refinedev/core";
import { formatNumber } from "../../config/formatters";

interface WriteOffsModalProps {
    open: boolean;
    onClose: () => void;
    onSaved: () => void;
}

interface AccountResult {
    account_id: number;
    accrued: number;
    available: number;
    written_off: number;
}

interface WriteoffDoc {
    id: number;
    status: string;
    total_allocated: number;
}

export const WriteOffsModal = ({ open, onClose, onSaved }: WriteOffsModalProps) => {
    const apiUrl = useApiUrl();
    const [running, setRunning] = useState(false);
    const [result, setResult] = useState<AccountResult[] | null>(null);
    const [doc, setDoc] = useState<WriteoffDoc | null>(null);
    const [error, setError] = useState<string | null>(null);

    const { mutate } = useCustomMutation();

    const reset = () => {
        setRunning(false);
        setResult(null);
        setDoc(null);
        setError(null);
    };

    const handleRun = () => {
        setRunning(true);
        setError(null);
        setResult(null);
        setDoc(null);
        mutate(
            {
                url: `${apiUrl}/writeoff_documents/run`,
                method: "post",
                values: {},
            },
            {
                onSuccess: (response) => {
                    const data = (response.data as any) ?? {};
                    setDoc({
                        id: data.document?.id ?? 0,
                        status: data.document?.status ?? "new",
                        total_allocated: data.document?.total_allocated ?? 0,
                    });
                    const processed = Array.isArray(data.processed) ? data.processed : [];
                    const rows: AccountResult[] = processed.map((p: any) => ({
                        account_id: p.account_id,
                        accrued: p.accrued ?? 0,
                        available: p.available ?? 0,
                        written_off: p.written_off ?? 0,
                    }));
                    setRunning(false);
                    setResult(rows);
                    const total = rows.reduce((s, r) => s + (r.written_off ?? 0), 0);
                    message.success(
                        total > 0
                            ? `Списание выполнено (документ №${data.document?.id ?? 0}): распределено ${formatNumber(total)} по ${rows.length} счетам`
                            : "Списание выполнено: нет задолженности для распределения",
                    );
                    onSaved();
                },
                onError: (err: any) => {
                    setRunning(false);
                    const detail = err?.response?.data?.detail ?? "Не удалось выполнить списание";
                    setError(detail);
                    message.error(detail);
                },
            },
        );
    };

    const columns = [
        { title: "№ счёта", dataIndex: "account_id", key: "account_id" },
        { title: "Начислено", dataIndex: "accrued", key: "accrued", render: formatNumber },
        { title: "Доступно", dataIndex: "available", key: "available", render: formatNumber },
        { title: "Списано", dataIndex: "written_off", key: "written_off", render: formatNumber },
    ];

    const totalWritten = (result ?? []).reduce((s, r) => s + (r.written_off ?? 0), 0);
    const totalAccounts = (result ?? []).length;

    return (
        <Modal
            title="Списание задолженностей"
            open={open}
            onCancel={() => {
                reset();
                onClose();
            }}
            width={720}
            destroyOnClose
            footer={[
                <Button key="cancel" onClick={() => { reset(); onClose(); }}>
                    Закрыть
                </Button>,
                <Button key="run" type="primary" loading={running} onClick={handleRun}>
                    Выполнить списание
                </Button>,
            ]}
        >
            <div style={{ color: "#666", marginBottom: 16 }}>
                Доступные средства лицевых счетов будут распределены по видам услуг в
                порядке приоритета списания (справочник «Виды услуг»). Операция
                перестраивает распределение заново и безопасна для повторного запуска.
            </div>

            {error && (
                <Typography.Text type="danger" style={{ display: "block", marginBottom: 12 }}>
                    {error}
                </Typography.Text>
            )}

            {result && (
                <div style={{ marginBottom: 16 }}>
                    <Typography.Text strong>
                        {doc && doc.id ? `Документ «Списание задолженностей» №${doc.id} (${doc.status}). ` : ""}
                        Итог: списано {formatNumber(totalWritten)} по {totalAccounts} счетам.
                        Переплата (если есть) остаётся отрицательным остатком счёта.
                    </Typography.Text>
                </div>
            )}

            {result && result.length > 0 && (
                <Table<AccountResult>
                    rowKey="account_id"
                    size="small"
                    pagination={false}
                    dataSource={result}
                    columns={columns}
                />
            )}

            {result && result.length === 0 && !error && (
                <Typography.Text type="secondary">
                    Активных лицевых счетов, по которым нужно распределить средства, нет.
                </Typography.Text>
            )}
        </Modal>
    );
};
