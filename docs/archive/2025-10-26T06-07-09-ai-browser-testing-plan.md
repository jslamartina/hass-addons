# AI Agent Browser Testing Guide

**Purpose:** Enable AI agents (like Claude) to test and interact with the Home Assistant UI using Cursor's built-in MCP Playwright tools.

**Status:** ✅ Active & In Use
**Last Updated:** October 24, 2025
**Maintained By:** AI Agent Development Team

---

## Overview

This is a living document that provides comprehensive guidance for AI agents to use browser automation tools for testing, debugging, and interacting with the Home Assistant UI. This guide captures real-world patterns, gotchas, and best practices discovered during active development and testing.

**Updates:** This document is actively maintained and updated as new patterns are discovered and best practices evolve. See [Real-World Testing Lessons](#real-world-testing-lessons) for findings from actual test execution.

## Available Tools

### Cursor MCP Playwright Tools

Cursor provides built-in MCP tools for browser automation (no additional configuration needed):

| Tool                                             | Purpose                    | When to Use                                    |
| ------------------------------------------------ | -------------------------- | ---------------------------------------------- |
| `mcp_cursor-playwright_browser_navigate`         | Navigate to URLs           | Opening HA pages, navigating between views     |
| `mcp_cursor-playwright_browser_snapshot`         | Capture accessibility tree | Understanding page structure, finding elements |
| `mcp_cursor-playwright_browser_click`            | Click elements             | Buttons, links, cards, tabs                    |
| `mcp_cursor-playwright_browser_type`             | Type text                  | Forms, search boxes, configuration inputs      |
| `mcp_cursor-playwright_browser_fill_form`        | Fill multiple form fields  | Login, configuration, bulk data entry          |
| `mcp_cursor-playwright_browser_evaluate`         | Run JavaScript             | Complex interactions, data extraction          |
| `mcp_cursor-playwright_browser_take_screenshot`  | Capture visual state       | Documentation, debugging, verification         |
| `mcp_cursor-playwright_browser_wait_for`         | Wait for conditions        | Dynamic content, async operations              |
| `mcp_cursor-playwright_browser_console_messages` | Get console logs           | Debug JavaScript errors                        |
| `mcp_cursor-playwright_browser_network_requests` | Get network activity       | API debugging, performance analysis            |

### Key Advantages

- ✅ No setup required - tools work immediately
- ✅ Headless by default (fast, non-intrusive)
- ✅ Built-in screenshot/snapshot capabilities
- ✅ Permission-based interaction (safe automation)

---

## Core Workflows

### 1. Login to Home Assistant

#### Pattern

```typescript
// 1. Navigate
mcp_cursor - playwright_browser_navigate({ url: "http://localhost:8123" });

// 2. Wait for login page
mcp_cursor - playwright_browser_wait_for({ text: "Log in", time: 5 });

// 3. Fill credentials (from hass-credentials.env)
mcp_cursor -
  playwright_browser_fill_form({
    fields: [
      {
        name: "Username",
        type: "textbox",
        ref: "input[name='username']",
        value: "dev",
      },
      {
        name: "Password",
        type: "textbox",
        ref: "input[name='password']",
        value: "dev",
      },
    ],
  });

// 4. Submit
mcp_cursor -
  playwright_browser_click({
    element: "Log in button",
    ref: "button[type='submit']",
  });

// 5. Wait for dashboard
mcp_cursor - playwright_browser_wait_for({ text: "Overview", time: 10 });
```text

### Credentials

- Location: `/mnt/supervisor/addons/local/hass-addons/hass-credentials.env`
- Username: `dev`
- Password: `dev`

### 2. Navigate to Add-on Configuration

#### Pattern

```typescript
// 1. Open Settings
mcp_cursor -
  playwright_browser_click({
    element: "Settings menu",
    ref: "a[href='/config']",
  });

// 2. Open Add-ons section
mcp_cursor -
  playwright_browser_click({
    element: "Add-ons link",
    ref: "a[href='/hassio/dashboard']",
  });

// 3. Find and click add-on
mcp_cursor -
  playwright_browser_click({
    element: "Cync Controller add-on",
    ref: "a[href*='local_cync-controller']",
  });

// 4. Switch to Configuration tab (add-on UI is in iframe!)
const iframe = page.frameLocator("iframe");
iframe.getByRole("tab", { name: "Configuration" }).click();
```text

**Important:** Add-on pages are rendered in iframes - use `frameLocator` to access content.

### 3. Verify Entity States

#### Pattern

```typescript
// 1. Navigate to Developer Tools → States
mcp_cursor -
  playwright_browser_navigate({
    url: "http://localhost:8123/developer-tools/state",
  });

// 2. Search for entities
mcp_cursor -
  playwright_browser_type({
    element: "Search box",
    ref: "input[placeholder='Filter entities']",
    text: "light.hallway",
  });

// 3. Take snapshot to see results
mcp_cursor - playwright_browser_snapshot();

// 4. Extract state data with JavaScript
mcp_cursor -
  playwright_browser_evaluate({
    function: `() => {
    const rows = document.querySelectorAll('ha-data-table tbody tr');
    return Array.from(rows).map(row => ({
      entity_id: row.querySelector('[data-column="entity_id"]')?.textContent,
      state: row.querySelector('[data-column="state"]')?.textContent
    }));
  }`,
  });
```text

### 4. Toggle Device Controls

#### Pattern

```typescript
// 1. Navigate to dashboard
mcp_cursor -
  playwright_browser_navigate({ url: "http://localhost:8123/lovelace/0" });

// 2. Take snapshot to see available controls
mcp_cursor - playwright_browser_snapshot();

// 3. Click entity card (NOT the toggle button - Shadow DOM issue)
mcp_cursor -
  playwright_browser_click({
    element: "Hallway Lights card",
    ref: "div[aria-label='Hallway Lights']",
  });

// 4. Wait for dialog
mcp_cursor - playwright_browser_wait_for({ text: "Brightness", time: 3 });

// 5. Adjust brightness slider
mcp_cursor -
  playwright_browser_click({
    element: "Brightness slider",
    ref: "input[type='range'][aria-label='Brightness']",
  });

// 6. Close dialog
mcp_cursor -
  playwright_browser_click({
    element: "Close button",
    ref: "button[aria-label='Close']",
  });
```text

### 5. Check Add-on Logs

#### Pattern

```typescript
// 1. Navigate to add-on page
mcp_cursor -
  playwright_browser_navigate({
    url: "http://localhost:8123/hassio/addon/local_cync-controller",
  });

// 2. Switch to Logs tab (in iframe)
const iframe = page.frameLocator("iframe");
iframe.getByRole("tab", { name: "Log" }).click();

// 3. Wait for logs to load
mcp_cursor - playwright_browser_wait_for({ time: 2 });

// 4. Extract logs
mcp_cursor -
  playwright_browser_evaluate({
    function: `() => document.querySelector('pre')?.textContent || "No logs found"`,
  });

// OR: Take screenshot for visual review
mcp_cursor - playwright_browser_take_screenshot({ filename: "addon-logs.png" });
```text

---

## Home Assistant UI Quirks

### Shadow DOM Elements

**Problem:** HA UI uses Web Components with Shadow DOM - standard selectors don't work.

#### Solutions

1. **Use `browser_snapshot` first** - Shows accessibility tree which pierces Shadow DOM

   ```typescript
   mcp_cursor - playwright_browser_snapshot();
   // Examine output to find accessible names and roles
   ```

```text

1. **Prefer role-based selectors** - Automatically work through Shadow DOM

   ```typescript
   // ✅ GOOD: Works with Shadow DOM
   ref: "button[role='button']" or use getByRole

   // ❌ BAD: Fails with Shadow DOM
   ref: "button.mdc-button"
```text

2. **Use text-based selectors** - Also pierce Shadow DOM

   ```typescript
   ref: "text=Configuration";
   ```

### SVG Icon Interference

**Problem:** Buttons with nested SVG icons cause "element intercepts pointer events" errors.

#### Solutions

1. **Click parent containers instead**

   ```typescript
   // ✅ GOOD: Click the card container
   mcp_cursor -
     playwright_browser_click({
       element: "Entity card",
       ref: "ha-card[data-entity-id='light.hallway']",
     });

   // ❌ BAD: Click the button (SVG blocks it)
   mcp_cursor -
     playwright_browser_click({
       element: "Toggle button",
       ref: "ha-icon-button",
     });
   ```

2. **Use programmatic clicks** (when UX testing isn't critical)

   ```typescript
   mcp_cursor -
     playwright_browser_evaluate({
       element: "Button description",
       ref: "button-selector",
       function: `(element) => element.click()`,
     });
   ```

3. **Click interactive controls directly** (sliders, switches, textboxes)

   ```typescript
   // ✅ GOOD: No SVG interference
   mcp_cursor -
     playwright_browser_click({
       element: "Brightness slider",
       ref: "input[type='range']",
     });
   ```

### Iframe Content

**Problem:** Add-on pages render in iframes - content isn't accessible from main page.

**Solution:** Reference iframe in selectors:

```typescript
// For add-on Configuration tab:
ref: "iframe >> button[name='Save']";

// Or use frameLocator pattern (see examples above)
```text

### Dynamic Content Loading

**Problem:** HA uses dynamic loading - elements appear after network requests.

#### Solutions

1. **Wait for specific text/elements**

   ```typescript
   mcp_cursor -
     playwright_browser_wait_for({ text: "Configuration saved", time: 5 });
   ```

```text

1. **Wait for network idle** (use browser_network_requests to monitor)

   ```typescript
   mcp_cursor - playwright_browser_network_requests();
   // Check if requests are complete
```text

2. **Use fixed delays** (last resort)

   ```typescript
   mcp_cursor - playwright_browser_wait_for({ time: 3 });
   ```

---

## Testing Strategies

### Strategy 1: Snapshot-Driven Testing

**When to use:** Exploring unfamiliar UI, finding elements, understanding state.

#### Pattern

```typescript
// 1. Navigate to page
mcp_cursor -
  playwright_browser_navigate({ url: "http://localhost:8123/config/entities" });

// 2. Take snapshot to understand structure
const snapshot = mcp_cursor - playwright_browser_snapshot();

// 3. Analyze snapshot output (accessibility tree)
// Look for:
// - Role attributes (button, link, textbox, etc.)
// - Accessible names (aria-label, text content)
// - Element hierarchy

// 4. Formulate interaction plan based on snapshot
// Example: Found 'button "Search entities"' in snapshot
mcp_cursor -
  playwright_browser_click({
    element: "Search button",
    ref: "button[aria-label='Search entities']",
  });
```text

### Advantages

- ✅ No guessing about element selectors
- ✅ Works with Shadow DOM
- ✅ Shows actual accessible names
- ✅ Faster than trial-and-error

### Strategy 2: Screenshot-First Debugging

**When to use:** Visual verification, understanding why something failed, documentation.

#### Pattern

```typescript
// 1. Navigate to problematic page
mcp_cursor -
  playwright_browser_navigate({ url: "http://localhost:8123/config/devices" });

// 2. Take screenshot before action
mcp_cursor -
  playwright_browser_take_screenshot({ filename: "before-click.png" });

// 3. Perform action
mcp_cursor -
  playwright_browser_click({ element: "Device", ref: "a[href*='/device/']" });

// 4. Take screenshot after action
mcp_cursor -
  playwright_browser_take_screenshot({ filename: "after-click.png" });

// 5. Compare screenshots to verify behavior
```text

### Advantages

- ✅ Visual proof of state
- ✅ Easier to communicate issues
- ✅ Useful for documentation
- ✅ Shows rendering issues

### Strategy 3: Console-Driven Debugging

**When to use:** JavaScript errors, API issues, performance problems.

#### Pattern

```typescript
// 1. Navigate and perform action
mcp_cursor - playwright_browser_navigate({ url: "http://localhost:8123" });
mcp_cursor -
  playwright_browser_click({ element: "Settings", ref: "a[href='/config']" });

// 2. Check console for errors
const messages = mcp_cursor - playwright_browser_console_messages();
// Look for errors, warnings, or unexpected log messages

// 3. Check network requests
const requests = mcp_cursor - playwright_browser_network_requests();
// Look for failed requests, slow responses, or unexpected API calls
```text

### Advantages

- ✅ Catches JavaScript errors
- ✅ Identifies failed API calls
- ✅ Shows timing issues
- ✅ Reveals unexpected behavior

### Strategy 4: Iterative Refinement

**When to use:** Complex workflows, multi-step operations, configuration testing.

#### Pattern

```typescript
// 1. Break task into small steps
// 2. Execute one step at a time
// 3. Verify after each step
// 4. Adjust based on results

// Example: Testing add-on configuration
// Step 1: Navigate
mcp_cursor -
  playwright_browser_navigate({
    url: "http://localhost:8123/hassio/addon/local_cync-controller",
  });
mcp_cursor - playwright_browser_snapshot(); // Verify we're on correct page

// Step 2: Open Configuration
const iframe = frameLocator("iframe");
// Click Configuration tab
mcp_cursor -
  playwright_browser_click({
    element: "Config tab",
    ref: "iframe >> a[role='tab']:has-text('Configuration')",
  });
mcp_cursor - playwright_browser_snapshot(); // Verify tab switched

// Step 3: Change setting
mcp_cursor -
  playwright_browser_click({
    element: "Debug toggle",
    ref: "iframe >> input[type='checkbox'][name='debug']",
  });
mcp_cursor -
  playwright_browser_take_screenshot({ filename: "config-changed.png" }); // Visual confirmation

// Step 4: Save
mcp_cursor -
  playwright_browser_click({
    element: "Save button",
    ref: "iframe >> button:has-text('Save')",
  });
mcp_cursor -
  playwright_browser_wait_for({ text: "Configuration saved", time: 5 }); // Wait for success
```text

### Advantages

- ✅ Easy to debug failures
- ✅ Clear understanding of each step
- ✅ Can recover from errors
- ✅ Builds reliable workflows

---

## Best Practices for AI Agents

### DO ✅

1. **Always start with `browser_snapshot`**
   - Understand page structure before interacting
   - Find accessible names and roles
   - Identify clickable elements

2. **Use descriptive element names**
   - "Login button" not "button1"
   - "Hallway Lights card" not "div"
   - Helps with permission prompts

3. **Wait for dynamic content**
   - Use `wait_for` with specific text/time
   - Check console/network for completion
   - Don't assume instant loading

4. **Verify after actions**
   - Take screenshots to confirm changes
   - Check console for errors
   - Use snapshots to verify state

5. **Handle iframes explicitly**
   - Add-on pages are in iframes
   - Use `iframe >>` selector prefix
   - Test iframe content separately

6. **Prefer API tools over browser**
   - Use `scripts/configure-addon.sh` for config
   - Use `ha` CLI for add-on management
   - Browser is for UI testing only

7. **Document your findings**
   - Save screenshots with descriptive names
   - Log successful patterns
   - Note UI quirks discovered

### DON'T ❌

1. **Don't use force clicks**
   - Bypasses safety checks
   - Hides real UX issues
   - Makes tests unreliable

2. **Don't hardcode selectors**
   - Use accessible names from snapshots
   - Prefer role-based selectors
   - HA UI changes frequently

3. **Don't assume page state**
   - Always verify with snapshot/screenshot
   - Wait for expected elements
   - Check console for errors

4. **Don't ignore Shadow DOM**
   - Standard CSS selectors fail
   - Use role-based or text selectors
   - Take snapshots to understand structure

5. **Don't skip error checking**
   - Check console messages
   - Review network requests
   - Verify expected outcomes

6. **Don't test what can be automated**
   - Use API tools for configuration
   - Use CLI for add-on operations
   - Browser is for UI-specific testing

7. **Don't create manual workflows**
   - Script repetitive tasks
   - Create helper functions
   - Share patterns in docs

---

## Common Testing Scenarios

### Scenario 1: Verify Add-on Configuration UI

**Goal:** Ensure new configuration options appear correctly.

#### Steps

1. Navigate to add-on configuration
2. Take snapshot to verify options present
3. Toggle each option and verify behavior
4. Save configuration and check for errors
5. Restart add-on and verify settings applied
6. Check add-on logs for configuration loading

### Expected Results

- All options visible in UI
- Changes save without errors
- Settings persist after restart
- Logs show correct configuration

### Scenario 2: Test Entity Discovery

**Goal:** Verify devices appear in Home Assistant after add-on starts.

#### Steps

1. Navigate to MQTT integration entities page
2. Take snapshot to count existing entities
3. Restart add-on (use API, not browser)
4. Wait for discovery (30-60 seconds)
5. Refresh entities page
6. Take snapshot to count new entities
7. Verify entity attributes (area, device class, etc.)

### Expected Results

- New entities appear after discovery
- Entity names match expected format
- Attributes set correctly
- Entities are controllable

### Scenario 3: Test Device Control

**Goal:** Verify toggling devices works end-to-end.

#### Steps

1. Navigate to dashboard
2. Take snapshot to find test device
3. Click device card to open control dialog
4. Adjust brightness/toggle state
5. Close dialog
6. Check add-on logs for command sent
7. Verify device state updated in UI

### Expected Results

- Control dialog opens without errors
- State changes reflected immediately
- Add-on logs show command sent
- Physical device responds (if available)

### Scenario 4: Test Error Handling

**Goal:** Verify graceful error handling in UI.

#### Steps

1. Stop MQTT broker (simulate failure)
2. Navigate to entities page
3. Attempt to toggle device
4. Check console for error messages
5. Take screenshot of error state
6. Restart MQTT broker
7. Verify recovery

### Expected Results

- Clear error message shown to user
- No JavaScript errors in console
- Graceful recovery after restart
- Entities become available again

---

## Integration with Existing Tools

### Complement to Playwright Scripts

#### MCP tools are for

- Interactive exploration
- Quick verification
- Ad-hoc testing
- Debugging issues

### TypeScript scripts are for

- Repeatable workflows
- CI/CD integration
- Bulk operations
- Complex scenarios

### When to use each

| Task                                 | MCP Tools   | TypeScript Script |
| ------------------------------------ | ----------- | ----------------- |
| "Is the config option visible?"      | ✅ Perfect  | ❌ Overkill       |
| "Delete all MQTT entities"           | ❌ Too slow | ✅ Perfect        |
| "How does the UI handle this error?" | ✅ Perfect  | ❌ Complex        |
| "Run full integration test suite"    | ❌ Manual   | ✅ Perfect        |

### Using MCP Tools to Build TypeScript Scripts

#### Pattern

1. Use MCP tools to explore UI interactively
2. Document successful element selectors and patterns
3. Convert to TypeScript script for automation
4. Add to `scripts/playwright/` directory
5. Create shell wrapper if needed

### Example

```typescript
// 1. Explored with MCP tools, found working selectors:
// - iframe >> button[role="tab"]:has-text("Configuration")
// - iframe >> input[type="checkbox"][name="debug"]
// - iframe >> button:has-text("Save")

// 2. Convert to TypeScript script:
import { test } from "@playwright/test";

test("Toggle debug mode", async ({ page }) => {
  await page.goto("http://localhost:8123/hassio/addon/local_cync-controller");
  const frame = page.frameLocator("iframe");

  await frame.getByRole("tab", { name: "Configuration" }).click();
  await frame.getByRole("checkbox", { name: "debug" }).click();
  await frame.getByRole("button", { name: "Save" }).click();

  await page.waitForSelector("text=Configuration saved");
});
```text

---

## Troubleshooting Guide

### Issue: "Element not found"

#### Possible causes

- Shadow DOM hiding element
- Element in iframe
- Element not yet loaded
- Incorrect selector

### Debug steps

1. Take `browser_snapshot` to see accessibility tree
2. Check if element is in iframe (add-on pages)
3. Wait for dynamic content with `wait_for`
4. Try role-based or text-based selector
5. Check console for JavaScript errors

### Issue: "Element intercepts pointer events"

#### Possible causes

- SVG icon covering button (⚠️ **VERY COMMON** in HA UI)
- Overlay/modal in the way
- Z-index issues

**Most common:** Small icon-only buttons (clear, filter, menu) have nested `<ha-svg-icon>` that intercept clicks.

### Best Practice Solutions (in priority order)

1. **Click parent container** (PREFERRED - tests real user behavior)

   ```typescript
   // ✅ Click the wrapper/card that users actually click
   await browser_click({
     element: "Filter card",
     ref: "div:has(button[aria-label='Filters'])",
   });
   ```

```text

1. **Use `browser_snapshot()` to find the actual clickable element**
   - The snapshot shows what's REALLY clickable (often a wrapper div)
   - Look for parent elements that contain the button

2. **Programmatic click** (LAST RESORT - bypasses Playwright safety checks)

   ```typescript
   // ⚠️ Only use when parent clicking isn't possible
   await browser_evaluate({
     element: "Button description",
     ref: "button-ref",
     function: "(element) => element.click()",
   });
```text

**Playwright Philosophy:** The "element intercepts pointer events" error is **catching a real UX issue** - something is blocking natural interaction. Work with Playwright, not against it.

**Real-world lesson:** Use `browser_snapshot()` to identify the actual clickable element (usually a parent container), not just the button itself.

### Issue: "Action succeeded but state didn't change"

#### Possible causes

- Command sent but not acknowledged
- Add-on not receiving command
- Device offline
- Network issue

### Debug steps

1. Check add-on logs for command sent
2. Check console for API errors
3. Check network requests for failures
4. Verify add-on is running
5. Test with CLI/API tools to isolate UI

### Issue: "Can't find configuration option"

#### Possible causes

- Add-on not rebuilt after schema change
- Browser cache showing old version
- Supervisor cache not cleared

### Additional Debug Steps

1. Verify add-on version with `ha addons info`
2. Take screenshot of current config UI
3. Rebuild add-on: `cd cync-controller && ./rebuild.sh`
4. Hard refresh browser
5. Check Supervisor logs for errors

---

## Examples and Templates

### Template: Login and Navigate

```typescript
// Reusable login pattern
async function loginToHomeAssistant() {
  (await mcp_cursor) -
    playwright_browser_navigate({ url: "http://localhost:8123" });
  (await mcp_cursor) - playwright_browser_wait_for({ text: "Log in", time: 5 });

  (await mcp_cursor) -
    playwright_browser_fill_form({
      fields: [
        {
          name: "Username",
          type: "textbox",
          ref: "input[name='username']",
          value: "dev",
        },
        {
          name: "Password",
          type: "textbox",
          ref: "input[name='password']",
          value: "dev",
        },
      ],
    });

  (await mcp_cursor) -
    playwright_browser_click({
      element: "Log in button",
      ref: "button[type='submit']",
    });

  (await mcp_cursor) -
    playwright_browser_wait_for({ text: "Overview", time: 10 });
}
```text

### Template: Verify Entity State

```typescript
// Check specific entity state
async function verifyEntityState(entityId: string, expectedState: string) {
  (await mcp_cursor) -
    playwright_browser_navigate({
      url: "http://localhost:8123/developer-tools/state",
    });

  (await mcp_cursor) -
    playwright_browser_type({
      element: "Entity filter",
      ref: "input[placeholder='Filter entities']",
      text: entityId,
    });

  const snapshot = (await mcp_cursor) - playwright_browser_snapshot();
  // Parse snapshot to find entity and verify state matches expectedState

  return snapshot.includes(expectedState);
}
```text

### Template: Take Debug Screenshots

```typescript
// Capture state at key points
async function debugWorkflow(workflowName: string) {
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const prefix = `${workflowName}-${timestamp}`;

  (await mcp_cursor) -
    playwright_browser_take_screenshot({
      filename: `${prefix}-01-start.png`,
    });

  // ... perform actions ...

  (await mcp_cursor) -
    playwright_browser_take_screenshot({
      filename: `${prefix}-02-after-action.png`,
    });

  const console = (await mcp_cursor) - playwright_browser_console_messages();
  const network = (await mcp_cursor) - playwright_browser_network_requests();

  // Log results for analysis
  return { console, network };
}
```text

---

## Success Metrics

### How to measure effective browser testing

1. **Coverage**
   - ✅ All configuration options tested
   - ✅ All entity types verified
   - ✅ Error scenarios handled
   - ✅ Edge cases explored

2. **Reliability**
   - ✅ Tests pass consistently
   - ✅ Failures are meaningful (not flaky)
   - ✅ Selectors work across HA versions
   - ✅ No force clicks needed

3. **Speed**
   - ✅ Tests complete in reasonable time
   - ✅ Minimal unnecessary waiting
   - ✅ Snapshots used before screenshots
   - ✅ API tools used when appropriate

4. **Documentation**
   - ✅ Patterns documented and reusable
   - ✅ Quirks and workarounds recorded
   - ✅ Screenshots saved with context
   - ✅ Findings shared in docs

---

## Future Enhancements

### Potential improvements

1. **Helper Library**
   - Create `scripts/playwright/helpers/ha-helpers.ts`
   - Centralize login, navigation, common patterns
   - Share selectors and element references

2. **Test Fixtures**
   - Standard test data setup/teardown
   - Predictable entity states
   - Isolated test environments

3. **Visual Regression Testing**
   - Screenshot comparison
   - Detect unexpected UI changes
   - Verify responsive design

4. **Performance Testing**
   - Measure page load times
   - Track network request counts
   - Identify slow interactions

5. **Accessibility Testing**
   - Verify ARIA labels
   - Check keyboard navigation
   - Test screen reader compatibility

---

## Related Documentation

- **[Browser Automation Guide](browser-automation.md)** - Detailed Playwright patterns
- **[AGENTS.md](../../AGENTS.md)** - Full AI agent guidelines
- **[MCP Tools Guide](mcp-tools.md)** - All available MCP tools
- **[Scripts README](../../scripts/playwright/README.md)** - TypeScript automation scripts
- **[Troubleshooting Guide](../user/troubleshooting.md)** - Common issues and solutions

---

## Quick Reference Card

```text
🏠 Home Assistant
   URL: http://localhost:8123
   User: dev / Pass: dev

🔧 Add-on Config
   Settings → Add-ons → Cync Controller → Configuration tab (IN IFRAME!)

🐛 Debugging

   1. snapshot() - See structure
   2. screenshot() - See visual state
   3. console_messages() - See errors
   4. network_requests() - See API calls

⚠️ Remember
   - Shadow DOM: Use role/text selectors
   - Iframes: Add "iframe >>" prefix
   - SVGs: Click parent containers
   - Wait: Dynamic content needs time

📚 More Help
   See docs/developer/browser-automation.md
```text

---

## Real-World Testing Lessons

### From actual Test Entity Discovery scenario execution (October 24, 2025)

### Gotcha 1: SVG Icon Interference is Pervasive

**Problem:** Small buttons (especially icon-only buttons) consistently fail to click due to SVG icon interception.

#### Examples encountered

- "Clear filter" button on Entities page
- "Clear input" (X) button in search boxes
- Any button with nested `<ha-svg-icon>` elements

**What Playwright is telling you:** The error "element intercepts pointer events" is Playwright catching a real UX issue - something is blocking the natural click target.

### Best Practice Solution

```typescript
// ✅ CORRECT: Click the parent container (tests real user behavior)
(await mcp_cursor) -
  playwright_browser_click({
    element: "Filter section",
    ref: "div:has(button[aria-label='Clear filter'])",
  });

// ❌ ANTI-PATTERN: Programmatic click (bypasses safety checks)
// Only use as last resort for non-critical UI elements
(await mcp_cursor) -
  playwright_browser_evaluate({
    element: "Clear filter button",
    ref: "button-ref",
    function: "(element) => element.click()",
  });
```text

**Lesson:** **Use `browser_snapshot()` to find the actual clickable element** (usually a parent container), not the button itself. Playwright's actionability checks are a feature, not a bug - they catch real UX issues.

### Gotcha 2: Filter Persistence Across Navigation

**Problem:** Navigating to entities page from MQTT integration carried over a filter (via URL parameter `config_entry=...`) showing "0 entities" with a badge indicator.

#### What happened

1. Clicked "65 entities" link from MQTT integration page
2. Landed on entities page with URL parameter filter active
3. Showed "Search 0 entities" with filter badge
4. Confusing because entities exist, just filtered out

### Solution

- Always check for filter badges/indicators
- Clear filters before taking entity counts
- Or navigate to clean URL: `http://localhost:8123/config/entities`

**Lesson:** Home Assistant **persists filters across navigation** - always check for active filters when entities appear missing.

### Gotcha 3: Search Box State Persists After Navigation

**Problem:** Typing "mqtt" in search box, then navigating away and back still showed "mqtt" in the input.

#### What happened

1. Filtered entities by typing "mqtt"
2. Navigated to different page
3. Navigated back to entities
4. Search input still contained "mqtt" text

**Solution:** Use full page refresh (`browser_navigate` to same URL) to clear all state.

**Lesson:** Browser state management can be **stickier than expected** - prefer full navigation over back/forward when you need clean state.

### Gotcha 4: CLI Flag Differences

**Problem:** Tried `ha addons logs local_cync-controller --tail 20` but flag doesn't exist.

**Correct flag:** `-n 20` (number of lines) not `--tail 20`

**Lesson:** Always check `ha [command] --help` for exact flag names - don't assume based on other CLI tools.

### Gotcha 5: Entity Count ≠ Entity Discovery Success

**Problem:** Expected entity count to change after restart, but it stayed at 112.

#### What actually changed

- Entity **states** updated (Unavailable → actual values)
- "Cync Devices Managed": Unavailable → "43"
- "Cync Export Server Running": Unavailable → "Running"
- "TCP Devices Connected": Unavailable → "8"

**Lesson:** Entity **discovery success** is about **state updates**, not count changes. Check entity states/availability, not just count.

### Gotcha 6: Discovery is Faster Than Expected

**Problem:** Test plan suggested 30-60 second wait for discovery.

**Reality:** Add-on logs showed discovery completed within ~5 seconds. The 30-second wait was overly cautious.

**Lesson:** Monitor add-on logs with `ha addons logs` to know exactly when discovery completes rather than guessing wait times.

### Gotcha 7: Can't Clear Search Input Easily

**Problem:** The "X" (clear) button in search boxes has SVG interference.

#### Attempted solutions

1. Normal click → Failed (SVG intercepts)
2. Programmatic click → Still failed
3. Navigate away and back → Works but clumsy

**Best solution:** Just refresh the page or type new text over existing.

**Lesson:** For search inputs, **don't bother clicking clear buttons** - just refresh page or type new search.

### Patterns That Worked Well

✅ **Starting with `browser_snapshot()`** - Instantly showed structure and available elements (reveals actual clickable elements)

✅ **Taking screenshots at key points** - Created visual record of before/after states

✅ **Using terminal commands for add-on operations** - `ha addons restart` worked perfectly, no need for browser automation

✅ **Filtering by "mqtt" to focus** - Made it easy to count and verify MQTT-specific entities

✅ **Using programmatic clicks when necessary** - For genuinely non-critical UI elements where parent clicking wasn't feasible (but prefer parent container clicks first)

### Recommendations for Future Tests

1. **Use `browser_snapshot()` first** - Reveals actual clickable elements (usually parent containers)

2. **Click parent containers, not buttons** - Tests real user behavior and avoids SVG issues

3. **Always check for filter badges** - HA UI loves to persist filters

4. **Use add-on logs to verify state** - More reliable than guessing wait times

5. **Take before/after screenshots** - Visual documentation is valuable

6. **Watch for state changes, not just counts** - Discovery updates states, not always counts

7. **Prefer page refresh over button clicks** - Especially for clearing filters/searches (or just type new search text)

8. **Start broad, then filter** - Easier to see full state then filter down than troubleshoot missing data

9. **Programmatic clicks are last resort** - Only for non-critical UI when parent clicking impossible

---

## How to Use This Document

- **Getting Started:** Begin with [Core Workflows](#core-workflows) to learn basic patterns
- **Troubleshooting:** Check [Troubleshooting Guide](#troubleshooting-guide) for common issues
- **Real Lessons:** See [Real-World Testing Lessons](#real-world-testing-lessons) for gotchas from actual testing
- **Contributing:** If you discover new patterns, please update this document

---

## Document Status

✅ **Active & In Use** - This document is actively used by AI agents for testing and has been validated through real-world test execution. See test results in [Test Results](test-results.md).

**Last Major Update:** October 24, 2025
**Validation:** Tested in multi-device environment with Playwright automation

_This is a living document. Update it as new patterns emerge._
