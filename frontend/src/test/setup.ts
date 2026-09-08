// src/test/setup.ts
// Глобальная подготовка среды для vitest + React Testing Library: полифиллы для
// компонентов antd/rc-* (в jsdom нет ResizeObserver/matchMedia), очистка DOM между
// тестами.

import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

if (typeof globalThis.ResizeObserver === "undefined") {
    class ResizeObserverMock {
        observe(): void {}
        unobserve(): void {}
        disconnect(): void {}
    }
    globalThis.ResizeObserver =
        ResizeObserverMock as unknown as typeof ResizeObserver;
}

if (typeof globalThis.matchMedia === "undefined") {
    globalThis.matchMedia = ((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
}

// rc-table в jsdom вызывает window.getComputedStyle(el, pseudoElt) для замера скроллбара;
// jsdom не реализует аргумент псевдоэлемента и печатает «Not implemented». Заглушка
// просто игнорирует второй аргумент, чтобы убрать шум (на реальной вёрстке не влияет).
const originalGetComputedStyle = window.getComputedStyle.bind(window);
window.getComputedStyle = ((elt: Element, _pseudoElt?: string | null) =>
    originalGetComputedStyle(elt)) as typeof window.getComputedStyle;

afterEach(() => {
    cleanup();
});
