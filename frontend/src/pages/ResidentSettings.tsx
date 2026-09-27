// src/pages/ResidentSettings.tsx
// Настройки жителя (Б2): контактные данные собственника + переход к смене пароля (Б9).
// Мобильный вид: узкая колонка, нижняя навигация как в ЛК.

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Button, Card, Form, Input, Spin, Typography, message } from "antd";
import { HomeOutlined, LockOutlined, LogoutOutlined } from "@ant-design/icons";
import { useApiUrl, useLogout } from "@refinedev/core";

import { authedFetch } from "../auth/http";
import { formatPhoneInput, normalizePhone } from "../config/formatters";

interface Contacts {
    full_name: string | null;
    phone: string | null;
    email: string | null;
    contact_info: string | null;
    login: string;
}

// Простое поле телефона с маской (по образцу renderFieldControl.PhoneInput).
const PhoneField = ({
    value,
    onChange,
}: {
    value?: string;
    onChange?: (value: string) => void;
}) => {
    const [focused, setFocused] = useState(false);
    const digits = normalizePhone(value);
    return (
        <Input
            inputMode="numeric"
            placeholder="+7 (___) ___-__-__"
            maxLength={11}
            value={focused ? digits : formatPhoneInput(digits)}
            onChange={(e) => onChange?.(normalizePhone(e.target.value))}
            onFocus={() => setFocused(true)}
            onBlur={() => {
                setFocused(false);
                onChange?.(normalizePhone(digits));
            }}
        />
    );
};

export const ResidentSettings = () => {
    const apiUrl = useApiUrl();
    const navigate = useNavigate();
    const { mutate: logout } = useLogout();
    const [form] = Form.useForm<Contacts>();
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [login, setLogin] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setError(null);
        authedFetch(`${apiUrl}/me/contacts`)
            .then(async (r) => {
                if (!r.ok) {
                    let d = "Не удалось загрузить контакты";
                    try { d = (await r.json())?.detail ?? d; } catch { /* ignore */ }
                    throw new Error(d);
                }
                return r.json() as Promise<Contacts>;
            })
            .then((c) => {
                setLogin(c.login);
                form.setFieldsValue({
                    full_name: c.full_name ?? "",
                    phone: c.phone ?? "",
                    email: c.email ?? "",
                    contact_info: c.contact_info ?? "",
                });
            })
            .catch((e: any) => setError(e?.message ?? "Не удалось загрузить контакты"))
            .finally(() => setLoading(false));
    }, [apiUrl, form]);

    useEffect(() => { load(); }, [load]);

    const onFinish = async (values: Contacts) => {
        setSaving(true);
        setError(null);
        try {
            const resp = await authedFetch(`${apiUrl}/me/contacts`, {
                method: "PATCH",
                body: JSON.stringify({
                    full_name: values.full_name ?? "",
                    phone: values.phone ?? "",
                    email: values.email ?? "",
                    contact_info: values.contact_info ?? "",
                }),
            });
            if (!resp.ok) {
                let d = "Не удалось сохранить контакты";
                try { d = (await resp.json())?.detail ?? d; } catch { /* ignore */ }
                throw new Error(d);
            }
            message.success("Контактные данные сохранены");
        } catch (e: any) {
            setError(e?.message ?? "Не удалось сохранить контакты");
        } finally {
            setSaving(false);
        }
    };

    return (
        <div style={{ maxWidth: 560, margin: "0 auto" }}>
            <Typography.Title level={4} style={{ marginTop: 0 }}>
                Настройки
            </Typography.Title>
            {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

            <Card title="Контактные данные" style={{ marginBottom: 16 }}>
                {loading ? (
                    <div style={{ textAlign: "center", padding: 40 }}><Spin /></div>
                ) : (
                    <Form form={form} layout="vertical" onFinish={onFinish} requiredMark={false}>
                        <Form.Item label="Логин">
                            <Input value={login} disabled />
                        </Form.Item>
                        <Form.Item
                            name="full_name"
                            label="ФИО"
                            rules={[{ required: true, message: "Укажите ФИО" }]}
                        >
                            <Input />
                        </Form.Item>
                        <Form.Item name="phone" label="Телефон">
                            <PhoneField />
                        </Form.Item>
                        <Form.Item
                            name="email"
                            label="E-mail"
                            rules={[{ type: "email", message: "Некорректный e-mail" }]}
                        >
                            <Input type="email" />
                        </Form.Item>
                        <Form.Item name="contact_info" label="Доп. контакты">
                            <Input.TextArea rows={2} />
                        </Form.Item>
                        <Button type="primary" htmlType="submit" loading={saving} block>
                            Сохранить
                        </Button>
                    </Form>
                )}
            </Card>

            <Card title="Безопасность" style={{ marginBottom: 16 }}>
                <Button icon={<LockOutlined />} onClick={() => navigate("/change-password")}>
                    Сменить пароль
                </Button>
            </Card>

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
                <Button
                    icon={<HomeOutlined />}
                    onClick={() => navigate("/")}
                    style={{ height: 48, borderRadius: 12 }}
                >
                    Главная
                </Button>
                <Button
                    danger
                    icon={<LogoutOutlined />}
                    onClick={() => logout()}
                    style={{ height: 48, borderRadius: 12 }}
                >
                    Выход
                </Button>
            </div>
        </div>
    );
};

export default ResidentSettings;
