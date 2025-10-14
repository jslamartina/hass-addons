/**
 * Playwright script to delete ALL MQTT entities except CyncLAN Bridge
 *
 * This script intelligently discovers and deletes all MQTT entities while
 * preserving the CyncLAN Bridge device and its entities.
 *
 * Workflow:
 *   1. Navigates to MQTT integration page
 *   2. Discovers all MQTT devices/entities
 *   3. Filters out CyncLAN Bridge and its entities
 *   4. Deletes all remaining entities
 *   5. Optionally restarts addon to republish entities
 *
 * Usage:
 *   npx ts-node scripts/playwright/delete-all-mqtt-entities-except-bridge.ts
 *
 * Environment variables:
 *   HA_BASE_URL     - Home Assistant URL (default: http://localhost:8123)
 *   HA_USERNAME     - Username (default: dev)
 *   HA_PASSWORD     - Password (default: dev)
 *   ADDON_SLUG      - Addon slug to restart (default: local_cync-lan)
 *   RESTART_ADDON   - Set to "true" to restart addon after deletion (default: false)
 *   HEADED          - Set to any value to run in headed mode (visible browser)
 *   BRIDGE_NAME     - Name of bridge to preserve (default: "CyncLAN Bridge")
 *   DRY_RUN         - Set to "true" to preview what would be deleted without actually deleting
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
  `delete-mqtt-${RUN_TIMESTAMP}`,
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
    log("Already logged in, skipping login", "INFO");
    return;
  }

  log("Logging in to Home Assistant", "INFO");
  await usernameField.fill(username);
  await page.getByRole("textbox", { name: /password/i }).fill(password);
  await clickReliably(page.getByRole("button", { name: /log in/i }));
  await page.waitForTimeout(3000);
  log("Login successful", "SUCCESS");
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

  log("MQTT integration card clicked", "SUCCESS");
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

interface EntityInfo {
  name: string;
  rowElement: Locator;
  isFromBridge: boolean;
}

async function discoverAllEntities(
  page: Page,
  bridgeName: string,
): Promise<{ toDelete: EntityInfo[]; toPreserve: EntityInfo[] }> {
  log("Discovering all MQTT entities", "INFO");

  const toDelete: EntityInfo[] = [];
  const toPreserve: EntityInfo[] = [];

  // Get all rows in the data table
  const allRows = page.getByRole("row");
  const rowCount = await allRows.count();
  log(`Found ${rowCount} total rows in the table`, "INFO");

  // Track seen entity names to avoid duplicates
  const seenEntities = new Set<string>();

  // Skip header row (index 0)
  for (let i = 1; i < rowCount; i++) {
    const row = allRows.nth(i);
    const rowText = await row.textContent();

    if (!rowText) continue;

    // Try multiple approaches to extract entity name
    let entityName = "";

    // Approach 1: Look for the first text node in the row
    const firstText = row.locator("div, span, a").first();
    const firstTextContent = (await firstText.textContent())?.trim();

    if (
      firstTextContent &&
      firstTextContent !== "—" &&
      firstTextContent !== "MQTT"
    ) {
      entityName = firstTextContent;
    }

    // Approach 2: If that didn't work, try to parse from row text
    if (!entityName) {
      // Row text format is typically: "EntityName — MQTT DeviceName Model —"
      // Extract the first meaningful part
      const parts = rowText
        .split(/—|\n/)
        .map((p) => p.trim())
        .filter((p) => p && p !== "MQTT");
      if (parts.length > 0) {
        entityName = parts[0];
      }
    }

    if (!entityName || seenEntities.has(entityName)) continue;
    seenEntities.add(entityName);

    // Check if this entity belongs to the bridge
    const isFromBridge =
      rowText.includes(bridgeName) || entityName.includes(bridgeName);

    const entityInfo: EntityInfo = {
      name: entityName,
      rowElement: row,
      isFromBridge,
    };

    if (isFromBridge) {
      toPreserve.push(entityInfo);
      log(`PRESERVE: ${entityName} (part of ${bridgeName})`, "INFO");
    } else {
      toDelete.push(entityInfo);
      log(`DELETE: ${entityName}`, "INFO");
    }
  }

  log(
    `Total entities discovered: ${toDelete.length + toPreserve.length}`,
    "INFO",
  );
  log(`To delete: ${toDelete.length}`, "WARN");
  log(`To preserve: ${toPreserve.length}`, "SUCCESS");

  return { toDelete, toPreserve };
}

async function selectAndDeleteEntities(
  page: Page,
  entitiesToDelete: EntityInfo[],
  dryRun: boolean,
): Promise<string[]> {
  if (entitiesToDelete.length === 0) {
    log("No entities to delete", "WARN");
    return [];
  }

  if (dryRun) {
    log("DRY RUN MODE - No entities will be actually deleted", "WARN");
    log("Entities that WOULD be deleted:", "INFO");
    entitiesToDelete.forEach((e) => log(`  - ${e.name}`, "INFO"));
    return [];
  }

  log("Entering selection mode", "INFO");

  // Enter selection mode
  const selectionButton = page.getByTitle("Enter selection mode");
  if ((await selectionButton.count()) > 0) {
    await clickReliably(selectionButton);
    await page.waitForTimeout(1000);
    log("Selection mode activated", "SUCCESS");
  }

  await takeScreenshot(page, "04-selection-mode-enabled");

  let selectedCount = 0;
  const deletedDeviceNames: string[] = [];

  // Select each entity
  for (const entity of entitiesToDelete) {
    try {
      const checkbox = entity.rowElement
        .locator(".mdc-checkbox__native-control")
        .first();
      const checkboxExists = (await checkbox.count()) > 0;

      if (checkboxExists && (await checkbox.isVisible())) {
        await clickReliably(checkbox);
        selectedCount++;
        deletedDeviceNames.push(entity.name);
        log(`Selected: ${entity.name}`, "SUCCESS");
      } else {
        log(`Could not find checkbox for: ${entity.name}`, "WARN");
      }
    } catch (err) {
      log(
        `Failed to select "${entity.name}": ${(err as Error).message}`,
        "WARN",
      );
    }
  }

  await takeScreenshot(page, "05-entities-selected");

  if (selectedCount === 0) {
    log("No entities were selected", "WARN");
    return [];
  }

  log(`Selected ${selectedCount} entities, proceeding to delete`, "INFO");

  // Click Action -> Delete selected
  const actionButton = page.getByRole("button", { name: /^Action$/i }).first();
  await clickReliably(actionButton);
  await page.waitForTimeout(500);

  await clickReliably(page.getByText("Delete selected"));
  await page.waitForTimeout(1000);

  // Confirm deletion
  const deleteButton = page.getByRole("button", { name: "Delete" }).last();
  await clickReliably(deleteButton);
  await page.waitForTimeout(2000);

  log("Deletion confirmed", "SUCCESS");
  await takeScreenshot(page, "06-after-deletion");

  return deletedDeviceNames;
}

async function deleteDevicesFromRegistry(
  page: Page,
  baseUrl: string,
  deviceNames: string[],
  bridgeName: string,
) {
  log("Navigating to devices page to delete device registry entries", "INFO");

  await page.goto(`${baseUrl}/config/devices`, {
    waitUntil: "domcontentloaded",
  });
  await page.waitForTimeout(3000);
  await takeScreenshot(page, "07-devices-page");

  for (const deviceName of deviceNames) {
    // Skip bridge device
    if (deviceName.includes(bridgeName)) {
      log(`Skipping bridge device: ${deviceName}`, "INFO");
      continue;
    }

    try {
      // Find and click the device row
      const deviceRow = page.getByRole("row", {
        name: new RegExp(deviceName, "i"),
      });
      if ((await deviceRow.count()) === 0) {
        log(`Device not found: ${deviceName}`, "WARN");
        continue;
      }

      await clickReliably(deviceRow.first());
      await page.waitForTimeout(2000);
      await takeScreenshot(
        page,
        `08-device-${deviceName.replace(/[^a-z0-9]/gi, "-")}`,
      );

      // Click Menu -> Delete
      const menuButton = page.getByRole("button", { name: "Menu" }).first();
      await clickReliably(menuButton);
      await page.waitForTimeout(500);

      await clickReliably(page.getByText("Delete"));
      await page.waitForTimeout(1000);

      // Confirm deletion
      await clickReliably(page.getByRole("button", { name: "Delete" }).last());
      await page.waitForTimeout(2000);

      log(`Deleted device from registry: ${deviceName}`, "SUCCESS");

      // Navigate back to devices page
      await page.goto(`${baseUrl}/config/devices`, {
        waitUntil: "domcontentloaded",
      });
      await page.waitForTimeout(2000);
    } catch (err) {
      log(
        `Failed to delete device "${deviceName}": ${(err as Error).message}`,
        "ERROR",
      );
    }
  }

  await takeScreenshot(page, "09-devices-deleted");
}

async function main() {
  const baseUrl = process.env.HA_BASE_URL ?? "http://localhost:8123";
  const username = process.env.HA_USERNAME ?? "dev";
  const password = process.env.HA_PASSWORD ?? "dev";
  const addonSlug = process.env.ADDON_SLUG ?? "local_cync-lan";
  const shouldRestart = process.env.RESTART_ADDON === "true";
  const bridgeName = process.env.BRIDGE_NAME ?? "CyncLAN Bridge";
  const dryRun = process.env.DRY_RUN === "true";

  console.log(
    "╔═══════════════════════════════════════════════════════════════════════╗",
  );
  console.log(
    "║     Delete All MQTT Entities (Except Bridge)                        ║",
  );
  console.log(
    "╚═══════════════════════════════════════════════════════════════════════╝",
  );
  console.log("");
  log(`Run directory: ${RUN_DIR}`, "INFO");
  log(`Bridge to preserve: ${bridgeName}`, "INFO");
  log(`Addon: ${addonSlug}`, "INFO");
  log(`Will restart addon: ${shouldRestart}`, "INFO");
  log(`Dry run mode: ${dryRun}`, dryRun ? "WARN" : "INFO");
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

    // Step 2: Discover all entities
    const { toDelete, toPreserve } = await discoverAllEntities(
      page,
      bridgeName,
    );

    await takeScreenshot(page, "03b-entities-discovered");

    console.log("");
    console.log("═════════════════ DISCOVERY SUMMARY ═════════════════");
    console.log(`Total entities found: ${toDelete.length + toPreserve.length}`);
    console.log(`✅ To preserve (${bridgeName}): ${toPreserve.length}`);
    toPreserve.forEach((e) => console.log(`   - ${e.name}`));
    console.log(`❌ To delete: ${toDelete.length}`);
    toDelete.forEach((e) => console.log(`   - ${e.name}`));
    console.log("═════════════════════════════════════════════════════");
    console.log("");

    // Step 3: Select and delete entities
    const deletedDeviceNames = await selectAndDeleteEntities(
      page,
      toDelete,
      dryRun,
    );

    if (deletedDeviceNames.length > 0) {
      log(
        `Successfully deleted ${deletedDeviceNames.length} entities`,
        "SUCCESS",
      );
      deletionSuccessful = true;

      // Step 4: Delete devices from device registry to allow fresh recreation
      if (!dryRun) {
        await deleteDevicesFromRegistry(
          page,
          baseUrl,
          deletedDeviceNames,
          bridgeName,
        );
        log("Device registry cleanup completed", "SUCCESS");
      }
    } else if (dryRun) {
      log("Dry run completed - no actual deletion performed", "INFO");
    } else {
      log("No entities were deleted", "WARN");
    }
  } finally {
    await context.close();
    await browser.close();

    // Optionally restart addon (only if deletion was successful)
    console.log("");
    if (deletionSuccessful && shouldRestart && !dryRun) {
      restartAddon(addonSlug);
    } else if (deletionSuccessful && !dryRun) {
      log(
        `Entities deleted but addon not restarted (set RESTART_ADDON=true to enable)`,
        "INFO",
      );
      console.log(`To restart manually: ha addons restart ${addonSlug}`);
    } else if (dryRun) {
      log("Dry run completed - no restart needed", "INFO");
    } else {
      log(`No entities were deleted - no restart needed`, "WARN");
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
