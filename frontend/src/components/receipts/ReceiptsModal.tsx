// ReceiptsModal.tsx

import { useEffect, useState } from "react";
import {
    Modal,
    Button,
    Space,
    Select,
    InputNumber,
    message,
    Popconfirm,
} from "antd";
import dayjs from "dayjs";
import { useApiUrl, useCustomMutation } from "@refinedev/core";

interface ReceiptsModalProps {
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
 * Модальное окно квитанций за период:
 * формирование по всем квартирам, массовое скачивание ZIP и массовое удаление.
 */
export const ReceiptsModal = ({ open, onClose, onSaved }: ReceiptsModalProps) => {
    const apiUrl = useApiUrl();
    const now = dayjs();
    const [year, setYear] = useState<number>(now.year());
    const [month, setMonth] = useState<number>(now.month() + 1);
    const [generating, setGenerating] = useState(false);
    const [downloading, setDownloading] = useState(false);
    const [deleting, setDeleting] = useState(false);

    const { mutate: generate } = useCustomMutation();

    useEffect(() => {
        if (open) {
            setYear(now.year());
            setMonth(now.month() + 1);
            setGenerating(false);
            setDownloading(false);
            setDeleting(false);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open]);

    const handleGenerate = () => {
        setGenerating(true);
        generate(
            {
                url: `${apiUrl}/receipt_documents/generate`,
                method: "post",
                values: { year, month },
            },
            {
                onSuccess: (response) => {
                    setGenerating(false);
                    const data = response.data as any;
                    const count = data?.created?.length ?? 0;
                    message.success(
                        count > 0
                            ? `Сформировано квитанций: ${count}`
                            : "Нет начислений за выбранный период — квитанции не созданы",
                    );
                    onSaved();
                    onClose();
                },
                onError: (err: any) => {
                    setGenerating(false);
                    message.error(
                        err?.response?.data?.detail ?? "Не удалось сформировать квитанции",
                    );
                },
            },
        );
    };

    const handleDownloadAll = async () => {
        setDownloading(true);
        try {
            const resp = await fetch(`${apiUrl}/receipt_documents/bulk_pdf`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ year, month }),
            });
            if (!resp.ok) {
                let detail = "Не удалось скачать квитанции";
                try {
                    const err = await resp.json();
                    detail = err?.detail ?? detail;
                } catch {
                    // ignore
                }
                message.error(detail);
                return;
            }
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `receipts_${String(month).padStart(2, "0")}_${year}.zip`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            message.success("Архив квитанций загружается");
        } catch (err: any) {
            message.error(err?.message ?? "Не удалось скачать квитанции");
        } finally {
            setDownloading(false);
        }
    };

    const handleDeleteAll = async () => {
        setDeleting(true);
        try {
            const resp = await fetch(
                `${apiUrl}/receipt_documents/bulk_delete?year=${year}&month=${month}`,
                { method: "DELETE" },
            );
            if (!resp.ok) {
                let detail = "Не удалось удалить квитанции";
                try {
                    const err = await resp.json();
                    detail = err?.detail ?? detail;
                } catch {
                    // ignore
                }
                message.error(detail);
                return;
            }
            const data = await resp.json();
            message.success(`Удалено квитанций: ${data?.deleted ?? 0}`);
            onSaved();
            onClose();
        } catch (err: any) {
            message.error(err?.message ?? "Не удалось удалить квитанции");
        } finally {
            setDeleting(false);
        }
    };

    return (
        <Modal
            title="Квитанции за период"
            open={open}
            onCancel={onClose}
            width={560}
            destroyOnClose
            footer={[
                <Button key="cancel" onClick={onClose}>
                    Отмена
                </Button>,
                <Popconfirm
                    key="del"
                    title="Удалить все квитанции за выбранный период?"
                    okText="Удалить"
                    cancelText="Отмена"
                    onConfirm={handleDeleteAll}
                >
                    <Button danger loading={deleting}>
                        Удалить
                    </Button>
                </Popconfirm>,
                <Button key="dl" loading={downloading} onClick={handleDownloadAll}>
                    Скачать (ZIP)
                </Button>,
                <Button
                    key="go"
                    type="primary"
                    loading={generating}
                    onClick={handleGenerate}
                >
                    Сформировать
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
                        onChange={(v) => v && setYear(Number(v))}
                    />
                </div>
            </Space>
            <div style={{ color: "#888" }}>
                Квитанции будут сформированы по всем активным лицевым счетам за выбранный
                период. ZIP-архив содержит PDF по каждой квитанции. Удаление затрагивает
                только квитанции за выбранный период.
            </div>
        </Modal>
    );
};
