// frontend/src/components/cabinet/CabinetView.tsx
// Общий блок «Личный кабинет»: сводка по лицевому счёту, детализация по услугам
// и список квитанций (просмотр/PDF). Используется:
//   - в ЛК жителя (pages/ResidentCabinet) — данные по своему счёту;
//   - в просмотре администратора (pages/AdminCabinet) — по выбранному счёту.

import { useState } from "react";
import { Button, Card, Space, Table, Typography } from "antd";
import { EyeOutlined, FilePdfOutlined } from "@ant-design/icons";
import { ReceiptViewModal } from "../receipts/ReceiptViewModal";

export interface StatementMetrics {
    accrued_total: number;
    paid_total: number;
    available: number;
    debt_total: number;
    overpayment: number;
    balance: number;
}

export interface StatementService {
    services_type_id: number;
    service_name: string | null;
    accrued: number;
    paid: number;
    debt: number;
}

export interface StatementData {
    account: { id: number; account_number: string; account_name: string };
    apartment: { apartment_number: number; address: string } | null;
    owner: { full_name: string; phone: string } | null;
    metrics: StatementMetrics;
    services: StatementService[];
}

export interface ReceiptRow {
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
    let num = Number(v ?? 0);
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

export const CabinetView = ({
    statement,
    receipts,
    apiUrl,
    userLabel,
    receiptsTitle = "Мои квитанции",
}: {
    statement: StatementData | null;
    receipts: ReceiptRow[];
    apiUrl: string;
    userLabel?: string;
    receiptsTitle?: string;
}) => {
    const [viewId, setViewId] = useState<number | undefined>(undefined);
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

    return (
        <div>
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
                    <Table
                        rowKey="metrics"
                        size="small"
                        pagination={false}
                        dataSource={[{ metrics: "", ...m }]}
                        columns={[
                            { title: "Начислено", dataIndex: "accrued_total", key: "accrued_total", align: "right" as const, render: (v: number) => fmt(v) },
                            { title: "Внесено на счёт", dataIndex: "available", key: "available", align: "right" as const, render: (v: number) => fmt(v) },
                            { title: "Списано", dataIndex: "paid_total", key: "paid_total", align: "right" as const, render: (v: number) => fmt(v) },
                            {
                                title: "Долг",
                                dataIndex: "debt_total",
                                key: "debt_total",
                                align: "right" as const,
                                render: (v: number) => <Typography.Text style={{ color: v > 0 ? "#cf1322" : "#3f8600" }}>{fmt(v)}</Typography.Text>,
                            },
                            { title: "Остаток на счёте", dataIndex: "overpayment", key: "overpayment", align: "right" as const, render: (v: number) => fmt(v) },
                        ]}
                    />
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
                            { title: "Списано", dataIndex: "paid", key: "paid", align: "right", render: (v: number) => fmt(v) },
                            { title: "Долг", dataIndex: "debt", key: "debt", align: "right", render: (v: number) => fmt(v) },
                        ]}
                    />
                </Card>
            )}

            <Card
                title={receiptsTitle}
                extra={userLabel ? <Typography.Text type="secondary">{userLabel}</Typography.Text> : undefined}
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

export default CabinetView;
