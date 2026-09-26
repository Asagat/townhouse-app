import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
    plugins: [react()],
    // Тот же define, что и в vite.config.ts: компоненты используют вшитый номер
    // релиза (__APP_VERSION__). В тестах env не задан → «dev».
    define: { __APP_VERSION__: JSON.stringify(process.env.APP_VERSION || "dev") },
    test: {
        globals: false,
        environment: "jsdom",
        setupFiles: ["./src/test/setup.ts"],
        css: false,
        include: ["src/**/*.{test,spec}.{ts,tsx}"],
    },
});
