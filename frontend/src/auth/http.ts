// src/auth/http.ts
// Axios-инстанс, который добавляет JWT в Authorization для всех запросов к API.

import axios from "axios";
import type { AxiosError } from "axios";
import { clearToken, getToken } from "./token";

export const apiUrl = "/api";

export const http = axios.create({ baseURL: apiUrl });

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
