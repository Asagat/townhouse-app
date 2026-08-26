import { Link } from "react-router-dom";
import { COLORS } from "../../config/colors";
import type { Category } from "../../config/menu";

// --- Заголовок категории с сворачиванием + список пунктов меню (развёрнутое состояние) ---
export const SidebarExpandedCategory = ({
    category,
    activePath,
    isOpen,
    onToggle,
}: {
    category: Category;
    activePath: string;
    isOpen: boolean;
    onToggle: () => void;
}) => {
    const hasActiveItem = category.items.some(
        (item) => activePath === `/${item.key}`,
    );

    return (
        <div style={{ marginBottom: 4 }}>
            <div
                onClick={onToggle}
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "10px 24px",
                    fontSize: 15,
                    cursor: "pointer",
                    userSelect: "none",
                    color: hasActiveItem ? COLORS.textActive : COLORS.textMuted,
                    fontWeight: hasActiveItem ? 600 : 500,
                    transition: "background 0.15s ease",
                }}
                onMouseEnter={(e) => {
                    e.currentTarget.style.background = COLORS.hoverBg;
                }}
                onMouseLeave={(e) => {
                    e.currentTarget.style.background = "transparent";
                }}
            >
                <span>{category.title}</span>
                <i
                    className="fa-solid fa-chevron-down"
                    style={{
                        fontSize: 11,
                        color: COLORS.textMuted,
                        transform: isOpen ? "rotate(0deg)" : "rotate(-90deg)",
                        transition: "transform 0.2s ease",
                    }}
                />
            </div>

            {isOpen && (
                <div>
                    {category.items.map((item) => {
                        const isActive = activePath === `/${item.key}`;
                        return (
                            <Link
                                key={item.key}
                                to={`/${item.key}`}
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 12,
                                    padding: "9px 24px 9px 32px",
                                    fontSize: 14,
                                    color: isActive ? COLORS.textActive : COLORS.textMuted,
                                    fontWeight: isActive ? 600 : 400,
                                    transition: "all 0.15s ease",
                                    background: isActive ? COLORS.hoverBg : "transparent",
                                }}
                                onMouseEnter={(e) => {
                                    if (!isActive) {
                                        e.currentTarget.style.background = COLORS.hoverBg;
                                    }
                                }}
                                onMouseLeave={(e) => {
                                    if (!isActive) {
                                        e.currentTarget.style.background = "transparent";
                                    }
                                }}
                            >
                                <i
                                    className={item.icon}
                                    style={{
                                        width: 16,
                                        textAlign: "center",
                                        color: isActive ? COLORS.accent : COLORS.iconMuted,
                                    }}
                                />
                                <span style={{ whiteSpace: "nowrap" }}>{item.label}</span>
                            </Link>
                        );
                    })}
                </div>
            )}
        </div>
    );
};
