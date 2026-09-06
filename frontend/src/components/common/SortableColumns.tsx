// src/components/common/SortableColumns.tsx
// Панель «Отображаемые колонки»: чек-боксы видимости + перетаскивание (drag&drop)
// для изменения порядка колонок (роадмап 2.10-C). Порядок/видимость сохраняются
// в localStorage по (ресурс, роль) — см. hooks/useColumnSettings.

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
