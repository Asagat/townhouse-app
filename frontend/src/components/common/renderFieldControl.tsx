// src/components/common/renderFieldControl.tsx

import { Input, InputNumber, DatePicker, Select, Switch } from "antd";
import type { FieldMeta } from "../../types";
import { ReferenceSelect } from "./ReferenceSelect";
import { DATE_FORMAT } from "../../config/formatters";

export const renderFieldControl = (field: FieldMeta) => {
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
            return <ReferenceSelect resource={field.reference!} />;
        default:
            return <Input />;
    }
};
