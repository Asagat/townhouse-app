// src/components/common/renderFieldControl.tsx

import { Input, InputNumber, DatePicker, Select, Switch, Form } from "antd";
import type { FormInstance } from "antd";
import type { FieldMeta } from "../../types";
import { ReferenceSelect } from "./ReferenceSelect";
import { DATE_FORMAT } from "../../config/formatters";

// Типы операций «Приход/Расход» — значения enum TransactionTypeEnum (в форме хранятся
// как метки: value+label совпадают).
const INCOME_TYPES = ["Приход в кассу", "Приход в банк"];
const EXPENSE_TYPES = ["Расход из кассы", "Расход из банка"];

/**
 * Выбор статьи аналитики, фильтруемой по типу операции документа «Приход/Расход»:
 * приход (в кассу/в банк) — только статьи Доход; расход (из кассы/из банка) — только Расход.
 */
const AnalyticArticleSelect = ({ form }: { form: FormInstance | undefined }) => {
    const transactionType: string | undefined = Form.useWatch("transaction_type", form);

    let filterFn: ((item: any) => boolean) | undefined;
    if (INCOME_TYPES.includes(transactionType as string)) {
        filterFn = (item: any) => item.kind === "Доход";
    } else if (EXPENSE_TYPES.includes(transactionType as string)) {
        filterFn = (item: any) => item.kind === "Расход";
    }

    return <ReferenceSelect resource="analytic_articles" filterFn={filterFn} />;
};

export const renderFieldControl = (field: FieldMeta, form?: FormInstance) => {
    switch (field.type) {
        case "text":
            return <Input.TextArea rows={3} />;
        case "integer":
            return <InputNumber style={{ width: "100%" }} precision={0} />;
        case "decimal":
            return <InputNumber style={{ width: "100%" }} step={0.01} />;
        case "boolean":
            return <Switch />;
        case "date":
            return <DatePicker style={{ width: "100%" }} format={DATE_FORMAT} />;
        case "enum":
            return (
                <Select
                    style={{ width: "100%" }}
                    options={(field.choices ?? []).map((c) => ({
                        value: c.value,
                        label: c.label,
                    }))}
                />
            );
        case "reference":
            // Статья аналитики зависит от выбранного типа операции (приход/расход).
            if (field.reference === "analytic_articles") {
                return <AnalyticArticleSelect form={form} />;
            }
            return <ReferenceSelect resource={field.reference!} />;
        default:
            return <Input />;
    }
};
