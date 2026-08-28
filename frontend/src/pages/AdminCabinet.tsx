// frontend/src/pages/AdminCabinet.tsx
// «Личный кабинет жителя» для администратора: выбор квартиры (лицевого счёта)
// и просмотр того же, что видит житель (сводка по ЛС + квитанции), по счёту.

import { useCallback, useEffect, useState } from "react";
import { Alert, Card, Select, Spin, Typography } from "antd";
import { useApiUrl } from "@refinedev/core";
import { authedFetch } from "../auth/http";
import { CabinetView } from "../components/cabinet/CabinetView";
import type { ReceiptRow, StatementData } from "../components/cabinet/CabinetView";

interface AccountOption {
    value: number;
    label: string;
}

export const AdminCabinet = () => {
    const apiUrl = useApiUrl();
    const [accounts, setAccounts] = useState<AccountOption[]>([]);
    const [selectedId, setSelectedId] = useState<number | undefined>(undefined);
    const [statement, setStatement] = useState<StatementData | null>(null);
    const [receipts, setReceipts] = useState<ReceiptRow[]>([]);
    const [loadingAccounts, setLoadingAccounts] = useState(true);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Список лицевых счетов с квартирой и собственником (для выпадающего списка).
    useEffect(() => {
        authedFetch(`${apiUrl}/accounts?_start=0&_end=1000`)
            .then(async (r) => {
                if (!r.ok) throw new Error("Не удалось загрузить лицевые счета");
                const data = await r.json();
                setAccounts(
                    (data as Array<Record<string, any>>).map((a) => {
                        const apt = a?.apartment;
                        const aptNum = apt?.apartment_number;
                        const label = aptNum != null
                            ? `Кв. №${aptNum} — ${apt?.owner?.full_name ?? ""} (${a.account_number})`
                            : `${a.account_number} — ${a.account_name ?? ""}`;
                        return { value: a.id, label };
                    }),
                );
            })
            .catch((e: any) => setError(e?.message ?? "Не удалось загрузить лицевые счета"))
            .finally(() => setLoadingAccounts(false));
    }, [apiUrl]);

    // Сводка и квитанции по выбранному счёту (те же данные, что видит житель).
    const loadAccount = useCallback((accountId: number) => {
        setLoading(true);
        setError(null);
        Promise.all([
            authedFetch(`${apiUrl}/accounts/${accountId}/statement`).then(async (r) => {
                if (!r.ok) {
                    let d = "Не удалось загрузить сводку";
                    try { d = (await r.json())?.detail ?? d; } catch { /* ignore */ }
                    throw new Error(d);
                }
                return r.json() as Promise<StatementData>;
            }),
            authedFetch(`${apiUrl}/accounts/${accountId}/receipts`).then(async (r) => {
                if (!r.ok) return [] as ReceiptRow[];
                return r.json() as Promise<ReceiptRow[]>;
            }),
        ])
            .then(([stmt, recs]: [StatementData, ReceiptRow[]]) => {
                setStatement(stmt);
                setReceipts(recs ?? []);
            })
            .catch((err: any) => setError(err?.message ?? "Не удалось загрузить данные"))
            .finally(() => setLoading(false));
    }, [apiUrl]);

    const onSelect = (value: number) => {
        setSelectedId(value);
        loadAccount(value);
    };

    const selectedAccount = accounts.find((a) => a.value === selectedId);

    return (
        <div>
            <Typography.Title level={4} style={{ marginTop: 0 }}>
                Личный кабинет жителя
            </Typography.Title>
            <Card style={{ marginBottom: 16 }}>
                <Select
                    placeholder="Выберите квартиру (лицевой счёт)"
                    style={{ width: 480 }}
                    showSearch
                    optionFilterProp="label"
                    loading={loadingAccounts}
                    options={accounts}
                    value={selectedId}
                    onChange={onSelect}
                />
            </Card>

            {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

            {!selectedId && !loading && (
                <Typography.Text type="secondary">
                    Выберите квартиру, чтобы увидеть данные, которые видит житель.
                </Typography.Text>
            )}

            {selectedId && loading && (
                <div style={{ textAlign: "center", padding: 60 }}>
                    <Spin size="large" />
                </div>
            )}

            {selectedId && !loading && (
                <CabinetView
                    statement={statement}
                    receipts={receipts}
                    apiUrl={apiUrl}
                    receiptsTitle="Квитанции жителя"
                    userLabel={selectedAccount ? selectedAccount.label : undefined}
                />
            )}
        </div>
    );
};

export default AdminCabinet;
