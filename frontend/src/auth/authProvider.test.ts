// src/auth/authProvider.test.ts
// Б9: после входа с флагом must_change_password — редирект на смену пароля.

import { describe, it, expect, vi, afterEach } from "vitest";

import { authProvider } from "./authProvider";

afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
});

const mockLogin = (mustChange: boolean) =>
    vi.stubGlobal(
        "fetch",
        vi.fn(async () =>
            new Response(
                JSON.stringify({
                    access_token: "t",
                    user: {
                        id: 1,
                        username: "u",
                        full_name: null,
                        role: "resident",
                        role_name: "Житель",
                        must_change_password: mustChange,
                    },
                }),
                { status: 200, headers: { "Content-Type": "application/json" } },
            ),
        ),
    );

describe("authProvider.login", () => {
    it("с флагом смены пароля ведёт на /change-password", async () => {
        mockLogin(true);
        const res = await authProvider.login!({ username: "u", password: "p" });
        expect(res).toMatchObject({ success: true, redirectTo: "/change-password" });
    });

    it("без флага ведёт на главную", async () => {
        mockLogin(false);
        const res = await authProvider.login!({ username: "u", password: "p" });
        expect(res).toMatchObject({ success: true, redirectTo: "/" });
    });
});
