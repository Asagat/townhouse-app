// frontend/src/pages/DebtorsReport.tsx
// Отчёт по должникам: активные л/с с положительным долгом, по убыванию.

import { useCallback, useEffect, useState } from "react";
import { Card, Table, Spin, Alert, Statistic, Space, Typography, Button } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { authedFetch, apiUrl } from "../auth/http";

interface DebtorRow {
    account_id: number;
    account_number: string;
    account_name: string;
    apartment_number: number | null;
    address: string | null;
    owner_name: string | null;
    accrued: number;
    paid: number;
    debt: number;
    overpayment: number;
}
interface DebtorsData {
    rows: DebtorRow[];
    total_debt: number;
    count: number;
}

const fmt = (v: number | null | undefined): string => {
    const num = Number(v ?? 0);
    let n = num, prefix = "";
    if (!Number.isFinite(n)) return "0,00";
    if (n < 0) { prefix = "-"; n = Math.abs(n); }
    const [i, f] = n.toFixed(2).split(".");
    return `${prefix}${i.replace(/\B(?=(\d{3})+(?!\d))/g, " ")}${f ? "," + f : ""}`;
};

export const DebtorsReport = () => {
    const [data, setData] = useState<DebtorsData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(() => {
        setLoading(true);
        setError(null);
        authedFetch(`${apiUrl}/reports/debtors`)
            .then(async (r) => {
                if (!r.ok) { let d = "Не удалось загрузить отчёт"; try { d = (await r.json())?.detail ?? d; } catch {} throw new Error(d); }
                return r.json();
            })
            .then((d: DebtorsData) => setData(d))
            .catch((e: any) => setError(e?.message ?? "Не удалось загрузить отчёт"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(); }, [load]);

    const cols = [
        { title: "№ квартиры", dataIndex: "apartment_number", key: "apartment_number", render: (v: number | null) => v ?? "—" },
        { title: "Лицевой счёт", dataIndex: "account_number", key: "account_number" },
        { title: "Собственник", dataIndex: "owner_name", key: "owner_name", render: (v: string | null) => v ?? "—" },
        { title: "Начислено", dataIndex: "accrued", key: "accrued", align: "right" as const, render: (v: number) => fmt(v) },
        { title: "Оплачено", dataIndex: "paid", key: "paid", align: "right" as const, render: (v: number) => fmt(v) },
        { title: "Переплата", dataIndex: "overpayment", key: "overpayment", align: "right" as const, render: (v: number) => (v ? fmt(v) : "—") },
        { title: "Долг", dataIndex: "debt", key: "debt", align: "right" as const, render: (v: number) => <Typography.Text style={{ color: v > 0 ? "#cf1322" : "#3f8600" }}>{fmt(v)}</Typography.Text> },
    ];

    return (
        <div>
            <Typography.Title level={4} style={{ marginTop: 0 }}>Отчёт по должникам</Typography.Title>
            <Card style={{ marginBottom: 16 }}><Space><Button type="primary" icon={<ReloadOutlined />} onClick={load} disabled={loading}>Обновить</Button></Space></Card>
            {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
            {loading && <div style={{ textAlign: "center", padding: 60 }}><Spin size="large" /></div>}
            {!loading && data && (
                <>
                    <Card style={{ marginBottom: 16 }}>
                        <Statistic title="Общий долг по л/с" value={data.total_debt} precision={2} />
                    </Card>
                    <Card title={`Должники (${data.count})`}>
                        <Table rowKey="account_id" size="small" dataSource={data.rows} columns={cols} pagination={{ pageSize: 20 }} />
                    </Card>
                </>
            )}
        </div>
    );
};

export default DebtorsReport;
