// src/components/accruals/PersonalAccrualModal.tsx

import { useState } from "react";
import {
    Modal,
    Button,
    Space,
    Select,
    Input,
    InputNumber,
    Table,
    Typography,
    message,
} from "antd";
import { useApiUrl, useCustomMutation, useList } from "@refinedev/core";
import dayjs from "dayjs";
import { formatMoney } from "../../config/formatters";

interface PersonalAccrualModalProps {
    open: boolean;
    onClose: () => void;
    onSaved: () => void;
}

interface RowDraft {
    key: string;
    account_id: number;
    service_id: number;
    amount: number;
}

const monthOptions = ["Январь","Февраль","Март","Апрель","Май","Июнь",
    "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"].map((label, i) => ({
    value: i + 1,
    label,
}));

/**
 * Форма «Персональное доначисление/корректировка» (единица №4).
 * Создаёт отдельный документ (doc_kind='oneoff') со строками по конкретным л/с,
 * не затрагивая общий тариф и месячные начисления (сохраняется при пересчёте).
 */
export const PersonalAccrualModal = ({
    open,
    onClose,
    onSaved,
}: PersonalAccrualModalProps) => {
    const apiUrl = useApiUrl();
    const now = dayjs();
    const [year, setYear] = useState<number>(now.year());
    const [month, setMonth] = useState<number>(now.month() + 1);
    const [reason, setReason] = useState<string>("");

    const { data: accountsData } = useList({ resource: "accounts", pagination: { mode: "off" } });
    const { data: servicesData } = useList({ resource: "services_type", pagination: { mode: "off" } });

    const accountOptions = (accountsData?.data ?? []).map((a: any) => ({
        value: a.id,
        label: `${a.account_number} — кв.${a.apartment?.apartment_number ?? "?"} ${a.account_name ?? ""}`.trim(),
    }));
    const serviceOptions = (servicesData?.data ?? []).map((s: any) => ({
        value: s.id,
        label: s.services_type ?? `#${s.id}`,
    }));
    const serviceLabel = (id: number) =>
        serviceOptions.find((o: any) => o.value === id)?.label ?? `услуга #${id}`;

    const [rows, setRows] = useState<RowDraft[]>([]);
    const [selAcc, setSelAcc] = useState<number | undefined>(undefined);
    const [selSvc, setSelSvc] = useState<number | undefined>(undefined);
    const [selAmt, setSelAmt] = useState<number | undefined>(undefined);
    const [saving, setSaving] = useState(false);
    const { mutate } = useCustomMutation();

    const resetFresh = () => {
        setRows([]);
        setReason("");
        setSelAcc(undefined);
        setSelSvc(undefined);
        setSelAmt(undefined);
    };

    const ui_date = `${year}-${String(month).padStart(2, "0")}-01`;

    const addRow = () => {
        if (selAcc === undefined || selSvc === undefined || selAmt === undefined || selAmt === 0) {
            message.warning("Выберите л/с, услугу и введите ненулевую сумму");
            return;
        }
        const key = `${Date.now()}-${Math.random()}`;
        setRows((p) => [...p, { key, account_id: selAcc, service_id: selSvc, amount: selAmt }]);
        setSelAmt(undefined);
    };

    const submit = () => {
        if (!reason.trim()) {
            message.error("Укажите причину («Примечание») персональной корректировки");
            return;
        }
        if (rows.length === 0) {
            message.error("Добавьте хотя бы одну строку");
            return;
        }
        setSaving(true);
        mutate(
            {
                url: `${apiUrl}/accrual_documents/personal`,
                method: "post",
                values: {
                    accrual_date: ui_date,
                    comment: reason.trim(),
                    entries: rows.map((r) => ({
                        account_id: r.account_id,
                        services_type_id: r.service_id,
                        amount: r.amount,
                    })),
                },
            },
            {
                onSuccess: () => {
                    message.success("Персональное доначисление сохранено");
                    setSaving(false);
                    resetFresh();
                    onSaved();
                    onClose();
                },
                onError: (err: any) => {
                    message.error(
                        err?.response?.data?.detail ?? "Не удалось сохранить персональное доначисление",
                    );
                    setSaving(false);
                },
            },
        );
    };

    const columns = [
        {
            title: "Лицевой счёт",
            dataIndex: "account_id",
            key: "account_id",
            render: (_: unknown, r: RowDraft) =>
                accountOptions.find((o: any) => o.value === r.account_id)?.label ?? String(r.account_id),
        },
        { title: "Услуга", render: (_: unknown, r: RowDraft) => serviceLabel(r.service_id), key: "svc" },
        {
            title: "Сумма (±)",
            dataIndex: "amount",
            key: "amount",
            render: (v: number) => formatMoney(v),
        },
        {
            title: "",
            key: "del",
            width: 50,
            render: (_: unknown, r: RowDraft) => (
                <Button size="small" danger type="text" onClick={() => setRows((p) => p.filter((x) => x.key !== r.key))}>
                    Удалить
                </Button>
            ),
        },
    ];

    return (
        <Modal
            open={open}
            title="Персональное доначисление / корректировка"
            width={820}
            onCancel={() => {
                resetFresh();
                onClose();
            }}
            footer={[
                <Button key="cancel" onClick={onClose}>
                    Отмена
                </Button>,
                <Button key="save" type="primary" loading={saving} onClick={submit}>
                    Сохранить
                </Button>,
            ]}
        >
            <Typography.Paragraph type="secondary">
                Корректировка оформляется отдельным документом по конкретным лицевым счетам;
                общие тарифы и месячные начисления при этом не меняются.
            </Typography.Paragraph>
            <Space style={{ marginBottom: 12 }} wrap>
                <div>
                    <div style={{ marginBottom: 4 }}>Месяц</div>
                    <Select style={{ width: 150 }} value={month} onChange={setMonth} options={monthOptions} />
                </div>
                <div>
                    <div style={{ marginBottom: 4 }}>Год</div>
                    <InputNumber style={{ width: 100 }} min={2000} value={year} onChange={(v) => v && setYear(Number(v))} />
                </div>
                <div style={{ minWidth: 320 }}>
                    <div style={{ marginBottom: 4 }}>Причина (обязательно)</div>
                    <Input
                        placeholder="Например: доначисление площадки, уточнение счёта ..."
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                    />
                </div>
            </Space>

            <Space style={{ marginBottom: 12 }} wrap>
                <Select
                    placeholder="Лицевой счёт"
                    style={{ width: 300 }}
                    showSearch
                    optionFilterProp="label"
                    value={selAcc}
                    onChange={(v) => setSelAcc(v)}
                    options={accountOptions}
                />
                <Select
                    placeholder="Услуга"
                    style={{ width: 200 }}
                    value={selSvc}
                    onChange={(v) => setSelSvc(v)}
                    options={serviceOptions}
                />
                <InputNumber
                    placeholder="Сумма ±"
                    style={{ width: 150 }}
                    value={selAmt}
                    onChange={(v) => setSelAmt(v === null || v === undefined ? undefined : Number(v))}
                />
                <Button onClick={addRow}>Добавить строку</Button>
            </Space>

            <Table rowKey="key" size="small" pagination={false} dataSource={rows} columns={columns} />

            {rows.length > 0 && (
                <div style={{ marginTop: 8, textAlign: "right" }}>
                    Итого: {formatMoney(rows.reduce((s, r) => s + r.amount, 0))}
                </div>
            )}
        </Modal>
    );
};
