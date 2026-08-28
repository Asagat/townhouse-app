// frontend/src/pages/ResidentCabinet.tsx
// Личный кабинет жителя: сводка по ЛС + список своих квитанций (просмотр/PDF).

import { useCallback, useEffect, useState } from "react";
import { Alert, Spin, Typography } from "antd";
import { useApiUrl } from "@refinedev/core";
import { authedFetch } from "../auth/http";
import { getIdentity } from "../auth/token";
import { CabinetView } from "../components/cabinet/CabinetView";
import type { ReceiptRow, StatementData } from "../components/cabinet/CabinetView";

export const ResidentCabinet = () => {
    const apiUrl = useApiUrl();
    const [statement, setStatement] = useState<StatementData | null>(null);
    const [receipts, setReceipts] = useState<ReceiptRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(() => {
        setLoading(true);
        setError(null);
        Promise.all([
            authedFetch(`${apiUrl}/me/statement`).then(async (r) => {
                if (!r.ok) {
                    let d = "Не удалось загрузить сводку";
                    try { d = (await r.json())?.detail ?? d; } catch { /* ignore */ }
                    throw new Error(d);
                }
                return r.json() as Promise<StatementData>;
            }),
            authedFetch(`${apiUrl}/me/receipts`).then(async (r) => {
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

    useEffect(() => { load(); }, [load]);

    const identity = getIdentity();

    if (loading) {
        return (
            <div style={{ textAlign: "center", padding: 80 }}>
                <Spin size="large" />
            </div>
        );
    }

    return (
        <div>
            <Typography.Title level={4} style={{ marginTop: 0 }}>
                Личный кабинет
            </Typography.Title>
            {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
            <CabinetView
                statement={statement}
                receipts={receipts}
                apiUrl={apiUrl}
                userLabel={`Пользователь: ${identity?.full_name || identity?.username || ""}`}
            />
        </div>
    );
};

export default ResidentCabinet;
