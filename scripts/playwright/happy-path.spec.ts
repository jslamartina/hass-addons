import { test, expect } from "@playwright/test";
import { login } from "./helpers/auth";

const BASE_URL = process.env.HA_BASE_URL || "http://localhost:8123";
const USERNAME = process.env.HA_USERNAME || "dev";
const PASSWORD = process.env.HA_PASSWORD || "dev";

test.describe("Cync add-on happy path", () => {
  test("successfully login to Home Assistant", async ({ page }) => {
    // Login via the helper
    await login(page, BASE_URL, USERNAME, PASSWORD);
    console.log("✓ Login successful");

    // Verify we're on the dashboard (not on auth page)
    expect(page.url()).not.toContain("/auth/");
    console.log("✓ On dashboard");

    console.log(
      "\n✅ Happy path PASSED: Successfully authenticated to Home Assistant!",
    );
  });
});
