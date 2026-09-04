// src/pages/Login.tsx

import { useRef, useState } from "react";
import { Form, Input, Button, Card, Typography } from "antd";
import { UserOutlined, LockOutlined } from "@ant-design/icons";
import { useLogin } from "@refinedev/core";
import { useNavigate } from "react-router-dom";
import { BRAND } from "../config/colors";

interface LoginForm {
    username: string;
    password: string;
}

export const Login = () => {
    const { mutateAsync: login, isLoading } = useLogin<LoginForm>();
    const navigate = useNavigate();
    const [error, setError] = useState<string | null>(null);
    // Защита от повторной отправки (двойной клик/Enter до блокировки кнопки):
    // пока первый запрос в полёте — игнорируем повторные submit-ы.
    const submittingRef = useRef(false);

    const onFinish = async (values: LoginForm) => {
        if (submittingRef.current) return;
        submittingRef.current = true;
        setError(null);
        try {
            const result = await login(values);
            if (result?.success) {
                navigate("/");
            } else if (result?.error?.message) {
                setError(result.error.message);
            }
        } catch (e: any) {
            setError(e?.message ?? "Не удалось выполнить вход");
        } finally {
            submittingRef.current = false;
        }
    };

    return (
        <div
            style={{
                minHeight: "100vh",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "#f2f8f3",
            }}
        >
            <Card style={{ width: 380, boxShadow: "0 2px 12px rgba(0,0,0,0.08)" }}>
                <div style={{ textAlign: "center", marginBottom: 24 }}>
                    <Typography.Title level={3} style={{ color: BRAND.primary, margin: 0 }}>
                        Family Townhouse
                    </Typography.Title>
                    <Typography.Text type="secondary">Вход в систему</Typography.Text>
                </div>
                {error && (
                    <Typography.Paragraph type="danger" style={{ textAlign: "center" }}>
                        {error}
                    </Typography.Paragraph>
                )}
                <Form<LoginForm> layout="vertical" onFinish={onFinish}>
                    <Form.Item
                        name="username"
                        label="Логин"
                        rules={[{ required: true, message: "Введите логин" }]}
                    >
                        <Input prefix={<UserOutlined />} placeholder="Логин" autoFocus />
                    </Form.Item>
                    <Form.Item
                        name="password"
                        label="Пароль"
                        rules={[{ required: true, message: "Введите пароль" }]}
                    >
                        <Input.Password prefix={<LockOutlined />} placeholder="Пароль" />
                    </Form.Item>
                    <Button type="primary" htmlType="submit" block loading={isLoading} style={{ marginTop: 8 }}>
                        Войти
                    </Button>
                </Form>
            </Card>
        </div>
    );
};
