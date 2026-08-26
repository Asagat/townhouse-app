// ReceiptViewModal.tsx
// Просмотр квитанции в модальном окне, вёрстка максимально повторяет PDF.

import { useEffect, useState } from "react";
import { Modal, Button, Spin, Table } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useApiUrl } from "@refinedev/core";
import { authedFetch } from "../../auth/http";

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
}

interface ReceiptViewModalProps {
    open: boolean;
    receiptId: number | undefined;
    onClose: () => void;
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

// Формат показаний как в PDF: целые без десятичных, остальные как есть
const fmtReading = (value: number | null | undefined): string => {
    if (value === null || value === undefined) return "-";
    const str = String(value);
    return /^-?\d+$/.test(str) ? str : str;
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
    leftColSpan?: number;
    isTotal?: boolean;
    bold?: boolean;
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
}: ReceiptViewModalProps) => {
    const apiUrl = useApiUrl();
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [doc, setDoc] = useState<ReceiptDocumentData | null>(null);
    const [items, setItems] = useState<ReceiptItemData[]>([]);

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

    const rows: TableRow[] = [];
    const dataRows = items.map((it, idx): TableRow => ({
        key: `r${it.id}`,
        service: it.service_name,
        prev: fmtReading(it.reading_prev),
        curr: fmtReading(it.reading_curr),
        quantity:
            it.quantity === null || it.quantity === undefined
                ? "-"
                : fmtAmount2(it.quantity),
        tariff: it.tariff === null || it.tariff === undefined ? "-" : fmtAmount2(it.tariff),
        amount: fmtAmount2(it.amount),
        debt: it.debt ? fmtAmount2(it.debt) : "0,00",
        overpayment: it.overpayment ? fmtAmount2(it.overpayment) : "0,00",
        payable: fmtAmount2(it.payable),
        bold: idx % 2 === 1,
    }));
    rows.push(...dataRows);

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
                <span style={{ fontWeight: r.isTotal ? 700 : 400 }}>
                    {r.service}
                </span>
            ),
        },
        {
            title: "Показания",
            key: "readings",
            align: "center",
            children: [
                {
                    title: "Пред.",
                    dataIndex: "prev",
                    key: "prev",
                    width: 62,
                    align: "right",
                },
                {
                    title: "Текущ.",
                    dataIndex: "curr",
                    key: "curr",
                    width: 62,
                    align: "right",
                },
            ],
        },
        { title: "Кол-во", dataIndex: "quantity", key: "quantity", width: 70, align: "right" },
        { title: "Тариф", dataIndex: "tariff", key: "tariff", width: 70, align: "right" },
        { title: "Сумма", dataIndex: "amount", key: "amount", width: 96, align: "right" },
        { title: "Долг", dataIndex: "debt", key: "debt", width: 70, align: "right" },
        { title: "Переплата", dataIndex: "overpayment", key: "overpayment", width: 80, align: "right" },
        { title: "К оплате", dataIndex: "payable", key: "payable", width: 92, align: "right" },
    ];

    const rowClassName = (r: TableRow): string => {
        if (r.isTotal) return "receipt-row-total";
        return r.key.startsWith("r") && parseInt(r.key.slice(1), 10) % 2 === 0
            ? "receipt-row-odd"
            : "";
    };

    return (
        <Modal
            title={`Квитанция № ${doc?.id ?? (receiptId ?? "")}`}
            open={open}
            onCancel={onClose}
            width={1000}
            destroyOnClose
            footer={[
                <Button key="close" onClick={onClose}>
                    Закрыть
                </Button>,
                <Button
                    key="pdf"
                    type="primary"
                    disabled={receiptId === undefined}
                    onClick={() =>
                        window.open(
                            `${apiUrl}/receipt_documents/${receiptId}/pdf`,
                            "_blank",
                        )
                    }
                >
                    PDF
                </Button>,
            ]}
        >
            <div
                style={{
                    background: "#fafafa",
                    padding: 24,
                    borderRadius: 8,
                    display: "flex",
                    justifyContent: "center",
                }}
            >
                <div
                    style={{
                        background: "#ffffff",
                        width: "100%",
                        maxWidth: 800,
                        padding: "34px 30px",
                        borderRadius: 4,
                        boxShadow: "0 2px 12px rgba(0,0,0,0.15)",
                        fontSize: 12,
                    }}
                    className="receipt-preview"
                >
                    {loading && (
                        <div style={{ textAlign: "center", padding: 40 }}>
                            <Spin />
                        </div>
                    )}

                    {error && !loading && (
                        <div style={{ textAlign: "center", padding: 24, color: "#cf1322" }}>
                            {error}
                        </div>
                    )}

                    {!loading && !error && doc && (
                        <>
                            {/* Шапка: слева «Квитанция», справа логотип + бренд */}
                            <div
                                style={{
                                    display: "flex",
                                    justifyContent: "space-between",
                                    alignItems: "center",
                                    marginBottom: 6,
                                }}
                            >
                                <div
                                    style={{
                                        fontSize: 14,
                                        fontWeight: 700,
                                        color: TITLE_TEXT,
                                    }}
                                >
                                    Квитанция
                                </div>
                                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                    <img
                                        src="/FTH.png"
                                        alt="Логотип"
                                        style={{ height: 26, objectFit: "contain", display: "block" }}
                                    />
                                    <span style={{ fontSize: 14, fontWeight: 700, color: BRAND_TEXT }}>
                                        Family Townhouse
                                    </span>
                                </div>
                            </div>

                            {/* Период */}
                            <div
                                style={{
                                    fontWeight: 700,
                                    color: PERIOD_TEXT,
                                    marginBottom: 6,
                                }}
                            >
                                {formatPeriod(doc.period_month, doc.period_year)}
                            </div>

                            {/* Квартира / собственник */}
                            <div
                                style={{
                                    fontWeight: 700,
                                    color: HEAD_TEXT,
                                    marginBottom: 14,
                                }}
                            >
                                Квартира № {doc.apartment_number ?? "—"}{" "}
                                {doc.owner_name ?? ""}
                            </div>

                            {/* Таблица данных */}
                            <Table<TableRow>
                                rowKey="key"
                                size="small"
                                pagination={false}
                                columns={entityCols}
                                dataSource={rows}
                                rowClassName={rowClassName}
                                bordered
                                components={{
                                    header: {
                                        cell: (props: any) => (
                                            <th
                                                {...props}
                                                style={{
                                                    ...props?.style,
                                                    borderColor: GRID,
                                                }}
                                                className={`${props?.className ?? ""} ${
                                                    props?.colSpan ? "receipt-head-group" : ""
                                                }`}
                                            />
                                        ),
                                    },
                                    body: {
                                        cell: (props: any) => (
                                            <td
                                                {...props}
                                                style={{
                                                    ...props?.style,
                                                    borderColor: GRID,
                                                }}
                                            />
                                        ),
                                    },
                                }}
                            />

                            {/* Дата формирования */}
                            <div
                                style={{
                                    textAlign: "right",
                                    fontSize: 9,
                                    color: STAMP_TEXT,
                                    marginTop: 18,
                                }}
                            >
                                {formatIssued(doc.issued_at)}
                            </div>
                        </>
                    )}
                </div>
            </div>
        </Modal>
    );
};

export default ReceiptViewModal;
