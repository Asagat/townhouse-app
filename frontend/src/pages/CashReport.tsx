// frontend/src/pages/CashReport.tsx
// Отчёт по кассе: движение денег по кассам/счетам за период.

import { useCallback, useEffect, useState } from "react";
import { Card, Row, Col, Statistic, Table, DatePicker, Button, Space, Select, Spin, Alert, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import dayjs, { Dayjs } from "dayjs";
import { useList } from "@refinedev/core";
import { authedFetch, apiUrl } from "../auth/http";

const { RangePicker } = DatePicker;

interface CashPointRow {
    cash_point_id: number;
    cash_point_name: string;
    is_active: boolean;
    opening: number;
    income: number;
    expense: number;
    closing: number;
}

interface MovementRow {
    operation_date: string | null;
    document_title: string;
    transaction_id: number;
    account_number: string | null;
    account_name: string | null;
    article_name: string | null;
    income: number;
    expense: number;
    amount: number;
}

interface ReportData {
    period: { from: string | null; to: string | null };
    totals: { opening: number; income: number; expense: number; closing: number };
    cash_points: CashPointRow[];
    movements: MovementRow[];
}

const fmt = (v: number | null | undefined): string => {
    const num = Number(v ?? 0);
    let n = num, prefix = "";
    if (!Number.isFinite(n)) return "0,00";
    if (n < 0) { prefix = "-"; n = Math.abs(n); }
    const [i, f] = n.toFixed(2).split(".");
    return `${prefix}${i.replace(/\B(?=(\d{3})+(?!\d))/g, " ")}${f ? "," + f : ""}`;
};

export const CashReport = () => {
    const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null);
    const [cashPointId, setCashPointId] = useState<number | undefined>(undefined);
    const { data: cashPointsData } = useList({ resource: "cash_points", pagination: { mode: "off" } });
    const cashPointOptions = (cashPointsData?.data ?? []).map((p: any) => ({ value: p.id, label: p.name }));
    const [data, setData] = useState<ReportData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback((from?: string, to?: string, cp?: number) => {
        setLoading(true);
        setError(null);
        const params = new URLSearchParams();
        if (from) params.set("from_date", from);
        if (to) params.set("to_date", to);
        if (cp) params.set("cash_point_id", String(cp));
        const qs = params.toString();
        authedFetch(`${apiUrl}/reports/cash_register${qs ? `?${qs}` : ""}`)
            .then(async (r) => {
                if (!r.ok) {
                    let d = "Не удалось загрузить отчёт";
                    try { d = (await r.json())?.detail ?? d; } catch { /* ignore */ }
                    throw new Error(d);
                }
                return r.json();
            })
            .then((d: ReportData) => setData(d))
            .catch((err: any) => setError(err?.message ?? "Не удалось загрузить отчёт"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(); }, [load]);

    const handleApply = () => {
        const from = range?.[0]?.format("YYYY-MM-DD") ?? undefined;
        const to = range?.[1]?.format("YYYY-MM-DD") ?? undefined;
        load(from, to, cashPointId);
    };

    const totals = data?.totals;

    const pointCols = [
        { title: "Касса", dataIndex: "cash_point_name", key: "cash_point_name" },
        { title: "Остаток на начало", dataIndex: "opening", key: "opening", align: "right" as const, render: (v: number) => fmt(v) },
        { title: "Приход", dataIndex: "income", key: "income", align: "right" as const, render: (v: number) => fmt(v) },
        { title: "Расход", dataIndex: "expense", key: "expense", align: "right" as const, render: (v: number) => fmt(v) },
        { title: "Остаток на конец", dataIndex: "closing", key: "closing", align: "right" as const, render: (v: number) => fmt(v) },
    ];

    const movementCols = [
        { title: "Дата", dataIndex: "operation_date", key: "operation_date", render: (v: string | null) => v ? dayjs(v).format("DD.MM.YYYY") : "—" },
        { title: "Документ", dataIndex: "document_title", key: "document_title" },
        { title: "Касса", dataIndex: "cash_point_name", key: "cash_point_name" },
        { title: "Лицевой счёт", dataIndex: "account_number", key: "account_number", render: (v: string | null) => v ?? "—" },
        { title: "Аналитика", dataIndex: "article_name", key: "article_name", render: (v: string | null) => v ?? "—" },
        { title: "Приход", dataIndex: "income", key: "income", align: "right" as const, render: (v: number) => fmt(v) },
        { title: "Расход", dataIndex: "expense", key: "expense", align: "right" as const, render: (v: number) => fmt(v) },
    ];

    return (
        <div>
            <Typography.Title level={4} style={{ marginTop: 0 }}>Отчёт по кассе</Typography.Title>

            <Card style={{ marginBottom: 16 }}>
                <Space wrap>
                    <RangePicker value={range as any} onChange={(v: any) => setRange(v)} allowClear />
                    <Select
                        style={{ width: 200 }}
                        placeholder="Все кассы"
                        allowClear
                        value={cashPointId}
                        onChange={(v: number | undefined) => setCashPointId(v)}
                        options={cashPointOptions}
                    />
                    <Button type="primary" icon={<ReloadOutlined />} onClick={handleApply} disabled={loading}>
                        Сформировать
                    </Button>
                </Space>
            </Card>

            {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

            {loading && (
                <div style={{ textAlign: "center", padding: 60 }}><Spin size="large" /></div>
            )}

            {!loading && data && totals && (
                <>
                    <Row gutter={16} style={{ marginBottom: 16 }}>
                        <Col span={6}><Card size="small"><Statistic title="Остаток на начало" value={totals.opening} precision={2} /></Card></Col>
                        <Col span={6}><Card size="small"><Statistic title="Приход" value={totals.income} precision={2} /></Card></Col>
                        <Col span={6}><Card size="small"><Statistic title="Расход" value={totals.expense} precision={2} /></Card></Col>
                        <Col span={6}><Card size="small"><Statistic title="Остаток на конец" value={totals.closing} precision={2} /></Card></Col>
                    </Row>

                    <Card title="По кассам" style={{ marginBottom: 16 }}>
                        <Table rowKey="cash_point_id" size="small" pagination={false} dataSource={data.cash_points} columns={pointCols} />
                    </Card>

                    <Card title="Движение по документам">
                        <Table
                            rowKey="transaction_id"
                            size="small"
                            dataSource={data.movements}
                            columns={movementCols}
                            pagination={{ pageSize: 25 }}
                            locale={{ emptyText: "Движений за период нет" }}
                        />
                    </Card>
                </>
            )}
        </div>
    );
};

export default CashReport;
