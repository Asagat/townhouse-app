// src/auth/authProvider.ts
// Refine authProvider: вход/выход, проверка авторизации и текущей личности.

import type { AuthProvider } from "@refinedev/core";
import { clearToken, getIdentity, getToken, setIdentity, setToken } from "./token";
import type { Identity } from "./token";
import { apiUrl } from "./http";

export const authProvider: AuthProvider = {
    login: async ({ username, password }) => {
        try {
            const res = await fetch(`${apiUrl}/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password }),
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                const message = data?.detail ?? "Неверный логин или пароль";
                return {
                    success: false,
                    error: { name: "Login", message },
                };
            }
            const data = await res.json();
            setToken(data.access_token);
            setIdentity(data.user as Identity);
            return { success: true, redirectTo: "/" };
        } catch {
            return {
                success: false,
                error: { name: "Login", message: "Не удалось выполнить вход" },
            };
        }
    },

    logout: async () => {
        clearToken();
        return { success: true, redirectTo: "/login" };
    },

    check: async () => {
        if (getToken()) {
            return { authenticated: true };
        }
        return { authenticated: false, redirectTo: "/login" };
    },

    onError: async (error) => {
        // 401 от API обрабатывается в http.ts (редирект на /login).
        if (error?.statusCode === 401) {
            clearToken();
            return { logout: true };
        }
        return {};
    },

    getIdentity: async () => {
        return getIdentity() ?? undefined;
    },
};
