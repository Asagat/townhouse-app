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

// --- Истёкшая/невалидная сессия (401) ---
// Пользователю показываем понятный текст и просим войти заново вместо технического
// «Токен истёк». Сообщение выводится на странице входа после перенаправления: пометка
// кладётся в sessionStorage и переживает перезагрузку (см. Login).
export const SESSION_EXPIRED_MESSAGE = "Сессия истекла. Выйдите из системы и войдите заново.";
const SESSION_EXPIRED_FLAG = "townhouse:session-expired";

let unauthorizedHandled = false;

/** Реакция на 401: сброс токена + переход на вход с пометкой для страницы входа. */
export const handleUnauthorized = (): void => {
    // На самом входе 401 — это неверные логин/пароль; форму обрабатывает Login сама.
    if (window.location.pathname === "/login" || unauthorizedHandled) return;
    unauthorizedHandled = true;
    clearToken();
    try {
        sessionStorage.setItem(SESSION_EXPIRED_FLAG, "1");
    } catch {
        /* приватный режим — пометку просто не сохраним */
    }
    window.location.href = "/login";
};

/** Забирает пометку «сессия истекла» (одноразово) для показа сообщения на входе. */
export const consumeSessionExpiredNotice = (): boolean => {
    try {
        const flag = sessionStorage.getItem(SESSION_EXPIRED_FLAG) === "1";
        if (flag) sessionStorage.removeItem(SESSION_EXPIRED_FLAG);
        return flag;
    } catch {
        return false;
    }
};

http.interceptors.response.use(
    (response) => response,
    (error: AxiosError) => {
        // 401 — сессия истекла/невалидна: сбрасываем и перенаправляем на вход.
        if (error.response?.status === 401) {
            handleUnauthorized();
        }
        return Promise.reject(error);
    },
);

// Авторизованный вариант fetch (добавляет Bearer-токен) для прямых вызовов API.
export const authedFetch = async (input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> => {
    const token = getToken();
    const headers = new Headers(init.headers ?? {});
    if (token) {
        headers.set("Authorization", `Bearer ${token}`);
    }
    if (init.body && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }
    const resp = await fetch(input, { ...init, headers });
    // Прямые fetch-вызовы (отчёты, PDF, ЛК) не идут через axios-интерцептор —
    // обрабатываем истёкшую сессию здесь так же (токен сбросить, уйти на вход).
    if (resp.status === 401) {
        handleUnauthorized();
    }
    return resp;
};

/**
 * Скачивает защищённый файл (PDF, Excel/CSV-экспорт и т.п.).
 *
 * JWT передаётся только заголовком Authorization, поэтому нельзя просто `window.open(url)` —
 * заголовок в новой вкладке не добавить. Поэтому запрашиваем blob через authedFetch и
 * скачиваем его как файл <a download href=blob:…> в рамках текущей страницы. Работает и на
 * десктопе, и в iOS-браузерах.
 *
 * options.kindLabel — как называть файл в сообщениях об ошибке (напр. «PDF», «Excel-файл»).
 * options.expectSubstring — если задан, проверяем MIME-тип blob: не совпало — не скачиваем мусор.
 */
export const downloadAuthorizedFile = async (
    url: string,
    fallbackName = "document",
    options: { kindLabel?: string; expectSubstring?: string } = {},
) => {
    const kind = options.kindLabel ?? "Файл";
    let blobUrl: string | null = null;
    // Таймаут на генерацию/загрузку, чтобы кнопка не висела бесконечно.
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 60_000);
    try {
        const resp = await authedFetch(url, { signal: controller.signal });
        if (resp.status === 401) {
            // Истёкшая сессия: переход на вход уже обработан в authedFetch —
            // технический текст ошибки не показываем.
            return;
        }
        if (!resp.ok) {
            let detail = `Не удалось загрузить ${kind} (${resp.status})`;
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
        // Предохранитель: если сервер вернул не то, что ожидали (часто это HTML/504/ошибка),
        // не скачиваем мусор — показываем внятное сообщение.
        const type = (blob.type || "").toLowerCase();
        if (blob.size === 0) {
            message.error(`${kind} не сформирован (пустой ответ). Попробуйте позже.`);
            return;
        }
        if (options.expectSubstring && type && !type.includes(options.expectSubstring)) {
            message.error(`${kind} не сформирован (некорректный ответ). Попробуйте позже.`);
            return;
        }
        blobUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = blobUrl;
        a.download = fallbackName || "document";
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
                ? `Не удалось сформировать ${kind}: превышен таймаут. Повторите попытку.`
                : e instanceof Error
                  ? e.message
                  : `Не удалось загрузить ${kind}`,
        );
    } finally {
        window.clearTimeout(timer);
    }
};

/**
 * Открывает/скачивает защищённый PDF (обёртка над downloadAuthorizedFile).
 *
 * JWT передаётся только заголовком Authorization (см. authedFetch), поэтому нельзя
 * просто `window.open(url)` на рендпоинт — заголовок в новой вкладке не добавить
 * (был бы 401). Поэтому запрашиваем blob через authedFetch и скачиваем его как файл
 * <a download href=blob:…> в рамках текущей страницы. Это даёт при нажатии "PDF"
 * именно скачивание документа, и работает и в iOS-браузерах, и на десктопе.
 */
export const downloadAuthorizedPdf = async (url: string, fallbackName = "document.pdf") =>
    downloadAuthorizedFile(url, fallbackName, { kindLabel: "PDF", expectSubstring: "pdf" });

/**
 * Скачивает защищённый PDF (синоним downloadAuthorizedPdf) — чтобы не править все
 * точки вызова. Нажатие на «PDF»/«Скачать» инициирует скачивание документа.
 */
export const openAuthorizedPdf = downloadAuthorizedPdf;
