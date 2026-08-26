// src/auth/token.ts
// Хранилище JWT-токена (localStorage) + текущего пользователя.

const TOKEN_KEY = "townhouse_token";
const USER_KEY = "townhouse_user";

export interface Identity {
    id: number;
    username: string;
    full_name: string | null;
    role: string;
    role_name: string;
}

export const getToken = (): string | null => localStorage.getItem(TOKEN_KEY);

export const setToken = (token: string): void => localStorage.setItem(TOKEN_KEY, token);

export const clearToken = (): void => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
};

export const getIdentity = (): Identity | null => {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
        return JSON.parse(raw) as Identity;
    } catch {
        return null;
    }
};

export const setIdentity = (user: Identity): void => {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
};
