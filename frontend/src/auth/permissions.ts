// src/auth/permissions.ts
// Права текущей роли (задача 2.6). Загружаются с /api/auth/permissions/me —
// backend остаётся источником истины, фронт лишь отражает права (меню и кнопки).
//
// Модуль держит снапшот прав и уведомляет подписчиков (React-хук usePermissions).
// Пока права не загружены (или запрос не удался) — can.ts/menuAccess.ts откатываются
// к историческим захардкоженным правилам, поэтому поведение не «мигает».

import { useEffect, useState } from "react";

import { apiUrl, authedFetch } from "./http";
import { AUTH_EVENT, getToken } from "./token";

export interface ResourcePerm {
    menu: boolean;
    read: boolean;
    create: boolean;
    edit: boolean;
    delete: boolean;
}

export type PermissionsMap = Record<string, ResourcePerm>;

let perms: PermissionsMap | null = null;
let role = "";
let inflight: Promise<void> | null = null;
const listeners = new Set<() => void>();

const notify = (): void => {
    for (const l of listeners) l();
};

const reset = (): void => {
    perms = null;
    role = "";
    notify();
};

/** Снапшот прав текущей роли (null — ещё не загружены/не удалось). */
export const getPermissions = (): PermissionsMap | null => perms;
export const getPermissionsRole = (): string => role;

/** Загружает права текущей роли (по токену). Идемпотентно: параллельные вызовы объединяются. */
export const loadPermissions = async (): Promise<void> => {
    if (inflight) return inflight;
    if (!getToken()) {
        reset();
        return;
    }
    inflight = (async () => {
        try {
            const resp = await authedFetch(`${apiUrl}/auth/permissions/me`);
            if (resp.ok) {
                const data = await resp.json();
                role = data?.role ?? "";
                perms = data?.keys ?? {};
                notify();
            }
        } catch {
            /* откат к историческим правилам (can.ts/menuAccess.ts) */
        } finally {
            inflight = null;
        }
    })();
    return inflight;
};

// Смена авторизации (вход/выход) — сбрасываем и перечитываем права.
if (typeof window !== "undefined") {
    window.addEventListener(AUTH_EVENT, () => {
        reset();
        void loadPermissions();
    });
}

/** React-хук: перерисовывает компонент при загрузке/смене прав. */
export const usePermissions = (): { perms: PermissionsMap | null; role: string } => {
    const [, setVersion] = useState(0);
    useEffect(() => {
        const listener = () => setVersion((v) => v + 1);
        listeners.add(listener);
        if (!perms && getToken()) void loadPermissions();
        return () => {
            listeners.delete(listener);
        };
    }, []);
    return { perms, role };
};
