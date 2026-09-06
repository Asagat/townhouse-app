// frontend/src/auth/preferences.ts
// Серверное хранение настроек интерфейса пользователя (роадмап 2.13).
//
// Настройки списка на пользователя (по имени ресурса): порядок/видимость/ширины
// колонок, сортировка, применённые фильтры, pageSize. Хранятся на сервере
// (user_preferences), в браузере — только локальный кэш для мгновенного старта
// (настройки переживают перезагрузку и смену устройства).

import { authedFetch, apiUrl } from "./http";

export interface StoredColumnSettings {
    order: string[];
    hidden: string[];
    widths: Record<string, number>;
}

export interface StoredListFilter {
    field: string;
    operator: string;
    value: unknown;
}

export interface ListSettings {
    columns?: StoredColumnSettings;
    sorters?: Array<{ field: string; order: "asc" | "desc" }>;
    filters?: StoredListFilter[];
    pageSize?: number;
}

export type PrefsMap = Record<string, ListSettings>;

const CACHE_PREFIX = "townhouse_prefs";

const cacheKey = (username: string) => `${CACHE_PREFIX}:${username}`;

export const readPrefsCache = (username: string): PrefsMap => {
    if (!username) return {};
    try {
        const raw = localStorage.getItem(cacheKey(username));
        return raw ? (JSON.parse(raw) as PrefsMap) : {};
    } catch {
        return {};
    }
};

export const writePrefsCache = (username: string, prefs: PrefsMap) => {
    if (!username) return;
    try {
        localStorage.setItem(cacheKey(username), JSON.stringify(prefs));
    } catch {
        // localStorage может быть переполнен/недоступен — кэш не критичен.
    }
};

/** Загружает настройки текущего пользователя с сервера. */
export const fetchServerPrefs = async (): Promise<PrefsMap> => {
    try {
        const resp = await authedFetch(`${apiUrl}/preferences`);
        if (!resp.ok) return {};
        const data = (await resp.json()) as Array<{ resource: string; data: ListSettings }>;
        const out: PrefsMap = {};
        for (const item of Array.isArray(data) ? data : []) {
            out[item.resource] = item.data ?? {};
        }
        return out;
    } catch {
        return {};
    }
};

/** Сохраняет настройки раздела на сервер (best effort, не блокирует UI). */
export const pushServerPref = async (resource: string, data: ListSettings) => {
    try {
        await authedFetch(`${apiUrl}/preferences/${encodeURIComponent(resource)}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        });
    } catch {
        // Настройка останется в локальном кэше и уйдёт на сервер при следующем изменении.
    }
};
