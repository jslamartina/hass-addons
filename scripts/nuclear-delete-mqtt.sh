#!/usr/bin/env bash
#
# NUCLEAR OPTION: Completely erase all MQTT entity traces
#
# This script:
# 1. Stops the addon
# 2. Deletes from entity & device registries
# 3. Clears restore_state (history/config memory)
# 4. Restarts Home Assistant
# 5. Starts addon (fresh entities)
#
# Usage:
#   sudo ./scripts/nuclear-delete-mqtt.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║              NUCLEAR DELETE - Complete MQTT Wipe                     ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo ""
echo "⚠️  WARNING: This will COMPLETELY erase all MQTT entities including:"
echo "   - Entity registry entries"
echo "   - Device registry entries"
echo "   - Restore state (history memory)"
echo "   - All configuration (areas, customizations)"
echo ""
echo "   CyncLAN Bridge will be preserved."
echo ""
read -p "Are you SURE? (type 'yes' to continue): " -r
echo
if [[ $REPLY != "yes" ]]; then
  echo "❌ Aborted"
  exit 1
fi

echo ""
echo "═══════════════════════════════════════════════════════════════════════"
echo "STEP 1: Stop addon"
echo "═══════════════════════════════════════════════════════════════════════"
ha addons stop local_cync-lan
echo "✅ Addon stopped"
echo ""

echo "═══════════════════════════════════════════════════════════════════════"
echo "STEP 2: Delete from entity & device registries"
echo "═══════════════════════════════════════════════════════════════════════"
python3 "$SCRIPT_DIR/delete-mqtt-completely.py" <<< "y"
echo ""

echo "═══════════════════════════════════════════════════════════════════════"
echo "STEP 3: Clear restore state (removes history memory)"
echo "═══════════════════════════════════════════════════════════════════════"
RESTORE_STATE="/mnt/supervisor/homeassistant/.storage/core.restore_state"
if [ -f "$RESTORE_STATE" ]; then
  echo "   Backing up restore_state..."
  cp "$RESTORE_STATE" "${RESTORE_STATE}.backup"
  echo "   ✅ Backup: ${RESTORE_STATE}.backup"

  echo "   Removing MQTT entities from restore_state..."
  python3 - << 'PYTHON_SCRIPT'
import json

RESTORE_FILE = "/mnt/supervisor/homeassistant/.storage/core.restore_state"
BRIDGE_PATTERN = "cync_lan_bridge"

# Load restore state
with open(RESTORE_FILE, "r") as f:
    restore_data = json.load(f)

# Get current states
states = restore_data.get("data", [])
print(f"   Found {len(states)} total states")

# Filter out MQTT entities (except bridge)
new_states = []
removed_count = 0

for state in states:
    entity_id = state.get("state", {}).get("entity_id", "")

    # Keep if not MQTT or if it's the bridge
    if not entity_id.startswith(("light.", "switch.", "fan.", "button.", "binary_sensor.", "sensor.", "number.")):
        new_states.append(state)
    elif BRIDGE_PATTERN in entity_id:
        new_states.append(state)
        print(f"   ✅ KEPT: {entity_id}")
    else:
        removed_count += 1
        print(f"   ❌ REMOVED: {entity_id}")

restore_data["data"] = new_states

# Save
with open(RESTORE_FILE, "w") as f:
    json.dump(restore_data, f, indent=2)

print(f"\n   ✅ Removed {removed_count} entities from restore_state")
print(f"   ✅ Kept {len(new_states)} entities")
PYTHON_SCRIPT

  echo "   ✅ Restore state cleared"
else
  echo "   ⚠️  Restore state file not found (this is OK)"
fi
echo ""

echo "═══════════════════════════════════════════════════════════════════════"
echo "STEP 4: Restart Home Assistant"
echo "═══════════════════════════════════════════════════════════════════════"
ha core restart
echo "✅ Restarting Home Assistant..."
echo "⏳ Waiting 20 seconds..."
sleep 20
echo ""

echo "═══════════════════════════════════════════════════════════════════════"
echo "STEP 5: Start addon"
echo "═══════════════════════════════════════════════════════════════════════"
ha addons start local_cync-lan
echo "✅ Addon started"
echo ""

echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║                    NUCLEAR DELETE COMPLETE! ✅                       ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo ""
echo "✅ All MQTT entities have been COMPLETELY erased:"
echo "   - Registry entries deleted"
echo "   - Restore state cleared"
echo "   - History forgotten"
echo ""
echo "🆕 Fresh entities will be created with:"
echo "   - New device IDs"
echo "   - No area assignments"
echo "   - No history"
echo "   - Clean configuration"
echo ""
echo "🔍 Check in Home Assistant:"
echo "   Settings → Devices & Services → Entities"
echo ""
