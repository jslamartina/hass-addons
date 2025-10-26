# Playwright Test Scripts

This directory contains Playwright automation scripts for testing and managing Home Assistant entities via the web UI.

## Available Scripts

### 1. Delete All MQTT Entities (Except Bridge)

**Purpose:** Delete all MQTT entities while preserving the Cync Controller device and its entities.

**Script:** `delete-all-mqtt-entities-except-bridge.ts`

**Shell Wrapper:** `../delete-mqtt-entities-except-bridge.sh`

**Use Cases:**
- Clean up test environment while keeping the bridge
- Remove all device entities for fresh rediscovery
- Test entity recreation scenarios

**Quick Start:**

```bash
# Preview what would be deleted (dry run)
./scripts/delete-mqtt-entities-except-bridge.sh --dry-run

# Delete entities and restart addon
./scripts/delete-mqtt-entities-except-bridge.sh --restart

# Delete with visible browser (for debugging)
./scripts/delete-mqtt-entities-except-bridge.sh --headed
```

**Direct TypeScript Usage:**

```bash
# Basic usage
HA_BASE_URL=http://localhost:8123 HA_USERNAME=dev HA_PASSWORD=dev \
npx ts-node scripts/playwright/delete-all-mqtt-entities-except-bridge.ts

# Dry run mode (preview only)
DRY_RUN=true npx ts-node scripts/playwright/delete-all-mqtt-entities-except-bridge.ts

# With addon restart
RESTART_ADDON=true npx ts-node scripts/playwright/delete-all-mqtt-entities-except-bridge.ts

# Custom bridge name
BRIDGE_NAME="My Custom Bridge" npx ts-node scripts/playwright/delete-all-mqtt-entities-except-bridge.ts

# Headed mode (visible browser)
HEADED=1 npx ts-node scripts/playwright/delete-all-mqtt-entities-except-bridge.ts
```

**Environment Variables:**
- `HA_BASE_URL` - Home Assistant URL (default: `http://localhost:8123`)
- `HA_USERNAME` - Username (default: `dev`)
- `HA_PASSWORD` - Password (default: `dev`)
- `ADDON_SLUG` - Addon to restart (default: `local_cync-controller`)
- `RESTART_ADDON` - Set to `true` to restart addon after deletion (default: `false`)
- `BRIDGE_NAME` - Bridge device name to preserve (default: `Cync Controller`)
- `DRY_RUN` - Set to `true` to preview without deleting (default: `false`)
- `HEADED` - Set to any value to show browser window (default: headless)

### 2. Delete Specific MQTT Entities

**Purpose:** Delete specific MQTT entities by name.

**Script:** `delete-mqtt-entities.ts`

**Use Cases:**
- Remove individual entities for testing
- Clean up specific devices
- Targeted entity management

**Usage:**

```bash
# Delete specific entities
HA_BASE_URL=http://localhost:8123 HA_USERNAME=dev HA_PASSWORD=dev \
npx ts-node scripts/playwright/delete-mqtt-entities.ts \
  "Hallway Front Switch" "Hallway Counter Switch"

# With addon restart
RESTART_ADDON=true npx ts-node scripts/playwright/delete-mqtt-entities.ts \
  "Entity Name 1" "Entity Name 2"
```

### 3. Delete Entities (Generic)

**Purpose:** Delete entities from the main Entities page.

**Script:** `delete-entities.ts`

**Note:** This script is for non-MQTT entities or entities after the integration has been stopped.

**Usage:**

```bash
npx ts-node scripts/playwright/delete-entities.ts "Entity 1" "Entity 2"
```

## Output and Debugging

All scripts generate timestamped run directories with:

```
test-results/runs/delete-mqtt-YYYY-MM-DDTHH-MM-SS/
├── run.log                    # Detailed execution log
└── screenshots/               # Screenshots at each step
    ├── 01-integrations-page.png
    ├── 02-mqtt-integration-opened.png
    ├── 03-mqtt-entities-list.png
    ├── 03b-entities-discovered.png
    ├── 04-selection-mode-enabled.png
    ├── 05-entities-selected.png
    ├── 06-after-deletion.png
    ├── 07-devices-page.png
    ├── 08-device-*.png
    ├── 09-devices-deleted.png
    └── *-a11y.yaml            # Accessibility tree snapshots
```

## Troubleshooting

### Script fails to find entities

- Check `screenshots/` directory to see current page state
- Verify MQTT integration is running
- Check if entity names match (case-sensitive)
- Review `run.log` for detailed error messages

### "Element intercepts pointer events" errors

Scripts use reliable click helpers that:
1. Try normal click first
2. Fall back to `dispatchEvent` if click is intercepted
3. Wait for elements to be visible before clicking

If clicks still fail, check `*-a11y.yaml` files to verify element structure.

### Entities not actually deleted

MQTT entities can only be deleted when:
1. Navigating through MQTT integration page (not main Entities page)
2. Integration is still running (entities are "available")
3. OR integration is stopped (entities become "unavailable" and deletable)

This script uses method #1 (MQTT integration page) which works while addon is running.

### Dry run mode

Use `DRY_RUN=true` or `--dry-run` to preview what would be deleted without actually deleting:

```bash
./scripts/delete-mqtt-entities-except-bridge.sh --dry-run
```

Output shows:
- ✅ Entities to preserve (bridge)
- ❌ Entities to delete (all others)
- Full discovery summary

## Best Practices

### When to use each script

| Scenario                                   | Recommended Script                          |
| ------------------------------------------ | ------------------------------------------- |
| Clean up all test entities but keep bridge | `delete-all-mqtt-entities-except-bridge.sh` |
| Remove specific known entities             | `delete-mqtt-entities.ts`                   |
| Delete after stopping integration          | `delete-entities.ts`                        |
| Preview before deletion                    | Any script with `DRY_RUN=true`              |

### Workflow for entity recreation

```bash
# 1. Preview what will be deleted
./scripts/delete-mqtt-entities-except-bridge.sh --dry-run

# 2. Delete entities (addon is still running)
./scripts/delete-mqtt-entities-except-bridge.sh

# 3. Restart addon to republish entities
ha addons restart local_cync-controller

# OR combine steps 2-3
./scripts/delete-mqtt-entities-except-bridge.sh --restart
```

### Debugging with headed mode

Run with visible browser to see what's happening:

```bash
./scripts/delete-mqtt-entities-except-bridge.sh --headed
```

Browser window will stay open during execution, showing each step.

## Technical Details

### Shadow DOM Handling

Home Assistant UI uses Web Components with Shadow DOM. Scripts use:

- **Role-based selectors** - `getByRole()` automatically pierces shadow boundaries
- **Accessibility tree snapshots** - Saved as `*-a11y.yaml` for debugging
- **Reliable click helpers** - Handle SVG icon interception issues

### Entity Discovery Algorithm

The `delete-all-mqtt-entities-except-bridge.ts` script:

1. Navigates to MQTT integration page
2. Iterates through all table rows
3. Checks row text content for bridge name
4. Classifies entities as:
   - **To Preserve** - Contains bridge name
   - **To Delete** - Does not contain bridge name
5. Selects and deletes only "To Delete" entities
6. Optionally cleans up device registry entries
7. Optionally restarts addon

### Device Registry Cleanup

After deleting entities, scripts also delete device registry entries to ensure:
- Fresh device creation on next discovery
- No stale device metadata
- Clean device attributes (e.g., `suggested_area`)

Bridge device is **never deleted** from registry.

## Development

### Adding New Scripts

1. Create TypeScript file in `scripts/playwright/`
2. Follow existing patterns:
   - Use `clickReliably()` helper
   - Take screenshots at key steps
   - Log all actions with timestamps
   - Save accessibility snapshots
3. Create shell wrapper in `scripts/` if needed
4. Update this README

### Testing Changes

```bash
# Test script with dry run first
DRY_RUN=true npx ts-node scripts/playwright/your-new-script.ts

# Test with headed mode to observe behavior
HEADED=1 npx ts-node scripts/playwright/your-new-script.ts

# Check output
cat test-results/runs/*/run.log
ls -la test-results/runs/*/screenshots/
```

## Related Documentation

- **../../docs/developer/agents-guide.md** - Browser automation best practices, Playwright patterns, Shadow DOM handling
- **../../docs/developer/exploration-notes.md** - UI navigation findings and system state reference
- **../../docs/developer/limitations-lifted.md** - Automated testing tools and resolved blockers
- **../../docs/developer/entity-management.md** - User guide for entity deletion workflows

### 4. Fan Speed Control E2E Tests

**Purpose:** Validate fan speed control through Home Assistant UI by testing slider and preset interactions.

**Script:** `test-fan-speed.spec.ts`

**Use Cases:**
- Test fan slider control at multiple speeds (0%, 25%, 50%, 75%, 100%)
- Verify preset mode selection (off, low, medium, high, max)
- Validate state persistence across page refreshes
- Test rapid speed changes for stability
- Diagnose fan speed control issues

**Quick Start:**

```bash
# Run all fan speed tests
npx playwright test scripts/playwright/test-fan-speed.spec.ts

# Run with visible browser (for debugging)
npx playwright test scripts/playwright/test-fan-speed.spec.ts --headed

# Run specific test
npx playwright test scripts/playwright/test-fan-speed.spec.ts -g "slider control"

# Run with custom fan name
FAN_ENTITY_NAME="Living Room Fan" npx playwright test scripts/playwright/test-fan-speed.spec.ts
```

**Environment Variables:**
- `HA_BASE_URL` - Home Assistant URL (default: `http://localhost:8123`)
- `HA_USERNAME` - Username (default: `dev`)
- `HA_PASSWORD` - Password (default: `dev`)
- `FAN_ENTITY_NAME` - Fan entity name to test (default: `Master Bedroom Fan Switch`)

**Test Cases:**

1. **Verify Fan Entity Exists** - Confirms fan card is visible on dashboard
2. **Test Power Toggle** - Baseline test for on/off functionality
3. **Test Slider Control** - Tests speed adjustment at 0%, 25%, 50%, 75%, 100%
4. **Test Preset Modes** - Validates low, medium, high, max, and off presets
5. **Test State Persistence** - Verifies state survives page refresh
6. **Test Rapid Changes** - Ensures system handles quick successive changes
7. **Verify via Developer Tools** - Cross-checks state in Developer Tools → States

**Output:**

Test results are saved to `test-results/` with screenshots at each step:

```
test-results/fan-speed-screenshots/
├── 01-fan-entity-found.png
├── 02-fan-on.png
├── 02-fan-off.png
├── 03-slider-0%.png
├── 03-slider-25%.png
├── 03-slider-50%.png
├── 03-slider-75%.png
├── 03-slider-100%.png
├── 04-preset-low.png
├── 04-preset-medium.png
├── 04-preset-high.png
├── 04-preset-max.png
├── 05-before-refresh.png
├── 05-after-refresh.png
├── 06-rapid-changes-final.png
└── 07-developer-tools.png
```

**Troubleshooting:**

If tests fail:

1. **Check screenshots** to see UI state at failure point
2. **Review add-on logs**: `ha addons logs local_cync-controller`
3. **Verify fan entity name** matches `FAN_ENTITY_NAME` environment variable
4. **Check diagnostic logs** from `FANSPEED-DIAGNOSIS.md` for backend issues
5. **Run in headed mode** to watch test execution: `--headed`

**Common Issues:**

- **Fan card not found**: Check entity name matches exactly
- **Slider not responding**: Verify fan is turned on first
- **Preset dropdown not found**: UI element selectors may need adjustment for your HA version
- **State not updating**: Check add-on logs for MQTT command reception

## Credits

These scripts were developed to automate MQTT entity management and E2E testing in the Cync Controller Add-on development workflow, following Home Assistant UI best practices for Shadow DOM interaction.

