// src/pages/Users.tsx
// Управление пользователями и их ролями (только администратор).

import { useEffect, useState } from "react";
import { Table, Button, Space, Modal, Form, Input, Select, Switch, Popconfirm, message, Tag } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { http } from "../auth/http";

interface UserRow {
    id: number;
    username: string;
    full_name: string | null;
    role: string;
    role_name: string;
    is_active: boolean;
}

const ROLE_OPTIONS = [
    { value: "admin", label: "Администратор" },
    { value: "operator", label: "Оператор" },
    { value: "cashier", label: "Кассир" },
    { value: "controller", label: "Контролер" },
    { value: "resident", label: "Житель" },
];

const roleColor: Record<string, string> = {
    admin: "red",
    operator: "geekblue",
    cashier: "blue",
    controller: "orange",
    resident: "default",
};

export const Users = () => {
    const [rows, setRows] = useState<UserRow[]>([]);
    const [loading, setLoading] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);
    const [editing, setEditing] = useState<UserRow | null>(null);
    const [form] = Form.useForm();

    const load = async () => {
        setLoading(true);
        try {
            const res = await http.get<UserRow[]>("/auth/users");
            setRows(res.data);
        } catch (e: any) {
            message.error(e?.response?.data?.detail ?? "Не удалось загрузить пользователей");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        load();
    }, []);

    const openCreate = () => {
        setEditing(null);
        form.resetFields();
        setModalOpen(true);
    };

    const openEdit = (row: UserRow) => {
        setEditing(row);
        form.setFieldsValue({
            username: row.username,
            full_name: row.full_name ?? "",
            role: row.role,
            is_active: row.is_active,
            password: "",
        });
        setModalOpen(true);
    };

    const handleOk = async () => {
        const values = await form.validateFields();
        try {
            if (editing) {
                await http.patch(`/auth/users/${editing.id}`, values);
                message.success("Пользователь обновлён");
            } else {
                await http.post("/auth/users", values);
                message.success("Пользователь создан");
            }
            setModalOpen(false);
            load();
        } catch (e: any) {
            message.error(e?.response?.data?.detail ?? "Не удалось сохранить пользователя");
        }
    };

    const handleDelete = async (row: UserRow) => {
        try {
            await http.delete(`/auth/users/${row.id}`);
            message.success("Пользователь удалён");
            load();
        } catch (e: any) {
            message.error(e?.response?.data?.detail ?? "Не удалось удалить пользователя");
        }
    };

    const columns = [
        { title: "Логин", dataIndex: "username", key: "username" },
        { title: "Имя", dataIndex: "full_name", key: "full_name", render: (v: string) => v || "—" },
        {
            title: "Роль",
            dataIndex: "role_name",
            key: "role_name",
            render: (_: string, r: UserRow) => <Tag color={roleColor[r.role]}>{r.role_name}</Tag>,
        },
        {
            title: "Активен",
            dataIndex: "is_active",
            key: "is_active",
            render: (v: boolean) => (v ? "Да" : "Нет"),
        },
        {
            title: "Действия",
            key: "actions",
            render: (_: unknown, r: UserRow) => (
                <Space>
                    <Button size="small" onClick={() => openEdit(r)}>Изменить</Button>
                    <Popconfirm title="Удалить пользователя?" onConfirm={() => handleDelete(r)}>
                        <Button size="small" danger>Удалить</Button>
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <div style={{ background: "#fff", padding: 30, borderRadius: 12, border: "1px solid #d9eedc" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                <h1 style={{ color: "#14501d", margin: 0 }}>Пользователи и права</h1>
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                    Создать пользователя
                </Button>
            </div>

            <Table<UserRow>
                rowKey="id"
                dataSource={rows}
                columns={columns}
                loading={loading}
                pagination={false}
            />

            <Modal
                title={editing ? `Редактировать: ${editing.username}` : "Новый пользователь"}
                open={modalOpen}
                onCancel={() => setModalOpen(false)}
                onOk={handleOk}
                destroyOnClose
                okText="Сохранить"
                cancelText="Отмена"
            >
                <Form form={form} layout="vertical" initialValues={{ role: "cashier", is_active: true }}>
                    <Form.Item
                        name="username"
                        label="Логин"
                        rules={[{ required: true, message: "Введите логин" }]}
                        extra={editing ? "Логин изменить нельзя" : undefined}
                    >
                        <Input disabled={!!editing} />
                    </Form.Item>
                    <Form.Item name="full_name" label="Имя">
                        <Input />
                    </Form.Item>
                    <Form.Item name="role" label="Роль" rules={[{ required: true }]}>
                        <Select options={ROLE_OPTIONS} />
                    </Form.Item>
                    <Form.Item name="is_active" label="Активен" valuePropName="checked">
                        <Switch />
                    </Form.Item>
                    <Form.Item
                        name="password"
                        label={editing ? "Новый пароль (оставьте пустым, чтобы не менять)" : "Пароль"}
                        rules={editing ? [] : [{ required: true, message: "Введите пароль" }]}
                    >
                        <Input.Password />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
};
