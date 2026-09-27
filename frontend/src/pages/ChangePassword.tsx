// src/pages/ChangePassword.tsx
// Смена пароля (Б9). После первого входа с флагом must_change_password доступны
// только эта страница (guard в ProtectedLayout). После смены флаг снимается.

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Button, Card, Form, Input, Typography, message } from "antd";

import { apiUrl, authedFetch } from "../auth/http";
import { setIdentity } from "../auth/token";

interface ChangePasswordValues {
    current_password: string;
    new_password: string;
    confirm: string;
}

export const ChangePassword = () => {
    const navigate = useNavigate();
    const [form] = Form.useForm<ChangePasswordValues>();
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const onFinish = async (values: ChangePasswordValues) => {
        if (values.new_password !== values.confirm) {
            setError("Новый пароль и подтверждение не совпадают");
            return;
        }
        setLoading(true);
        setError(null);
        try {
            const resp = await authedFetch(`${apiUrl}/auth/change-password`, {
                method: "POST",
                body: JSON.stringify({
                    current_password: values.current_password,
                    new_password: values.new_password,
                }),
            });
            if (!resp.ok) {
                let detail = "Не удалось сменить пароль";
                try {
                    detail = (await resp.json())?.detail ?? detail;
                } catch {
                    /* ignore */
                }
                throw new Error(detail);
            }
            // Обновляем личность — флаг must_change_password снят.
            const me = await authedFetch(`${apiUrl}/auth/me`);
            if (me.ok) setIdentity(await me.json());
            message.success("Пароль изменён");
            navigate("/");
        } catch (e: any) {
            setError(e?.message ?? "Не удалось сменить пароль");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{ maxWidth: 520, margin: "0 auto" }}>
            <Card>
                <Typography.Title level={4} style={{ marginTop: 0 }}>
                    Смена пароля
                </Typography.Title>
                <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>
                    Задайте свой пароль для входа.
                </Typography.Paragraph>
                {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}
                <Form form={form} layout="vertical" onFinish={onFinish} requiredMark={false}>
                    <Form.Item
                        name="current_password"
                        label="Текущий пароль"
                        rules={[{ required: true, message: "Введите текущий пароль" }]}
                    >
                        <Input.Password autoComplete="current-password" />
                    </Form.Item>
                    <Form.Item
                        name="new_password"
                        label="Новый пароль"
                        rules={[
                            { required: true, message: "Введите новый пароль" },
                            { min: 6, message: "Минимум 6 символов" },
                        ]}
                    >
                        <Input.Password autoComplete="new-password" />
                    </Form.Item>
                    <Form.Item
                        name="confirm"
                        label="Повторите новый пароль"
                        rules={[{ required: true, message: "Повторите новый пароль" }]}
                    >
                        <Input.Password autoComplete="new-password" />
                    </Form.Item>
                    <Button type="primary" htmlType="submit" loading={loading} block>
                        Сменить пароль
                    </Button>
                </Form>
            </Card>
        </div>
    );
};

export default ChangePassword;
