import { useLocation } from "react-router-dom";
import { COLORS } from "../../config/colors";
import { categories } from "../../config/menu";
import { useSidebarState } from "../../hooks/useSidebarState";
import { SidebarHeader } from "./SidebarHeader";
import { SidebarCollapsedCategory } from "./SidebarCollapsedCategory";
import { SidebarExpandedCategory } from "./SidebarExpandedCategory";

// --- БОКОВОЕ МЕНЮ (визуально повторяет админ-панель sqladmin) ---
export const Sidebar = () => {
    const location = useLocation();
    const { isCollapsed, openCategories, toggleCategory, toggleSidebar } =
        useSidebarState();

    const sidebarWidth = isCollapsed ? 72 : 260;

    return (
        <div
            style={{
                width: sidebarWidth,
                flexShrink: 0,
                minHeight: "100vh",
                background: COLORS.sidebarBg,
                borderRight: `1px solid ${COLORS.border}`,
                padding: "24px 0",
                boxSizing: "border-box",
                transition: "width 0.2s ease",
                display: "flex",
                flexDirection: "column",
                position: "sticky",
                top: 0,
                overflow: "hidden",
            }}
        >
            <SidebarHeader isCollapsed={isCollapsed} onToggle={toggleSidebar} />

            <nav style={{ flex: 1, overflow: "hidden" }}>
                {categories.map((category) =>
                    isCollapsed ? (
                        <SidebarCollapsedCategory
                            key={category.title}
                            category={category}
                            activePath={location.pathname}
                        />
                    ) : (
                        <SidebarExpandedCategory
                            key={category.title}
                            category={category}
                            activePath={location.pathname}
                            isOpen={openCategories[category.title]}
                            onToggle={() => toggleCategory(category.title)}
                        />
                    ),
                )}
            </nav>
        </div>
    );
};
