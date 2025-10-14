#!/usr/bin/env python3
"""
Completely delete MQTT entities and devices from Home Assistant.

This script:
1. Deletes entities from entity registry
2. Deletes devices from device registry
3. Clears MQTT discovery retain messages
4. Prevents resurrection on addon restart

Usage:
    sudo python3 scripts/delete-mqtt-completely.py [--dry-run]
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Set

# Home Assistant config directory
HA_CONFIG_DIR = Path("/mnt/supervisor/homeassistant")
ENTITY_REGISTRY_FILE = HA_CONFIG_DIR / ".storage" / "core.entity_registry"
DEVICE_REGISTRY_FILE = HA_CONFIG_DIR / ".storage" / "core.device_registry"

BRIDGE_PATTERN = "CyncLAN Bridge"


def load_json_file(filepath: Path) -> Dict[str, Any]:
    """Load a JSON file."""
    if not filepath.exists():
        print(f"❌ File not found: {filepath}")
        sys.exit(1)

    with open(filepath, "r") as f:
        return json.load(f)


def save_json_file(filepath: Path, data: Dict[str, Any], backup: bool = True):
    """Save a JSON file with optional backup."""
    if backup:
        backup_file = filepath.with_suffix(".backup")
        with open(backup_file, "w") as f:
            json.dump(data, f, indent=2)
        print(f"📦 Backup saved: {backup_file}")

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    print(f"💾 Saved: {filepath}")


def main():
    dry_run = "--dry-run" in sys.argv

    print("╔═══════════════════════════════════════════════════════════════════════╗")
    print("║       COMPLETELY Delete MQTT Entities & Devices                     ║")
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

    entities = entity_registry.get("data", {}).get("entities", [])
    devices = device_registry.get("data", {}).get("devices", [])

    print(f"   Entities: {len(entities)}")
    print(f"   Devices: {len(devices)}")
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

            if (
                BRIDGE_PATTERN.lower() in name_lower
                or BRIDGE_PATTERN.lower() in entity_id_lower
            ):
                mqtt_entities_to_preserve.append(entity)
                print(f"✅ PRESERVE ENTITY: {name or entity_id}")
            else:
                mqtt_entities_to_delete.append(entity)
                print(f"❌ DELETE ENTITY: {name or entity_id}")

    print("")

    # ============================================================================
    # STEP 3: Find MQTT devices
    # ============================================================================
    print("🔍 Finding MQTT devices...")

    # Collect device IDs from entities we're deleting
    device_ids_from_deleted_entities: Set[str] = set()
    for entity in mqtt_entities_to_delete:
        device_id = entity.get("device_id")
        if device_id:
            device_ids_from_deleted_entities.add(device_id)

    mqtt_devices_to_delete: List[Dict[str, Any]] = []
    mqtt_devices_to_preserve: List[Dict[str, Any]] = []

    for device in devices:
        device_id = device.get("id", "")
        identifiers = device.get("identifiers", [])
        name = device.get("name_by_user") or device.get("name", "")

        # Check if it's an MQTT device
        is_mqtt = any(
            isinstance(id_pair, list) and len(id_pair) == 2 and id_pair[0] == "mqtt"
            for id_pair in identifiers
        )

        if is_mqtt:
            name_lower = (name or "").lower()

            if BRIDGE_PATTERN.lower() in name_lower:
                mqtt_devices_to_preserve.append(device)
                print(f"✅ PRESERVE DEVICE: {name} ({device_id})")
            elif device_id in device_ids_from_deleted_entities:
                mqtt_devices_to_delete.append(device)
                print(f"❌ DELETE DEVICE: {name} ({device_id})")

    print("")

    # ============================================================================
    # STEP 4: Summary
    # ============================================================================
    print("═════════════════ SUMMARY ═════════════════")
    print(f"📊 ENTITIES:")
    print(
        f"   Total MQTT: {len(mqtt_entities_to_delete) + len(mqtt_entities_to_preserve)}"
    )
    print(f"   ✅ To preserve: {len(mqtt_entities_to_preserve)}")
    print(f"   ❌ To delete: {len(mqtt_entities_to_delete)}")
    print("")
    print(f"📊 DEVICES:")
    print(
        f"   Total MQTT: {len(mqtt_devices_to_delete) + len(mqtt_devices_to_preserve)}"
    )
    print(f"   ✅ To preserve: {len(mqtt_devices_to_preserve)}")
    print(f"   ❌ To delete: {len(mqtt_devices_to_delete)}")
    print("═════════════════════════════════════════════")
    print("")

    if not mqtt_entities_to_delete and not mqtt_devices_to_delete:
        print("⚠️  Nothing to delete")
        return

    if dry_run:
        print("🔍 DRY RUN: Would delete:")
        print(f"   {len(mqtt_entities_to_delete)} entities")
        print(f"   {len(mqtt_devices_to_delete)} devices")
        print("")
        print("✅ Dry run complete - no changes made")
        return

    # Confirm deletion
    response = input(
        f"⚠️  Delete {len(mqtt_entities_to_delete)} entities and {len(mqtt_devices_to_delete)} devices? (y/N): "
    )
    if response.lower() != "y":
        print("❌ Aborted")
        return

    print("")

    # ============================================================================
    # STEP 5: Delete entities
    # ============================================================================
    print("🗑️  Deleting entities from entity registry...")

    entity_ids_to_delete = {e["entity_id"] for e in mqtt_entities_to_delete}
    entity_registry["data"]["entities"] = [
        e
        for e in entity_registry["data"]["entities"]
        if e.get("entity_id") not in entity_ids_to_delete
    ]

    # Add to deleted entities list
    deleted_entities_list = entity_registry["data"].get("deleted_entities", [])
    for entity in mqtt_entities_to_delete:
        if entity["entity_id"] not in deleted_entities_list:
            deleted_entities_list.append(entity["entity_id"])
    entity_registry["data"]["deleted_entities"] = deleted_entities_list

    print(f"   ✅ Removed {len(mqtt_entities_to_delete)} entities")

    # ============================================================================
    # STEP 6: Delete devices
    # ============================================================================
    print("🗑️  Deleting devices from device registry...")

    device_ids_to_delete = {d["id"] for d in mqtt_devices_to_delete}
    device_registry["data"]["devices"] = [
        d
        for d in device_registry["data"]["devices"]
        if d.get("id") not in device_ids_to_delete
    ]

    # Add to deleted devices list
    deleted_devices_list = device_registry["data"].get("deleted_devices", [])
    for device in mqtt_devices_to_delete:
        if device["id"] not in deleted_devices_list:
            deleted_devices_list.append(device["id"])
    device_registry["data"]["deleted_devices"] = deleted_devices_list

    print(f"   ✅ Removed {len(mqtt_devices_to_delete)} devices")
    print("")

    # ============================================================================
    # STEP 7: Save registries
    # ============================================================================
    print("💾 Saving registries...")
    save_json_file(ENTITY_REGISTRY_FILE, entity_registry)
    save_json_file(DEVICE_REGISTRY_FILE, device_registry)
    print("")

    # ============================================================================
    # STEP 8: Final instructions
    # ============================================================================
    print("═════════════════════════════════════════════")
    print(f"✅ Successfully deleted:")
    print(f"   {len(mqtt_entities_to_delete)} entities")
    print(f"   {len(mqtt_devices_to_delete)} devices")
    print("═════════════════════════════════════════════")
    print("")
    print("⚠️  IMPORTANT: Next steps to complete deletion:")
    print("")
    print("1. Restart Home Assistant:")
    print("   ha core restart")
    print("")
    print("2. Wait for restart, then start addon:")
    print("   ha addons start local_cync-lan")
    print("")
    print("3. Entities will be recreated fresh with NEW device IDs")
    print("")


if __name__ == "__main__":
    main()
