import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Mantine + jsdom are slow when the whole suite runs in parallel
configure({ asyncUtilTimeout: 10000 });

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// Mantine relies on these browser APIs, which jsdom does not implement.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
window.HTMLElement.prototype.scrollIntoView = () => {};
