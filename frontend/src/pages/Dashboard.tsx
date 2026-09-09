// frontend/src/pages/Dashboard.tsx
// Дашборд главной страницы (2.19): сводка по дому «на сейчас».
// Информационный экран без параметров — углубление в детали через готовые отчёты.

import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Card, Row, Col, Spin, Statistic, Table, Typography } from "antd";
import { ArrowRightOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { authedFetch, apiUrl } from "../auth/http";
import { formatMoney } from "../config/formatters";

interface Metrics {
    accrued: number;        // начислено за последние 30 дней
    received: number;       // внесено в кассу за последние 30 дней
    written_off: number;    // списано (погашение долга) за последние 30 дней
    debt: number;           // долг на сейчас (кумулятивно)
    cash_balance: number;   // остаток в кассе на сейчас
    debtors_count: number;  // число л/с с долгом
}

interface DebtorRow {
    account_id: number;
    account_number: string;
    apartment_number: number | null;
    owner_name: string | null;
    accrued: number;
    paid: number;
    debt: number;
}

interface DebtPoint {
    month: string;
    debt: number;
    label: string;
}

interface Article {
    name: string;
    expense: number;
}
interface Expenses {
    total: number;
    articles: Article[];
    count: number;
}

interface DashboardData {
    metrics: Metrics;
    top_debtors: DebtorRow[];
    debt_dynamics: DebtPoint[];
    expenses: Expenses;
    window_days: number;
}

const MONEY_STYLE: React.CSSProperties = { whiteSpace: "nowrap" };

export const Dashboard = () => {
    const [data, setData] = useState<DashboardData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const navigate = useNavigate();

    const load = useCallback(() => {
        setLoading(true);
        setError(null);
        authedFetch(`${apiUrl}/dashboard`)
            .then(async (r) => {
                if (!r.ok) {
                    let d = "Не удалось загрузить дашборд";
                    try { d = (await r.json())?.detail ?? d; } catch { /* ignore */ }
                    throw new Error(d);
                }
                return r.json() as Promise<DashboardData>;
            })
            .then((d) => setData(d))
            .catch((e: any) => setError(e?.message ?? "Не удалось загрузить дашборд"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(); }, [load]);

    const debtorCols = [
        {
            title: "№ квартиры", dataIndex: "apartment_number", key: "apartment",
            align: "center" as const,
            render: (v: number | null) => v ?? "—",
        },
        {
            title: "Лицевой счёт", dataIndex: "account_number", key: "account_number",
            align: "center" as const,
        },
        {
            title: "Собственник", dataIndex: "owner_name", key: "owner_name",
            align: "left" as const,
            render: (v: string | null) => v ?? "—",
        },
        {
            title: "Долг", dataIndex: "debt", key: "debt",
            align: "right" as const,
            render: (v: number) => (
                <Typography.Text style={{ color: v > 0 ? "#cf1322" : "#3f8600", ...MONEY_STYLE }}>
                    {formatMoney(v)}
                </Typography.Text>
            ),
        },
    ];

    const dynCols = [
        {
            title: "Месяц", dataIndex: "label", key: "month",
            align: "center" as const,
        },
        {
            title: "Долг на конец месяца", dataIndex: "debt", key: "debt",
            align: "right" as const,
            render: (v: number) => (
                <Typography.Text style={{ color: v > 0 ? "#cf1322" : "#3f8600", ...MONEY_STYLE }}>
                    {formatMoney(v)}
                </Typography.Text>
            ),
        },
    ];

    const m = data?.metrics;

    return (
        <div>
            <Typography.Title level={4} style={{ marginTop: 0 }}>Дашборд</Typography.Title>

            {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

            {loading && (
                <div style={{ textAlign: "center", padding: 60 }}><Spin size="large" /></div>
            )}

            {!loading && m && (
                <>
                    {/* Движение денег за период */}
                    <Typography.Title level={5} style={{ marginTop: 8, marginBottom: 12 }}>
                        Движение за последние {data?.window_days ?? 30} дней
                    </Typography.Title>
                    <Row gutter={16}>
                        <Col flex="1 1 230px">
                            <Card size="small">
                                <Statistic title="Начислено" value={m.accrued} precision={2} valueStyle={{ fontSize: 22 }} />
                            </Card>
                        </Col>
                        <Col flex="1 1 230px">
                            <Card size="small">
                                <Statistic title="Внесено в кассу" value={m.received} precision={2} valueStyle={{ fontSize: 22 }} />
                            </Card>
                        </Col>
                        <Col flex="1 1 230px">
                            <Card size="small">
                                <Statistic title="Списано" value={m.written_off} precision={2} valueStyle={{ fontSize: 22 }} />
                            </Card>
                        </Col>
                    </Row>

                    {/* Состояния на сейчас */}
                    <Typography.Title level={5} style={{ marginTop: 24, marginBottom: 12 }}>Состояние на сейчас</Typography.Title>
                    <Row gutter={16}>
                        <Col flex="1 1 230px">
                            <Card size="small">
                                <Statistic
                                    title={`Долг (л/с с долгом: ${m.debtors_count})`}
                                    value={m.debt} precision={2}
                                    valueStyle={{ color: m.debt > 0 ? "#cf1322" : "#3f8600", fontSize: 22 }}
                                />
                            </Card>
                        </Col>
                        <Col flex="1 1 230px">
                            <Card size="small">
                                <Statistic title="Остаток в кассе" value={m.cash_balance} precision={2}
                                    valueStyle={{ fontSize: 22 }} />
                            </Card>
                        </Col>
                    </Row>

                    {/* Должники */}
                    {data && (
                        <Card
                            title={`Должники`}
                            style={{ marginTop: 24 }}
                            extra={
                                <Button icon={<ArrowRightOutlined />}
                                    onClick={() => navigate("/debtors_report")}>
                                    Отчёт по должникам
                                </Button>
                            }
                        >
                            <Table
                                rowKey="account_id"
                                size="small"
                                dataSource={data.top_debtors}
                                columns={debtorCols}
                                pagination={false}
                                locale={{ emptyText: "Должников нет" }}
                            />
                        </Card>
                    )}

                    {/* Динамика долга */}
                    {data && (
                        <Card title="Динамика долга (12 месяцев)" style={{ marginTop: 24 }}>
                            <Table
                                rowKey="month"
                                size="small"
                                dataSource={data.debt_dynamics}
                                columns={dynCols}
                                pagination={false}
                            />
                        </Card>
                    )}

                    {/* Расходы по кассе */}
                    {data && data.expenses && (
                        <Card
                            title={`Расходы по кассе (за последние ${data.window_days} дней)`}
                            style={{ marginTop: 24 }}
                        >
                            {data.expenses.count === 0 ? (
                                <Typography.Text type="secondary">Расходов за период нет</Typography.Text>
                            ) : (
                                <Table
                                    rowKey="name"
                                    size="small"
                                    pagination={false}
                                    dataSource={[
                                        ...data.expenses.articles,
                                        {
                                            name: "Итого расходов",
                                            expense: data.expenses.total,
                                        },
                                    ]}
                                    columns={[
                                        {
                                            title: "Статья", dataIndex: "name", key: "name",
                                            align: "left" as const,
                                        },
                                        {
                                            title: "Сумма", dataIndex: "expense", key: "expense",
                                            align: "right" as const,
                                            render: (v: number, row: any) => (
                                                <Typography.Text strong={row.name === "Итого расходов"}
                                                    style={MONEY_STYLE}>
                                                    {formatMoney(v)}
                                                </Typography.Text>
                                            ),
                                        },
                                    ]}
                                />
                            )}
                        </Card>
                    )}
                </>
            )}
        </div>
    );
};

export default Dashboard;
