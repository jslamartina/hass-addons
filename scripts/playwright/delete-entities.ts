/**
 * Playwright script to delete Home Assistant entities via the UI
 *
 * IMPORTANT LIMITATION:
 * - MQTT entities cannot be deleted through the UI while the integration is running
 * - Home Assistant will show "You can only delete 0 of N entities" for MQTT entities
 * - To remove MQTT entities: stop the addon, wait for unavailability, then delete
 *
 * Usage:
 *   HA_BASE_URL=http://localhost:8123 HA_USERNAME=dev HA_PASSWORD=dev \
 *   npx ts-node scripts/playwright/delete-entities.ts "Entity Name 1" "Entity Name 2"
 *
 * Environment variables:
 *   HA_BASE_URL - Home Assistant URL (default: http://localhost:8123)
 *   HA_USERNAME - Username (default: dev)
 *   HA_PASSWORD - Password (default: dev)
 *   HEADED - Set to any value to run in headed mode (visible browser)
 */

import console from "console";
import { chromium, Locator, Page } from "playwright";

async function clickReliably(locator: Locator) {
  await locator.waitFor({ state: "visible", timeout: 5000 });
  try {
    await locator.click();
  } catch {
    await locator.dispatchEvent("click");
  }
}

async function loginIfNeeded(page: Page, username: string, password: string) {
  const usernameField = page.getByRole("textbox", { name: /username/i });
  if ((await usernameField.count()) === 0) {
    return;
  }

  await usernameField.fill(username);
  await page.getByRole("textbox", { name: /password/i }).fill(password);
  await clickReliably(page.getByRole("button", { name: /log in/i }));
  await page
    .waitForURL(/config\/entities/, { timeout: 15000 })
    .catch(() => undefined);
}

async function ensureSelectionMode(page: Page) {
  const selectionButton = page.getByRole("button", {
    name: /enter selection mode/i,
  });
  if ((await selectionButton.count()) > 0) {
    await clickReliably(selectionButton);
  }
}

async function locateSearchInput(page: Page) {
  // Home Assistant search inputs are inside shadow DOM and must be located via role
  // The label pattern is "Search N entities" where N is the entity count
  const searchInput = page.getByRole("textbox", { name: /^Search/i }).first();

  await searchInput
    .waitFor({ state: "visible", timeout: 5000 })
    .catch(() => undefined);

  if (await searchInput.isVisible()) {
    return searchInput;
  }

  return null;
}

async function selectEntityRow(page: Page, entityName: string) {
  const searchInput = await locateSearchInput(page);
  if (!searchInput) {
    throw new Error("Search input not found on entities page");
  }

  await searchInput.fill("");
  await searchInput.fill(entityName);
  await page.waitForTimeout(400);

  const row = page
    .getByRole("row", { name: new RegExp(entityName, "i") })
    .first();
  await row.waitFor({ state: "visible", timeout: 5000 });

  // In selection mode, checkboxes appear directly in the row as role="checkbox"
  const checkbox = row.getByRole("checkbox").first();
  await clickReliably(checkbox);

  await searchInput.fill("");
  await page.waitForTimeout(200);
}

async function deleteSelected(page: Page) {
  const actionButton = page.getByRole("button", { name: /^Action$/i }).first();
  await clickReliably(actionButton);

  // Click the text directly to avoid SVG interception in the menu item
  await clickReliably(page.getByText("Delete selected"));

  const dialog = page.getByRole("dialog");
  await clickReliably(dialog.getByRole("button", { name: /^Delete$/i }));
  await dialog.waitFor({ state: "hidden", timeout: 10000 });
}

async function main() {
  const baseUrl = process.env.HA_BASE_URL ?? "http://localhost:8123";
  const username = process.env.HA_USERNAME ?? "dev";
  const password = process.env.HA_PASSWORD ?? "dev";
  const entityNames = process.argv.slice(2);

  if (entityNames.length === 0) {
    console.error("Usage: node delete-entities.ts entity_id1 entity_id2 ...");
    process.exit(1);
  }

  const browser = await chromium.launch({
    headless: process.env.HEADED ? false : true,
  });
  const context = await browser.newContext();
  const page = await context.newPage();

  let selectionCount = 0;

  try {
    await page.goto(`${baseUrl}/config/entities`, { waitUntil: "networkidle" });
    await loginIfNeeded(page, username, password);
    await page.goto(`${baseUrl}/config/entities`, { waitUntil: "networkidle" });

    await ensureSelectionMode(page);

    for (const entity of entityNames) {
      try {
        await selectEntityRow(page, entity);
        selectionCount += 1;
        console.log(`Queued for deletion: ${entity}`);
      } catch (err) {
        console.warn(`Skipping ${entity}: ${(err as Error).message}`);
      }
    }

    if (selectionCount === 0) {
      console.warn("No entities were selected; skipping delete action.");
      return;
    }

    await deleteSelected(page);
    console.log("Deletion flow completed.");
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
