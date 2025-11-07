# Browser Automation with Playwright

**When to use:** Manual UI verification, visual testing, or when API tools are insufficient.

**Important:** Home Assistant UI uses Web Components with Shadow DOM and nested SVG icons that can interfere with clicks. Follow these best practices:

## Clicking Elements Properly

**Problem:** Buttons with nested SVG icons fail with "element intercepts pointer events" error.

### Solutions (in order of preference)

1. **Click parent containers** - Click the card/container element instead of buttons:

   ```javascript
   // ✅ GOOD: Click the entity card to open dialog
   await page
     .locator("div")
     .filter({ hasText: "Hallway Lights" })
     .nth(5)
     .click();
   ```

2. **Click interactive elements directly** - Use sliders, textboxes, and switches when available:

   ```javascript
   // ✅ GOOD: Click slider (no SVG interference)
   await page.getByRole("slider", { name: "Brightness" }).click();

   // ✅ GOOD: Type in textbox
   await page.getByRole("textbox", { name: "Username*" }).fill("dev");
   ```

3. **Use dispatchEvent for programmatic clicks** - When user interaction isn't critical:

   ```javascript
   // ⚠️ ACCEPTABLE: Programmatic click (doesn't test real UX)
   await page.evaluate(() => {
     document
       .querySelector('button[aria-label="Toggle"]')
       .dispatchEvent(new MouseEvent("click", { bubbles: true }));
   });
   ```

4. **Force clicks as last resort** - Only when absolutely necessary:

   ```javascript
   // ❌ AVOID: Bypasses actionability checks (makes tests flaky)
   await page.getByRole("button", { name: "Toggle" }).click({ force: true });
   ```

## Best Practices

- **Never use `{force: true}`** unless absolutely necessary - it bypasses Playwright's safety checks
- **Prefer API tools** over browser automation for configuration changes (see `scripts/configure-addon.sh`)
- **Wait for elements** - Playwright autowaits, but add explicit waits for dynamic content:

  ```javascript
  await page.waitForTimeout(3000); // Wait for dialog to load
  ```

- **Use semantic selectors** - Prefer `getByRole`, `getByLabel`, `getByText` over CSS selectors
- **Test with snapshots** - Use `browser_snapshot` to see current page state before clicking

## Common Patterns

```javascript
// Login
await page.getByRole("textbox", { name: "Username*" }).fill("dev");
await page.getByRole("textbox", { name: "Password*" }).fill("dev");
await page.getByRole("button", { name: "Log in" }).click();
await page.waitForTimeout(3000);

// Open entity dialog - Click the card, not the button
await page.locator("div").filter({ hasText: "Entity Name" }).click();

// Adjust slider
await page.getByRole("slider", { name: "Brightness" }).click();

// Close dialog - Find close button by label
await page.getByLabel("Close").click();
```

## Reliable Control Interaction Patterns

### Buttons and Tabs

- Prefer `getByRole` with accessible names:

  ```ts
  await page.getByRole("button", { name: /Save/i }).click();
  await page.getByRole("tab", { name: /Configuration/i }).click();
  ```

- If an SVG inside the button intercepts pointer events, click the parent container:

  ```ts
  await page
    .locator("div, ha-card, section, a, button")
    .filter({ hasText: /Configuration/i })
    .first()
    .click();
  ```

- Programmatic fallback when user interaction isn't critical:

  ```ts
  const btn = page.getByRole("button", { name: /Save/i });
  await btn.evaluate((el: HTMLElement) => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  ```

- Avoid `{ force: true }` unless absolutely necessary.

### Switches, Sliders, and Textboxes

- Prefer interactive controls directly (more reliable than small icon buttons):

  ```ts
  await page.getByRole("switch", { name: /Debug/i }).click();
  await page.getByRole("slider", { name: /Brightness/i }).click();
  await page.getByRole("textbox", { name: /Username\*/i }).fill("dev");
  ```

### Iframes (Supervisor Add-on UI)

- The add-on pages under Settings → Add-ons are rendered in an iframe. Use a frame locator to interact with inner content:

  ```ts
  const f = page.frameLocator("iframe");
  await f.getByRole("link", { name: /Configuration/i }).click();
  await f.getByRole("button", { name: /^Save$/i }).click();
  ```

### Enable Save Before Clicking

- The add-on "Save" button is disabled until a change is made. Toggle a field (for example, `Debug`) first, then click Save:

  ```ts
  const f = page.frameLocator("iframe");
  // Toggle to enable Save
  await f.getByRole("switch", { name: /Debug/i }).click();
  // Now Save should be enabled
  const save = f.getByRole("button", { name: /^Save$/i });
  await save.click().catch(async () => {
    // Fallback: parent container or programmatic dispatch
    await save.evaluate((el: HTMLElement) => {
      el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
  });
  ```

### Waiting for Stability

- Autowait helps, but add explicit waits for dynamic content or tab changes:

  ```ts
  const tab = page.getByRole("tab", { name: /Configuration/i });
  await tab.waitFor({ state: "visible" });
  await tab.click();
  ```

- Prefer `expect` when available for clearer intent:

  ```ts
  import { expect } from "@playwright/test";
  const f = page.frameLocator("iframe");
  const save = f.getByRole("button", { name: /^Save$/i });
  await expect(save).toBeVisible();
  await expect(save).toBeEnabled();
  ```

### Reusable Helper

- A small helper to attempt a normal click and fall back to programmatic dispatch:

  ```ts
  async function clickReliably(locator: import("@playwright/test").Locator) {
    try {
      await locator.click();
    } catch {
      await locator.evaluate((el: HTMLElement) => {
        el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      });
    }
  }

  const f = page.frameLocator("iframe");
  await clickReliably(f.getByRole("link", { name: /Configuration/i }));
  await clickReliably(f.getByRole("button", { name: /^Save$/i }));
  ```

### Finding Search Inputs in Shadow DOM

- Home Assistant's search boxes (for example, on Settings → Entities page) are nested inside shadow roots and can't be located with plain CSS selectors
- **Always use role-based selectors** that pierce through shadow DOM:

  ```ts
  // ✅ GOOD: Role-based selector works through shadow DOM
  const searchInput = page.getByRole("textbox", { name: /^Search/i });
  await searchInput.fill("Hallway");

  // ❌ BAD: querySelector can't find inputs inside shadow roots
  const input = page.locator("ha-data-table input"); // Returns empty
  ```

- The search input on `/config/entities` has a dynamic label like "Search 56 entities"
- Use a flexible pattern: `/^Search/i` or `/^Search \\d+ entities$/i`
- Playwright's `getByRole` automatically pierces shadow boundaries, making it the most reliable approach

### Deleting Entities via UI

- **MQTT entities can't be deleted through the UI** - they require the integration to stop providing them
- When attempting to delete MQTT entities, Home Assistant shows: "You can only delete 0 of N entities"
- To actually remove MQTT entities:
  1. Stop the addon/integration that provides them
  2. Wait for entities to become unavailable
  3. Delete them through the UI (they become deletable once unavailable)
  4. Alternatively: Restart Home Assistant after stopping the integration to clear the MQTT discovery cache

- For the "Delete selected" menu item: click the text "Delete selected" directly (ref to text element) rather than the menuitem role to avoid SVG interception

## Credentials

- **Location**: `/mnt/supervisor/addons/local/hass-addons/hass-credentials.env`
- **Username**: `dev`
- **Password**: `dev`

---

_For more information, see [AGENTS.md](../../AGENTS.md) in the repository root._
