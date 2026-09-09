// frontend/src/components/cabinet/CabinetView.tsx
// Общий блок «Личный кабинет»: сводка по лицевому счёту, детализация по услугам,
// движения по счёту и список квитанций (просмотр/PDF). Используется:
//   - в ЛК жителя (pages/ResidentCabinet) — данные по своему счёту (mode='me');
//   - в просмотре администратора (pages/AdminCabinet) — по выбранному счёту (mode='account').

import { useEffect, useState } from "react";
import { Button, Card, Col, DatePicker, Row, Select, Space, Statistic, Tooltip, Typography } from "antd";
import { FilePdfOutlined } from "@ant-design/icons";
import dayjs, { type Dayjs } from "dayjs";
import { authedFetch, openAuthorizedPdf } from "../../auth/http";
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

export interface CashMovementRow {
    date: string | null;
    cash_point: string;
    amount: number;
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
    return `${cap}, ${receipt.period_year}`;
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

// Единый стиль крупных денежных сумм в списках ЛК (кегль как в «Общедомовых расходах»).
const SUM_FONT = {
    fontSize: "clamp(22px, 6vw, 30px)",
    fontWeight: 700 as const,
    lineHeight: 1.2,
    whiteSpace: "nowrap",
};

export const CabinetView = ({
    statement,
    receipts,
    apiUrl,
    receiptsTitle = "Квитанции",
    mode = "me",
    houseExpenses,
}: {
    statement: StatementData | null;
    receipts: ReceiptRow[];
    apiUrl: string;
    receiptsTitle?: string;
    /** me — данные «моего» счёта (эндпоинты /me), account — по выбранному счёту. */
    mode?: "me" | "account";
    /** Показывать блок «Расходы по кассе» (в ЛК жителя и в админ-просмотре). */
    houseExpenses?: boolean;
}) => {
    const houseExpensesEnabled = houseExpenses === true;
    const accountId = statement?.account?.id;

    // --- Блок «Деньги»: период + метрики + список Регистра денежных средств + PDF. ---
    const [movements, setMovements] = useState<CashMovementRow[]>([]);
    const [movementMetrics, setMovementMetrics] = useState<MovementMetrics | null>(null);
    const [, setMovementsLoading] = useState(false);
    // --- Общий период страницы: стандартные пресеты или «За период» (свои даты). ---
    type PeriodPreset = "3m" | "prev_month" | "cur_month" | "custom";
    const [periodPreset, setPeriodPreset] = useState<PeriodPreset>("3m");
    // Период по умолчанию — текущий и два предыдущих месяца («За 3 месяца»).
    const [fromDate, setFromDate] = useState<string | undefined>(
        dayjs().startOf("month").subtract(2, "month").format("YYYY-MM-DD"),
    );
    const [toDate, setToDate] = useState<string | undefined>(
        dayjs().endOf("month").format("YYYY-MM-DD"),
    );
    const applyPeriodPreset = (p: PeriodPreset) => {
        setPeriodPreset(p);
        if (p === "custom") return; // даты выбираются вручную ниже
        const now = dayjs();
        let from: Dayjs;
        let to: Dayjs;
        switch (p) {
            case "cur_month":
                from = now.startOf("month");
                to = now.endOf("month");
                break;
            case "prev_month":
                from = now.startOf("month").subtract(1, "month");
                to = now.endOf("month").subtract(1, "month");
                break;
            default: // "3m"
                from = now.startOf("month").subtract(2, "month");
                to = now.endOf("month");
        }
        setFromDate(from.format("YYYY-MM-DD"));
        setToDate(to.format("YYYY-MM-DD"));
    };

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
                if (!r.ok) return { cash_movements: [] as CashMovementRow[] };
                return r.json();
            })
            .then((d: any) => {
                if (!cancelled) {
                    setMovements((d?.cash_movements ?? []) as CashMovementRow[]);
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

    // --- Блок «Общедомовые расходы» (в ЛК жителя и в админ-просмотре): ---
    // всегда за последние 30 дней, без выбора периода.
    const [expData, setExpData] = useState<{ articles: { name: string; expense: number }[]; total: number } | null>(null);
    useEffect(() => {
        if (!houseExpensesEnabled) return;
        let cancelled = false;
        // «Общедомовые расходы» показываются за общий выбранный период страницы.
        const p = new URLSearchParams();
        if (fromDate) p.set("from_date", fromDate);
        if (toDate) p.set("to_date", toDate);
        const q = p.toString();
        authedFetch(q ? `${apiUrl}/me/house_expenses?${q}` : `${apiUrl}/me/house_expenses`)
            .then(async (r) => (r.ok ? r.json() : null))
            .then((d: any) => {
                if (!cancelled) setExpData(d ?? null);
            })
            .catch(() => {
                if (!cancelled) setExpData(null);
            });
        return () => { cancelled = true; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [houseExpensesEnabled, apiUrl, fromDate, toDate]);

    // --- Квитанции/списки: видимый период = общий выбранный период (fromDate/toDate). ---
    const visibleReceipts = receipts.filter((r) => {
        const start = dayjs(new Date(r.period_year, r.period_month - 1, 1)).startOf("month");
        const end = start.endOf("month");
        if (fromDate && end < dayjs(fromDate).startOf("day")) return false;
        if (toDate && start > dayjs(toDate).endOf("day")) return false;
        return true;
    });

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

            {statement && accountId !== undefined && (
                <Card size="small" style={{ marginBottom: 16 }}>
                    <Space wrap>
                        <Typography.Text strong style={{ fontSize: 17 }}>Период:</Typography.Text>
                        <Select
                            value={periodPreset}
                            onChange={applyPeriodPreset}
                            style={{ width: 200 }}
                            options={[
                                { value: "3m", label: "За 3 месяца" },
                                { value: "prev_month", label: "За прошлый месяц" },
                                { value: "cur_month", label: "За текущий месяц" },
                                { value: "custom", label: "За период" },
                            ]}
                        />
                        {periodPreset === "custom" && (
                            <>
                                <DatePicker
                                    format="DD.MM.YYYY"
                                    placeholder="Дата начала"
                                    allowClear
                                    value={fromDate ? dayjs(fromDate) : null}
                                    onChange={(d) => setFromDate(d ? d.format("YYYY-MM-DD") : undefined)}
                                />
                                <DatePicker
                                    format="DD.MM.YYYY"
                                    placeholder="Дата конца"
                                    allowClear
                                    value={toDate ? dayjs(toDate) : null}
                                    onChange={(d) => setToDate(d ? d.format("YYYY-MM-DD") : undefined)}
                                />
                            </>
                        )}
                    </Space>
                </Card>
            )}

            {statement && statement.services && statement.services.length > 0 && (
                <Card title="Услуги" style={{ marginBottom: 16 }}>
                    {movementMetrics && (
                        <Row gutter={[8, 8]} style={{ marginBottom: 12 }}>
                            <Col xs={24} md={8}>
                                <Card size="small"><Statistic title="Начислено за период" value={movementMetrics.accrued} precision={2} valueStyle={{ fontSize: 19 }} /></Card>
                            </Col>
                            <Col xs={24} md={8}>
                                <Card size="small"><Statistic title="Оплачено за период" value={movementMetrics.paid} precision={2} valueStyle={{ fontSize: 19 }} /></Card>
                            </Col>
                            <Col xs={24} md={8}>
                                <Card size="small"><Statistic title="Долг на конец периода" value={movementMetrics.debt} precision={2} valueStyle={{ fontSize: 19, color: movementMetrics.debt > 0 ? "#cf1322" : "#3f8600" }} /></Card>
                            </Col>
                        </Row>
                    )}
                    {statement.services.map((s, i) => (
                        <div
                            key={s.services_type_id}
                            style={{
                                padding: "12px 0",
                                borderBottom:
                                    i < statement.services.length - 1 ? "1px solid #e8e8e8" : "none",
                            }}
                        >
                            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <Typography.Text style={{ fontSize: 18, fontWeight: 600 }}>
                                        {s.service_name}
                                    </Typography.Text>
                                    <div
                                        style={{
                                            ...SUM_FONT,
                                            color: s.debt > 0 ? "#cf1322" : "#1f1f1f",
                                        }}
                                    >
                                        {fmt(s.debt)}
                                    </div>
                                </div>
                            </div>
                        </div>
                    ))}
                </Card>
            )}

            {statement && accountId !== undefined && (
                <Card title="Деньги" style={{ marginBottom: 16 }}>
                    {movements.length === 0 ? (
                        <Typography.Text type="secondary">
                            Денежных операций за выбранный период нет
                        </Typography.Text>
                    ) : (
                        movements.map((mv, i) => (
                            <div
                                key={`${mv.date ?? ""}-${i}`}
                                style={{
                                    padding: "12px 0",
                                    borderBottom:
                                        i < movements.length - 1 ? "1px solid #e8e8e8" : "none",
                                }}
                            >
                                <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <Typography.Text strong style={{ fontSize: 18 }}>
                                            {fmtDate(mv.date)}
                                        </Typography.Text>
                                        <div
                                            style={{
                                                ...SUM_FONT,
                                                color:
                                                    mv.amount > 0
                                                        ? "#3f8600"
                                                        : mv.amount < 0
                                                          ? "#cf1322"
                                                          : "#1f1f1f",
                                            }}
                                        >
                                            {fmtSigned(mv.amount)}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ))
                    )}
                    <div style={{ textAlign: "center", marginTop: 12 }}>
                        <Tooltip title="PDF">
                            <Button
                                type="primary"
                                aria-label="PDF"
                                icon={<FilePdfOutlined style={{ fontSize: 24 }} />}
                                disabled={!accountId}
                                onClick={handlePdf}
                                style={{
                                    width: 53,
                                    height: 53,
                                    display: "inline-flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                }}
                            />
                        </Tooltip>
                    </div>
                </Card>
            )}

            <Card title={receiptsTitle} style={{ marginBottom: 16 }}>
                {visibleReceipts.length === 0 ? (
                    <Typography.Text type="secondary">Квитанций за выбранный период нет</Typography.Text>
                ) : (
                    visibleReceipts.map((r, idx) => (
                        <div
                            key={r.id}
                            style={{
                                padding: "14px 0",
                                borderBottom:
                                    idx < visibleReceipts.length - 1 ? "1px solid #e8e8e8" : "none",
                            }}
                        >
                            <div
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 16,
                                }}
                            >
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <Typography.Text strong style={{ fontSize: 18 }}>
                                        {periodLabel(r)}
                                    </Typography.Text>
                                    <div
                                        style={{
                                            marginTop: 4,
                                            ...SUM_FONT,
                                            color: "#1f1f1f",
                                        }}
                                    >
                                        {fmt(r.payable_amount)}
                                    </div>
                                </div>
                                <Tooltip title="PDF">
                                    <Button
                                        type="primary"
                                        aria-label="PDF"
                                        icon={<FilePdfOutlined style={{ fontSize: 24 }} />}
                                        onClick={() =>
                                            openAuthorizedPdf(
                                                `${apiUrl}/receipt_documents/${r.id}/pdf`,
                                                `receipt_${r.id}.pdf`,
                                            )
                                        }
                                        style={{
                                            width: 53,
                                            height: 53,
                                            display: "inline-flex",
                                            alignItems: "center",
                                            justifyContent: "center",
                                            flexShrink: 0,
                                        }}
                                    />
                                </Tooltip>
                            </div>
                        </div>
                    ))
                )}
            </Card>

            {houseExpensesEnabled && (
                <Card title="Общедомовые расходы" style={{ marginTop: 16 }}>
                    {!expData || expData.articles.length === 0 ? (
                        <Typography.Text type="secondary">Расходов за выбранный период нет</Typography.Text>
                    ) : (
                        <>
                            {expData.articles.map((a, idx) => (
                                <div
                                    key={a.name}
                                    style={{
                                        padding: "12px 0",
                                        borderBottom:
                                            idx < expData.articles.length - 1
                                                ? "1px solid #e8e8e8"
                                                : "none",
                                    }}
                                >
                                    <div
                                        style={{
                                            display: "flex",
                                            alignItems: "baseline",
                                            justifyContent: "space-between",
                                            gap: 16,
                                        }}
                                    >
                                        <Typography.Text style={{ fontSize: 17 }}>
                                            {a.name}
                                        </Typography.Text>
                                        <Typography.Text
                                            style={{ ...SUM_FONT, textAlign: "right" }}
                                        >
                                            {fmt(a.expense)}
                                        </Typography.Text>
                                    </div>
                                </div>
                            ))}
                            <div
                                style={{
                                    padding: "16px 0",
                                    marginTop: 8,
                                    borderTop: "1px solid #e8e8e8",
                                    borderBottom: "1px solid #e8e8e8",
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "space-between",
                                    gap: 16,
                                }}
                            >
                                <Typography.Text strong style={{ fontSize: 18 }}>
                                    Итого расходов
                                </Typography.Text>
                                <Typography.Text strong style={{ ...SUM_FONT, textAlign: "right" }}>
                                    {fmt(expData.total)}
                                </Typography.Text>
                            </div>
                        </>
                    )}
                </Card>
            )}
        </div>
    );
};

export default CabinetView;
