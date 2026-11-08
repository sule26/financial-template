import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

type NodeEnvHolder = { process?: { env?: Record<string, string | undefined> } };
const env = (globalThis as NodeEnvHolder).process?.env ?? {};
const apiTarget: string = env.API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
  // Never inline assets as data: URLs: the backend CSP (default-src 'self', no font-src)
  // blocks data: fonts, so every font subset must ship as its own file.
  build: { outDir: "dist", sourcemap: false, assetsInlineLimit: 0 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
    testTimeout: 20000,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**", "src/main.tsx", "src/vite-env.d.ts"],
      thresholds: { lines: 80 },
      reporter: ["text-summary"],
    },
  },
});
