// src/components/apartments/ApartmentResidentsModal.tsx
// Сведения о жильцах квартиры (Б8): список жителей с периодами проживания.
// Открывается из списка «Квартиры». Используется тарифом «На человека».

import { useCallback, useEffect, useState } from "react";
import { Button, DatePicker, Form, Input, Modal, Popconfirm, Select, Space, Table, Typography, message } from "antd";
import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import dayjs from "dayjs";

import { apiUrl, http } from "../../auth/http";

interface ResidentRow {
    id: number;
    apartment_id: number;
    full_name: string;
    birth_date: string | null;
    role: string;
    date_from: string | null;
    date_to: string | null;
}

const ROLE_OPTIONS = [
    { value: "Собственник", label: "Собственник" },
    { value: "Проживающий", label: "Проживающий" },
];

export const ApartmentResidentsModal = ({
    open,
    apartment,
    onClose,
    canEdit = true,
}: {
    open: boolean;
    apartment: { id: number; apartment_number?: number } | null;
    onClose: () => void;
    canEdit?: boolean;
}) => {
    const [rows, setRows] = useState<ResidentRow[]>([]);
    const [loading, setLoading] = useState(false);
    const [form] = Form.useForm();

    const load = useCallback(async () => {
        if (!apartment) return;
        setLoading(true);
        try {
            const res = await http.get<ResidentRow[]>(
                `${apiUrl}/apartment_residents?_start=0&_end=200&_sort=id&_order=asc&apartment_id=${apartment.id}`,
            );
            setRows(res.data);
        } catch (e: any) {
            message.error(e?.response?.data?.detail ?? "Не удалось загрузить жильцов");
        } finally {
            setLoading(false);
        }
    }, [apartment]);

    useEffect(() => {
        if (open) {
            form.resetFields();
            load();
        }
    }, [open, load, form]);

    const handleAdd = async () => {
        if (!apartment) return;
        try {
            const values = await form.validateFields();
            await http.post(`${apiUrl}/apartment_residents`, {
                apartment_id: apartment.id,
                full_name: values.full_name,
                role: values.role,
                birth_date: values.birth_date ? values.birth_date.format("YYYY-MM-DD") : null,
                date_from: values.date_from ? values.date_from.format("YYYY-MM-DD") : null,
                date_to: values.date_to ? values.date_to.format("YYYY-MM-DD") : null,
            });
            message.success("Жилец добавлен");
            form.resetFields();
            load();
        } catch (e: any) {
            // Ошибки валидации формы (antd присылает errorFields) уже подсвечены у полей —
            // повторное сообщение не нужно и не должно уходить в unhandled rejection.
            if (e?.errorFields) return;
            message.error(e?.response?.data?.detail ?? "Не удалось добавить жильца");
        }
    };

    const handleDelete = async (id: number) => {
        try {
            await http.delete(`${apiUrl}/apartment_residents/${id}`);
            message.success("Запись удалена");
            load();
        } catch (e: any) {
            message.error(e?.response?.data?.detail ?? "Не удалось удалить запись");
        }
    };

    const columns = [
        { title: "ФИО", dataIndex: "full_name", key: "full_name" },
        { title: "Статус", dataIndex: "role", key: "role" },
        { title: "Дата рождения", dataIndex: "birth_date", key: "birth_date", render: (v: string | null) => (v ? dayjs(v).format("DD.MM.YYYY") : "—") },
        { title: "Проживает с", dataIndex: "date_from", key: "date_from", render: (v: string | null) => (v ? dayjs(v).format("DD.MM.YYYY") : "—") },
        { title: "Проживает по", dataIndex: "date_to", key: "date_to", render: (v: string | null) => (v ? dayjs(v).format("DD.MM.YYYY") : "по н.в.") },
        ...(canEdit
            ? [{
                  title: "",
                  key: "actions",
                  width: 50,
                  render: (_: unknown, r: ResidentRow) => (
                      <Popconfirm title="Удалить запись о жильце?" onConfirm={() => handleDelete(r.id)}>
                          <Button size="small" danger icon={<DeleteOutlined />} />
                      </Popconfirm>
                  ),
              }]
            : []),
    ];

    return (
        <Modal
            title={`Жильцы квартиры ${apartment?.apartment_number ?? ""}`.trim()}
            open={open}
            onCancel={onClose}
            footer={null}
            width={720}
            destroyOnClose
        >
            <Table<ResidentRow>
                rowKey="id"
                size="small"
                loading={loading}
                dataSource={rows}
                columns={columns as any}
                pagination={false}
                locale={{ emptyText: "Жильцы не заведены" }}
                style={{ marginBottom: 16 }}
            />

            {canEdit && (
                <>
                    <Typography.Text type="secondary">Добавить жильца</Typography.Text>
                    <Form form={form} layout="inline" style={{ marginTop: 8, rowGap: 8 }} initialValues={{ role: "Проживающий" }}>
                        <Form.Item name="full_name" rules={[{ required: true, message: "Укажите ФИО" }]}>
                            <Input placeholder="ФИО" style={{ width: 200 }} />
                        </Form.Item>
                        <Form.Item name="role">
                            <Select options={ROLE_OPTIONS} style={{ width: 150 }} />
                        </Form.Item>
                        <Form.Item name="birth_date">
                            <DatePicker placeholder="Дата рождения" format="DD.MM.YYYY" style={{ width: 150 }} />
                        </Form.Item>
                        <Form.Item name="date_from">
                            <DatePicker placeholder="Проживает с" format="DD.MM.YYYY" style={{ width: 150 }} />
                        </Form.Item>
                        <Form.Item name="date_to">
                            <DatePicker placeholder="Проживает по" format="DD.MM.YYYY" style={{ width: 150 }} />
                        </Form.Item>
                        <Space>
                            <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
                                Добавить
                            </Button>
                        </Space>
                    </Form>
                </>
            )}
        </Modal>
    );
};

export default ApartmentResidentsModal;
