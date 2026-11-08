import { defineConfig } from "@playwright/test";

/** Visual tour (task ui-tour): seeds a synthetic household and screenshots every screen. */
export default defineConfig({
  testDir: ".",
  timeout: 240_000,
  expect: { timeout: 15_000 },
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.BASE_URL ?? "http://127.0.0.1:8080",
    viewport: { width: 1440, height: 900 },
    locale: "pt-BR",
    extraHTTPHeaders: { "X-Requested-With": "expense-tracker-tour" },
  },
});
