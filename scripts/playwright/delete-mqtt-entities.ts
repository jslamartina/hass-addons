/**
 * Playwright script to delete MQTT entities from Home Assistant via MQTT Integration page
 *
 * MQTT entities must be deleted from Settings -> Devices & Integrations -> MQTT
 * They cannot be deleted from the main Entities page while the integration is running.
 *
 * This script:
 *   1. Navigates to MQTT integration page
 *   2. Selects and deletes the entities
 *   3. Optionally restarts addon to republish entities
 *
 * Usage:
 *   HA_BASE_URL=http://localhost:8123 HA_USERNAME=dev HA_PASSWORD=dev \
 *   ADDON_SLUG=local_cync-lan RESTART_ADDON=true \
 *   npx ts-node scripts/playwright/delete-mqtt-entities.ts "Entity Name 1" "Entity Name 2"
 *
 * Environment variables:
 *   HA_BASE_URL   - Home Assistant URL (default: http://localhost:8123)
 *   HA_USERNAME   - Username (default: dev)
 *   HA_PASSWORD   - Password (default: dev)
 *   ADDON_SLUG    - Addon slug to restart (default: local_cync-lan)
 *   RESTART_ADDON - Set to "true" to restart addon after deletion (default: false)
 *   HEADED        - Set to any value to run in headed mode (visible browser)
 */

import { chromium, Locator, Page } from "playwright";
import { execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";

// Create a run-specific directory with timestamp
const RUN_TIMESTAMP = new Date()
  .toISOString()
  .replace(/[:.]/g, "-")
  .substring(0, 19);
const RUN_DIR = path.join(
  __dirname,
  "../../test-results/runs",
  `mqtt-${RUN_TIMESTAMP}`,
);
const SCREENSHOTS_DIR = path.join(RUN_DIR, "screenshots");
const LOG_FILE = path.join(RUN_DIR, "run.log");

let logLines: string[] = [];

function log(
  message: string,
  level: "INFO" | "SUCCESS" | "WARN" | "ERROR" = "INFO",
) {
  const icons = { INFO: "ℹ️", SUCCESS: "✅", WARN: "⚠️", ERROR: "❌" };
  const timestamp = new Date().toISOString();
  const logLine = `[${timestamp}] ${icons[level]} ${message}`;
  logLines.push(logLine);
  console.log(message);
}

function saveLog() {
  if (!fs.existsSync(RUN_DIR)) {
    fs.mkdirSync(RUN_DIR, { recursive: true });
  }
  fs.writeFileSync(LOG_FILE, logLines.join("\n"), "utf-8");
  console.log(`\n📝 Full log saved: ${LOG_FILE}`);
}

async function takeScreenshot(page: Page, name: string) {
  if (!fs.existsSync(SCREENSHOTS_DIR)) {
    fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  }
  const filename = path.join(SCREENSHOTS_DIR, `${name}.png`);
  await page.screenshot({ path: filename, fullPage: true });

  // Save accessibility tree (includes shadow DOM content)
  const accessibilityFilename = path.join(SCREENSHOTS_DIR, `${name}-a11y.yaml`);
  const snapshot = await page.accessibility.snapshot();
  fs.writeFileSync(
    accessibilityFilename,
    JSON.stringify(snapshot, null, 2),
    "utf-8",
  );

  log(`Captured: ${name}.png + ${name}-a11y.yaml`, "INFO");
}

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
  await page.waitForTimeout(3000);
}

function restartAddon(addonSlug: string) {
  log(`Restarting addon: ${addonSlug}`, "INFO");
  try {
    execSync(`ha addons restart ${addonSlug}`, { stdio: "inherit" });
    log(`Addon restarted successfully`, "SUCCESS");
  } catch (err) {
    log(`Failed to restart addon: ${err}`, "ERROR");
    throw err;
  }
}

async function navigateToMQTTIntegration(page: Page, baseUrl: string) {
  log("Navigating to MQTT integration page", "INFO");

  // Go to integrations page
  await page.goto(`${baseUrl}/config/integrations`, {
    waitUntil: "domcontentloaded",
  });
  await page.waitForTimeout(3000);
  await takeScreenshot(page, "01-integrations-page");

  // Find and click MQTT integration
  const mqttCard = page
    .locator("ha-integration-card")
    .filter({ hasText: /MQTT/i })
    .first();
  await mqttCard.waitFor({ state: "visible", timeout: 10000 });
  await clickReliably(mqttCard);
  await page.waitForTimeout(3000);

  await takeScreenshot(page, "02-mqtt-integration-opened");

  // Click on "N devices" link to see entities
  const devicesLink = page.getByRole("link", { name: /device/i }).first();
  if ((await devicesLink.count()) > 0) {
    await clickReliably(devicesLink);
    await page.waitForTimeout(2000);
    log("Opened MQTT devices view", "SUCCESS");
  } else {
    // Try clicking "N entities" if devices link not found
    const entitiesLink = page.getByRole("link", { name: /entit/i }).first();
    await clickReliably(entitiesLink);
    await page.waitForTimeout(2000);
    log("Opened MQTT entities view", "SUCCESS");
  }

  await takeScreenshot(page, "03-mqtt-entities-list");
}

async function selectAndDeleteEntities(page: Page, entityNames: string[]) {
  log("Entering selection mode on MQTT page", "INFO");

  // Enter selection mode
  const selectionButton = page.getByTitle("Enter selection mode");
  if ((await selectionButton.count()) > 0) {
    await clickReliably(selectionButton);
    await page.waitForTimeout(1000);
    log("Selection mode activated", "SUCCESS");
  }

  await takeScreenshot(page, "04-selection-mode-enabled");

  let selectedCount = 0;

  // Select each entity
  for (const entityName of entityNames) {
    try {
      const rows = page.getByRole("row").filter({ hasText: entityName });
      const count = await rows.count();

      log(
        `Found ${count} rows for "${entityName}"`,
        count > 0 ? "INFO" : "WARN",
      );

      for (let i = 0; i < count; i++) {
        const row = rows.nth(i);
        const checkbox = row.locator(".mdc-checkbox__native-control").first();
        const checkboxExists = (await checkbox.count()) > 0;

        if (checkboxExists && (await checkbox.isVisible())) {
          await clickReliably(checkbox);
          selectedCount++;
          log(`Selected entity row for "${entityName}"`, "SUCCESS");
        }
      }
    } catch (err) {
      log(
        `Failed to select "${entityName}": ${(err as Error).message}`,
        "WARN",
      );
    }
  }

  await takeScreenshot(page, "05-entities-selected");

  if (selectedCount === 0) {
    log("No entities were selected", "WARN");
    return false;
  }

  log(`Selected ${selectedCount} entity rows, proceeding to delete`, "INFO");

  // Click Action -> Delete selected
  const actionButton = page.getByRole("button", { name: /^Action$/i }).first();
  await clickReliably(actionButton);
  await page.waitForTimeout(500);

  await clickReliably(page.getByText("Delete selected"));
  await page.waitForTimeout(1000);

  // Confirm deletion
  await clickReliably(page.getByRole("button", { name: "Delete" }).last());
  await page.waitForTimeout(2000);

  log("Deletion confirmed", "SUCCESS");
  await takeScreenshot(page, "06-after-deletion");

  return true;
}

async function main() {
  const baseUrl = process.env.HA_BASE_URL ?? "http://localhost:8123";
  const username = process.env.HA_USERNAME ?? "dev";
  const password = process.env.HA_PASSWORD ?? "dev";
  const addonSlug = process.env.ADDON_SLUG ?? "local_cync-lan";
  const shouldRestart = process.env.RESTART_ADDON === "true";
  const entityNames = process.argv.slice(2);

  if (entityNames.length === 0) {
    console.error(
      "Usage: node delete-mqtt-entities.ts entity_name1 entity_name2 ...",
    );
    console.error("");
    console.error("Example:");
    console.error(
      '  npx ts-node scripts/playwright/delete-mqtt-entities.ts "Hallway Front Switch" "Hallway Counter Switch"',
    );
    process.exit(1);
  }

  console.log(
    "╔═══════════════════════════════════════════════════════════════════════╗",
  );
  console.log(
    "║          MQTT Entity Deletion - Via Integration Page               ║",
  );
  console.log(
    "╚═══════════════════════════════════════════════════════════════════════╝",
  );
  console.log("");
  log(`Run directory: ${RUN_DIR}`, "INFO");
  log(`Target entities: ${entityNames.join(", ")}`, "INFO");
  log(`Addon: ${addonSlug}`, "INFO");
  log(`Will restart addon: ${shouldRestart}`, "INFO");
  console.log("");

  const browser = await chromium.launch({
    headless: process.env.HEADED ? false : true,
  });
  const context = await browser.newContext();
  const page = await context.newPage();

  let deletionSuccessful = false;

  try {
    await page.goto(`${baseUrl}`, { waitUntil: "networkidle" });
    await loginIfNeeded(page, username, password);

    // Step 1: Navigate to MQTT integration
    await navigateToMQTTIntegration(page, baseUrl);

    // Step 2: Select and delete entities
    deletionSuccessful = await selectAndDeleteEntities(page, entityNames);

    if (deletionSuccessful) {
      log("MQTT entity deletion completed successfully", "SUCCESS");
    } else {
      log("No entities were deleted", "WARN");
    }
  } finally {
    await context.close();
    await browser.close();

    // Optionally restart addon (only if deletion was successful)
    console.log("");
    if (deletionSuccessful && shouldRestart) {
      restartAddon(addonSlug);
    } else if (deletionSuccessful) {
      log(
        `Entities deleted but addon not restarted (set RESTART_ADDON=true to enable)`,
        "INFO",
      );
      console.log(`To restart manually: ha addons restart ${addonSlug}`);
    } else {
      log(`No entities were deleted`, "WARN");
    }

    console.log("");
    console.log(
      "═══════════════════════════════════════════════════════════════════════",
    );
    saveLog();
    console.log(`📂 Screenshots: ${SCREENSHOTS_DIR}`);
    console.log(
      "═══════════════════════════════════════════════════════════════════════",
    );
  }
}

main().catch((err) => {
  log(`Fatal error: ${err}`, "ERROR");
  saveLog();
  console.error(err);
  process.exit(1);
});
