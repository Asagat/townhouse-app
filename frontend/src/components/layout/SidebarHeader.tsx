import { Button } from "antd";
import { MenuFoldOutlined, MenuUnfoldOutlined } from "@ant-design/icons";
import { COLORS } from "../../config/colors";

export const SidebarHeader = ({
    isCollapsed,
    onToggle,
}: {
    isCollapsed: boolean;
    onToggle: () => void;
}) => (
    <div
        style={{
            display: "flex",
            alignItems: "center",
            justifyContent: isCollapsed ? "center" : "space-between",
            padding: isCollapsed ? "0 16px" : "0 20px",
            marginBottom: 28,
            gap: isCollapsed ? 0 : 8,
        }}
    >
        {!isCollapsed && (
            <span
                style={{
                    color: COLORS.textActive,
                    fontWeight: 700,
                    fontSize: 18,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                }}
            >
                Family Townhouse
            </span>
        )}
        <Button
            type="text"
            icon={isCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={onToggle}
            style={{
                color: COLORS.textMuted,
                fontSize: 16,
                padding: 4,
                height: "auto",
                minWidth: isCollapsed ? "auto" : undefined,
            }}
        />
    </div>
);
