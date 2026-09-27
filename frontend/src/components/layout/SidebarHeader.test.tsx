// src/components/layout/SidebarHeader.test.tsx
// Заголовок панели навигации: под названием продукта выводится номер релиза
// (вшит в сборку — см. vite.config.ts), в свёрнутом виде надписи скрыты.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SidebarHeader } from "./SidebarHeader";

describe("SidebarHeader", () => {
    it("показывает название и номер релиза под ним", () => {
        render(<SidebarHeader isCollapsed={false} onToggle={() => {}} />);
        expect(screen.getByText("Family Townhouse")).toBeTruthy();
        // В тестовой сборке версия не задана → «dev» (см. vitest.config.ts).
        expect(screen.getByText(__APP_VERSION__)).toBeTruthy();
    });

    it("показывает логотип перед названием", () => {
        render(<SidebarHeader isCollapsed={false} onToggle={() => {}} />);
        const logo = screen.getByAltText("FTH") as HTMLImageElement;
        expect(logo.getAttribute("src")).toBe("/FTH.svg");
    });

    it("в свёрнутом виде название и логотип не показываются", () => {
        render(<SidebarHeader isCollapsed onToggle={() => {}} />);
        expect(screen.queryByText("Family Townhouse")).toBeNull();
        expect(screen.queryByAltText("FTH")).toBeNull();
    });
});
