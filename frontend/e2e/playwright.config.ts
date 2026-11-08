import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  // The visual tour (task ui-tour) has its own config and seed; it is not part of task e2e.
  testIgnore: ["tour/**"],
  timeout: 90_000,
  expect: { timeout: 15_000 },
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.BASE_URL ?? "http://127.0.0.1:8080",
    trace: "retain-on-failure",
    extraHTTPHeaders: { "X-Requested-With": "expense-tracker-e2e" },
  },
});
