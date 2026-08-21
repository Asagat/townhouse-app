import { Link } from "react-router-dom";
import { Tooltip } from "antd";
import { COLORS } from "../../config/colors";
import type { Category } from "../../config/menu";

// --- Список иконок категории для свёрнутого состояния меню ---
export const SidebarCollapsedCategory = ({
    category,
    activePath,
}: {
    category: Category;
    activePath: string;
}) => (
    <div style={{ marginBottom: 8 }}>
        {category.items.map((item) => {
            const isActive = activePath === `/${item.key}`;
            return (
                <Tooltip
                    key={item.key}
                    title={item.label}
                    placement="right"
                    mouseEnterDelay={0.3}
                >
                    <Link
                        to={`/${item.key}`}
                        style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            padding: "10px 16px",
                            margin: "0 8px",
                            borderRadius: "6px",
                            color: isActive ? COLORS.textActive : COLORS.textMuted,
                            background: isActive ? COLORS.hoverBg : "transparent",
                            transition: "all 0.15s ease",
                            position: "relative",
                        }}
                    >
                        <i
                            className={item.icon}
                            style={{
                                fontSize: 18,
                                width: 20,
                                textAlign: "center",
                                color: isActive ? COLORS.accent : COLORS.iconMuted,
                            }}
                        />
                        {isActive && (
                            <div
                                style={{
                                    position: "absolute",
                                    left: 0,
                                    top: "50%",
                                    transform: "translateY(-50%)",
                                    width: 3,
                                    height: 24,
                                    background: COLORS.accent,
                                    borderRadius: "0 3px 3px 0",
                                }}
                            />
                        )}
                    </Link>
                </Tooltip>
            );
        })}
    </div>
);
