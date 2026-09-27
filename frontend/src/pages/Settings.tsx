// src/pages/Settings.tsx
// Префиксы (раздел «5. Администрирование», Б3; только админ). Сейчас — префикс
// лицевого счёта (используется при авто-генерации номера счёта); раздел рассчитан
// на расширение (доп. префиксы для документов и т.п.).

import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Card, Form, Input, Spin, Typography, message } from "antd";

import { apiUrl, http } from "../auth/http";

interface AppSettings {
    account_number_prefix: string;
}

export const Settings = () => {
    const [form] = Form.useForm<AppSettings>();
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(() => {
        setLoading(true);
        setError(null);
        http.get(`${apiUrl}/auth/settings`)
            .then((res) => form.setFieldsValue(res.data.settings))
            .catch((e: any) => setError(e?.response?.data?.detail ?? "Не удалось загрузить настройки"))
            .finally(() => setLoading(false));
    }, [form]);

    useEffect(() => { load(); }, [load]);

    const onFinish = async (values: AppSettings) => {
        setSaving(true);
        setError(null);
        try {
            await http.put(`${apiUrl}/auth/settings`, { settings: values });
            message.success("Настройки сохранены");
        } catch (e: any) {
            setError(e?.response?.data?.detail ?? "Не удалось сохранить настройки");
        } finally {
            setSaving(false);
        }
    };

    return (
        <div style={{ maxWidth: 640, margin: "0 auto" }}>
            <Typography.Title level={4} style={{ marginTop: 0 }}>
                Префиксы
            </Typography.Title>
            {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
            {loading ? (
                <div style={{ textAlign: "center", padding: 40 }}><Spin /></div>
            ) : (
                <Card title="Лицевые счета">
                    <Form form={form} layout="vertical" onFinish={onFinish} requiredMark={false}>
                        <Form.Item
                            name="account_number_prefix"
                            label="Префикс лицевого счёта"
                            rules={[{ required: true, message: "Укажите префикс" }]}
                            extra="Номер генерируется как «префикс + номер квартиры», например «LS-0001»."
                        >
                            <Input style={{ maxWidth: 240 }} />
                        </Form.Item>
                        <Button type="primary" htmlType="submit" loading={saving}>
                            Сохранить
                        </Button>
                    </Form>
                </Card>
            )}
        </div>
    );
};

export default Settings;
