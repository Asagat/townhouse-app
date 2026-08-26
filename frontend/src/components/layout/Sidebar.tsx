import { useLocation } from "react-router-dom";
import { useLogout, useGetIdentity } from "@refinedev/core";
import { Button, Tooltip } from "antd";
import { LogoutOutlined, UserOutlined } from "@ant-design/icons";
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
    const { mutate: logout } = useLogout();
    const { data: identity } = useGetIdentity<any>();

    const sidebarWidth = isCollapsed ? 72 : 260;

    const displayName =
        identity?.full_name || identity?.username || identity?.role_name || identity?.role || "";

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

            <div
                style={{
                    borderTop: `1px solid ${COLORS.border}`,
                    padding: isCollapsed ? "12px 12px" : "16px",
                    display: "flex",
                    flexDirection: isCollapsed ? "column" : "column",
                    gap: 8,
                    alignItems: isCollapsed ? "center" : "stretch",
                }}
            >
                {!isCollapsed && (
                    <div style={{ fontSize: 13, color: "#66806b", overflow: "hidden", textOverflow: "ellipsis" }}>
                        <UserOutlined style={{ marginRight: 6 }} />
                        {displayName}
                    </div>
                )}
                <Tooltip title={isCollapsed ? "Выйти" : undefined} placement="right">
                    <Button
                        onClick={() => logout()}
                        icon={<LogoutOutlined />}
                        size="small"
                        style={{
                            width: isCollapsed ? "100%" : "100%",
                            justifyContent: "center",
                        }}
                    >
                        {!isCollapsed && "Выйти"}
                    </Button>
                </Tooltip>
            </div>
        </div>
    );
};
