// src/components/common/SortableColumns.test.tsx
// RTL-тесты настройки колонок списка (2.10): панель «Отображаемые колонки»
// (чек-боксы видимости + ручки перетаскивания) и заголовок колонки для таблицы
// (ColumnDragTitle) в связке с ячейкой заголовка antd Table.
//
// Перетаскивание dnd-kit в jsdom не воспроизводим (нестабильно) — проверяем статику
// и клики: отрисовку подписей/ручек, вызов onToggle при переключении чек-бокса и
// «прозрачность» короткого клика по заголовку (сортировка продолжает работать).
// Ресайз-ручка живёт в ResizableHeader (вынесена туда, см. комментарий в шапке
// SortableColumns) — здесь проверяем её наличие в ячейке заголовка.

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DndContext } from "@dnd-kit/core";
import { SortableContext } from "@dnd-kit/sortable";

import { SortableColumns, ColumnDragTitle, type SortableColumnItem } from "./SortableColumns";
import { ResizableHeaderCell, headerResizeProps } from "./ResizableHeader";

const ITEMS: SortableColumnItem[] = [
    { key: "id", label: "ID", checked: true },
    { key: "amount", label: "Сумма", checked: false },
    { key: "notes", label: "Примечание", checked: true },
];

describe("SortableColumns — панель «Отображаемые колонки»", () => {
    it("отрисовывает чек-боксы и ручки перетаскивания для всех колонок", () => {
        render(<SortableColumns items={ITEMS} onToggle={vi.fn()} onMove={vi.fn()} />);

        expect((screen.getByLabelText("ID") as HTMLInputElement).checked).toBe(true);
        expect((screen.getByLabelText("Сумма") as HTMLInputElement).checked).toBe(false);
        expect((screen.getByLabelText("Примечание") as HTMLInputElement).checked).toBe(true);

        // По одной ручке (HolderOutlined) на строку + подсказка.
        expect(document.querySelectorAll(".anticon-holder").length).toBe(ITEMS.length);
        expect(screen.getAllByTitle("Перетащите, чтобы изменить порядок").length).toBe(
            ITEMS.length,
        );
    });

    it("клик по чек-боксу вызывает onToggle с ключом и новым состоянием", () => {
        const onToggle = vi.fn();
        render(<SortableColumns items={ITEMS} onToggle={onToggle} onMove={vi.fn()} />);

        fireEvent.click(screen.getByLabelText("Сумма"));
        expect(onToggle).toHaveBeenCalledWith("amount", true);

        fireEvent.click(screen.getByLabelText("ID"));
        expect(onToggle).toHaveBeenCalledWith("id", false);
    });
});

describe("ColumnDragTitle — заголовок колонки таблицы", () => {
    it("рендерит подпись и пропускает короткий клик (сортировка не блокируется)", () => {
        const onSort = vi.fn();
        render(
            <DndContext>
                <SortableContext items={["full_name"]}>
                    <div onClick={onSort}>
                        <ColumnDragTitle columnKey="full_name">ФИО</ColumnDragTitle>
                    </div>
                </SortableContext>
            </DndContext>,
        );

        const title = screen.getByText("ФИО") as HTMLElement;
        expect(title.getAttribute("title")).toBe("Перетащите, чтобы изменить порядок колонок");

        // dnd-kit вешается на pointer-события, поэтому обычный клик доходит до хэндлера.
        fireEvent.click(title);
        expect(onSort).toHaveBeenCalledTimes(1);
    });

    it("ячейка заголовка таблицы содержит заголовок и ресайз-ручку (наличие)", () => {
        const onSort = vi.fn();
        const onResize = vi.fn();
        render(
            <DndContext>
                <SortableContext items={["full_name"]}>
                    <table>
                        <thead>
                            <tr>
                                <ResizableHeaderCell
                                    {...headerResizeProps("full_name", onResize)}
                                    onClick={onSort}
                                >
                                    <ColumnDragTitle columnKey="full_name">ФИО</ColumnDragTitle>
                                </ResizableHeaderCell>
                            </tr>
                        </thead>
                    </table>
                </SortableContext>
            </DndContext>,
        );

        // Ручка изменения ширины — на правом краю <th>.
        const handle = screen.getByTitle("Изменить ширину колонки");
        expect((handle as HTMLElement).style.position).toBe("absolute");

        // Клик по заголовку по-прежнему доходит до сортировки.
        fireEvent.click(screen.getByText("ФИО"));
        expect(onSort).toHaveBeenCalledTimes(1);
    });
});
