// frontend/src/pages/DebtorsReport.tsx
// Отчёт по должникам: активные л/с с положительным долгом.
// Позволяет выбрать дату, по состоянию на которую считается долг (as_of).

import { useCallback, useEffect, useState } from "react";
import { Card, Table, Spin, Alert, Statistic, Space, Typography, Button, DatePicker } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import dayjs, { type Dayjs } from "dayjs";
import { authedFetch, apiUrl, openAuthorizedPdf } from "../auth/http";

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
    as_of?: string | null;
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
    // «На дату»: если дата выбрана — долг считается по состоянию на конец этого дня;
    // если очищена — как «на сейчас» (вся история), как раньше.
    const [asOf, setAsOf] = useState<Dayjs | null>(() => dayjs());
    const [data, setData] = useState<DebtorsData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const qs = (asOf: Dayjs | null): string =>
        asOf ? `?as_of=${asOf.format("YYYY-MM-DD")}` : "";

    const load = useCallback(() => {
        setLoading(true);
        setError(null);
        authedFetch(`${apiUrl}/reports/debtors${qs(asOf)}`)
            .then(async (r) => {
                if (!r.ok) { let d = "Не удалось загрузить отчёт"; try { d = (await r.json())?.detail ?? d; } catch {} throw new Error(d); }
                return r.json();
            })
            .then((d: DebtorsData) => setData(d))
            .catch((e: any) => setError(e?.message ?? "Не удалось загрузить отчёт"))
            .finally(() => setLoading(false));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [asOf]);

    useEffect(() => { load(); }, [load]);

    const handlePdf = () => {
        openAuthorizedPdf(`${apiUrl}/reports/debtors/pdf${qs(asOf)}`, "debtors_report.pdf");
    };

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
            <Card style={{ marginBottom: 16 }}>
                <Space wrap>
                    <span>Состояние на дату:</span>
                    <DatePicker
                        value={asOf}
                        onChange={(v) => setAsOf(v)}
                        format="DD.MM.YYYY"
                        allowClear
                        placeholder="На сейчас"
                    />
                    <Button type="primary" icon={<ReloadOutlined />} onClick={load} disabled={loading}>Сформировать</Button>
                    <Button onClick={handlePdf} disabled={loading}>PDF</Button>
                </Space>
            </Card>
            {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
            {loading && <div style={{ textAlign: "center", padding: 60 }}><Spin size="large" /></div>}
            {!loading && data && (
                <>
                    <Card style={{ marginBottom: 16 }}>
                        <Statistic
                            title={asOf ? `Общий долг по л/с на ${asOf.format("DD.MM.YYYY")}` : "Общий долг по л/с (на сейчас)"}
                            value={data.total_debt}
                            precision={2}
                        />
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
