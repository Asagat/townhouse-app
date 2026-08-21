import { useEffect, useState } from "react";
import { categories } from "../config/menu";

const COLLAPSED_STORAGE_KEY = "sidebarCollapsed";
const CATEGORIES_STORAGE_KEY = "sidebarCategories";

const allCategoriesOpen = () =>
    Object.fromEntries(categories.map((c) => [c.title, true]));

// --- Состояние бокового меню (свёрнуто/развёрнуто, открытые категории) с сохранением в localStorage ---
export const useSidebarState = () => {
    const [isCollapsed, setIsCollapsed] = useState(() => {
        const saved = localStorage.getItem(COLLAPSED_STORAGE_KEY);
        return saved === "true";
    });

    const [openCategories, setOpenCategories] = useState<Record<string, boolean>>(
        () => {
            const saved = localStorage.getItem(CATEGORIES_STORAGE_KEY);
            if (saved) {
                try {
                    return JSON.parse(saved);
                } catch {
                    return allCategoriesOpen();
                }
            }
            return allCategoriesOpen();
        },
    );

    useEffect(() => {
        localStorage.setItem(COLLAPSED_STORAGE_KEY, String(isCollapsed));
    }, [isCollapsed]);

    useEffect(() => {
        localStorage.setItem(CATEGORIES_STORAGE_KEY, JSON.stringify(openCategories));
    }, [openCategories]);

    const toggleCategory = (title: string) => {
        if (isCollapsed) return; // В свернутом виде не сворачиваем категории
        setOpenCategories((prev) => ({ ...prev, [title]: !prev[title] }));
    };

    const toggleSidebar = () => {
        setIsCollapsed(!isCollapsed);
        // При разворачивании показываем все категории
        if (isCollapsed) {
            setOpenCategories(allCategoriesOpen());
        }
    };

    return { isCollapsed, openCategories, toggleCategory, toggleSidebar };
};
