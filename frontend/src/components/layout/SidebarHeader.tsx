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
            <div style={{ minWidth: 0 }}>
                {/* Логотип и название — в одной строке с `alignItems: center`, поэтому
                    вертикальный центр картинки совпадает с центром строки названия. */}
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    {/* SVG с прозрачным фоном и viewBox="0 0 1024 1024» — корректно
                        масштабируется до 32 px. */}
                    <img
                        src="/FTH.svg"
                        width={32}
                        height={32}
                        alt="FTH"
                        style={{ display: "block", flexShrink: 0 }}
                    />
                    <span
                        style={{
                            color: COLORS.textActive,
                            fontWeight: 700,
                            fontSize: 16,
                            whiteSpace: "nowrap",
                            overflow: "hidden",
                        }}
                    >
                        Family Townhouse
                    </span>
                </div>
                {/* Номер релиза (вшит в сборку, см. vite.config.ts) — под названием
                    (отступ равен ширине логотипа + зазору, чтобы стоял под текстом). */}
                <span
                    title={`Версия: ${__APP_VERSION__}`}
                    style={{
                        display: "block",
                        paddingLeft: 40,
                        color: COLORS.textMuted,
                        fontSize: 11,
                        lineHeight: 1.2,
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                    }}
                >
                    {__APP_VERSION__}
                </span>
            </div>
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
