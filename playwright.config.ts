import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./scripts/playwright",
  timeout: 120000,
  use: {
    baseURL: process.env.HA_BASE_URL || "http://localhost:8123",
    screenshot: "on",
    video: "retain-on-failure",
    trace: "retain-on-failure",
  },
  reporter: [["html", { outputFolder: "playwright-report" }], ["list"]],
  outputDir: "test-results",
});
