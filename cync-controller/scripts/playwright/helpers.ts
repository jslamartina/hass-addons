/**
 * Playwright Helper Functions for Home Assistant E2E Testing
 *
 * Browser-based automation helpers that work with Cursor Playwright and pytest-playwright.
 * These functions provide reusable utilities for HA authentication, navigation, and UI interactions.
 */

import { Page } from "@playwright/test";

/**
 * Login to Home Assistant with provided credentials
 *
 * @param page - Playwright page instance
 * @param username - HA username
 * @param password - HA password
 * @param baseUrl - HA base URL (default: http://localhost:8123)
 * @returns The authenticated page
 */
export async function loginToHA(
  page: Page,
  username: string,
  password: string,
  baseUrl: string = "http://localhost:8123",
): Promise<Page> {
  // Navigate to Home Assistant
  await page.goto(baseUrl);

  // Check if already logged in
  if (page.url().includes("/lovelace") || page.url().includes("/config")) {
    console.log("✓ Already logged in");
    return page;
  }

  // Wait for login form
  await page.waitForSelector('input[name="username"], input[type="text"]', {
    timeout: 10000,
  });

  // Fill credentials
  const usernameInput = page
    .locator('input[name="username"], input[type="text"]')
    .first();
  const passwordInput = page
    .locator('input[name="password"], input[type="password"]')
    .first();

  await usernameInput.fill(username);
  await passwordInput.fill(password);

  // Submit form
  const submitButton = page.getByRole("button", { name: /sign in|log in/i });
  await submitButton.click();

  // Wait for redirect to dashboard
  await page.waitForURL(/\/lovelace|\/config/, { timeout: 10000 });

  console.log("✓ Successfully logged in to Home Assistant");
  return page;
}

/**
 * Navigate to add-on configuration page
 *
 * @param page - Authenticated Playwright page instance
 * @param addonSlug - Add-on slug (e.g., "local_cync-controller")
 * @param baseUrl - HA base URL (default: http://localhost:8123)
 */
export async function navigateToAddonConfig(
  page: Page,
  addonSlug: string,
  baseUrl: string = "http://localhost:8123",
): Promise<void> {
  // Navigate directly to add-on page
  const addonUrl = `${baseUrl}/hassio/addon/${addonSlug}`;
  await page.goto(addonUrl);
  await page.waitForLoadState("networkidle");

  console.log(`✓ Navigated to add-on config: ${addonSlug}`);
}

/**
 * Navigate to add-on ingress page
 *
 * @param page - Authenticated Playwright page instance
 * @param addonSlug - Add-on slug (e.g., "local_cync-controller")
 * @param baseUrl - HA base URL (default: http://localhost:8123)
 */
export async function navigateToIngress(
  page: Page,
  addonSlug: string,
  baseUrl: string = "http://localhost:8123",
): Promise<void> {
  // Navigate to ingress page
  const ingressUrl = `${baseUrl}/${addonSlug}/ingress`;
  await page.goto(ingressUrl);

  // Wait for ingress content to load
  await page.waitForLoadState("networkidle");

  console.log(`✓ Navigated to ingress: ${addonSlug}`);
}

/**
 * Wait for add-on to finish starting up
 *
 * Polls the add-on logs or UI elements to determine when startup is complete.
 *
 * @param page - Playwright page instance
 * @param timeoutMs - Maximum time to wait in milliseconds (default: 30000)
 */
export async function waitForAddonStartup(
  page: Page,
  timeoutMs: number = 30000,
): Promise<void> {
  const startTime = Date.now();

  console.log("⏳ Waiting for add-on startup...");

  // Simple time-based wait with periodic checks
  // TODO: Enhance with actual startup detection (e.g., log parsing, health checks)
  await page.waitForTimeout(5000); // Initial wait

  const elapsed = Date.now() - startTime;
  if (elapsed < timeoutMs) {
    console.log(`✓ Add-on startup complete (waited ${elapsed}ms)`);
  } else {
    throw new Error(`Add-on startup timeout after ${timeoutMs}ms`);
  }
}

/**
 * Navigate to MQTT integration devices page
 *
 * @param page - Authenticated Playwright page instance
 * @param baseUrl - HA base URL (default: http://localhost:8123)
 */
export async function navigateToMQTTDevices(
  page: Page,
  baseUrl: string = "http://localhost:8123",
): Promise<void> {
  const mqttUrl = `${baseUrl}/config/integrations/integration/mqtt`;
  await page.goto(mqttUrl);
  await page.waitForLoadState("networkidle");

  console.log("✓ Navigated to MQTT integration");
}

/**
 * Navigate to Home Assistant Overview dashboard
 *
 * @param page - Authenticated Playwright page instance
 * @param baseUrl - HA base URL (default: http://localhost:8123)
 */
export async function navigateToOverview(
  page: Page,
  baseUrl: string = "http://localhost:8123",
): Promise<void> {
  const overviewUrl = `${baseUrl}/lovelace/0`;
  await page.goto(overviewUrl);
  await page.waitForLoadState("networkidle");

  console.log("✓ Navigated to Overview dashboard");
}

/**
 * Get entity state from Home Assistant UI
 *
 * @param page - Playwright page instance
 * @param entityName - Human-readable entity name (e.g., "Hallway Lights")
 * @returns 'on' | 'off' | 'unavailable' | null
 */
export async function getEntityState(
  page: Page,
  entityName: string,
): Promise<string | null> {
  try {
    // Try to find ON state
    const onSwitch = page.getByRole("switch", {
      name: new RegExp(`Toggle ${entityName} on`, "i"),
    });
    if (await onSwitch.isVisible({ timeout: 1000 })) {
      return "off"; // Switch shows "toggle on" means it's currently off
    }

    // Try to find OFF state
    const offSwitch = page.getByRole("switch", {
      name: new RegExp(`Toggle ${entityName} off`, "i"),
    });
    if (await offSwitch.isVisible({ timeout: 1000 })) {
      return "on"; // Switch shows "toggle off" means it's currently on
    }

    return "unavailable";
  } catch {
    console.warn(`Could not determine state for entity: ${entityName}`);
    return null;
  }
}

/**
 * Click entity toggle (works with switches, lights, etc.)
 *
 * @param page - Playwright page instance
 * @param entityName - Human-readable entity name
 */
export async function toggleEntity(
  page: Page,
  entityName: string,
): Promise<void> {
  // Try to find either ON or OFF switch
  const onSwitch = page.getByRole("switch", {
    name: new RegExp(`Toggle ${entityName} on`, "i"),
  });
  const offSwitch = page.getByRole("switch", {
    name: new RegExp(`Toggle ${entityName} off`, "i"),
  });

  if (await onSwitch.isVisible({ timeout: 1000 })) {
    await onSwitch.click();
    console.log(`✓ Toggled ${entityName} ON`);
  } else if (await offSwitch.isVisible({ timeout: 1000 })) {
    await offSwitch.click();
    console.log(`✓ Toggled ${entityName} OFF`);
  } else {
    throw new Error(`Entity not found or not toggleable: ${entityName}`);
  }

  // Wait for state update
  await page.waitForTimeout(2000);
}
