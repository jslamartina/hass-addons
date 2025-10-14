# Playwright Scripts - Quick Start

**TL;DR:** Delete all MQTT entities except the bridge in 3 commands.

## Prerequisites

```bash
# Install Playwright (one-time setup)
npm run playwright:install
```

## Most Common Use Cases

### 1. Preview What Would Be Deleted

```bash
# See what will happen without actually deleting
./scripts/delete-mqtt-entities-except-bridge.sh --dry-run
```

**When to use:** Before running the actual deletion to verify what will be removed.

### 2. Delete All MQTT Entities (Keep Bridge)

```bash
# Delete all entities except CyncLAN Bridge
./scripts/delete-mqtt-entities-except-bridge.sh
```

**When to use:** Clean up all device entities for fresh rediscovery while keeping the bridge.

### 3. Delete and Restart Addon

```bash
# Delete entities and restart addon to republish them
./scripts/delete-mqtt-entities-except-bridge.sh --restart
```

**When to use:** Testing entity recreation after changing `suggested_area` or other discovery config.

## npm Scripts (Alternative)

```bash
# Preview deletion
npm run playwright:delete-all-except-bridge:dry-run

# Actually delete
npm run playwright:delete-all-except-bridge
```

## Output

Scripts create timestamped directories with:

```
test-results/runs/delete-mqtt-2025-10-14T08-45-23/
├── run.log                    # What happened
└── screenshots/               # Visual proof
    ├── 01-integrations-page.png
    ├── 03-mqtt-entities-list.png
    ├── 03b-entities-discovered.png  # Shows what was found
    ├── 05-entities-selected.png     # Shows what was selected
    └── 06-after-deletion.png        # Shows result
```

## Troubleshooting

### Script doesn't find any entities

```bash
# Run with visible browser to debug
./scripts/delete-mqtt-entities-except-bridge.sh --headed
```

### Want to delete specific entities only

```bash
npx ts-node scripts/playwright/delete-mqtt-entities.ts \
  "Entity Name 1" "Entity Name 2"
```

### Need to change bridge name

```bash
./scripts/delete-mqtt-entities-except-bridge.sh --bridge "My Bridge Name"
```

## Complete Documentation

- **README.md** - Full script documentation
- **EXAMPLES.md** - Real-world usage examples
- **AGENTS.md** - Technical details and best practices

## Safety Features

✅ **Dry run mode** - Preview before deletion
✅ **Bridge preservation** - Never deletes the bridge
✅ **Detailed logs** - Audit trail of all actions
✅ **Screenshots** - Visual confirmation at each step
✅ **Safe defaults** - No restart unless explicitly requested

## Help

```bash
./scripts/delete-mqtt-entities-except-bridge.sh --help
```

