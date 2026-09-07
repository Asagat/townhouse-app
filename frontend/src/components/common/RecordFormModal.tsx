// src/components/common/RecordFormModal.tsx

import { useEffect, useMemo } from "react";
import { Modal, Form, Input, Button } from "antd";
import dayjs from "dayjs";
import type { FieldMeta } from "../../types";
import { renderFieldControl } from "./renderFieldControl";
import { sortFieldsForForm } from "../../config/columns";
import { formatDate, formatDateTime, formatMoney, formatPhone, isMoneyFieldName } from "../../config/formatters";

interface RecordFormModalProps {
    open: boolean;
    title: string;
    fields: FieldMeta[];
    initialValues?: Record<string, any>;
    confirmLoading: boolean;
    onCancel: () => void;
    onSubmit: (values: Record<string, any>) => void;
    resourceName?: string;
    /** Режим «только просмотр»: поля отключены, сохранение недоступно. */
    readonly?: boolean;
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
    readonly = false,
}: RecordFormModalProps) => {
    const [form] = Form.useForm();

    // Сортируем поля в соответствии с конфигурацией
    const sortedFields = useMemo(() => {
        return resourceName ? sortFieldsForForm(fields, resourceName) : fields;
    }, [fields, resourceName]);

    // Определяем, является ли поле readonly (только для просмотра)
    const isReadonlyField = (field: FieldMeta): boolean => {
        const readonlyFields = ['id', 'created_at', 'accruals_count', 'total_amount', 'title'];
        return readonlyFields.includes(field.name);
    };

    // Текстовое представление поля в режиме просмотра: дата — «DD.MM.YYYY»,
    // телефон — «+7(XXX)XXX-XX-XX», деньги — с разделителями и 2 знаками,
    // булево — «Да/Нет», reference — текстовое значение связанной записи.
    const _pickLabel = (obj: any): string | null => {
        if (obj == null) return null;
        if (typeof obj !== "object") {
            // Уже строка/текст — берём как есть.
            return typeof obj === "string" ? obj : null;
        }
        const keys = [
            "name",
            "full_name",
            "title",
            "account_name",
            "account_number",
            "label",
            "value",
        ];
        for (const k of keys) {
            const v = obj[k];
            if (v !== undefined && v !== null && v !== "") {
                return String(v);
            }
        }
        return null;
    };
    const fieldViewText = (field: FieldMeta): string => {
        const raw = initialValues?.[field.name];
        if (field.type === "date") return formatDate(raw);
        if (field.type === "datetime") return formatDateTime(raw);
        if (field.type === "boolean") return raw ? "Да" : "Нет";
        if (isMoneyFieldName(field.name)) return formatMoney(raw);
        if (field.name === "phone") return formatPhone(raw);

        // Reference-поле: показываем не id, а подставленное название связанной записи.
        // Сначала пробуем готовый «*_name»-атрибут из сериализатора, затем вложенный
        // объект по корню поля (например cash_point_id -> record.cash_point.name).
        if (field.type === "reference") {
            const nameAttr = `${field.name.replace(/_id$/, "")}_name`;
            const flat = initialValues?.[nameAttr];
            if (flat !== undefined && flat !== null && flat !== "") {
                return String(flat);
            }
            const root = field.name.replace(/_id$/, "");
            const label = _pickLabel(initialValues?.[root]);
            if (label) return label;
            // Нет подставленного значения — хотя бы не оставлять связку «голым» id.
            if (raw != null) return String(raw);
            return "—";
        }
        return String(raw ?? "—");
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
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open]);

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

    return (
        <Modal
            title={title}
            open={open}
            onCancel={onCancel}
            onOk={readonly ? undefined : handleOk}
            confirmLoading={confirmLoading}
            okText={readonly ? "Закрыть" : "Сохранить"}
            cancelText="Отмена"
            footer={
                readonly
                    ? [
                          <Button key="close" type="primary" onClick={onCancel}>
                              Закрыть
                          </Button>,
                      ]
                    : undefined
            }
            destroyOnClose
            width={800}
        >
            <Form
                form={form}
                layout="vertical"
                disabled={readonly}
                className={readonly ? "form-view-mode" : undefined}
            >
                {sortedFields.map((field) => {
                    const fieldReadonly = readonly || isReadonlyField(field);

                    // В режиме просмотра поле НЕ привязываем к хранилищу формы (без name):
                    // иначе Form.Item подменяет наш отформатированный текст значением из
                    // формы (dayjs для дат, число для цены и т.п.).
                    const itemProps: Record<string, any> = { label: field.label };
                    if (!fieldReadonly) {
                        itemProps.name = field.name;
                        itemProps.valuePropName =
                            field.type === "boolean" ? "checked" : "value";
                        if (
                            field.type === "reference" &&
                            field.reference === "analytic_articles"
                        ) {
                            itemProps.dependencies = ["transaction_type"];
                        }
                        const rules: any[] = [];
                        if (field.required) {
                            rules.push({
                                required: true,
                                message: `Поле «${field.label}» обязательно`,
                            });
                        }
                        // Денежные поля — только положительные значения. Для «Приход/Расход»
                        // уменьшение суммы выполняется правкой документа или противоположным
                        // документом (сервер тоже проверяет).
                        if (field.type === "decimal" && isMoneyFieldName(field.name)) {
                            rules.push({
                                validator: (_: any, value: any) =>
                                    value == null || value === "" || Number(value) > 0
                                        ? Promise.resolve()
                                        : Promise.reject(
                                              new Error(
                                                  field.name === "amount" &&
                                                      (resourceName === "transactions" ||
                                                          resourceName === "payments")
                                                      ? "Сумма документа должна быть положительной: уменьшение — правкой документа или противоположным (расход/приход)"
                                                      : "Значение должно быть положительным",
                                              ),
                                          ),
                            });
                        }
                        if (rules.length > 0) {
                            itemProps.rules = rules;
                        }
                    }

                    return (
                        <Form.Item key={field.name} {...itemProps}>
                            {fieldReadonly ? (
                                // Для readonly полей показываем просто текст;
                                // булево — «Да/Нет», дата — прописью, деньги — с разделителями.
                                <Input disabled value={fieldViewText(field)} />
                            ) : (
                                renderFieldControl(field, form, resourceName)
                            )}
                        </Form.Item>
                    );
                })}
            </Form>
        </Modal>
    );
};
