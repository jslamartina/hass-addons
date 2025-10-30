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
  // The dialog is inside shadow DOM, so we use getByRole which pierces shadow DOM
  const moreInfo = page.getByRole("alertdialog").first();

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
 * Select a preset mode from buttons or dropdown
 */
export async function selectFanPreset(
  page: Page,
  card: Locator,
  preset: string,
): Promise<void> {
  // First, try to find preset buttons (newer UI style)
  // Use page-level getByRole which pierces shadow DOM
  const presetButton = page.getByRole("button", {
    name: new RegExp(preset, "i"),
  }).first();

  if ((await presetButton.count()) > 0) {
    // Preset buttons found - verify it's visible and clickable
    await expect(presetButton).toBeVisible({ timeout: 3000 });
    // Use force click in case dialog intercepts pointer events
    await presetButton.click({ force: true });
    await page.waitForTimeout(1000);
    return;
  }

  // Fallback: look for combobox (using page-level getByRole to pierce shadow DOM)
  const presetCombobox = page.getByRole("combobox", {
    name: /preset mode/i,
  }).first();

  // Wait for combobox to be visible (might take time for dialog to render)
  // Also ensure dialog is still open
  const dialog = page.getByRole("alertdialog").first();
  try {
    await expect(dialog).toBeAttached({ timeout: 2000 });
    await expect(presetCombobox).toBeVisible({ timeout: 5000 });
  } catch {
    // If dialog closed or combobox not visible, check if combobox exists at all
    if ((await presetCombobox.count()) === 0) {
      throw new Error(
        `Preset mode '${preset}' not found - dialog may have closed or combobox unavailable`,
      );
    }
    // If dialog closed, we need to wait for UI to settle
    await page.waitForTimeout(1000);
    // Retry visibility check
    await expect(presetCombobox).toBeVisible({ timeout: 3000 });
  }

  // Wait for combobox to be ready (dropdown closed from previous selection)
  await page.waitForTimeout(500);

  // Click to open dropdown - ensure it's not already expanded
  const isExpanded = await presetCombobox.getAttribute("aria-expanded");
  if (isExpanded !== "true") {
    // Verify combobox is still visible before clicking
    await expect(presetCombobox).toBeVisible({ timeout: 3000 });
    await presetCombobox.click({ force: true });
    await page.waitForTimeout(500);
  }

  // Click the preset option from the dropdown menu
  const presetOption = page.getByRole("option", {
    name: new RegExp(preset, "i"),
  });

  if ((await presetOption.count()) === 0) {
    throw new Error(`Preset option '${preset}' not found in dropdown`);
  }

  // Verify option is visible before clicking
  await expect(presetOption).toBeVisible({ timeout: 3000 });
  await presetOption.click();

  // Wait for state update
  await page.waitForTimeout(1000);
}

/**
 * Get the current fan percentage from preset mode
 */
export async function getFanPercentage(
  page: Page,
  card: Locator,
): Promise<number> {
  const presetMap: Record<string, number> = {
    off: 0,
    low: 20,
    medium: 50,
    high: 75,
    max: 100,
  };

  // First, try to read from preset buttons (check for pressed/selected state)
  // Use page-level getByRole which pierces shadow DOM
  for (const [presetName, percent] of Object.entries(presetMap)) {
    const presetButton = page
      .getByRole("button", {
        name: new RegExp(presetName, "i"),
      })
      .first();

    if ((await presetButton.count()) > 0) {
      // Verify button is visible before checking attributes
      try {
        await expect(presetButton).toBeVisible({ timeout: 2000 });
      } catch {
        // Button exists but not visible - skip this preset and continue searching
        continue;
      }
      const isPressed = await presetButton.getAttribute("aria-pressed");
      const className = await presetButton.getAttribute("class");
      const hasSelectedClass =
        className?.includes("selected") || className?.includes("active");

      if (isPressed === "true" || hasSelectedClass) {
        return percent;
      }
    }
  }

  // Fallback: try to read from combobox (using page-level getByRole to pierce shadow DOM)
  const presetCombobox = page.getByRole("combobox", {
    name: /preset mode/i,
  }).first();

  if ((await presetCombobox.count()) > 0) {
    await expect(presetCombobox).toBeVisible({ timeout: 3000 });
    const comboboxText = (await presetCombobox.textContent()) || "";
    const preset = comboboxText.toLowerCase().trim();
    // Extract preset name from text (e.g., "medium" from "Preset mode\nmedium")
    const presetMatch = comboboxText.match(/\b(off|low|medium|high|max)\b/i);
    if (presetMatch) {
      return presetMap[presetMatch[1].toLowerCase()] || 0;
    }
    return presetMap[preset] || 0;
  }

  // If we can't find preset controls, throw an error instead of silently returning a default
  // Check if fan is on to provide better error message
  const isOn = await isFanOn(page, card);
  throw new Error(
    `Could not determine fan percentage - preset controls not found. Fan is ${isOn ? "on" : "off"}.`,
  );
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

  // Verify switch is visible before clicking
  await expect(toggleSwitch).toBeVisible({ timeout: 3000 });
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
