import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./scripts/playwright",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  timeout: 60000,
  use: {
    baseURL: process.env.HA_BASE_URL || "http://localhost:8123",
    actionTimeout: 10000,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices.chromium },
    },
  ],
  reporter: [["html", { outputFolder: "playwright-report" }], ["list"]],
  outputDir: "test-results",
});
