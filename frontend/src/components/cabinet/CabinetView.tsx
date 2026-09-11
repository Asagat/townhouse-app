// frontend/src/components/cabinet/CabinetView.tsx
// Общий блок «Личный кабинет»: сводка по лицевому счёту, детализация по услугам,
// движения по счёту и список квитанций (просмотр/PDF). Используется:
//   - в ЛК жителя (pages/ResidentCabinet) — данные по своему счёту (mode='me');
//   - в просмотре администратора (pages/AdminCabinet) — по выбранному счёту (mode='account').

import { useEffect, useState } from "react";
import { Button, Card, Col, ConfigProvider, DatePicker, Row, Select, Space, Statistic, Tooltip, Typography } from "antd";
import { FilePdfOutlined } from "@ant-design/icons";
import dayjs, { type Dayjs } from "dayjs";
import { authedFetch, openAuthorizedPdf } from "../../auth/http";
import { formatDate, formatMoney, formatPeriod, formatPhone } from "../../config/formatters";

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

interface AccountMovementRow {
    date: string | null;
    kind: "accrual" | "payment" | "writeoff" | string;
    kind_label: string;
    service: string;
    /** Статья доходов/расходов документа «Приход/Расход» (у начислений — null). */
    article: string | null;
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

// --- Строка движения в ЛК: что показывается крупно, а что мелко ---
// Крупно — название движения: у денежных документов («Приход/Расход») это статья
// доходов/расходов («Поступления от жителей»), остальное — вид услуги («Фонд
// развития»); у начисления/списания статьи нет, поэтому там остаётся услуга.
const movementTitle = (mv: AccountMovementRow): string => mv.article ?? mv.service;

// Мелко — вид/название документа: у денежных движений это вид денежного документа
// («Приход в кассу №10», «Списание задолженностей №…»), у начисления заголовка
// документа нет — там остаётся подпись «Начисление». Если документа в данных нет
// (исторические строки) — откат к подписи вида движения.
const movementSubtitle = (mv: AccountMovementRow): string =>
    mv.document ?? mv.kind_label;

// Знаки — «глазами жителя»: начисление увеличивает долг (минус), оплата/списание
// долг гасят (плюс). API и PDF выписки при этом остаются «по счёту» (начисление
// «+», оплата/списание «−»), поэтому инвертируем знак только при отображении.
const residentAmount = (mv: AccountMovementRow): number => -Number(mv.amount ?? 0);

// Цвет суммы по знаку для жителя: минус (долг вырос) — красный, плюс — зелёный.
const amountColor = (v: number): string =>
    v > 0 ? "#3f8600" : v < 0 ? "#cf1322" : "#1f1f1f";

// Денежная сумма со знаком «+/−» для движений по счёту; формат чисел — общий
// `formatMoney` (2 знака, запятая, без знака валюты). Ноль — без знака.
const fmtSigned = (v: number): string => {
    const num = Number(v ?? 0);
    if (!Number.isFinite(num) || num === 0) return formatMoney(0);
    return (num > 0 ? "+" : "−") + formatMoney(Math.abs(num));
};

// Единый стиль денежных сумм в списках ЛК: заметный, но уже не «баннер» —
// кегль адаптивный (от 17px на узком экране до 22px на широком), среднее начертание.
const SUM_FONT = {
    fontSize: "clamp(17px, 4vw, 22px)",
    fontWeight: 600 as const,
    lineHeight: 1.25,
    whiteSpace: "nowrap",
};

// Единый стиль подписей-строк внутри блоков ЛК. Эталон — отчёт «Общедомовые
// расходы»: обычный вес (без «полужирного» акцента), кегль 17px, слева.
const ROW_LABEL = {
    fontSize: 17,
    fontWeight: 400 as const,
};

// Стиль строки-итога: та же подпись, но подчёркнута как сумма.
const ROW_TOTAL_LABEL = {
    fontSize: 17,
    fontWeight: 600 as const,
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

    // --- Блок «Движения»: период + метрики + движения по счёту + PDF. ---
    const [movements, setMovements] = useState<AccountMovementRow[]>([]);
    const [cashMovements, setCashMovements] = useState<CashMovementRow[]>([]);
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
            setCashMovements([]);
            setMovementMetrics(null);
            return;
        }
        let cancelled = false;
        setMovementsLoading(true);
        const q = rangeParams();
        authedFetch(q ? `${movementBase}?${q}` : movementBase)
            .then(async (r) => {
                if (!r.ok) return { movements: [], cash_movements: [] };
                return r.json();
            })
            .then((d: any) => {
                if (!cancelled) {
                    setMovements((d?.movements ?? []) as AccountMovementRow[]);
                    setCashMovements((d?.cash_movements ?? []) as CashMovementRow[]);
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
        // Единый вид ЛК и в кабинете жителя, и в админ-просмотре: крупный шрифт
        // задаётся здесь (а не в странице), чтобы оба режима выглядели одинаково.
        <ConfigProvider theme={{ token: { fontSize: 17 } }}>
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
                                <Card size="small"><Statistic title="Начислено за период" value={movementMetrics.accrued} formatter={formatMoney} valueStyle={{ fontSize: 19 }} /></Card>
                            </Col>
                            <Col xs={24} md={8}>
                                <Card size="small"><Statistic title="Оплачено за период" value={movementMetrics.paid} formatter={formatMoney} valueStyle={{ fontSize: 19 }} /></Card>
                            </Col>
                            <Col xs={24} md={8}>
                                <Card size="small"><Statistic title="Долг на конец периода" value={movementMetrics.debt} formatter={formatMoney} valueStyle={{ fontSize: 19, color: movementMetrics.debt > 0 ? "#cf1322" : "#3f8600" }} /></Card>
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
                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
                                <Typography.Text style={{ ...ROW_LABEL, minWidth: 0 }}>
                                    {s.service_name}
                                </Typography.Text>
                                <div
                                    style={{
                                        ...SUM_FONT,
                                        textAlign: "right",
                                        color: s.debt > 0 ? "#cf1322" : "#1f1f1f",
                                    }}
                                >
                                    {formatMoney(s.debt)}
                                </div>
                            </div>
                        </div>
                    ))}
                </Card>
            )}

            {statement && accountId !== undefined && (
                <Card title="Движения" style={{ marginBottom: 16 }}>
                    {movements.length === 0 ? (
                        <Typography.Text type="secondary">
                            Движений за выбранный период нет
                        </Typography.Text>
                    ) : (
                        movements.map((mv, i) => {
                            const amount = residentAmount(mv);
                            return (
                                <div
                                    key={`${mv.date ?? ""}-${i}`}
                                    style={{
                                        padding: "12px 0",
                                        borderBottom:
                                            i < movements.length - 1 ? "1px solid #e8e8e8" : "none",
                                    }}
                                >
                                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
                                        <div style={{ minWidth: 0 }}>
                                            <Typography.Text style={{ ...ROW_LABEL, display: "block" }}>
                                                {formatDate(mv.date)} — {movementTitle(mv)}
                                            </Typography.Text>
                                            <Typography.Text type="secondary" style={{ fontSize: 15 }}>
                                                {movementSubtitle(mv)}
                                            </Typography.Text>
                                        </div>
                                        <div
                                            style={{
                                                ...SUM_FONT,
                                                textAlign: "right",
                                                color: amountColor(amount),
                                            }}
                                        >
                                            {fmtSigned(amount)}
                                        </div>
                                    </div>
                                </div>
                            );
                        })
                    )}
                    <div
                        style={{
                            padding: "14px 0 0",
                            marginTop: 8,
                            borderTop: "1px solid #e8e8e8",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: 16,
                        }}
                    >
                        <Typography.Text style={ROW_TOTAL_LABEL}>
                            Внесено в кассу за период
                        </Typography.Text>
                        <Typography.Text style={{ ...SUM_FONT, textAlign: "right" }}>
                            {formatMoney(
                                cashMovements.reduce((sum, c) => sum + (c.amount || 0), 0),
                            )}
                        </Typography.Text>
                    </div>
                    {cashMovements.length > 0 && (
                        <div style={{ marginTop: 8 }}>
                            {cashMovements.map((c, i) => (
                                <div
                                    key={`${c.date ?? ""}-${i}`}
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        justifyContent: "space-between",
                                        gap: 16,
                                        padding: "6px 0",
                                    }}
                                >
                                    <Typography.Text type="secondary" style={{ fontSize: 15 }}>
                                        {formatDate(c.date)} — {c.cash_point}
                                    </Typography.Text>
                                    <Typography.Text type="secondary" style={{ fontSize: 15, textAlign: "right" }}>
                                        {formatMoney(c.amount)}
                                    </Typography.Text>
                                </div>
                            ))}
                        </div>
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
                                    <Typography.Text style={ROW_LABEL}>
                                        {formatPeriod(`${r.period_year}-${String(r.period_month).padStart(2, "0")}`)}
                                    </Typography.Text>
                                </div>
                                <div
                                    style={{
                                        ...SUM_FONT,
                                        textAlign: "right",
                                        color: "#1f1f1f",
                                    }}
                                >
                                    {formatMoney(r.payable_amount)}
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
                                        <Typography.Text style={ROW_LABEL}>
                                            {a.name}
                                        </Typography.Text>
                                        <Typography.Text
                                            style={{ ...SUM_FONT, textAlign: "right" }}
                                        >
                                            {formatMoney(a.expense)}
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
                                <Typography.Text style={ROW_TOTAL_LABEL}>
                                    Итого расходов
                                </Typography.Text>
                                <Typography.Text style={{ ...SUM_FONT, fontWeight: 600, textAlign: "right" }}>
                                    {formatMoney(expData.total)}
                                </Typography.Text>
                            </div>
                        </>
                    )}
                </Card>
            )}
            </div>
        </ConfigProvider>
    );
};

export default CabinetView;
