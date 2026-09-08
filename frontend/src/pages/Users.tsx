// src/pages/Users.tsx
// Управление пользователями и их ролями (только администратор).
// Интерфейс единой компоновки списков (см. GenericList): без колонки «Действия»
// в строках — запись выделяется (radio), а действия записи «Редактировать»/«Удалить»
// показаны иконками с подсказками под заголовком слева. Отдельного «Просмотра» нет.

import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { Table, Button, Space, Tooltip, Modal, Form, Input, Select, Switch, Popconfirm, message, Tag } from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined } from "@ant-design/icons";
import { http, apiUrl } from "../auth/http";

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
    { value: "auditor", label: "Аудитор" },
];

const roleColor: Record<string, string> = {
    admin: "red",
    operator: "geekblue",
    cashier: "blue",
    controller: "orange",
    resident: "default",
    auditor: "cyan",
};

// Иконка действия в стиле GenericList.iconButton (акцент, без заливки).
const actionIconStyle: CSSProperties = {
    color: "#22ae2e",
    borderColor: "#22ae2e",
};

const actionIconBtn = (onClick: () => void, danger = false, label?: string) => (
    <Tooltip title={label}>
        <Button
            icon={danger ? <DeleteOutlined /> : <EditOutlined />}
            danger={danger}
            style={danger ? undefined : actionIconStyle}
            onClick={onClick}
        />
    </Tooltip>
);

export const Users = () => {
    const [rows, setRows] = useState<UserRow[]>([]);
    const [loading, setLoading] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);
    const [editing, setEditing] = useState<UserRow | null>(null);
    const [selectedKey, setSelectedKey] = useState<number | null>(null);
    const [form] = Form.useForm();

    const load = async () => {
        setLoading(true);
        try {
            const res = await http.get<UserRow[]>(`${apiUrl}/auth/users`);
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

    // Если выделенная запись исчезла (удалена/перезагружена) — снимаем выбор.
    useEffect(() => {
        if (selectedKey != null && !rows.some((r) => r.id === selectedKey)) {
            setSelectedKey(null);
        }
    }, [rows, selectedKey]);

    const selectedRecord = rows.find((r) => r.id === selectedKey) ?? null;

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
                await http.patch(`${apiUrl}/auth/users/${editing.id}`, values);
                message.success("Пользователь обновлён");
            } else {
                await http.post(`${apiUrl}/auth/users`, values);
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
            await http.delete(`${apiUrl}/auth/users/${row.id}`);
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
    ];

    return (
        <div style={{ background: "#fff", padding: 30, borderRadius: 12, border: "1px solid #d9eedc" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, marginBottom: 20 }}>
                <div>
                    <h1 style={{ color: "#14501d", margin: 0 }}>Пользователи и права</h1>
                    <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 8 }}>
                        {selectedRecord ? (
                            <>
                                {actionIconBtn(() => openEdit(selectedRecord), false, "Редактировать")}
                                <Popconfirm title="Удалить пользователя?" onConfirm={() => handleDelete(selectedRecord)}>
                                    {actionIconBtn(() => undefined, true, "Удалить")}
                                </Popconfirm>
                                <span style={{ color: "#888", fontSize: 12, marginLeft: 4 }}>
                                    Запись № {selectedRecord.id}
                                </span>
                            </>
                        ) : (
                            <Space>
                                <Tooltip title="Редактировать">
                                    <Button icon={<EditOutlined />} disabled />
                                </Tooltip>
                                <Tooltip title="Удалить">
                                    <Button icon={<DeleteOutlined />} danger disabled />
                                </Tooltip>
                            </Space>
                        )}
                    </div>
                </div>
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
                rowSelection={{
                    type: "radio",
                    selectedRowKeys: selectedKey != null ? [selectedKey] : [],
                    onChange: (keys) => setSelectedKey((keys[0] as number) ?? null),
                }}
                onRow={(record) => ({
                    onClick: () => setSelectedKey(record.id),
                    style: { cursor: "pointer" },
                })}
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
