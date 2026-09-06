// src/components/common/ResizableHeader.tsx
// Ресайз ширины колонок таблицы (роадмап 2.1) через кастомную ячейку заголовка
// antd Table (components.header.cell): ручка на всю высоту правого края <th>.
//
// Ширина считается дельтой движения указателя от стартовой ширины <th>
// (getBoundingClientRect) — работает при любом scroll таблицы, включая
// scroll={{ x: 'max-content' }}. Ручка использует pointer events с захватом
// и не конфликтует ни с перетаскиванием заголовков (dnd-kit), ни с сортировкой
// по клику.

import { useRef } from "react";

/**
 * Пропсы для onHeaderCell колонки: ячейка заголовка узнаёт свою колонку и коллбэк
 * ресайза. Использование: `onHeaderCell: () => headerResizeProps(col.key, setWidth)`.
 */
export const headerResizeProps = (columnKey: string, onResize: (key: string, px: number) => void) => ({
    colKey: columnKey,
    onResize,
});

export const ResizableHeaderCell = (props: any) => {
    const { children, colKey, onResize, style, ...rest } = props;
    const dragState = useRef<{ startX: number; startWidth: number } | null>(null);

    const canResize = !!colKey && colKey !== "actions" && typeof onResize === "function";

    const handlePointerDown = (e: React.PointerEvent<HTMLSpanElement>) => {
        if (e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        const th = (e.currentTarget as HTMLElement).closest("th");
        const startWidth = th ? th.getBoundingClientRect().width : 120;
        dragState.current = { startX: e.clientX, startWidth };
        e.currentTarget.setPointerCapture(e.pointerId);
    };

    const handlePointerMove = (e: React.PointerEvent<HTMLSpanElement>) => {
        const st = dragState.current;
        if (!st) return;
        const next = Math.max(50, st.startWidth + (e.clientX - st.startX));
        onResize(colKey, next);
    };

    const handlePointerEnd = () => {
        dragState.current = null;
    };

    return (
        <th {...rest} style={{ position: "relative", ...(style as React.CSSProperties | undefined) }}>
            {children}
            {canResize && (
                <span
                    onPointerDown={handlePointerDown}
                    onPointerMove={handlePointerMove}
                    onPointerUp={handlePointerEnd}
                    onPointerCancel={handlePointerEnd}
                    onClick={(e) => e.stopPropagation()}
                    style={{
                        position: "absolute",
                        top: 0,
                        right: 0,
                        bottom: 0,
                        width: 12,
                        cursor: "col-resize",
                        touchAction: "none",
                        userSelect: "none",
                        zIndex: 5,
                    }}
                    title="Изменить ширину колонки"
                />
            )}
        </th>
    );
};

/** components для antd Table: подставляет кастомные ячейки заголовка. */
export const tableHeaderComponents = {
    header: { cell: ResizableHeaderCell },
};
