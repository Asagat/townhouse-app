// --- ЦВЕТА (палитра в оттенках зелёного) ---
export const BRAND = {
    primary: "#268061", // тёмно-зелёный (акцент/основной)
    primaryHover: "#2fc33c",
    primaryActive: "#1b9625",
    accent: "#7ed98b", // светло-зелёный (подсветка)
    fade: "#d8f5dd", // очень светлый зелёный для фоновых плашек
};

export const COLORS = {
    // Фон тёмного сайдбара — глубокий зелёный
    sidebarBg: "#0f4d38",
    border: "#1c3a26",
    textMuted: "#c1e6ce",
    textActive: "#ffffff",
    iconMuted: "#5f8f6e",
    accent: BRAND.accent,
    hoverBg: "rgba(126,217,139,0.10)",
};

// Основной цвет antd-темы (кнопки, таблицы, пагинация и т.д.)
export const ANT_PRIMARY = BRAND.primary;
