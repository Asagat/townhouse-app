// ReceiptsModal.tsx

import { useEffect, useState } from "react";
import { Modal, Button, Space, Select, InputNumber, message } from "antd";
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
 * Модальное окно формирования квитанций за период по всем квартирам.
 * После успешной генерации список обновляется; PDF доступен из таблицы.
 */
export const ReceiptsModal = ({ open, onClose, onSaved }: ReceiptsModalProps) => {
    const apiUrl = useApiUrl();
    const now = dayjs();
    const [year, setYear] = useState<number>(now.year());
    const [month, setMonth] = useState<number>(now.month() + 1);
    const [generating, setGenerating] = useState(false);

    const { mutate: generate } = useCustomMutation();

    useEffect(() => {
        if (open) {
            setYear(now.year());
            setMonth(now.month() + 1);
            setGenerating(false);
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

    return (
        <Modal
            title="Формирование квитанций"
            open={open}
            onCancel={onClose}
            destroyOnClose
            footer={[
                <Button key="cancel" onClick={onClose}>
                    Отмена
                </Button>,
                <Button key="go" type="primary" loading={generating} onClick={handleGenerate}>
                    Сформировать по всем квартирам
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
                период. Скачивание PDF доступно из списка квитанций.
            </div>
        </Modal>
    );
};
