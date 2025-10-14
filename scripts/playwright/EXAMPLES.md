# Playwright Script Examples

This file contains real-world usage examples for the Playwright automation scripts.

## Delete All MQTT Entities Except Bridge

### Example 1: Preview Before Deletion (Dry Run)

```bash
# See what would be deleted without actually deleting
./scripts/delete-mqtt-entities-except-bridge.sh --dry-run
```

**Output:**
```
╔═══════════════════════════════════════════════════════════════════════╗
║     Delete All MQTT Entities (Except Bridge) - Shell Wrapper        ║
╚═══════════════════════════════════════════════════════════════════════╝

Configuration:
  Home Assistant URL: http://localhost:8123
  Bridge to preserve: CyncLAN Bridge
  Addon slug:         local_cync-lan
  Restart after:      false
  Dry run mode:       true

ℹ️ Run directory: test-results/runs/delete-mqtt-2025-10-14T08-45-23
ℹ️ Bridge to preserve: CyncLAN Bridge
ℹ️ Addon: local_cync-lan
ℹ️ Will restart addon: false
⚠️ Dry run mode: true

ℹ️ Navigating to MQTT integration page
✅ MQTT integration card clicked
✅ Opened MQTT devices view
ℹ️ Discovering all MQTT entities
ℹ️ Found 25 total rows in the table
ℹ️ PRESERVE: CyncLAN Bridge (part of CyncLAN Bridge)
ℹ️ DELETE: Hallway Front Switch
ℹ️ DELETE: Hallway Counter Switch
ℹ️ DELETE: Hallway 4way Switch
ℹ️ DELETE: Bedroom Ceiling Light
...

═════════════════ DISCOVERY SUMMARY ═════════════════
Total entities found: 24
✅ To preserve (CyncLAN Bridge): 1
   - CyncLAN Bridge
❌ To delete: 23
   - Hallway Front Switch
   - Hallway Counter Switch
   - Hallway 4way Switch
   - Bedroom Ceiling Light
   ...
═════════════════════════════════════════════════════

⚠️ DRY RUN MODE - No entities will be actually deleted
ℹ️ Entities that WOULD be deleted:
ℹ️   - Hallway Front Switch
ℹ️   - Hallway Counter Switch
...
ℹ️ Dry run completed - no actual deletion performed

📝 Full log saved: test-results/runs/delete-mqtt-2025-10-14T08-45-23/run.log
📂 Screenshots: test-results/runs/delete-mqtt-2025-10-14T08-45-23/screenshots
```

### Example 2: Delete and Restart Addon

```bash
# Delete all entities except bridge and restart addon
./scripts/delete-mqtt-entities-except-bridge.sh --restart
```

This will:
1. Delete all MQTT entities except CyncLAN Bridge
2. Clean up device registry entries
3. Restart the addon to republish entities

**Use case:** Testing entity rediscovery with fresh device metadata.

### Example 3: Custom Bridge Name

```bash
# If your bridge has a different name
./scripts/delete-mqtt-entities-except-bridge.sh --bridge "My Custom Bridge"
```

### Example 4: Debugging with Visible Browser

```bash
# Watch the script execute in a visible browser window
./scripts/delete-mqtt-entities-except-bridge.sh --headed
```

**Use case:** Debugging script issues or understanding how it works.

### Example 5: Full TypeScript Control

```bash
# Use environment variables for complete control
cd /mnt/supervisor/addons/local/hass-addons

# Set all configuration via environment
export HA_BASE_URL="http://localhost:8123"
export HA_USERNAME="dev"
export HA_PASSWORD="dev"
export ADDON_SLUG="local_cync-lan"
export BRIDGE_NAME="CyncLAN Bridge"
export RESTART_ADDON="true"
export DRY_RUN="false"
export HEADED="1"

# Run the TypeScript script directly
npx ts-node scripts/playwright/delete-all-mqtt-entities-except-bridge.ts
```

## Delete Specific MQTT Entities

### Example 1: Delete Individual Entities

```bash
# Delete specific entities by name
HA_USERNAME=dev HA_PASSWORD=dev \
npx ts-node scripts/playwright/delete-mqtt-entities.ts \
  "Hallway Front Switch" \
  "Hallway Counter Switch" \
  "Hallway 4way Switch"
```

### Example 2: Delete and Restart

```bash
# Delete entities and restart addon immediately
RESTART_ADDON=true \
npx ts-node scripts/playwright/delete-mqtt-entities.ts \
  "Bedroom Ceiling Light" \
  "Kitchen Under Cabinet Lights"
```

## Common Workflows

### Workflow 1: Clean Slate for Testing

```bash
# 1. Stop addon
ha addons stop local_cync-lan

# 2. Preview what will be deleted
./scripts/delete-mqtt-entities-except-bridge.sh --dry-run

# 3. Delete all entities except bridge
./scripts/delete-mqtt-entities-except-bridge.sh

# 4. Verify bridge is still present
ha addons start local_cync-lan
ha addons logs local_cync-lan --follow

# 5. Entities should republish automatically
```

### Workflow 2: Test Entity Recreation After Config Change

```bash
# Scenario: You changed suggested_area in mqtt_client.py

# 1. Delete all entities (bridge preserved)
./scripts/delete-mqtt-entities-except-bridge.sh

# 2. Restart addon to apply Python changes and republish
ha addons restart local_cync-lan

# 3. Check that entities appear in new areas
# Navigate to Settings → Devices & Services → Entities
# Verify entities are in correct suggested_area
```

### Workflow 3: Targeted Entity Cleanup

```bash
# Delete only specific problematic entities
npx ts-node scripts/playwright/delete-mqtt-entities.ts \
  "$(cat entities-to-delete.txt)"

# Where entities-to-delete.txt contains:
# Hallway Front Switch
# Hallway Counter Switch
# Bedroom Ceiling Light
```

### Workflow 4: Automated Testing in CI/CD

```bash
#!/bin/bash
# ci-test-entity-discovery.sh

# Clean environment
./scripts/delete-mqtt-entities-except-bridge.sh --restart

# Wait for republishing
sleep 10

# Verify entities exist
ha addons logs local_cync-lan | grep "Publishing MQTT discovery"

# Run additional tests
npm test
```

## Troubleshooting Examples

### Debug: Entity Not Found

```bash
# Run with headed mode to see current page
HEADED=1 DRY_RUN=true \
./scripts/delete-mqtt-entities-except-bridge.sh

# Check screenshots
ls -la test-results/runs/delete-mqtt-*/screenshots/
open test-results/runs/delete-mqtt-*/screenshots/03-mqtt-entities-list.png

# Check accessibility tree
cat test-results/runs/delete-mqtt-*/screenshots/03-mqtt-entities-list-a11y.yaml
```

### Debug: Click Failed

```bash
# Enable headed mode to watch clicks
HEADED=1 ./scripts/delete-mqtt-entities-except-bridge.sh

# The script uses clickReliably() which:
# 1. Waits for element to be visible
# 2. Tries normal click
# 3. Falls back to dispatchEvent if click intercepted
```

### Debug: Wrong Entities Selected

```bash
# Use dry run to verify discovery logic
DRY_RUN=true ./scripts/delete-mqtt-entities-except-bridge.sh

# Check the DISCOVERY SUMMARY section to see:
# - Which entities are classified as "to preserve"
# - Which entities are classified as "to delete"

# If classification is wrong, check BRIDGE_NAME matches exactly
BRIDGE_NAME="Exact Bridge Name" DRY_RUN=true \
./scripts/delete-mqtt-entities-except-bridge.sh
```

## Advanced Examples

### Custom Script: Delete Entities Matching Pattern

```typescript
// scripts/playwright/delete-entities-by-pattern.ts
import { chromium } from "playwright";

async function main() {
  const pattern = process.argv[2]; // e.g., "Hallway.*"
  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Login, navigate, discover entities
  // Filter entities by regex pattern
  // Delete matches

  await browser.close();
}

main();
```

Usage:
```bash
npx ts-node scripts/playwright/delete-entities-by-pattern.ts "Hallway.*"
```

### Integration with Test Suite

```typescript
// tests/entity-discovery.test.ts
import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';

test.beforeEach(async () => {
  // Clean slate before each test
  execSync('./scripts/delete-mqtt-entities-except-bridge.sh', {
    env: { ...process.env, RESTART_ADDON: 'true' }
  });

  // Wait for republishing
  await new Promise(resolve => setTimeout(resolve, 10000));
});

test('entities republish with correct areas', async ({ page }) => {
  await page.goto('http://localhost:8123/config/entities');
  // Verify entities exist and have correct suggested_area
});
```

## Performance Notes

### Execution Time

Typical execution times (headless mode):

- **Dry run**: ~15-20 seconds
- **Actual deletion (5-10 entities)**: ~30-40 seconds
- **Actual deletion (20-30 entities)**: ~60-90 seconds
- **With addon restart**: Add ~15-20 seconds

### Optimization Tips

1. Use dry run first to verify before actual deletion
2. Run headless (default) for faster execution
3. Use specific entity deletion for small changes
4. Batch multiple entities in one run

## Security Notes

### Credentials

Scripts default to dev environment credentials:
- Username: `dev`
- Password: `dev`

For production environments:
```bash
export HA_USERNAME="your-username"
export HA_PASSWORD="your-password"
./scripts/delete-mqtt-entities-except-bridge.sh
```

Or use credentials file:
```bash
# Load from hass-credentials.env
source hass-credentials.env
./scripts/delete-mqtt-entities-except-bridge.sh
```

### Safety Features

1. **Dry run mode** - Preview before deletion
2. **Bridge preservation** - Never deletes bridge device
3. **Detailed logging** - Audit trail of all actions
4. **Screenshots** - Visual confirmation at each step
5. **Accessibility snapshots** - Machine-readable page state

## See Also

- **README.md** - Complete script documentation
- **AGENTS.md** - Playwright best practices for HA UI
- **playwright.config.ts** - Playwright configuration
- **test-results/** - Execution logs and screenshots

