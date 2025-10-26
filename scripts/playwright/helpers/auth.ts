import { Page, expect } from "@playwright/test";

export async function login(
  page: Page,
  baseURL: string,
  username: string,
  password: string,
) {
  await page.goto(baseURL);
  // Wait for page to load
  await page.waitForLoadState("networkidle");

  // Check if already logged in (URL should be lovelace dashboard, not auth page)
  if (!page.url().includes("/auth/")) {
    // Already logged in
    return;
  }

  // Fill and submit login form (use role textbox to avoid "Show password" button conflict)
  await page.getByRole("textbox", { name: /username/i }).fill(username);
  await page.getByRole("textbox", { name: /password/i }).fill(password);

  // Press Enter to submit (more reliable than clicking in some UIs)
  await page.getByRole("textbox", { name: /password/i }).press("Enter");

  // Wait for redirect from auth page to dashboard (lovelace or home)
  await expect(async () => {
    const url = page.url();
    expect(url).not.toContain("/auth/");
  }).toPass({ timeout: 15000 });

  // Wait for page to fully load
  await page.waitForLoadState("networkidle");
}
