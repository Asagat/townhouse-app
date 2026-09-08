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
 * Открывает/скачивает защищённый PDF.
 *
 * JWT передаётся только заголовком Authorization (см. authedFetch), поэтому нельзя
 * просто `window.open(url)` на рендпоинт — заголовок в новой вкладке не добавить
 * (был бы 401). Поэтому запрашиваем blob через authedFetch и скачиваем его как файл
 * <a download href=blob:…> в рамках текущей страницы. Это даёт при нажатии "PDF"
 * именно скачивание документа, и работает и в iOS-браузерах, и на десктопе.
 */
export const downloadAuthorizedPdf = async (url: string, fallbackName = "document.pdf") => {
    let blobUrl: string | null = null;
    // Таймаут на генерацию/загрузку отчёта, чтобы кнопка «PDF» не висела
    // бесконечно, если бэкенд падает при сборке файла или соединение зависло.
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 60_000);
    try {
        const resp = await authedFetch(url, { signal: controller.signal });
        if (!resp.ok) {
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
        // Предохранитель: если сервер вернул не-PDF (часто это HTML/504/ошибка),
        // не скачиваем мусор — показываем внятное сообщение.
        const type = (blob.type || "").toLowerCase();
        if (blob.size === 0 || (type && !type.includes("pdf")) && resp.status === 200) {
            message.error("PDF не сформирован (пустой/некорректный ответ). Попробуйте позже.");
            return;
        }
        // Экспонируем blob как файл-ссылку и скачиваем её из текущей страницы.
        // Никаких window.open/about:blank: скачивание идёт только по пользовательской
        // кнопке и не зависит от новых вкладок (работает и в iOS/WebView).
        blobUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = blobUrl;
        a.download = fallbackName || "document.pdf";
        a.style.display = "none";
        document.body.appendChild(a);
        a.click();
        a.remove();
        // Даём браузеру время начать скачивание, затем освобождаем объектный URL.
        window.setTimeout(() => URL.revokeObjectURL(blobUrl as string), 30_000);
        blobUrl = null;
    } catch (e) {
        if (blobUrl) URL.revokeObjectURL(blobUrl);
        const aborted = e instanceof DOMException && e.name === "AbortError";
        message.error(
            aborted
                ? "Не удалось сформировать PDF: превышен таймаут. Повторите попытку."
                : e instanceof Error
                  ? e.message
                  : "Не удалось загрузить PDF",
        );
    } finally {
        window.clearTimeout(timer);
    }
};

/**
 * Скачивает защищённый PDF (синоним downloadAuthorizedPdf) — чтобы не править все
 * точки вызова. Нажатие на «PDF»/«Скачать» инициирует скачивание документа.
 */
export const openAuthorizedPdf = downloadAuthorizedPdf;
