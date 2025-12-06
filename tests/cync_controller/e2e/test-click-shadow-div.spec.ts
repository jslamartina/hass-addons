import { test } from "@playwright/test";
import { login } from "./helpers/auth";

const BASE_URL = process.env.HA_BASE_URL || "http://localhost:8123";
const USERNAME = process.env.HA_USERNAME || "dev";
const PASSWORD = process.env.HA_PASSWORD || "dev";

test("Click div.row.pointer inside shadow DOM", async ({ page }) => {
  await login(page, BASE_URL, USERNAME, PASSWORD);

  await page.goto("/lovelace/0");
  await page.waitForLoadState("networkidle");

  console.log("Looking for div.row.pointer inside shadow DOM...");

  // Find the web component
  const fanRow = page
    .locator("hui-generic-entity-row, hui-toggle-entity-row")
    .filter({ hasText: "Bedroom Fan Switch" })
    .first();

  // Check if div.row.pointer exists inside shadow DOM
  const clickableDiv = fanRow.locator("div.row.pointer");
  const divCount = await clickableDiv.count();
  console.log(`Found ${divCount} div.row.pointer elements inside shadow DOM`);

  if (divCount === 0) {
    // Try without .pointer class
    const divRow = fanRow.locator("div.row");
    const divRowCount = await divRow.count();
    console.log(
      `Found ${divRowCount} div.row elements (without .pointer class)`,
    );

    // Try with just .row class
    const rowClass = fanRow.locator(".row");
    const rowClassCount = await rowClass.count();
    console.log(`Found ${rowClassCount} .row elements`);

    // List all divs inside
    const allDivs = fanRow.locator("div");
    const allDivsCount = await allDivs.count();
    console.log(`Found ${allDivsCount} total div elements inside shadow DOM`);

    // Get classes of first few divs
    for (let i = 0; i < Math.min(allDivsCount, 5); i++) {
      const div = allDivs.nth(i);
      const className = await div.getAttribute("class");
      console.log(`  Div ${i + 1} class: "${className}"`);
    }
  } else {
    console.log(" Found div.row.pointer, trying to click it...");
    await clickableDiv.click();
    await page.waitForTimeout(2000);

    const dialog = page.locator("ha-more-info-dialog");
    const isVisible = await dialog.isVisible();
    console.log(`Dialog visible after click: ${isVisible}`);
  }
});
