// src/auth/http.ts
// Axios-инстанс (без baseURL), который добавляет JWT в Authorization.
// Refine-dataProvider и useCustom передают ПОЛНЫЙ путь (/api/...), поэтому
// baseURL здесь не ставим — иначе получилось бы двойное /api/api.

import axios from "axios";
import type { AxiosError } from "axios";
import { message } from "antd";
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

/**
 * Открывает защищённый PDF в новой вкладке.
 *
 * Простой `window.open(url)` не работает: JWT передаётся только заголовком
 * Authorization (см. authedFetch), а в новой вкладке заголовок не добавить —
 * сервер вернул бы 401 «Требуется авторизация». Поэтому:
 *   1) синхронно открываем пустую вкладку (в рамках клика — иначе сработает
 *      блокировщик всплывающих окон);
 *   2) запрашиваем PDF через authedFetch;
 *   3) подставляем blob-URL в уже открытую вкладку.
 * Если вкладка заблокирована — скачиваем файл напрямую (fallback).
 */
export const openAuthorizedPdf = async (url: string, fallbackName = "document.pdf") => {
    const win = window.open("", "_blank");
    try {
        const resp = await authedFetch(url);
        if (!resp.ok) {
            win?.close();
            let detail = `Не удалось загрузить PDF (${resp.status})`;
            try {
                const body = await resp.json();
                if (body?.detail) detail = String(body.detail);
            } catch {
                // тело не JSON — оставляем сообщение по умолчанию
            }
            message.error(detail);
            return;
        }
        const blob = await resp.blob();
        const objectUrl = URL.createObjectURL(blob);
        // Освобождаем blob после того, как вкладка успеет открыть PDF.
        const revoke = () => URL.revokeObjectURL(objectUrl);
        if (win) {
            win.location.href = objectUrl;
        } else {
            // Всплывающее окно заблокировано — скачиваем файл напрямую.
            const a = document.createElement("a");
            a.href = objectUrl;
            a.download = fallbackName;
            document.body.appendChild(a);
            a.click();
            a.remove();
        }
        setTimeout(revoke, 60_000);
    } catch (e) {
        win?.close();
        message.error(e instanceof Error ? e.message : "Не удалось загрузить PDF");
    }
};
