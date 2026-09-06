// src/components/common/SortableColumns.tsx
// Настройка колонок списка: панель «Отображаемые колонки» (чек-боксы видимости +
// drag&drop порядка, роадмап 2.10-C) и заголовки таблицы — drag&drop для порядка
// и ручка ресайза ширины (роадмап 2.1). Сохраняется в localStorage по (ресурс, роль)
// — см. hooks/useColumnSettings.

import {
    DndContext,
    PointerSensor,
    closestCenter,
    useSensor,
    useSensors,
    type DragEndEvent,
} from "@dnd-kit/core";
import {
    SortableContext,
    useSortable,
    verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Checkbox } from "antd";
import { HolderOutlined } from "@ant-design/icons";
import { useRef } from "react";

export interface SortableColumnItem {
    key: string;
    label: string;
    checked: boolean;
}

const SortableRow = ({
    item,
    onToggle,
}: {
    item: SortableColumnItem;
    onToggle: (key: string, checked: boolean) => void;
}) => {
    const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
        useSortable({ id: item.key });

    const style: React.CSSProperties = {
        transform: CSS.Transform.toString(transform),
        transition,
        display: "flex",
        alignItems: "center",
        gap: 4,
        padding: "2px 0",
        ...(isDragging ? { opacity: 0.4 } : {}),
    };

    return (
        <div ref={setNodeRef} style={style}>
            <span
                {...attributes}
                {...listeners}
                style={{ cursor: "grab", color: "#999", flex: "0 0 auto" }}
                title="Перетащите, чтобы изменить порядок"
            >
                <HolderOutlined />
            </span>
            <Checkbox
                checked={item.checked}
                onChange={(e) => onToggle(item.key, e.target.checked)}
            >
                {item.label}
            </Checkbox>
        </div>
    );
};

/**
 * Заголовок колонки таблицы, который можно перетаскивать для изменения порядка
 * (альтернатива панели «Колонки»). Должен находиться внутри SortableContext,
 * оборачивающего таблицу (см. GenericList). Короткий клик без перемещения
 * не начинает drag — сортировка по заголовку продолжает работать.
 */
export const ColumnDragTitle = ({
    columnKey,
    children,
}: {
    columnKey: string;
    children: React.ReactNode;
}) => {
    const { attributes, listeners, setNodeRef, isDragging, transform, transition } =
        useSortable({ id: columnKey });

    const style: React.CSSProperties = {
        transform: CSS.Transform.toString(transform),
        transition,
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        cursor: "grab",
        userSelect: "none",
        opacity: isDragging ? 0.55 : 1,
    };

    return (
        <span
            ref={setNodeRef}
            {...attributes}
            {...listeners}
            style={style}
            title="Перетащите, чтобы изменить порядок колонок"
        >
            {children}
        </span>
    );
};

/**
 * Ручка ресайза ширины колонки на правом краю заголовка (роадмап 2.1).
 * Ширина считается дельтой движения указателя от стартовой ширины заголовка
 * (`th.getBoundingClientRect().width`) — работает при любом scroll таблицы,
 * включая `scroll={{ x: 'max-content' }}`.
 * pointer-события ручки не запускают ни drag колонки (dnd-kit), ни сортировку по клику.
 */
const ColumnResizeHandle = ({
    columnKey,
    onResize,
}: {
    columnKey: string;
    onResize: (columnKey: string, px: number) => void;
}) => {
    const dragState = useRef<{ startX: number; startWidth: number } | null>(null);

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
        const next = st.startWidth + (e.clientX - st.startX);
        onResize(columnKey, Math.max(50, next));
    };

    const finish = () => {
        dragState.current = null;
    };

    return (
        <span
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={finish}
            onPointerCancel={finish}
            onClick={(e) => e.stopPropagation()}
            style={{
                flex: "0 0 auto",
                width: 10,
                height: "100%",
                cursor: "col-resize",
                touchAction: "none",
                userSelect: "none",
                alignSelf: "stretch",
                marginLeft: 2,
            }}
            title="Изменить ширину колонки"
        />
    );
};

/**
 * Заголовок колонки таблицы: перетаскивание (drag&drop порядка) + ресайз ширины.
 * Для «закреплённых» колонок (`draggable=false`, напр. ID) — только ресайз.
 * Должен находиться внутри SortableContext, оборачивающего таблицу (см. GenericList).
 */
export const ColumnHeader = ({
    columnKey,
    label,
    draggable = true,
    onResize,
}: {
    columnKey: string;
    label: React.ReactNode;
    draggable?: boolean;
    onResize?: (columnKey: string, px: number) => void;
}) => {
    return (
        <span
            style={{
                display: "inline-flex",
                alignItems: "center",
                width: "100%",
            }}
        >
            {draggable ? (
                <ColumnDragTitle columnKey={columnKey}>{label}</ColumnDragTitle>
            ) : (
                <span style={{ userSelect: "none" }}>{label}</span>
            )}
            {onResize && <ColumnResizeHandle columnKey={columnKey} onResize={onResize} />}
        </span>
    );
};

export const SortableColumns = ({
    items,
    onToggle,
    onMove,
}: {
    items: SortableColumnItem[];
    onToggle: (key: string, checked: boolean) => void;
    onMove: (fromIndex: number, toIndex: number) => void;
}) => {
    const sensors = useSensors(
        useSensor(PointerSensor, {
            // Активация перетаскивания после небольшого смещения — клики по чек-боксу
            // (и по строке) не должны сразу начинать drag.
            activationConstraint: { distance: 5 },
        }),
    );

    const handleDragEnd = (event: DragEndEvent) => {
        const { active, over } = event;
        if (!over || active.id === over.id) return;
        const oldIndex = items.findIndex((i) => i.key === active.id);
        const newIndex = items.findIndex((i) => i.key === over.id);
        if (oldIndex < 0 || newIndex < 0) return;
        onMove(oldIndex, newIndex);
    };

    return (
        <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
        >
            <SortableContext items={items.map((i) => i.key)} strategy={verticalListSortingStrategy}>
                {items.map((item) => (
                    <SortableRow key={item.key} item={item} onToggle={onToggle} />
                ))}
            </SortableContext>
        </DndContext>
    );
};
