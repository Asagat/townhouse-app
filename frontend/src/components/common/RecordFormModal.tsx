// src/components/common/RecordFormModal.tsx

import { useEffect, useMemo } from "react";
import { Modal, Form, Input } from "antd";
import dayjs from "dayjs";
import type { FieldMeta } from "../../types";
import { renderFieldControl } from "./renderFieldControl";
import { sortFieldsForForm } from "../../config/columns";

interface RecordFormModalProps {
    open: boolean;
    title: string;
    fields: FieldMeta[];
    initialValues?: Record<string, any>;
    confirmLoading: boolean;
    onCancel: () => void;
    onSubmit: (values: Record<string, any>) => void;
    resourceName?: string;
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
    resourceName,
}: RecordFormModalProps) => {
    const [form] = Form.useForm();

    // Сортируем поля в соответствии с конфигурацией
    const sortedFields = useMemo(() => {
        return resourceName ? sortFieldsForForm(fields, resourceName) : fields;
    }, [fields, resourceName]);

    // Определяем, является ли поле readonly (только для просмотра)
    const isReadonlyField = (field: FieldMeta): boolean => {
        const readonlyFields = ['id', 'created_at', 'accruals_count', 'total_amount'];
        return readonlyFields.includes(field.name);
    };

    useEffect(() => {
        if (!open) return;

        const prepared: Record<string, any> = {};
        sortedFields.forEach((field) => {
            const raw = initialValues?.[field.name];

            // Для reference полей - используем raw значение (это ID)
            if (field.type === "reference") {
                prepared[field.name] = raw ?? undefined;
                return;
            }

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
    }, [open, initialValues, sortedFields, form]);

    const handleOk = () => {
        form.validateFields().then((values) => {
            const payload: Record<string, any> = {};
            sortedFields.forEach((field) => {
                // Пропускаем readonly поля при отправке
                if (isReadonlyField(field)) return;

                const value = values[field.name];
                if (field.type === "date" && value) {
                    payload[field.name] = value.format("YYYY-MM-DD");
                } else {
                    payload[field.name] = value;
                }
            });
            onSubmit(payload);
        });
    };

    // Фильтруем поля для отображения
    const visibleFields = sortedFields.filter((field) => {
        // Пропускаем служебные поля, которые не нужно показывать в форме
        return true;
    });

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
            width={800}
        >
            <Form form={form} layout="vertical">
                {visibleFields.map((field) => {
                    const readonly = isReadonlyField(field);

                    return (
                        <Form.Item
                            key={field.name}
                            name={field.name}
                            label={field.label}
                            valuePropName={field.type === "boolean" ? "checked" : "value"}
                            rules={
                                !readonly && field.required
                                    ? [{ required: true, message: `Поле «${field.label}» обязательно` }]
                                    : []
                            }
                        >
                            {readonly ? (
                                // Для readonly полей показываем просто текст
                                <Input disabled value={initialValues?.[field.name] ?? "—"} />
                            ) : (
                                renderFieldControl(field)
                            )}
                        </Form.Item>
                    );
                })}
            </Form>
        </Modal>
    );
};
