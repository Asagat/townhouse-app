// frontend/src/pages/StatementReport.tsx
// «Выписка по лицевому счёту» — движения по счёту за период, как в ЛК жителя
// (та же таблица/формат, тот же /accounts/{id}/movements), по умолчанию текущий месяц.

import { useCallback, useEffect, useState } from "react";
import {
    Card,
    Table,
    Spin,
    Alert,
    Select,
    Button,
    Space,
    Typography,
    Statistic,
    Row,
    Col,
    DatePicker,
} from "antd";
import { ReloadOutlined, FilePdfOutlined } from "@ant-design/icons";
import dayjs, { Dayjs } from "dayjs";
import { useList } from "@refinedev/core";
import { authedFetch, apiUrl, openAuthorizedPdf } from "../auth/http";

interface MovementRow {
    date: string | null;
    kind: string;
    kind_label: string;
    service: string | null;
    document: string | null;
    amount: number;
    balance_after: number;
}
interface MovementMetrics {
    accrued: number;
    paid: number;
    available: number;
    debt: number;
}
interface StmtData {
    account: {
        id: number;
        account_number: string;
        account_name: string;
        apartment_number: number | null;
        owner_name: string | null;
    };
    metrics: MovementMetrics | null;
    movements: MovementRow[];
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
const fmtSigned = (v: number): string => {
    const s = fmt(Math.abs(v));
    return v > 0 ? `+${s}` : v < 0 ? `-${s}` : "0,00";
};
const fmtDate = (v: string | null): string =>
    v ? dayjs(v).format("DD.MM.YYYY") : "—";

export const StatementReport = () => {
    const [accountId, setAccountId] = useState<number | undefined>(undefined);
    const { data: accountsData } = useList({ resource: "accounts", pagination: { mode: "off" } });
    const accountOptions = (accountsData?.data ?? []).map((a: any) => ({
        value: a.id,
        label: `${a.account_number} — кв.${a.apartment?.apartment_number ?? "?"} ${a.account_name ?? ""}`.trim(),
    }));

    const [range, setRange] = useState<[Dayjs, Dayjs] | null>(() => [
        dayjs().startOf("month"),
        dayjs().endOf("month"),
    ]);
    const [data, setData] = useState<StmtData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback((id?: number, a?: Dayjs, b?: Dayjs) => {
        if (!id) { setData(null); return; }
        setLoading(true); setError(null);
        const p = new URLSearchParams();
        if (a) p.set("from_date", a.format("YYYY-MM-DD"));
        if (b) p.set("to_date", b.format("YYYY-MM-DD"));
        const q = p.toString();
        authedFetch(`${apiUrl}/accounts/${id}/movements${q ? `?${q}` : ""}`)
            .then(async (r) => {
                if (!r.ok) { let d = "Не удалось загрузить выписку"; try { d = (await r.json())?.detail ?? d; } catch { /* ignore */ } throw new Error(d); }
                return r.json();
            })
            .then((d: StmtData) => setData(d))
            .catch((e: any) => setError(e?.message ?? "Не удалось загрузить выписку"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load(accountId, range?.[0], range?.[1]);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [accountId, range]);

    const handlePdf = () => {
        if (!accountId) return;
        const p = new URLSearchParams({ account_id: String(accountId) });
        if (range?.[0]) p.set("from_date", range[0].format("YYYY-MM-DD"));
        if (range?.[1]) p.set("to_date", range[1].format("YYYY-MM-DD"));
        openAuthorizedPdf(
            `${apiUrl}/reports/statement/pdf?${p.toString()}`,
            `statement_${accountId}.pdf`,
        );
    };

    const cols = [
        { title: "Дата", dataIndex: "date", key: "date", width: 90, render: (v: string | null) => fmtDate(v) },
        { title: "Вид", dataIndex: "kind_label", key: "kind_label", width: 120 },
        { title: "Услуга", dataIndex: "service", key: "service", render: (v: string | null) => v ?? "—" },
        { title: "Основание", dataIndex: "document", key: "document", render: (v: string | null) => v ?? "—" },
        {
            title: "Сумма",
            dataIndex: "amount",
            key: "amount",
            align: "right" as const,
            width: 110,
            render: (_v: number, r: MovementRow) => {
                const shown = -r.amount;
                return (
                    <Typography.Text style={{ color: shown > 0 ? "#3f8600" : shown < 0 ? "#cf1322" : undefined }}>
                        {fmtSigned(shown)}
                    </Typography.Text>
                );
            },
        },
        {
            title: "Долг",
            dataIndex: "balance_after",
            key: "balance_after",
            align: "right" as const,
            width: 110,
            render: (v: number) => <Typography.Text>{fmt(v)}</Typography.Text>,
        },
    ];

    const m = data?.metrics;

    return (
        <div>
            <Typography.Title level={4} style={{ marginTop: 0 }}>Выписка по лицевому счёту</Typography.Title>
            <Card style={{ marginBottom: 16 }}>
                <Space wrap>
                    <Select
                        style={{ width: 360 }}
                        placeholder="Выберите лицевой счёт"
                        showSearch
                        optionFilterProp="label"
                        value={accountId}
                        onChange={setAccountId}
                        options={accountOptions}
                    />
                    <DatePicker.RangePicker
                        format="DD.MM.YYYY"
                        value={range as any}
                        onChange={(v) => setRange(v as any)}
                        allowClear
                    />
                    <Button
                        type="primary"
                        icon={<ReloadOutlined />}
                        onClick={() => load(accountId, range?.[0], range?.[1])}
                        disabled={loading || !accountId}
                    >
                        Сформировать
                    </Button>
                    <Button icon={<FilePdfOutlined />} onClick={handlePdf} disabled={!accountId || loading}>
                        PDF
                    </Button>
                </Space>
            </Card>
            {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
            {loading && <div style={{ textAlign: "center", padding: 60 }}><Spin size="large" /></div>}
            {!loading && data && data.account && (
                <Card style={{ marginBottom: 16 }}>
                    <Typography.Text>
                        Л/с {data.account.account_number}
                        {data.account.apartment_number != null ? `, кв. ${data.account.apartment_number}` : ""}
                        {data.account.owner_name ? ` — ${data.account.owner_name}` : ""}
                    </Typography.Text>
                </Card>
            )}
            {!loading && data && (
                <>
                    {m && (
                        <Row gutter={16} style={{ marginBottom: 16 }}>
                            <Col span={8}><Card size="small"><Statistic title="Начислено (период)" value={m.accrued} precision={2} /></Card></Col>
                            <Col span={8}><Card size="small"><Statistic title="Списано (период)" value={m.paid} precision={2} /></Card></Col>
                            <Col span={8}><Card size="small"><Statistic title="Долг" value={m.debt} precision={2} valueStyle={{ color: m.debt > 0 ? "#cf1322" : "#3f8600" }} /></Card></Col>
                        </Row>
                    )}
                    <Card title="Движения по счёту">
                        <Table<MovementRow>
                            rowKey={(r, i) => `${r.date ?? ""}-${r.kind}-${i}`}
                            size="small"
                            dataSource={data.movements}
                            columns={cols}
                            pagination={{ pageSize: 25, showSizeChanger: true }}
                            scroll={{ y: 460 }}
                            locale={{ emptyText: "Движений за период нет" }}
                        />
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
