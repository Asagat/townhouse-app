// frontend/src/pages/StatementReport.tsx
// Выписка по лицевому счёту: помесячно начислено/списано/остаток.

import { useCallback, useState } from "react";
import { Card, Table, Spin, Alert, Select, Button, Space, Typography, Statistic, Row, Col } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useList } from "@refinedev/core";
import { authedFetch, apiUrl } from "../auth/http";

interface MonthlyRow { period: string; accrued: number; paid: number; closing: number; }
interface StmtData {
    account: { id: number; account_number: string; account_name: string; apartment_number: number | null; owner_name: string | null; };
    monthly: MonthlyRow[];
    closing: number;
}

const fmt = (v: number | null | undefined): string => {
    const num = Number(v ?? 0);
    let n = num, prefix = "";
    if (!Number.isFinite(n)) return "0,00";
    if (n < 0) { prefix = "-"; n = Math.abs(n); }
    const [i, f] = n.toFixed(2).split(".");
    return `${prefix}${i.replace(/\B(?=(\d{3})+(?!\d))/g, " ")}${f ? "," + f : ""}`;
};
const periodLabel = (p: string) => { const [y, m] = p.split("-"); return `${m}.${y}`; };

export const StatementReport = () => {
    const [accountId, setAccountId] = useState<number | undefined>(undefined);
    const { data: accountsData } = useList({ resource: "accounts", pagination: { mode: "off" } });
    const accountOptions = (accountsData?.data ?? []).map((a: any) => ({ value: a.id, label: `${a.account_number} — ${a.apartment?.apartment_number ?? ""} ${a.account_name ?? ""}`.trim() }));
    const [data, setData] = useState<StmtData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback((id?: number) => {
        if (!id) { setData(null); return; }
        setLoading(true); setError(null);
        authedFetch(`${apiUrl}/reports/statement?account_id=${id}`)
            .then(async (r) => {
                if (!r.ok) { let d = "Не удалось загрузить выписку"; try { d = (await r.json())?.detail ?? d; } catch {} throw new Error(d); }
                return r.json();
            })
            .then((d: StmtData) => setData(d))
            .catch((e: any) => setError(e?.message ?? "Не удалось загрузить выписку"))
            .finally(() => setLoading(false));
    }, []);

    const handleSelect = (id?: number) => { setAccountId(id); load(id); };

    const cols = [
        { title: "Период", dataIndex: "period", key: "period", render: (v: string) => periodLabel(v) },
        { title: "Начислено", dataIndex: "accrued", key: "accrued", align: "right" as const, render: (v: number) => fmt(v) },
        { title: "Списано/оплачено", dataIndex: "paid", key: "paid", align: "right" as const, render: (v: number) => fmt(v) },
        { title: "Остаток на конец периода", dataIndex: "closing", key: "closing", align: "right" as const, render: (v: number) => {
            const color = v > 0 ? "#cf1322" : v < 0 ? "#3f8600" : undefined;
            return <Typography.Text style={{ color }}>{fmt(v)}</Typography.Text>;
        } },
    ];

    return (
        <div>
            <Typography.Title level={4} style={{ marginTop: 0 }}>Выписка по лицевому счёту</Typography.Title>
            <Card style={{ marginBottom: 16 }}>
                <Space wrap>
                    <Select
                        style={{ width: 340 }}
                        placeholder="Выберите лицевой счёт"
                        showSearch optionFilterProp="label"
                        value={accountId}
                        onChange={handleSelect}
                        options={accountOptions}
                    />
                    <Button type="primary" icon={<ReloadOutlined />} onClick={() => load(accountId)} disabled={loading || !accountId}>
                        Сформировать
                    </Button>
                </Space>
            </Card>
            {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
            {loading && <div style={{ textAlign: "center", padding: 60 }}><Spin size="large" /></div>}
            {!loading && data && (
                <>
                    {data.account.owner_name && (
                        <Card size="small" style={{ marginBottom: 16 }}>
                            <Typography.Text>
                                Л/с {data.account.account_number} (кв. {data.account.apartment_number ?? "—"}): {data.account.owner_name}
                            </Typography.Text>
                        </Card>
                    )}
                    <Row gutter={16} style={{ marginBottom: 16 }}>
                        <Col span={12}><Card size="small"><Statistic title="Записей периодов" value={data.monthly.length} /></Card></Col>
                        <Col span={12}><Card size="small"><Statistic title="Текущий остаток по счёту" value={data.closing} precision={2} /></Card></Col>
                    </Row>
                    <Card title="Движение по периодам">
                        <Table rowKey="period" size="small" dataSource={data.monthly} columns={cols} pagination={{ pageSize: 25 }} scroll={{ y: 420 }} />
                    </Card>
                </>
            )}
            {!loading && !data && !error && !accountId && (
                <Alert type="info" showIcon message="Выберите лицевой счёт для построения выписки" />
            )}
        </div>
    );
};

export default StatementReport;
