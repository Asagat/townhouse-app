import type { CSSProperties, DragEvent, MouseEvent } from "react";

interface ColumnHeaderProps {
    label: string;
    dragging?: boolean;
    onDragStart: (e: DragEvent) => void;
    onDragEnd: () => void;
    onResizeStart: (e: MouseEvent) => void;
}

/**
 * Заголовок колонки с поддержкой:
 *  - перетаскивания для изменения порядка (за ручку "≡"),
 *  - изменения ширины колонки (за правый край).
 * Сортировка остаётся на AntD Table (клик по заголовку колонки с sorter),
 * drop/рисование порядка обрабатывается на всей ячейке заголовка (см. onHeaderCell).
 */
export const ColumnHeader = ({
    label,
    dragging,
    onDragStart,
    onDragEnd,
    onResizeStart,
}: ColumnHeaderProps) => {
    const containerStyle: CSSProperties = {
        display: "inline-flex",
        alignItems: "center",
        width: "100%",
        userSelect: "none",
        paddingRight: 6,
    };

    return (
        <div style={containerStyle}>
            <span
                draggable
                title="Перетащите, чтобы изменить порядок колонок"
                onDragStart={onDragStart}
                onDragEnd={onDragEnd}
                style={{
                    cursor: dragging ? "grabbing" : "grab",
                    color: "#8c8c8c",
                    marginRight: 4,
                    fontSize: 12,
                    flexShrink: 0,
                }}
            >
                ≡
            </span>
            <span style={{ flex: 1, whiteSpace: "nowrap" }}>{label}</span>
            <span
                title="Потяните, чтобы изменить ширину колонки"
                onMouseDown={(e) => onResizeStart(e)}
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
