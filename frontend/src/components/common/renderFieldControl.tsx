// src/components/common/renderFieldControl.tsx

import { useEffect, useRef } from "react";
import { Input, InputNumber, DatePicker, Select, Switch, Form } from "antd";
import type { FormInstance } from "antd";
import type { FieldMeta } from "../../types";
import { ReferenceSelect } from "./ReferenceSelect";
import { DATE_FORMAT } from "../../config/formatters";

// Типы операций «Приход/Расход» — и по метке (value из /meta), и по имени члена enum.
// Надёжно определяем приход/расход независимо от того, в каком виде пришло значение.
const INCOME_KEYS = ["Приход в кассу", "Приход в банк", "in_cash", "in_bank"];
const EXPENSE_KEYS = ["Расход из кассы", "Расход из банка", "out_cash", "out_bank"];

const isIncomeType = (t?: string) => !!t && INCOME_KEYS.includes(t);
const isExpenseType = (t?: string) => !!t && EXPENSE_KEYS.includes(t);

/**
 * Выбор статьи аналитики для документа «Приход/Расход».
 * - Показывает статьи только соответствующего типа (приход → Доход, расход → Расход).
 * - При смене типа операции очищает статью, если она больше не подходит (страховка от
 *   несоответствия при сохранении).
 */
const AnalyticArticleSelect = ({
    form,
    value,
    onChange,
    optional,
}: {
    form: FormInstance | undefined;
    value?: number;
    onChange?: (value: number | undefined) => void;
    optional?: boolean;
}) => {
    const transactionType: string | undefined = Form.useWatch("transaction_type", form);

    // При смене типа операции (приход↔расход) очищаем ранее выбранную статью, чтобы
    // исключить несоответствие при сохранении.
    const prevTypeRef = useRef<string | undefined>(undefined);
    useEffect(() => {
        const prev = prevTypeRef.current;
        prevTypeRef.current = transactionType;
        if (!form || !transactionType || form.isFieldTouched === undefined) return;
        // Только когда тип реально сменил знак (не первая установка при открытии).
        const prevIncome = isIncomeType(prev);
        const curIncome = isIncomeType(transactionType);
        const prevExpense = isExpenseType(prev);
        const curExpense = isExpenseType(transactionType);
        const signChanged =
            (prevIncome && curExpense) || (prevExpense && curIncome);
        if (signChanged) {
            form.setFieldValue("article_id", undefined);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [transactionType, form]);

    let filterFn: ((item: any) => boolean) | undefined;
    if (isIncomeType(transactionType)) {
        filterFn = (item: any) => item.kind === "Доход";
    } else if (isExpenseType(transactionType)) {
        filterFn = (item: any) => item.kind === "Расход";
    }

    return (
        <ReferenceSelect
            resource="analytic_articles"
            filterFn={filterFn}
            value={value}
            onChange={onChange}
            optional={optional}
        />
    );
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
                return (
                    <AnalyticArticleSelect
                        form={form}
                        optional={!field.required}
                    />
                );
            }
            return (
                <ReferenceSelect
                    resource={field.reference!}
                    optional={!field.required}
                />
            );
        default:
            return <Input />;
    }
};
