import type { CSSProperties, MouseEvent } from "react";

interface ColumnHeaderProps {
    label: string;
    onResizeStart: (e: MouseEvent) => void;
}

/**
 * Заголовок колонки с поддержкой изменения ширины колонки
 * (потяните за правый край заголовка).
 */
export const ColumnHeader = ({ label, onResizeStart }: ColumnHeaderProps) => {
    const containerStyle: CSSProperties = {
        display: "inline-flex",
        alignItems: "center",
        width: "100%",
        userSelect: "none",
        paddingRight: 6,
    };

    return (
        <div style={containerStyle}>
            <span style={{ flex: 1, whiteSpace: "nowrap" }}>{label}</span>
            <span
                title="Потяните, чтобы изменить ширину колонки"
                onMouseDown={onResizeStart}
                style={{
                    width: 6,
                    marginLeft: 4,
                    cursor: "col-resize",
                    flexShrink: 0,
                    position: "relative",
                    alignSelf: "stretch",
                }}
            />
        </div>
    );
};
