# Delete MQTT Entities Guide

This guide explains the automated tools available for managing MQTT entities in the development environment.

## The Problem

When developing the CyncLAN Add-on, you often need to:
- Clean up test entities without losing the bridge configuration
- Test entity rediscovery after changing discovery settings
- Verify entities appear in correct areas after `suggested_area` changes
- Remove stale entities without manually clicking through the UI

**Manual deletion is tedious:** 20+ entities × 3 clicks each = waste of time.

## The Solution

### Automated Script: Delete All Except Bridge

**Script:** `scripts/delete-mqtt-entities-except-bridge.sh`

**What it does:**
1. ✅ Discovers all MQTT entities
2. ✅ Preserves CyncLAN Bridge (and its entities)
3. ✅ Deletes everything else
4. ✅ Cleans up device registry
5. ✅ Optionally restarts addon

**Safety:**
- Bridge is **never deleted**
- Dry run mode to preview first
- Detailed logs and screenshots
- Atomic operation (all or nothing)

## Quick Start

### Primary Method: Python Script (Recommended)

```bash
# Preview what will be deleted (dry run)
sudo python3 scripts/delete-mqtt-safe.py --dry-run

# Actually delete entities (preserves bridge, cleans registries)
sudo python3 scripts/delete-mqtt-safe.py

# Delete and automatically restart addon
sudo python3 scripts/delete-mqtt-safe.py --restart
```

**Features:**
- ✅ Preserves CyncLAN Bridge entities
- ✅ Cleans entity and device registries
- ✅ Clears restore state (removes history memory)
- ✅ Safe dry-run mode for preview
- ✅ Comprehensive logging and backup creation

## Common Workflows

### Workflow: Test Entity Rediscovery

```bash
# 1. Preview what will be deleted (dry run)
sudo python3 scripts/delete-mqtt-safe.py --dry-run

# 2. Delete all entities (keep bridge, clean registries)
sudo python3 scripts/delete-mqtt-safe.py

# 3. Restart addon to republish
ha addons restart local_cync-controller

# 4. Verify entities republished correctly
ha addons logs local_cync-controller | grep "Publishing MQTT discovery"
```

### Workflow: Change suggested_area and Rediscover

```bash
# Scenario: You edited mqtt_client.py to change suggested_area

# 1. Rebuild addon (Python changes require rebuild)
cd cync-controller && ./rebuild.sh

# 2. Delete all entities except bridge (clean deletion)
sudo python3 scripts/delete-mqtt-safe.py

# 3. Restart addon
ha addons restart local_cync-controller

# 4. Entities republish with new suggested_area
# Navigate to Settings → Devices & Services → Entities
# Verify entities appear in correct areas
```

### Workflow: Clean Slate Testing

```bash
# Complete reset (except bridge)
./scripts/delete-mqtt-entities-except-bridge.sh --restart

# Or combined:
./scripts/delete-mqtt-entities-except-bridge.sh --dry-run && \
./scripts/delete-mqtt-entities-except-bridge.sh --restart
```

## Understanding the Output

### Discovery Summary

```
═════════════════ DISCOVERY SUMMARY ═════════════════
Total entities found: 24
✅ To preserve (CyncLAN Bridge): 1
   - CyncLAN Bridge
❌ To delete: 23
   - Hallway Front Switch
   - Hallway Counter Switch
   - Bedroom Ceiling Light
   ...
═════════════════════════════════════════════════════
```

- **To preserve** - Bridge entities (never deleted)
- **To delete** - All other MQTT entities (will be deleted)

### Dry Run Output

```bash
⚠️ DRY RUN MODE - No entities will be actually deleted
ℹ️ Entities that WOULD be deleted:
ℹ️   - Hallway Front Switch
ℹ️   - Hallway Counter Switch
...
```

Use `--dry-run` to verify before actual deletion.

### Actual Deletion Output

```bash
✅ Selected: Hallway Front Switch
✅ Selected: Hallway Counter Switch
...
ℹ️ Selected 23 entities, proceeding to delete
✅ Deletion confirmed
✅ Successfully deleted 23 entities
✅ Device registry cleanup completed
```

## Configuration Options

### Environment Variables

```bash
export HA_BASE_URL="http://localhost:8123"  # HA URL
export HA_USERNAME="dev"                     # Username
export HA_PASSWORD="dev"                     # Password
export ADDON_SLUG="local_cync-controller"          # Addon to restart
export BRIDGE_NAME="CyncLAN Bridge"         # Bridge to preserve
export RESTART_ADDON="true"                  # Restart after deletion
export DRY_RUN="true"                        # Preview mode
export HEADED="1"                            # Show browser
```

### Shell Flags

```bash
--dry-run       # Preview without deleting
--restart       # Restart addon after deletion
--headed        # Show browser window
--bridge NAME   # Custom bridge name
--help          # Show help
```

## Troubleshooting

### "No entities found"

**Check:**
1. Is MQTT integration running?
2. Is addon running and publishing entities?
3. Run with `--headed` to see current page state

```bash
./scripts/delete-mqtt-entities-except-bridge.sh --headed
```

### "Wrong entities selected"

**Check bridge name:**
```bash
# Verify bridge name matches exactly
./scripts/delete-mqtt-entities-except-bridge.sh \
  --bridge "Exact Bridge Name" --dry-run
```

### "Deletion failed"

**Debug with screenshots:**
```bash
# Check what happened
ls -la test-results/runs/delete-mqtt-*/screenshots/
cat test-results/runs/delete-mqtt-*/run.log
```

### "Script is slow"

**Normal execution times:**
- Dry run: ~15-20 seconds
- Actual deletion (20 entities): ~60-90 seconds
- With addon restart: Add ~15-20 seconds

**Optimization:**
- Headless mode (default) is faster
- Headed mode (`--headed`) is slower but helps debugging

## Alternative: Delete Specific Entities

If you only need to delete specific entities:

```bash
# Delete by name
npx ts-node scripts/playwright/delete-mqtt-entities.ts \
  "Hallway Front Switch" \
  "Bedroom Light"

# With restart
RESTART_ADDON=true \
npx ts-node scripts/playwright/delete-mqtt-entities.ts \
  "Entity 1" "Entity 2"
```

## Safety and Audit

### What Gets Preserved

- ✅ CyncLAN Bridge device
- ✅ Bridge sensor entities
- ✅ MQTT integration configuration
- ✅ All non-MQTT entities

### What Gets Deleted

- ❌ All MQTT device entities (lights, switches)
- ❌ Device registry entries for deleted entities
- ⚠️ Entity configuration (helpers, areas) - reset to discovery defaults

### Audit Trail

Every run creates:
- **run.log** - Complete action log with timestamps
- **screenshots/** - Visual proof at each step
- **\*-a11y.yaml** - Machine-readable page state

## Technical Details

### How It Works

1. **Login** - Authenticates with Home Assistant
2. **Navigate** - Goes to MQTT integration page
3. **Discover** - Scans all table rows for entities
4. **Classify** - Separates bridge entities from others
5. **Select** - Checks checkboxes for non-bridge entities
6. **Delete** - Clicks Action → Delete selected
7. **Cleanup** - Removes device registry entries
8. **Restart** - Optionally restarts addon (if `--restart`)

### Shadow DOM Handling

Home Assistant UI uses Web Components with Shadow DOM. The script:
- Uses role-based selectors (pierce shadow boundaries)
- Falls back to programmatic clicks if UI blocks normal clicks
- Saves accessibility tree for debugging

### Error Recovery

- Continues on individual entity failures
- Logs warnings for problematic entities
- Never fails on checkbox selection issues
- Cleans up browser even on errors

## See Also

- **scripts/playwright/README.md** - Complete Playwright automation documentation
- **docs/developer/agents-guide.md** - Browser automation best practices and patterns

## Support

If you encounter issues:

1. Run with `--dry-run` first
2. Run with `--headed` to see browser
3. Check `test-results/runs/*/run.log`
4. Review screenshots in `test-results/runs/*/screenshots/`
5. Verify bridge name matches exactly

---

**Created:** October 14, 2025
**Purpose:** Automate MQTT entity management for CyncLAN Add-on development

