// frontend/src/pages/ResidentCabinet.tsx
// Личный кабинет жителя: сводка по ЛС + список своих квитанций (просмотр/PDF).
// Боковой панели у жителя нет — внизу страницы кнопки «Главная»/«Настройки»/«Выход».

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Button, Spin, Typography, message } from "antd";
import { HomeOutlined, LogoutOutlined, SettingOutlined } from "@ant-design/icons";
import { useApiUrl, useLogout } from "@refinedev/core";
import { authedFetch } from "../auth/http";
import { CabinetView } from "../components/cabinet/CabinetView";
import type { ReceiptRow, StatementData } from "../components/cabinet/CabinetView";

export const ResidentCabinet = () => {
    const apiUrl = useApiUrl();
    const navigate = useNavigate();
    const { mutate: logout } = useLogout();
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

    if (loading) {
        return (
            <div style={{ textAlign: "center", padding: 80 }}>
                <Spin size="large" />
            </div>
        );
    }

    return (
        // Крупный шрифт ЛК задаёт сам CabinetView (единый вид в ЛК и админ-просмотре).
        <div>
            <Typography.Title level={4} style={{ marginTop: 0 }}>
                Личный кабинет
            </Typography.Title>
            {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
            <CabinetView
                statement={statement}
                receipts={receipts}
                houseExpenses={true}
                apiUrl={apiUrl}
            />

                <div
                    style={{
                        marginTop: 24,
                        paddingTop: 16,
                        borderTop: "1px solid #d9d9d9",
                        display: "flex",
                        justifyContent: "center",
                        gap: 12,
                    }}
                >
                    {[
                        {
                            key: "home",
                            icon: <HomeOutlined />,
                            label: "Главная",
                            onClick: () => navigate("/"),
                        },
                        {
                            key: "settings",
                            icon: <SettingOutlined />,
                            label: "Настройки",
                            onClick: () => message.info("Раздел «Настройки» появится позже"),
                        },
                        {
                            key: "logout",
                            icon: <LogoutOutlined />,
                            label: "Выход",
                            danger: true,
                            onClick: () => logout(),
                        },
                    ].map((b) => (
                        <Button
                            key={b.key}
                            danger={b.danger}
                            onClick={b.onClick}
                            style={{
                                width: 88,
                                height: 72,
                                display: "flex",
                                flexDirection: "column",
                                alignItems: "center",
                                justifyContent: "center",
                                gap: 6,
                                borderRadius: 14,
                            }}
                        >
                            <span style={{ fontSize: 20, lineHeight: 1 }}>{b.icon}</span>
                            <span style={{ fontSize: 13, lineHeight: 1 }}>{b.label}</span>
                        </Button>
                    ))}
                </div>
        </div>
    );
};

export default ResidentCabinet;
