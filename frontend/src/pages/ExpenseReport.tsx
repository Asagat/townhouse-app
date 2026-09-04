// frontend/src/pages/ExpenseReport.tsx
// Отчёт по расходам: расход кассы за период — итог, по статьям и детализация по документам.

import { useCallback, useEffect, useState } from "react";
import { Card, Row, Col, Statistic, Table, DatePicker, Button, Space, Select, Spin, Alert, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import dayjs, { Dayjs } from "dayjs";
import { useList } from "@refinedev/core";
import { authedFetch, apiUrl } from "../auth/http";

const { RangePicker } = DatePicker;

interface ArticleRow { name: string; expense: number; }
interface MovementRow {
    operation_date: string | null;
    document_title: string;
    transaction_id: number;
    account_number: string | null;
    article_name: string | null;
    contractor_name: string | null;
    amount: number;
}
interface ExpenseData {
    period: { from: string | null; to: string | null };
    total_expense: number;
    articles: ArticleRow[];
    movements: MovementRow[];
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

export const ExpenseReport = () => {
    const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null);
    const [cashPointId, setCashPointId] = useState<number | undefined>(undefined);
    const { data: cashPointsData } = useList({ resource: "cash_points", pagination: { mode: "off" } });
    const cashPointOptions = (cashPointsData?.data ?? []).map((p: any) => ({ value: p.id, label: p.name }));
    const [data, setData] = useState<ExpenseData | null>(null);
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
        authedFetch(`${apiUrl}/reports/expenses${qs ? `?${qs}` : ""}`)
            .then(async (r) => {
                if (!r.ok) {
                    let d = "Не удалось загрузить отчёт";
                    try { d = (await r.json())?.detail ?? d; } catch { /* ignore */ }
                    throw new Error(d);
                }
                return r.json();
            })
            .then((d: ExpenseData) => setData(d))
            .catch((err: any) => setError(err?.message ?? "Не удалось загрузить отчёт"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(); }, [load]);

    const handleApply = () => {
        const from = range?.[0]?.format("YYYY-MM-DD") ?? undefined;
        const to = range?.[1]?.format("YYYY-MM-DD") ?? undefined;
        load(from, to, cashPointId);
    };

    const articleCols = [
        { title: "Статья расхода", dataIndex: "name", key: "name" },
        { title: "Сумма", dataIndex: "expense", key: "expense", align: "right" as const, render: (v: number) => fmt(v) },
    ];

    const movementCols = [
        { title: "Дата", dataIndex: "operation_date", key: "operation_date", render: (v: string | null) => v ? dayjs(v).format("DD.MM.YYYY") : "—" },
        { title: "Документ", dataIndex: "document_title", key: "document_title" },
        { title: "Статья", dataIndex: "article_name", key: "article_name", render: (v: string | null) => v ?? "—" },
        { title: "Контрагент", dataIndex: "contractor_name", key: "contractor_name", render: (v: string | null) => v ?? "—" },
        { title: "Лицевой счёт", dataIndex: "account_number", key: "account_number", render: (v: string | null) => v ?? "—" },
        { title: "Сумма", dataIndex: "amount", key: "amount", align: "right" as const, render: (v: number) => fmt(v) },
    ];

    return (
        <div>
            <Typography.Title level={4} style={{ marginTop: 0 }}>Отчёт по расходам</Typography.Title>

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

            {loading && <div style={{ textAlign: "center", padding: 60 }}><Spin size="large" /></div>}

            {!loading && data && (
                <>
                    <Row gutter={16} style={{ marginBottom: 16 }}>
                        <Col span={12}><Card size="small"><Statistic title="Расходы за период" value={data.total_expense} precision={2} /></Card></Col>
                        <Col span={12}><Card size="small"><Statistic title="Количество операций" value={data.count} /></Card></Col>
                    </Row>

                    <Card title="По статьям расходов" style={{ marginBottom: 16 }}>
                        <Table rowKey="name" size="small" pagination={{ pageSize: 20 }} dataSource={data.articles} columns={articleCols} />
                    </Card>

                    <Card title="Движение по документам (расходы)">
                        <Table
                            rowKey="transaction_id"
                            size="small"
                            dataSource={data.movements}
                            columns={movementCols}
                            pagination={{ pageSize: 25 }}
                            locale={{ emptyText: "Расходов за период нет" }}
                        />
                    </Card>
                </>
            )}
        </div>
    );
};

export default ExpenseReport;
