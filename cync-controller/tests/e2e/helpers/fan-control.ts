import { Page, Locator, expect } from "@playwright/test";

/**
 * Find and open a fan entity more-info dialog from the Overview dashboard
 * Fan entities in groups are shown as rows - clicking opens the more-info dialog
 */
export async function findFanCard(page: Page, name: string): Promise<Locator> {
  // Navigate to Overview if not already there
  await page.goto("/lovelace/0");
  await page.waitForLoadState("networkidle");

  // Use getByText() which automatically pierces shadow DOM and triggers correct events
  // This is the KEY - .locator() doesn't work, but getByText() does!
  const fanText = page.getByText(name, { exact: true });
  await expect(fanText).toBeVisible({ timeout: 10000 });

  // Click the text - this opens the more-info dialog
  await fanText.click();
  await page.waitForTimeout(1500);

  // Return the more-info dialog
  // It's at: document > home-assistant > ha-more-info-dialog
  // The dialog is inside shadow DOM, so we use getByText from the page to find content inside it
  // This pierces the shadow DOM boundaries automatically
  const moreInfo = page.locator("ha-more-info-dialog");

  // Wait for dialog to be attached to DOM and visible
  await expect(moreInfo).toBeAttached({ timeout: 5000 });

  // Wait a bit longer for it to become visible
  try {
    await expect(moreInfo).toBeVisible({ timeout: 3000 });
  } catch {
    // Dialog might be partially visible or transitioning, that's ok
  }

  return moreInfo;
}

/**
 * Set fan slider to a specific percentage
 */
export async function setFanSlider(
  page: Page,
  card: Locator,
  percent: number,
): Promise<void> {
  // Find the slider - use page-level locator which pierces shadow DOM
  const slider = page.locator("ha-control-slider").first();

  if ((await slider.count()) === 0) {
    throw new Error("Could not find fan slider");
  }

  // Set the slider value with proper event simulation
  await slider.evaluate((el, value) => {
    const input = el.shadowRoot?.querySelector(
      'input[type="range"]',
    ) as HTMLInputElement;
    if (input) {
      // Convert percentage to 0-255 range
      const numValue = (value * 255) / 100;

      // Simulate user interaction with proper events
      input.dispatchEvent(
        new PointerEvent("pointerdown", { bubbles: true, composed: true }),
      );
      input.value = String(numValue);
      input.dispatchEvent(
        new Event("input", { bubbles: true, composed: true }),
      );
      input.dispatchEvent(
        new Event("change", { bubbles: true, composed: true }),
      );
      input.dispatchEvent(
        new PointerEvent("pointerup", { bubbles: true, composed: true }),
      );
    }
  }, percent);

  // Wait for state to update
  await page.waitForTimeout(2500);
}

/**
 * Select a preset mode from the dropdown
 */
export async function selectFanPreset(
  page: Page,
  card: Locator,
  preset: string,
): Promise<void> {
  // Find preset dropdown - use page-level locator
  const presetSelect = page.locator("ha-select").first();

  if ((await presetSelect.count()) === 0) {
    console.log(
      `    Preset dropdown not found - preset feature may not be available`,
    );
    return;
  }

  // Click to open dropdown
  await presetSelect.click();
  await page.waitForTimeout(500);

  // Click the preset option from the dropdown menu
  const presetOption = page.getByRole("option", {
    name: new RegExp(preset, "i"),
  });

  if ((await presetOption.count()) === 0) {
    console.log(`    Preset option '${preset}' not found in dropdown`);
    return;
  }

  await presetOption.click();

  // Wait for state update
  await page.waitForTimeout(1000);
}

/**
 * Get the current fan percentage from the card
 */
export async function getFanPercentage(
  page: Page,
  card: Locator,
): Promise<number> {
  // Look for the slider control which shows current percentage
  const slider = page.locator("ha-control-slider").first();

  if ((await slider.count()) === 0) {
    return 0;
  }

  // Get aria-valuenow from the slider
  const percentage = await slider.getAttribute("aria-valuenow");
  if (!percentage) {
    return 0;
  }

  // Convert from 0-255 range back to 0-100 percentage
  const value = parseInt(percentage, 10);
  return Math.round((value / 255) * 100);
}

/**
 * Toggle fan power on or off
 */
export async function toggleFanPower(page: Page, card: Locator): Promise<void> {
  // Use page-level getByRole which pierces ALL shadow DOM boundaries
  const toggleSwitch = page.getByRole("switch").first();

  if ((await toggleSwitch.count()) === 0) {
    throw new Error("Could not find fan toggle switch");
  }

  // Use force: true because the dialog may intercept pointer events
  await toggleSwitch.click({ force: true });
  await page.waitForTimeout(2000); // Wait for state change and ACK
}

/**
 * Check if fan is currently on
 */
export async function isFanOn(page: Page, card: Locator): Promise<boolean> {
  // Use page-level selector to find switch
  const toggleSwitch = page.getByRole("switch").first();

  if ((await toggleSwitch.count()) === 0) {
    return false;
  }

  // Get aria-checked or check the input element
  const ariaChecked = await toggleSwitch.getAttribute("aria-checked");
  if (ariaChecked) {
    return ariaChecked === "true";
  }

  // Fallback: check for "on" state in text
  const stateText = await card.textContent();
  return stateText?.toLowerCase().includes("on") ?? false;
}

/**
 * Take a labeled screenshot for debugging
 */
export async function screenshot(page: Page, label: string): Promise<void> {
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const filename = `${timestamp}-${label.replace(/\s+/g, "-")}.png`;
  await page.screenshot({
    path: `test-results/fan-speed-screenshots/${filename}`,
    fullPage: true,
  });
}

/**
 * Get fan entity state from Developer Tools
 */
export async function getFanStateFromDevTools(
  page: Page,
  entityId: string,
): Promise<{
  state: string;
  percentage?: number;
  preset_mode?: string;
}> {
  // Navigate to Developer Tools  States
  await page.goto("/developer-tools/state");
  await page.waitForLoadState("networkidle");

  // Find entity row
  const entityRow = page.locator(`tr:has-text("${entityId}")`);
  await expect(entityRow).toBeVisible({ timeout: 5000 });

  // Extract state data
  const stateCell = entityRow.locator("td").nth(1);
  const stateText = (await stateCell.textContent()) || "";

  // Parse JSON attributes if available
  const attributesCell = entityRow.locator("td").nth(2);
  const attributesText = (await attributesCell.textContent()) || "{}";

  let percentage: number | undefined;
  let preset_mode: string | undefined;

  try {
    const attributes = JSON.parse(attributesText);
    percentage = attributes.percentage;
    preset_mode = attributes.preset_mode;
  } catch {
    // Attributes not in JSON format or parsing failed
  }

  return {
    state: stateText.trim(),
    percentage,
    preset_mode,
  };
}
