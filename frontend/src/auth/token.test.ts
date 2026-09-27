// src/auth/token.test.ts
// Юнит-тесты хранилища токена/пользователя и события смены авторизации (3.2).

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import {
    AUTH_EVENT,
    getToken,
    setToken,
    clearToken,
    getIdentity,
    setIdentity,
    type Identity,
} from "./token";

const IDENTITY: Identity = {
    id: 1,
    username: "admin",
    full_name: "Админ",
    role: "admin",
    role_name: "Администратор",
};

beforeEach(() => {
    localStorage.clear();
});

afterEach(() => {
    localStorage.clear();
});

describe("токен", () => {
    it("set/get/clear", () => {
        expect(getToken()).toBeNull();
        setToken("abc");
        expect(getToken()).toBe("abc");
        clearToken();
        expect(getToken()).toBeNull();
    });
});

describe("пользователь (identity)", () => {
    it("roundtrip set/get", () => {
        setIdentity(IDENTITY);
        expect(getIdentity()).toEqual(IDENTITY);
    });

    it("битый JSON → null (не падает)", () => {
        localStorage.setItem("townhouse_user", "{не json");
        expect(getIdentity()).toBeNull();
    });

    it("clearToken удаляет и токен, и пользователя", () => {
        setToken("t");
        setIdentity(IDENTITY);
        clearToken();
        expect(getToken()).toBeNull();
        expect(getIdentity()).toBeNull();
    });
});

describe("событие AUTH_EVENT", () => {
    it("диспатчится при входе/выходе", () => {
        const spy = vi.fn();
        window.addEventListener(AUTH_EVENT, spy);

        setToken("t");
        setIdentity(IDENTITY);
        clearToken();

        expect(spy).toHaveBeenCalledTimes(3);
        window.removeEventListener(AUTH_EVENT, spy);
    });
});
