// src/auth/http.ts
// Axios-инстанс (без baseURL), который добавляет JWT в Authorization.
// Refine-dataProvider и useCustom передают ПОЛНЫЙ путь (/api/...), поэтому
// baseURL здесь не ставим — иначе получилось бы двойное /api/api.

import axios from "axios";
import type { AxiosError } from "axios";
import { clearToken, getToken } from "./token";

export const apiUrl = "/api";

export const http = axios.create();

http.interceptors.request.use((config) => {
    const token = getToken();
    if (token) {
        config.headers = config.headers || {};
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

http.interceptors.response.use(
    (response) => response,
    (error: AxiosError) => {
        // 401 — токен истёк/невалиден: сбрасываем и перенаправляем на вход.
        if (error.response && error.response.status === 401 && window.location.pathname !== "/login") {
            clearToken();
            window.location.href = "/login";
        }
        return Promise.reject(error);
    },
);

// Авторизованный вариант fetch (добавляет Bearer-токен) для прямых вызовов API.
export const authedFetch = (input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> => {
    const token = getToken();
    const headers = new Headers(init.headers ?? {});
    if (token) {
        headers.set("Authorization", `Bearer ${token}`);
    }
    if (init.body && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }
    return fetch(input, { ...init, headers });
};
