#!/usr/bin/env python3
"""
SAFE MQTT entity deletion - deletes from registries AND restore_state

This version correctly handles the registry format to avoid breaking HA.

Usage:
    sudo python3 scripts/delete-mqtt-safe.py [--dry-run]
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# Home Assistant config directory (host container path)
HA_CONFIG_DIR = Path("/tmp/supervisor_data/homeassistant")
ENTITY_REGISTRY_FILE = HA_CONFIG_DIR / ".storage" / "core.entity_registry"
DEVICE_REGISTRY_FILE = HA_CONFIG_DIR / ".storage" / "core.device_registry"
RESTORE_STATE_FILE = HA_CONFIG_DIR / ".storage" / "core.restore_state"

BRIDGE_PATTERN = "cync_lan_bridge"


def load_json_file(filepath: Path) -> Dict[str, Any]:
    """Load a JSON file."""
    if not filepath.exists():
        print(f"❌ File not found: {filepath}")
        sys.exit(1)

    with filepath.open("r") as f:
        return json.load(f)


def save_json_file(filepath: Path, data: Dict[str, Any], backup: bool = True):
    """Save a JSON file with optional backup."""
    if backup:
        backup_file = filepath.with_suffix(filepath.suffix + ".safe_backup")
        with backup_file.open("w") as f:
            json.dump(data, f, indent=2)
        print(f"📦 Backup: {backup_file}")

    with filepath.open("w") as f:
        json.dump(data, f, indent=2)
    print(f"💾 Saved: {filepath.name}")


def main():
    dry_run = "--dry-run" in sys.argv

    print("╔═══════════════════════════════════════════════════════════════════════╗")
    print("║          SAFE MQTT Deletion (Registry + Restore State)              ║")
    print("╚═══════════════════════════════════════════════════════════════════════╝")
    print("")

    if dry_run:
        print("⚠️  DRY RUN MODE - No changes will be saved")
        print("")

    # ============================================================================
    # STEP 1: Load registries
    # ============================================================================
    print("📂 Loading registries...")
    entity_registry = load_json_file(ENTITY_REGISTRY_FILE)
    device_registry = load_json_file(DEVICE_REGISTRY_FILE)
    restore_state = load_json_file(RESTORE_STATE_FILE)

    entities = entity_registry.get("data", {}).get("entities", [])
    devices = device_registry.get("data", {}).get("devices", [])
    states = restore_state.get("data", [])

    print(f"   Entities: {len(entities)}")
    print(f"   Devices: {len(devices)}")
    print(f"   Restore states: {len(states)}")
    print("")

    # ============================================================================
    # STEP 2: Find MQTT entities
    # ============================================================================
    print("🔍 Finding MQTT entities...")
    mqtt_entities_to_delete: List[Dict[str, Any]] = []
    mqtt_entities_to_preserve: List[Dict[str, Any]] = []

    for entity in entities:
        platform = entity.get("platform", "")
        entity_id = entity.get("entity_id", "")
        name = entity.get("name") or entity.get("original_name", "")

        if platform == "mqtt":
            name_lower = (name or "").lower()
            entity_id_lower = (entity_id or "").lower()

            if BRIDGE_PATTERN in name_lower or BRIDGE_PATTERN in entity_id_lower:
                mqtt_entities_to_preserve.append(entity)
                print(f"✅ PRESERVE: {name or entity_id}")
            else:
                mqtt_entities_to_delete.append(entity)
                print(f"❌ DELETE: {name or entity_id}")

    print("")

    # ============================================================================
    # STEP 3: Find MQTT devices
    # ============================================================================
    print("🔍 Finding MQTT devices...")

    device_ids_from_deleted_entities = {
        e.get("device_id") for e in mqtt_entities_to_delete if e.get("device_id")
    }

    mqtt_devices_to_delete: List[Dict[str, Any]] = []
    mqtt_devices_to_preserve: List[Dict[str, Any]] = []

    for device in devices:
        if not isinstance(device, dict):
            continue

        device_id = device.get("id", "")
        identifiers = device.get("identifiers", [])
        name = device.get("name_by_user") or device.get("name", "")

        is_mqtt = any(
            isinstance(id_pair, list) and len(id_pair) == 2 and id_pair[0] == "mqtt"
            for id_pair in identifiers
        )

        if is_mqtt:
            name_lower = (name or "").lower()

            if BRIDGE_PATTERN in name_lower:
                mqtt_devices_to_preserve.append(device)
                print(f"✅ PRESERVE: {name}")
            elif device_id in device_ids_from_deleted_entities:
                mqtt_devices_to_delete.append(device)
                print(f"❌ DELETE: {name}")

    print("")

    # ============================================================================
    # STEP 4: Find restore states
    # ============================================================================
    print("🔍 Finding restore states...")

    entity_ids_to_delete = {e["entity_id"] for e in mqtt_entities_to_delete}

    states_to_delete = []
    states_to_keep = []

    for state in states:
        entity_id = state.get("state", {}).get("entity_id", "")

        if entity_id in entity_ids_to_delete:
            states_to_delete.append(entity_id)
            print(f"❌ DELETE STATE: {entity_id}")
        elif BRIDGE_PATTERN in entity_id:
            states_to_keep.append(entity_id)
        else:
            states_to_keep.append(entity_id)

    print("")

    # ============================================================================
    # STEP 5: Summary
    # ============================================================================
    print("═════════════════ SUMMARY ═════════════════")
    print("📊 ENTITIES:")
    print(
        f"   Total MQTT: {len(mqtt_entities_to_delete) + len(mqtt_entities_to_preserve)}"
    )
    print(f"   ✅ Preserve: {len(mqtt_entities_to_preserve)}")
    print(f"   ❌ Delete: {len(mqtt_entities_to_delete)}")
    print("")
    print("📊 DEVICES:")
    print(
        f"   Total MQTT: {len(mqtt_devices_to_delete) + len(mqtt_devices_to_preserve)}"
    )
    print(f"   ✅ Preserve: {len(mqtt_devices_to_preserve)}")
    print(f"   ❌ Delete: {len(mqtt_devices_to_delete)}")
    print("")
    print("📊 RESTORE STATES:")
    print(f"   ❌ Delete: {len(states_to_delete)}")
    print("═════════════════════════════════════════════")
    print("")

    if not mqtt_entities_to_delete:
        print("⚠️  Nothing to delete")
        return

    if dry_run:
        print("✅ Dry run complete - no changes made")
        return

    # Confirm
    response = input(
        f"⚠️  Delete {len(mqtt_entities_to_delete)} entities, {len(mqtt_devices_to_delete)} devices, {len(states_to_delete)} states? (y/N): "
    )
    if response.lower() != "y":
        print("❌ Aborted")
        return

    print("")

    # ============================================================================
    # STEP 6: Delete entities from entity registry
    # ============================================================================
    print("🗑️  Deleting from entity registry...")

    entity_ids_to_delete = {e["entity_id"] for e in mqtt_entities_to_delete}
    entity_registry["data"]["entities"] = [
        e
        for e in entity_registry["data"]["entities"]
        if e.get("entity_id") not in entity_ids_to_delete
    ]

    # DON'T add to deleted_entities - let HA manage this
    print(f"   ✅ Removed {len(mqtt_entities_to_delete)} entities")

    # ============================================================================
    # STEP 7: Delete devices from device registry
    # ============================================================================
    print("🗑️  Deleting from device registry...")

    device_ids_to_delete = {d["id"] for d in mqtt_devices_to_delete}
    device_registry["data"]["devices"] = [
        d
        for d in device_registry["data"]["devices"]
        if d.get("id") not in device_ids_to_delete
    ]

    # DON'T add to deleted_devices - let HA manage this
    print(f"   ✅ Removed {len(mqtt_devices_to_delete)} devices")

    # ============================================================================
    # STEP 8: Delete from restore_state
    # ============================================================================
    print("🗑️  Deleting from restore_state...")

    restore_state["data"] = [
        s
        for s in restore_state["data"]
        if s.get("state", {}).get("entity_id", "") not in entity_ids_to_delete
    ]

    print(f"   ✅ Removed {len(states_to_delete)} states")
    print("")

    # ============================================================================
    # STEP 9: Save all files
    # ============================================================================
    print("💾 Saving files...")
    save_json_file(ENTITY_REGISTRY_FILE, entity_registry)
    save_json_file(DEVICE_REGISTRY_FILE, device_registry)
    save_json_file(RESTORE_STATE_FILE, restore_state)
    print("")

    print("═════════════════════════════════════════════")
    print("✅ Successfully deleted:")
    print(f"   {len(mqtt_entities_to_delete)} entities")
    print(f"   {len(mqtt_devices_to_delete)} devices")
    print(f"   {len(states_to_delete)} restore states")
    print("═════════════════════════════════════════════")
    print("")
    print("⚠️  NEXT STEPS:")
    print("")
    print("1. Restart Home Assistant:")
    print("   ha core restart")
    print("")
    print("2. Wait ~20 seconds, then start addon:")
    print("   ha addons start local_cync-controller")
    print("")
    print("3. Entities will be FRESH with correct 'Living Room' area!")
    print("")


if __name__ == "__main__":
    main()
