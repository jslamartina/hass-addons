#!/usr/bin/env python3
"""
Permanently delete MQTT entities from Home Assistant entity registry.

This script:
1. Reads the entity registry directly
2. Finds all MQTT entities (except bridge)
3. Removes them from the registry
4. Saves the modified registry

Usage:
    python3 scripts/delete-mqtt-entities-permanent.py [--dry-run]
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any

# Home Assistant config directory (in supervisor environment)
HA_CONFIG_DIR = Path("/mnt/supervisor/homeassistant")
ENTITY_REGISTRY_FILE = HA_CONFIG_DIR / ".storage" / "core.entity_registry"

BRIDGE_PATTERN = "CyncLAN Bridge"


def load_entity_registry() -> Dict[str, Any]:
    """Load the entity registry file."""
    if not ENTITY_REGISTRY_FILE.exists():
        print(f"❌ Entity registry not found: {ENTITY_REGISTRY_FILE}")
        sys.exit(1)

    with open(ENTITY_REGISTRY_FILE, "r") as f:
        return json.load(f)


def save_entity_registry(registry: Dict[str, Any]):
    """Save the entity registry file."""
    # Create backup first
    backup_file = ENTITY_REGISTRY_FILE.with_suffix(".backup")
    with open(backup_file, "w") as f:
        json.dump(registry, f, indent=2)
    print(f"📦 Backup saved: {backup_file}")

    # Save modified registry
    with open(ENTITY_REGISTRY_FILE, "w") as f:
        json.dump(registry, f, indent=2)
    print(f"💾 Registry saved: {ENTITY_REGISTRY_FILE}")


def main():
    dry_run = "--dry-run" in sys.argv

    print("╔═══════════════════════════════════════════════════════════════════════╗")
    print("║       Permanently Delete MQTT Entities (Registry Method)            ║")
    print("╚═══════════════════════════════════════════════════════════════════════╝")
    print("")

    if dry_run:
        print("⚠️  DRY RUN MODE - No changes will be saved")
        print("")

    # Load entity registry
    print("📂 Loading entity registry...")
    registry = load_entity_registry()

    entities = registry.get("data", {}).get("entities", [])
    print(f"   Found {len(entities)} total entities in registry")
    print("")

    # Find MQTT entities
    mqtt_entities_to_delete: List[Dict[str, Any]] = []
    mqtt_entities_to_preserve: List[Dict[str, Any]] = []

    for entity in entities:
        platform = entity.get("platform", "")
        entity_id = entity.get("entity_id", "")
        name = entity.get("name") or entity.get("original_name", "")

        # Check if it's an MQTT entity
        if platform == "mqtt":
            # Check if it's a bridge entity
            name_lower = (name or "").lower()
            entity_id_lower = (entity_id or "").lower()

            if (
                BRIDGE_PATTERN.lower() in name_lower
                or BRIDGE_PATTERN.lower() in entity_id_lower
            ):
                mqtt_entities_to_preserve.append(entity)
                print(f"✅ PRESERVE: {name or entity_id} ({entity_id})")
            else:
                mqtt_entities_to_delete.append(entity)
                print(f"❌ DELETE: {name or entity_id} ({entity_id})")

    print("")
    print("═════════════════ SUMMARY ═════════════════")
    print(
        f"Total MQTT entities: {len(mqtt_entities_to_delete) + len(mqtt_entities_to_preserve)}"
    )
    print(f"✅ To preserve (bridge): {len(mqtt_entities_to_preserve)}")
    print(f"❌ To delete: {len(mqtt_entities_to_delete)}")
    print("═════════════════════════════════════════════")
    print("")

    if not mqtt_entities_to_delete:
        print("⚠️  No MQTT entities to delete")
        return

    if dry_run:
        print("🔍 DRY RUN: These entities WOULD be deleted:")
        for entity in mqtt_entities_to_delete:
            print(f"   - {entity.get('name', entity.get('entity_id'))}")
        print("")
        print("✅ Dry run complete - no changes made")
        return

    # Confirm deletion
    response = input(
        f"⚠️  Delete {len(mqtt_entities_to_delete)} entities from registry? (y/N): "
    )
    if response.lower() != "y":
        print("❌ Aborted")
        return

    print("")
    print("🗑️  Deleting entities from registry...")

    # Remove entities
    entity_ids_to_delete = {e["entity_id"] for e in mqtt_entities_to_delete}
    registry["data"]["entities"] = [
        e
        for e in registry["data"]["entities"]
        if e.get("entity_id") not in entity_ids_to_delete
    ]

    # Update deleted entities list
    deleted_entities_list = registry["data"].get("deleted_entities", [])
    for entity in mqtt_entities_to_delete:
        if entity["entity_id"] not in deleted_entities_list:
            deleted_entities_list.append(entity["entity_id"])
    registry["data"]["deleted_entities"] = deleted_entities_list

    print(f"   Removed {len(mqtt_entities_to_delete)} entities from registry")
    print("")

    # Save registry
    save_entity_registry(registry)

    print("")
    print("═════════════════════════════════════════════")
    print(f"✅ Successfully deleted {len(mqtt_entities_to_delete)} entities")
    print("═════════════════════════════════════════════")
    print("")
    print("⚠️  IMPORTANT: Restart Home Assistant for changes to take effect:")
    print("   ha core restart")
    print("")


if __name__ == "__main__":
    main()
