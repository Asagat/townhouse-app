// ReceiptViewModal.tsx
// Просмотр квитанции в модальном окне, вёрстка максимально повторяет PDF.
// На узких экранах (телефон) широкая «PDF-подобная» таблица не помещается,
// поэтому там выводится компактная сводка + кнопка «PDF» (скачивание документа).

import { useEffect, useState } from "react";
import { Modal, Button, Spin, Table, Input, message, Grid } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useApiUrl } from "@refinedev/core";
import { authedFetch, openAuthorizedPdf } from "../../auth/http";

interface ReceiptItemData {
    id: number;
    service_name: string;
    reading_prev: number | null;
    reading_curr: number | null;
    quantity: number | null;
    tariff: number | null;
    amount: number;
    debt: number;
    overpayment: number;
    payable: number;
}

interface ReceiptDocumentData {
    id: number;
    period_month: number;
    period_year: number;
    apartment_number: number | null;
    owner_name: string;
    total_amount: number;
    debt: number;
    overpayment: number;
    payable_amount: number;
    issued_at: string | null;
    comment?: string | null;
}

interface ReceiptViewModalProps {
    open: boolean;
    receiptId: number | undefined;
    onClose: () => void;
    editable?: boolean;
}

const MONTH_NAMES = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
];

// Русское форматирование чисел как в PDF: «1 525,00», «-12,34»
const fmtAmount2 = (value: number | null | undefined): string => {
    const v = Number(value ?? 0);
    let num = v;
    let prefix = "";
    if (!Number.isFinite(num)) return "0,00";
    if (num < 0) {
        prefix = "-";
        num = Math.abs(num);
    }
    const rounded = num.toFixed(2);
    const [intPart, frac] = rounded.split(".");
    const withSpaces = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    return `${prefix}${withSpaces},${frac}`;
};

const fmtReading = (value: number | null | undefined): string => {
    if (value === null || value === undefined) return "-";
    return String(value);
};

// «Май 2026»
const formatPeriod = (month: number, year: number): string => {
    const name = MONTH_NAMES[month - 1] ?? "";
    const cap = name ? name.charAt(0).toUpperCase() + name.slice(1) : String(month);
    return `${cap} ${year}`;
};

// «14.06.2026 12:30:00» из ISO
const formatIssued = (iso: string | null): string => {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const p = (n: number) => String(n).padStart(2, "0");
    return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(
        d.getHours(),
    )}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
};

interface TableRow {
    key: string;
    service: string;
    prev: string;
    curr: string;
    quantity: string;
    tariff: string;
    amount: string;
    debt: string;
    overpayment: string;
    payable: string;
    isTotal?: boolean;
}

const GRID = "#b8b8b8";
const TITLE_TEXT = "#666666";
const PERIOD_TEXT = "#666666";
const HEAD_TEXT = "#666666";
const BRAND_TEXT = "#7ed98b";
const STAMP_TEXT = "#666666";

export const ReceiptViewModal = ({
    open,
    receiptId,
    onClose,
    editable = false,
}: ReceiptViewModalProps) => {
    const apiUrl = useApiUrl();
    const screens = Grid.useBreakpoint();
    // Телефон/узкий вьюпорт: показываем компактную сводку + PDF, без широкой таблицы.
    const mobile = screens.md === false;

    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [doc, setDoc] = useState<ReceiptDocumentData | null>(null);
    const [items, setItems] = useState<ReceiptItemData[]>([]);
    const [commentDraft, setCommentDraft] = useState("");
    const [savingComment, setSavingComment] = useState(false);

    useEffect(() => {
        if (!open || receiptId === undefined) return;
        let cancelled = false;
        setLoading(true);
        setError(null);
        setDoc(null);
        setItems([]);
        authedFetch(`${apiUrl}/receipt_documents/${receiptId}/items`)
            .then(async (resp) => {
                if (!resp.ok) {
                    let detail = "Не удалось загрузить квитанцию";
                    try {
                        const err = await resp.json();
                        detail = err?.detail ?? detail;
                    } catch {
                        // ignore
                    }
                    throw new Error(detail);
                }
                return resp.json();
            })
            .then((data) => {
                if (cancelled) return;
                setDoc(data?.document ?? null);
                setItems((data?.items ?? []).slice().sort((a: ReceiptItemData, b: ReceiptItemData) => a.id - b.id));
            })
            .catch((err: any) => {
                if (!cancelled) setError(err?.message ?? "Не удалось загрузить квитанцию");
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [open, receiptId, apiUrl]);

    useEffect(() => {
        setCommentDraft(doc?.comment ?? "");
    }, [doc]);

    const rows: TableRow[] = items.map((it): TableRow => ({
        key: `r${it.id}`,
        service: it.service_name,
        prev: fmtReading(it.reading_prev),
        curr: fmtReading(it.reading_curr),
        quantity: it.quantity === null || it.quantity === undefined ? "-" : fmtAmount2(it.quantity),
        tariff: it.tariff === null || it.tariff === undefined ? "-" : fmtAmount2(it.tariff),
        amount: fmtAmount2(it.amount),
        debt: it.debt ? fmtAmount2(it.debt) : "0,00",
        overpayment: it.overpayment ? fmtAmount2(it.overpayment) : "0,00",
        payable: fmtAmount2(it.payable),
    }));

    if (doc) {
        rows.push({
            key: "total",
            isTotal: true,
            service: "Итого",
            prev: "",
            curr: "",
            quantity: "",
            tariff: "",
            amount: fmtAmount2(doc.total_amount),
            debt: doc.debt ? fmtAmount2(doc.debt) : "0,00",
            overpayment: doc.overpayment ? fmtAmount2(doc.overpayment) : "0,00",
            payable: fmtAmount2(doc.payable_amount),
        });
    }

    const entityCols: ColumnsType<TableRow> = [
        {
            title: "Услуга",
            dataIndex: "service",
            key: "service",
            width: 120,
            render: (_: unknown, r: TableRow) => (
                <span style={{ fontWeight: r.isTotal ? 700 : 400 }}>{r.service}</span>
            ),
        },
        {
            title: "Показания",
            key: "readings",
            align: "center",
            children: [
                { title: "Пред.", dataIndex: "prev", key: "prev", width: 62, align: "right" },
                { title: "Текущ.", dataIndex: "curr", key: "curr", width: 62, align: "right" },
            ],
        },
        { title: "Кол-во", dataIndex: "quantity", key: "quantity", width: 76, align: "right" },
        { title: "Тариф", dataIndex: "tariff", key: "tariff", width: 80, align: "right" },
        { title: "Сумма", dataIndex: "amount", key: "amount", width: 96, align: "right" },
        { title: "Долг", dataIndex: "debt", key: "debt", width: 96, align: "right" },
        { title: "Переплата", dataIndex: "overpayment", key: "overpayment", width: 100, align: "right" },
        { title: "К оплате", dataIndex: "payable", key: "payable", width: 96, align: "right" },
    ];

    const rowClassName = (r: TableRow): string => {
        if (r.isTotal) return "receipt-row-total";
        const n = Number(r.key.replace(/^r/, ""));
        return Number.isFinite(n) && n % 2 === 0 ? "receipt-row-odd" : "";
    };

    const saveComment = async () => {
        if (receiptId === undefined) return;
        setSavingComment(true);
        try {
            const resp = await authedFetch(`${apiUrl}/receipt_documents/${receiptId}/comment`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ comment: commentDraft }),
            });
            if (!resp.ok) {
                let detail = "Не удалось сохранить примечание";
                try {
                    const err = await resp.json();
                    detail = err?.detail ?? detail;
                } catch {
                    // ignore
                }
                throw new Error(detail);
            }
            const updated = await resp.json();
            setDoc((prev: ReceiptDocumentData | null) =>
                prev ? { ...prev, comment: updated?.comment ?? commentDraft } : prev,
            );
            message.success("Примечание сохранено");
        } catch (err: any) {
            message.error(err?.message ?? "Не удалось сохранить примечание");
        } finally {
            setSavingComment(false);
        }
    };


    return (
        <Modal
            title={`Квитанция № ${doc?.id ?? (receiptId ?? "")}`}
            open={open}
            onCancel={onClose}
            centered
            width={mobile ? "min(480px, calc(100vw - 24px))" : "min(1200px, calc(100vw - 24px))"}
            destroyOnClose
            bodyStyle={{ maxHeight: "calc(100vh - 120px)", overflowY: "auto" }}
            footer={[
                <Button key="close" onClick={onClose}>
                    Закрыть
                </Button>,
                <Button
                    key="pdf"
                    size={mobile ? "large" : undefined}
                    block={mobile}
                    type="primary"
                    disabled={receiptId === undefined}
                    onClick={() =>
                        openAuthorizedPdf(
                            `${apiUrl}/receipt_documents/${receiptId}/pdf`,
                            `receipt_${receiptId}.pdf`,
                        )
                    }
                >
                    PDF
                </Button>,
            ]}
        >
            {loading && (
                <div style={{ textAlign: "center", padding: 48 }}>
                    <Spin />
                </div>
            )}
            {error && !loading && (
                <div style={{ textAlign: "center", padding: 24, color: "#cf1322" }}>{error}</div>
            )}

            {doc && !loading && !error && !mobile && (
                <div
                    style={{
                        background: "#fafafa",
                        padding: "clamp(8px, 2vw, 24px)",
                        borderRadius: 8,
                        display: "flex",
                        justifyContent: "center",
                    }}
                >
                    <div
                        style={{
                            background: "#ffffff",
                            width: "100%",
                            maxWidth: "100%",
                            padding: "34px 30px",
                            borderRadius: 4,
                            boxShadow: "0 2px 12px rgba(0,0,0,0.15)",
                            fontSize: 12,
                        }}
                        className="receipt-preview"
                    >
                        {/* Шапка */}
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                            <div style={{ fontSize: 14, fontWeight: 700, color: TITLE_TEXT }}>Квитанция</div>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <img src="/FTH.png" alt="Логотип" style={{ height: 26, objectFit: "contain", display: "block" }} />
                                <span style={{ fontSize: 14, fontWeight: 700, color: BRAND_TEXT }}>Family Townhouse</span>
                            </div>
                        </div>

                        <div style={{ fontWeight: 700, color: PERIOD_TEXT, marginBottom: 6 }}>
                            {formatPeriod(doc.period_month, doc.period_year)}
                        </div>
                        <div style={{ fontWeight: 700, color: HEAD_TEXT, marginBottom: 14 }}>
                            Квартира № {doc.apartment_number ?? "—"} {doc.owner_name ?? ""}
                        </div>

                        <Table<TableRow>
                            rowKey="key"
                            size="small"
                            pagination={false}
                            columns={entityCols}
                            dataSource={rows}
                            rowClassName={rowClassName}
                            bordered
                            scroll={{ x: 1000 }}
                            components={{
                                header: {
                                    cell: (props: any) => (
                                        <th
                                            {...props}
                                            style={{ ...props?.style, borderColor: GRID, textAlign: "center" }}
                                            className={`${props?.className ?? ""} ${
                                                props?.colSpan ? "receipt-head-group" : ""
                                            }`}
                                        />
                                    ),
                                },
                                body: {
                                    cell: (props: any) => (
                                        <td {...props} style={{ ...props?.style, borderColor: GRID }} />
                                    ),
                                },
                            }}
                        />

                        <div style={{ textAlign: "right", fontSize: 9, color: STAMP_TEXT, marginTop: 18 }}>
                            {formatIssued(doc.issued_at)}
                        </div>

                        {/* Примечание */}
                        <div style={{ marginTop: 22 }}>
                            <div style={{ fontWeight: 700, color: HEAD_TEXT, marginBottom: 6 }}>Примечание</div>
                            <div style={{ display: "flex", gap: 8 }}>
                                <Input.TextArea
                                    rows={2}
                                    maxLength={500}
                                    value={commentDraft}
                                    readOnly={!editable}
                                    onChange={(e) => setCommentDraft(e.target.value)}
                                    placeholder="Дополнительная пометка по квитанции (не влияет на суммы)"
                                    style={{ fontSize: 12 }}
                                />
                                {editable && (
                                    <Button size="small" type="primary" loading={savingComment} onClick={saveComment} style={{ alignSelf: "flex-end" }}>
                                        Сохранить
                                    </Button>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {doc && !loading && !error && mobile && (
                <div className="receipt-mobile-summary">
                    <div style={{ borderBottom: "1px solid #eaeaea", paddingBottom: 8, marginBottom: 10 }}>
                        <div style={{ fontWeight: 700, color: "#14501d" }}>
                            {formatPeriod(doc.period_month, doc.period_year)}
                        </div>
                        <div style={{ fontSize: 12, color: "#667" }}>
                            Квартира № {doc.apartment_number ?? "—"} · {doc.owner_name ?? "—"}
                        </div>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0" }}>
                        <span style={{ color: "#444" }}>Начислено</span>
                        <span style={{ fontWeight: 700, color: "#111" }}>{fmtAmount2(doc.total_amount)}</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0" }}>
                        <span style={{ color: "#444" }}>Долг</span>
                        <span style={{ fontWeight: 700, color: "#111" }}>{fmtAmount2(doc.debt)}</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0" }}>
                        <span style={{ color: "#444" }}>Переплата</span>
                        <span style={{ fontWeight: 700, color: "#111" }}>{fmtAmount2(doc.overpayment)}</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", borderTop: "1px solid #eaeaea", marginTop: 4 }}>
                        <span style={{ color: "#444", fontWeight: 700 }}>К оплате</span>
                        <span style={{ fontWeight: 700, color: "#22ae2e" }}>{fmtAmount2(doc.payable_amount)}</span>
                    </div>
                    <div style={{ fontSize: 11, color: "#889", marginTop: 8 }}>
                        Сформирована: {formatIssued(doc.issued_at) || "—"}
                    </div>
                    {rows.length > 0 && (
                        <div style={{ marginTop: 12, fontSize: 12, color: "#666" }}>
                            Услуг в квитанции: {rows.length}. Полная детализация — в PDF.
                        </div>
                    )}
                    <div style={{ marginTop: 10 }}>
                        <div style={{ fontWeight: 700, color: "#333", marginBottom: 4 }}>Примечание</div>
                        {editable ? (
                            <Input.TextArea
                                rows={2}
                                maxLength={500}
                                value={commentDraft}
                                onChange={(e) => setCommentDraft(e.target.value)}
                                placeholder="Пометка по квитанции"
                            />
                        ) : (
                            <div style={{ minHeight: 40, whiteSpace: "pre-wrap" }}>{commentDraft || "—"}</div>
                        )}
                        {editable && (
                            <Button size="small" type="primary" loading={savingComment} onClick={saveComment} style={{ marginTop: 6 }}>
                                Сохранить
                            </Button>
                        )}
                    </div>
                </div>
            )}
        </Modal>
    );
};

export default ReceiptViewModal;
