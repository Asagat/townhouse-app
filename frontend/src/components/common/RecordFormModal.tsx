// src/components/common/RecordFormModal.tsx

import { useEffect } from "react";
import { Modal, Form } from "antd";
import dayjs from "dayjs";
import type { FieldMeta } from "../../types";
import { renderFieldControl } from "./renderFieldControl";

interface RecordFormModalProps {
    /** Открыто ли модальное окно */
    open: boolean;
    /** Заголовок модального окна */
    title: string;
    /** Список полей формы */
    fields: FieldMeta[];
    /** Начальные значения для формы (при редактировании) */
    initialValues?: Record<string, any>;
    /** Состояние загрузки при сохранении */
    confirmLoading: boolean;
    /** Обработчик отмены */
    onCancel: () => void;
    /** Обработчик отправки формы */
    onSubmit: (values: Record<string, any>) => void;
}

/**
 * Модальное окно для создания/редактирования записи
 * Динамически строит форму на основе метаданных полей
 */
export const RecordFormModal = ({
    open,
    title,
    fields,
    initialValues,
    confirmLoading,
    onCancel,
    onSubmit,
}: RecordFormModalProps) => {
    const [form] = Form.useForm();

    useEffect(() => {
        if (!open) return;

        const prepared: Record<string, any> = {};
        fields.forEach((field) => {
            const raw = initialValues?.[field.name];

            if (field.type === "date") {
                if (raw) {
                    prepared[field.name] = dayjs(raw);
                } else if (field.default === "today") {
                    prepared[field.name] = dayjs();
                } else {
                    prepared[field.name] = undefined;
                }
            } else if (field.type === "boolean") {
                prepared[field.name] = raw ?? field.default ?? false;
            } else {
                prepared[field.name] = raw ?? field.default;
            }
        });

        form.resetFields();
        form.setFieldsValue(prepared);
    }, [open, initialValues, fields, form]);

    const handleOk = () => {
        form.validateFields().then((values) => {
            const payload: Record<string, any> = {};
            fields.forEach((field) => {
                const value = values[field.name];
                payload[field.name] =
                    field.type === "date" && value ? value.format("YYYY-MM-DD") : value;
            });
            onSubmit(payload);
        });
    };

    return (
        <Modal
            title={title}
            open={open}
            onCancel={onCancel}
            onOk={handleOk}
            confirmLoading={confirmLoading}
            okText="Сохранить"
            cancelText="Отмена"
            destroyOnClose
        >
            <Form form={form} layout="vertical">
                {fields.map((field) => (
                    <Form.Item
                        key={field.name}
                        name={field.name}
                        label={field.label}
                        valuePropName={field.type === "boolean" ? "checked" : "value"}
                        rules={
                            field.required
                                ? [{ required: true, message: `Поле «${field.label}» обязательно` }]
                                : []
                        }
                    >
                        {renderFieldControl(field)}
                    </Form.Item>
                ))}
            </Form>
        </Modal>
    );
};
