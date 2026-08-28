// frontend/src/pages/ResidentCabinet.tsx
// Личный кабинет жителя: сводка по ЛС + список своих квитанций (просмотр/PDF).

import { useCallback, useEffect, useState } from "react";
import { Card, Col, Row, Statistic, Spin, Table, Button, Alert, Space, Typography } from "antd";
import { EyeOutlined, FilePdfOutlined } from "@ant-design/icons";
import { useApiUrl } from "@refinedev/core";
import { authedFetch } from "../auth/http";
import { getIdentity } from "../auth/token";
import { ReceiptViewModal } from "../components/receipts/ReceiptViewModal";

interface StatementMetrics {
    accrued_total: number;
    paid_total: number;
    available: number;
    debt_total: number;
    overpayment: number;
    balance: number;
}

interface StatementService {
    services_type_id: number;
    service_name: string | null;
    accrued: number;
    paid: number;
    debt: number;
}

interface StatementData {
    account: { id: number; account_number: string; account_name: string };
    apartment: { apartment_number: number; address: string } | null;
    owner: { full_name: string; phone: string } | null;
    metrics: StatementMetrics;
    services: StatementService[];
}

interface ReceiptRow {
    id: number;
    period_month: number;
    period_year: number;
    apartment_number: number | null;
    owner_name: string;
    total_amount: number;
    payable_amount: number;
}

const MONTH_NAMES = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
];

const fmt = (v: number | null | undefined): string => {
    const num = Number(v ?? 0);
    if (!Number.isFinite(num)) num = 0;
    let n = num, prefix = "";
    if (n < 0) { prefix = "-"; n = Math.abs(n); }
    const [i, f] = n.toFixed(2).split(".");
    return `${prefix}${i.replace(/\B(?=(\d{3})+(?!\d))/g, " ")}${f ? "," + f : ""}`;
};

const periodLabel = (receipt: ReceiptRow): string => {
    const name = MONTH_NAMES[receipt.period_month - 1] ?? "";
    const cap = name ? name.charAt(0).toUpperCase() + name.slice(1) : String(receipt.period_month);
    return `${cap} ${receipt.period_year}`;
};

export const ResidentCabinet = () => {
    const apiUrl = useApiUrl();
    const [statement, setStatement] = useState<StatementData | null>(null);
    const [receipts, setReceipts] = useState<ReceiptRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [viewId, setViewId] = useState<number | undefined>(undefined);

    const load = useCallback(() => {
        setLoading(true);
        setError(null);
        Promise.all([
            authedFetch(`${apiUrl}/me/statement`).then(async (r) => {
                if (!r.ok) {
                    let d = "Не удалось загрузить сводку";
                    try { d = (await r.json())?.detail ?? d; } catch { /* ignore */ }
                    throw new Error(d);
                }
                return r.json() as Promise<StatementData>;
            }),
            authedFetch(`${apiUrl}/me/receipts`).then(async (r) => {
                if (!r.ok) return [] as ReceiptRow[];
                return r.json() as Promise<ReceiptRow[]>;
            }),
        ])
            .then(([stmt, recs]: [StatementData, ReceiptRow[]]) => {
                setStatement(stmt);
                setReceipts(recs ?? []);
            })
            .catch((err: any) => setError(err?.message ?? "Не удалось загрузить данные"))
            .finally(() => setLoading(false));
    }, [apiUrl]);

    useEffect(() => { load(); }, [load]);

    const identity = getIdentity();
    const m = statement?.metrics;

    const receiptCols = [
        { title: "Период", dataIndex: "period", key: "period", render: (_: unknown, r: ReceiptRow) => periodLabel(r) },
        { title: "Квартира", dataIndex: "apartment_number", key: "apartment_number" },
        { title: "Собственник", dataIndex: "owner_name", key: "owner_name" },
        { title: "К оплате", dataIndex: "payable_amount", key: "payable_amount", align: "right" as const, render: (v: number) => fmt(v) },
        {
            title: "Действия",
            key: "actions",
            width: 220,
            render: (_: unknown, r: ReceiptRow) => (
                <Space>
                    <Button size="small" onClick={() => setViewId(r.id)}>
                        <EyeOutlined /> Просмотр
                    </Button>
                    <Button
                        size="small"
                        type="primary"
                        onClick={() => window.open(`${apiUrl}/receipt_documents/${r.id}/pdf`, "_blank")}
                    >
                        <FilePdfOutlined /> PDF
                    </Button>
                </Space>
            ),
        },
    ];

    if (loading) {
        return (
            <div style={{ textAlign: "center", padding: 80 }}>
                <Spin size="large" />
            </div>
        );
    }

    return (
        <div>
            <Typography.Title level={4} style={{ marginTop: 0 }}>
                Личный кабинет
            </Typography.Title>
            {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

            {statement && m && (
                <Card title={`Лицевой счёт ${statement.account.account_number}`} style={{ marginBottom: 16 }}>
                    <Space direction="vertical" style={{ width: "100%" }}>
                        {statement.apartment && (
                            <Typography.Text>
                                {`Квартира № ${statement.apartment.apartment_number} — ${statement.apartment.address}`}
                            </Typography.Text>
                        )}
                        {statement.owner && (
                            <Typography.Text>{`Собственник: ${statement.owner.full_name} (${statement.owner.phone})`}</Typography.Text>
                        )}
                    </Space>
                    <Row gutter={16} style={{ marginTop: 16 }}>
                        <Col span={8}><Card size="small"><Statistic title="Начислено" value={m.accrued_total} precision={2} /></Card></Col>
                        <Col span={8}><Card size="small"><Statistic title="Оплачено" value={m.paid_total} precision={2} /></Card></Col>
                        <Col span={8}><Card size="small"><Statistic title="Внесено на счёт" value={m.available} precision={2} /></Card></Col>
                        <Col span={8}><Card size="small"><Statistic title="Долг" value={m.debt_total} precision={2} valueStyle={{ color: m.debt_total > 0 ? "#cf1322" : "#3f8600" }} /></Card></Col>
                        <Col span={8}><Card size="small"><Statistic title="Переплата" value={m.overpayment} precision={2} /></Card></Col>
                        <Col span={8}><Card size="small"><Statistic title="Баланс" value={m.balance} precision={2} /></Card></Col>
                    </Row>
                </Card>
            )}

            {statement && statement.services && statement.services.length > 0 && (
                <Card title="Детализация по услугам" style={{ marginBottom: 16 }}>
                    <Table
                        rowKey="services_type_id"
                        size="small"
                        pagination={false}
                        dataSource={statement.services}
                        columns={[
                            { title: "Услуга", dataIndex: "service_name", key: "service_name" },
                            { title: "Начислено", dataIndex: "accrued", key: "accrued", align: "right", render: (v: number) => fmt(v) },
                            { title: "Оплачено", dataIndex: "paid", key: "paid", align: "right", render: (v: number) => fmt(v) },
                            { title: "Долг", dataIndex: "debt", key: "debt", align: "right", render: (v: number) => fmt(v) },
                        ]}
                    />
                </Card>
            )}

            <Card
                title="Мои квитанции"
                extra={<Typography.Text type="secondary">{`Пользователь: ${identity?.full_name || identity?.username || ""}`}</Typography.Text>}
            >
                <Table
                    rowKey="id"
                    size="small"
                    dataSource={receipts}
                    columns={receiptCols}
                    locale={{ emptyText: "Квитанций пока нет" }}
                />
            </Card>

            <ReceiptViewModal
                open={viewId !== undefined}
                receiptId={viewId}
                onClose={() => setViewId(undefined)}
            />
        </div>
    );
};

export default ResidentCabinet;
