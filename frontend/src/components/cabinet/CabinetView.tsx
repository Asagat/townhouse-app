// frontend/src/components/cabinet/CabinetView.tsx
// Общий блок «Личный кабинет»: сводка по лицевому счёту, детализация по услугам,
// движения по счёту и список квитанций (просмотр/PDF). Используется:
//   - в ЛК жителя (pages/ResidentCabinet) — данные по своему счёту (mode='me');
//   - в просмотре администратора (pages/AdminCabinet) — по выбранному счёту (mode='account').

import { useEffect, useState } from "react";
import { Button, Card, Col, DatePicker, Row, Space, Statistic, Table, Typography } from "antd";
import { FilePdfOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { authedFetch, openAuthorizedPdf } from "../../auth/http";
import { cellAlignStyle, headerAlignStyle } from "../../config/columnAlign";
import { formatPhone } from "../../config/formatters";

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

export interface MovementRow {
    date: string | null;
    kind: string;
    kind_label: string;
    service: string;
    amount: number;
    balance_after: number;
    document: string | null;
}

export interface MovementMetrics {
    accrued: number;
    paid: number;
    available: number;
    debt: number;
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

const fmtDate = (iso?: string | null): string => {
    if (!iso) return "—";
    const s = String(iso);
    return s.length >= 10 ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : s;
};

const fmtSigned = (v: number): string => {
    const num = Number(v ?? 0);
    return (num >= 0 ? "+" : "−") + fmt(Math.abs(num));
};

export const CabinetView = ({
    statement,
    receipts,
    apiUrl,
    userLabel,
    receiptsTitle = "Мои квитанции",
    mode = "me",
    houseExpenses,
}: {
    statement: StatementData | null;
    receipts: ReceiptRow[];
    apiUrl: string;
    userLabel?: string;
    receiptsTitle?: string;
    /** me — данные «моего» счёта (эндпоинты /me), account — по выбранному счёту. */
    mode?: "me" | "account";
    /** Показывать блок «Расходы по кассе» (в ЛК жителя и админ-просмотре). */
    houseExpenses?: boolean;
}) => {
    const houseExpensesEnabled = houseExpenses === true;
    const accountId = statement?.account?.id;

    // --- Движения по счёту (2.3 + Б15): период + таблица + PDF выписки. ---
    const [movements, setMovements] = useState<MovementRow[]>([]);
    const [movementMetrics, setMovementMetrics] = useState<MovementMetrics | null>(null);
    const [movementsLoading, setMovementsLoading] = useState(false);
    // Период движений по умолчанию — последние 30 дней (компактный сценарий ЛК).
    const [fromDate, setFromDate] = useState<string | undefined>(
        dayjs().subtract(30, "day").format("YYYY-MM-DD"),
    );
    const [toDate, setToDate] = useState<string | undefined>(
        dayjs().format("YYYY-MM-DD"),
    );

    const movementBase =
        mode === "me" ? `${apiUrl}/me/movements` : `${apiUrl}/accounts/${accountId}/movements`;
    const pdfBase =
        mode === "me" ? `${apiUrl}/me/statement/pdf` : `${apiUrl}/accounts/${accountId}/statement/pdf`;

    const rangeParams = () => {
        const p = new URLSearchParams();
        if (fromDate) p.set("from_date", fromDate);
        if (toDate) p.set("to_date", toDate);
        return p.toString();
    };

    useEffect(() => {
        if (!accountId) {
            setMovements([]);
            setMovementMetrics(null);
            return;
        }
        let cancelled = false;
        setMovementsLoading(true);
        const q = rangeParams();
        authedFetch(q ? `${movementBase}?${q}` : movementBase)
            .then(async (r) => {
                if (!r.ok) return { movements: [] as MovementRow[] };
                return r.json();
            })
            .then((d: any) => {
                if (!cancelled) {
                    setMovements((d?.movements ?? []) as MovementRow[]);
                    setMovementMetrics((d?.metrics ?? null) as MovementMetrics | null);
                }
            })
            .finally(() => {
                if (!cancelled) setMovementsLoading(false);
            });
        return () => {
            cancelled = true;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [accountId, apiUrl, mode, fromDate, toDate]);

    const handlePdf = () => {
        const q = rangeParams();
        openAuthorizedPdf(q ? `${pdfBase}?${q}` : pdfBase, `statement_${accountId}.pdf`);
    };

    const receiptCols = [
        {
            title: "Период",
            dataIndex: "period",
            key: "period",
            render: (_: unknown, r: ReceiptRow) => periodLabel(r),
            onHeaderCell: (): any => ({ style: headerAlignStyle() }),
            onCell: (): any => ({ style: cellAlignStyle("period") }),
        },
        {
            title: "К оплате",
            dataIndex: "payable_amount",
            key: "payable_amount",
            render: (v: number) => fmt(v),
            onHeaderCell: (): any => ({ style: headerAlignStyle() }),
            onCell: (): any => ({ style: cellAlignStyle("payable_amount") }),
        },
        {
            title: "Действия",
            key: "actions",
            width: 110,
            align: "center" as const,
            onHeaderCell: (): any => ({ style: headerAlignStyle() }),
            render: (_: unknown, r: ReceiptRow) => (
                <Button
                    size="small"
                    type="primary"
                    onClick={() =>
                        openAuthorizedPdf(
                            `${apiUrl}/receipt_documents/${r.id}/pdf`,
                            `receipt_${r.id}.pdf`,
                        )
                    }
                >
                    <FilePdfOutlined /> PDF
                </Button>
            ),
        },
    ];

    // --- Блок «Общедомовые расходы» (в ЛК жителя и в админ-просмотре): ---
    // всегда за последние 30 дней, без выбора периода.
    const [expData, setExpData] = useState<{ articles: { name: string; expense: number }[]; total: number } | null>(null);
    useEffect(() => {
        if (!houseExpensesEnabled) return;
        let cancelled = false;
        const from = dayjs().subtract(30, "day").format("YYYY-MM-DD");
        const to = dayjs().format("YYYY-MM-DD");
        authedFetch(`${apiUrl}/me/house_expenses?from_date=${from}&to_date=${to}`)
            .then(async (r) => (r.ok ? r.json() : null))
            .then((d: any) => {
                if (!cancelled) setExpData(d ?? null);
            })
            .catch(() => {
                if (!cancelled) setExpData(null);
            });
        return () => { cancelled = true; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [houseExpensesEnabled, apiUrl]);

    return (
        <div>
            {statement && (
                <Card title={`Лицевой счёт ${statement.account.account_number}`} style={{ marginBottom: 16 }}>
                    <Space direction="vertical" style={{ width: "100%" }}>
                        {statement.apartment && (
                            <Typography.Text>
                                {`Квартира № ${statement.apartment.apartment_number} — ${statement.apartment.address}`}
                            </Typography.Text>
                        )}
                        {statement.owner && (
                            <Typography.Text>{`Собственник: ${statement.owner.full_name}, ${formatPhone(statement.owner.phone)}`}</Typography.Text>
                        )}
                    </Space>
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
                            {
                                title: "Услуга",
                                dataIndex: "service_name",
                                key: "service_name",
                                onHeaderCell: (): any => ({ style: headerAlignStyle() }),
                                onCell: (): any => ({ style: cellAlignStyle("service_name") }),
                            },
                            {
                                title: "Долг",
                                dataIndex: "debt",
                                key: "debt",
                                render: (v: number) => fmt(v),
                                onHeaderCell: (): any => ({ style: headerAlignStyle() }),
                                onCell: (): any => ({ style: cellAlignStyle("debt") }),
                            },
                        ]}
                    />
                </Card>
            )}

            {statement && accountId !== undefined && (
                <Card
                    title="Движения по счёту"
                    style={{ marginBottom: 16 }}
                    extra={
                        <Space wrap>
                            <DatePicker.RangePicker
                                allowEmpty={[true, true]}
                                format="DD.MM.YYYY"
                                value={
                                    fromDate || toDate
                                        ? [
                                              fromDate ? dayjs(fromDate) : null,
                                              toDate ? dayjs(toDate) : null,
                                          ]
                                        : undefined
                                }
                                onChange={(dates) => {
                                    setFromDate(dates?.[0]?.format("YYYY-MM-DD"));
                                    setToDate(dates?.[1]?.format("YYYY-MM-DD"));
                                }}
                            />
                            <Button icon={<FilePdfOutlined />} disabled={!accountId} onClick={handlePdf}>
                                Выписка PDF
                            </Button>
                        </Space>
                    }
                >
                    {movementMetrics && (
                        <Row gutter={[8, 8]} style={{ marginBottom: 12 }}>
                            <Col xs={24} md={8}>
                                <Card size="small"><Statistic title="Начислено за период" value={movementMetrics.accrued} precision={2} valueStyle={{ fontSize: 15 }} /></Card>
                            </Col>
                            <Col xs={24} md={8}>
                                <Card size="small"><Statistic title="Оплачено за период" value={movementMetrics.paid} precision={2} valueStyle={{ fontSize: 15 }} /></Card>
                            </Col>
                            <Col xs={24} md={8}>
                                <Card size="small"><Statistic title="Долг на конец периода" value={movementMetrics.debt} precision={2} valueStyle={{ fontSize: 15, color: movementMetrics.debt > 0 ? "#cf1322" : "#3f8600" }} /></Card>
                            </Col>
                        </Row>
                    )}
                    <Table<MovementRow>
                        rowKey={(r, i) => `${r.date ?? ""}-${r.kind}-${i}`}
                        size="small"
                        loading={movementsLoading}
                        dataSource={movements}
                        pagination={{ pageSize: 20, showSizeChanger: true }}
                        scroll={{ x: "max-content", y: 420 }}
                        columns={[
                            {
                                title: "Дата",
                                dataIndex: "date",
                                key: "date",
                                width: 90,
                                render: (v: string | null) => fmtDate(v),
                                onHeaderCell: (): any => ({ style: headerAlignStyle() }),
                                onCell: (): any => ({ style: cellAlignStyle("date") }),
                            },
                            {
                                title: "Вид",
                                dataIndex: "kind_label",
                                key: "kind_label",
                                width: 140,
                                onHeaderCell: (): any => ({ style: headerAlignStyle() }),
                                onCell: (): any => ({ style: cellAlignStyle("kind_label") }),
                            },
                            {
                                title: "Услуга",
                                dataIndex: "service",
                                key: "service",
                                onHeaderCell: (): any => ({ style: headerAlignStyle() }),
                                onCell: (): any => ({ style: cellAlignStyle("service") }),
                            },
                            {
                                title: "Сумма",
                                dataIndex: "amount",
                                key: "amount",
                                width: 110,
                                // Для наглядности жителю знак инвертирован (только отображение):
                                // начисление — «−» (растёт долг), приход/оплата — «+».
                                render: (_v: number, r: MovementRow) => {
                                    const shown = -r.amount;
                                    return (
                                        <Typography.Text
                                            style={{
                                                color:
                                                    shown > 0 ? "#3f8600" : shown < 0 ? "#cf1322" : undefined,
                                            }}
                                        >
                                            {fmtSigned(shown)}
                                        </Typography.Text>
                                    );
                                },
                                onHeaderCell: (): any => ({ style: headerAlignStyle() }),
                                onCell: (): any => ({ style: cellAlignStyle("amount") }),
                            },
                            {
                                title: "Долг",
                                dataIndex: "balance_after",
                                key: "balance_after",
                                width: 110,
                                render: (v: number) => fmt(v),
                                onHeaderCell: (): any => ({ style: headerAlignStyle() }),
                                onCell: (): any => ({ style: cellAlignStyle("balance_after") }),
                            },
                        ]}
                        locale={{ emptyText: "Движений за выбранный период нет" }}
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

            {houseExpensesEnabled && (
                <Card title="Общедомовые расходы" style={{ marginTop: 16 }}>
                    <Table
                        rowKey="name"
                        size="small"
                        pagination={false}
                        dataSource={expData?.articles ?? []}
                        locale={{ emptyText: "Расходов за последние 30 дней нет" }}
                        columns={[
                            {
                                title: "Статья расхода",
                                dataIndex: "name",
                                key: "name",
                                onHeaderCell: (): any => ({ style: headerAlignStyle() }),
                                onCell: (): any => ({ style: cellAlignStyle("name") }),
                            },
                            {
                                title: "Сумма",
                                dataIndex: "expense",
                                key: "expense",
                                render: (v: number) => fmt(v),
                                onHeaderCell: (): any => ({ style: headerAlignStyle() }),
                                onCell: (): any => ({ style: cellAlignStyle("expense") }),
                            },
                        ]}
                        footer={() => (
                            <Typography.Text strong>
                                Итого расходов: {fmt(expData?.total ?? 0)}
                            </Typography.Text>
                        )}
                    />
                </Card>
            )}
        </div>
    );
};

export default CabinetView;
