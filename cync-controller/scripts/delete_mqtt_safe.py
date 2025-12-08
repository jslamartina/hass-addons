#!/usr/bin/env python3
"""SAFE MQTT entity deletion.

Deletes MQTT entities, devices, and restore_state entries while preserving bridge
devices. This version matches the registry format used by Home Assistant.

Usage:
    sudo python3 scripts/delete_mqtt_safe.py [--dry-run] [--config-dir PATH]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import gettempdir
from typing import TypedDict, cast

LOGGER = logging.getLogger(__name__)

BRIDGE_PATTERN = "cync_lan_bridge"
MQTT_IDENTIFIER_PARTS = 2
DEFAULT_CONFIG_DIR = Path(gettempdir()) / "supervisor_data" / "homeassistant"


class EntityEntry(TypedDict, total=False):
    """Entity entry stored in Home Assistant entity registry."""

    platform: str
    entity_id: str
    name: str
    original_name: str
    device_id: str


class EntityRegistryData(TypedDict):
    """Entity registry payload structure."""

    entities: list[EntityEntry]


class EntityRegistry(TypedDict):
    """Entity registry root object."""

    data: EntityRegistryData


class DeviceEntry(TypedDict, total=False):
    """Device entry stored in Home Assistant device registry."""

    id: str
    identifiers: list[list[str]]
    name: str
    name_by_user: str


class DeviceRegistryData(TypedDict):
    """Device registry payload structure."""

    devices: list[DeviceEntry]


class DeviceRegistry(TypedDict):
    """Device registry root object."""

    data: DeviceRegistryData


class RestoreStateState(TypedDict, total=False):
    """Restore state inner payload."""

    entity_id: str


class RestoreStateEntry(TypedDict, total=False):
    """Restore state entry in Home Assistant."""

    state: RestoreStateState


class RestoreState(TypedDict):
    """Restore state root structure."""

    data: list[RestoreStateEntry]


@dataclass
class RegistryPaths:
    """Paths to registry files on disk."""

    entity: Path
    device: Path
    restore_state: Path


@dataclass
class Registries:
    """Loaded registry contents."""

    entity_registry: EntityRegistry
    device_registry: DeviceRegistry
    restore_state: RestoreState


@dataclass
class DeletionPlan:
    """Planned deletions and preserved entries."""

    entities_to_delete: list[EntityEntry]
    entities_to_preserve: list[EntityEntry]
    devices_to_delete: list[DeviceEntry]
    devices_to_preserve: list[DeviceEntry]
    states_to_delete: list[str]
    states_to_keep: list[str]


@dataclass
class CliArgs:
    """Typed CLI arguments."""

    dry_run: bool
    config_dir: str | None


def configure_logging() -> None:
    """Configure logging to stdout."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def parse_args() -> CliArgs:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Safely delete MQTT entities/devices.")
    _ = parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without modifying files.",
    )
    _ = parser.add_argument(
        "--config-dir",
        help="Home Assistant config directory (defaults to HA_CONFIG_DIR or supervisor data path).",
    )
    parsed = parser.parse_args()
    return CliArgs(
        dry_run=bool(cast(bool, parsed.dry_run)),
        config_dir=cast(str | None, parsed.config_dir),
    )


def resolve_config_dir(raw_config_dir: str | None) -> Path:
    """Resolve the Home Assistant config directory."""
    if raw_config_dir:
        candidate = Path(raw_config_dir).expanduser()
    else:
        env_dir = os.environ.get("HA_CONFIG_DIR")
        candidate = Path(env_dir).expanduser() if env_dir else DEFAULT_CONFIG_DIR

    resolved = candidate.resolve()
    if not resolved.exists():
        message = f"Config directory not found: {resolved}"
        raise SystemExit(message)

    return resolved


def build_paths(config_dir: Path) -> RegistryPaths:
    """Build registry file paths."""
    storage_dir = config_dir / ".storage"
    return RegistryPaths(
        entity=storage_dir / "core.entity_registry",
        device=storage_dir / "core.device_registry",
        restore_state=storage_dir / "core.restore_state",
    )


def load_json_file(filepath: Path) -> object:
    """Load a JSON file."""
    if not filepath.exists():
        message = f"File not found: {filepath}"
        raise SystemExit(message)

    with filepath.open("r", encoding="utf-8") as file:
        return cast(object, json.load(file))


def save_json_file(filepath: Path, data: object, *, backup: bool = True) -> None:
    """Save a JSON file with optional backup."""
    if backup:
        backup_file = filepath.with_suffix(filepath.suffix + ".safe_backup")
        with backup_file.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)
        LOGGER.info("Backup: %s", backup_file)

    with filepath.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
    LOGGER.info("Saved: %s", filepath.name)


def load_registries(paths: RegistryPaths) -> Registries:
    """Load entity, device, and restore_state registries."""
    LOGGER.info("Loading registries from %s", paths.entity.parent)
    entity_registry = cast(EntityRegistry, load_json_file(paths.entity))
    device_registry = cast(DeviceRegistry, load_json_file(paths.device))
    restore_state = cast(RestoreState, load_json_file(paths.restore_state))
    return Registries(entity_registry, device_registry, restore_state)


def find_mqtt_entities(entities: list[EntityEntry]) -> tuple[list[EntityEntry], list[EntityEntry]]:
    """Split MQTT entities into delete/preserve buckets."""
    to_delete: list[EntityEntry] = []
    to_preserve: list[EntityEntry] = []

    for entity in entities:
        if entity.get("platform") != "mqtt":
            continue

        entity_id = entity.get("entity_id", "")
        name = entity.get("name") or entity.get("original_name", "") or ""
        name_lower = name.lower()
        entity_id_lower = entity_id.lower()

        if BRIDGE_PATTERN in name_lower or BRIDGE_PATTERN in entity_id_lower:
            to_preserve.append(entity)
        else:
            to_delete.append(entity)

    return to_delete, to_preserve


def _is_mqtt_identifier(identifier: list[str]) -> bool:
    """Check whether the identifier represents an MQTT device."""
    return len(identifier) == MQTT_IDENTIFIER_PARTS and identifier[0] == "mqtt"


def find_mqtt_devices(
    devices: list[DeviceEntry],
    device_ids_from_deleted_entities: set[str],
) -> tuple[list[DeviceEntry], list[DeviceEntry]]:
    """Split MQTT devices into delete/preserve buckets."""
    to_delete: list[DeviceEntry] = []
    to_preserve: list[DeviceEntry] = []

    for device in devices:
        identifiers = device.get("identifiers", [])
        if any(_is_mqtt_identifier(identifier) for identifier in identifiers):
            name = device.get("name_by_user") or device.get("name", "") or ""
            if BRIDGE_PATTERN in name.lower():
                to_preserve.append(device)
            elif device.get("id", "") in device_ids_from_deleted_entities:
                to_delete.append(device)

    return to_delete, to_preserve


def classify_restore_states(
    states: list[RestoreStateEntry],
    entity_ids_to_delete: set[str],
) -> tuple[list[str], list[str]]:
    """Separate restore_state entries into delete/keep buckets."""
    states_to_delete: list[str] = []
    states_to_keep: list[str] = []

    for state in states:
        entity_id = state.get("state", {}).get("entity_id")
        if not entity_id:
            continue

        if entity_id in entity_ids_to_delete:
            states_to_delete.append(entity_id)
        else:
            states_to_keep.append(entity_id)

    return states_to_delete, states_to_keep


def build_plan(registries: Registries) -> DeletionPlan:
    """Build a deletion plan from loaded registries."""
    entities = registries.entity_registry["data"]["entities"]
    devices = registries.device_registry["data"]["devices"]
    states = registries.restore_state.get("data", [])

    entities_to_delete, entities_to_preserve = find_mqtt_entities(entities)
    device_ids_from_deleted_entities = {
        device_id for entity in entities_to_delete if (device_id := entity.get("device_id"))
    }
    devices_to_delete, devices_to_preserve = find_mqtt_devices(
        devices,
        device_ids_from_deleted_entities,
    )
    states_to_delete, states_to_keep = classify_restore_states(
        states,
        {entity_id for entity in entities_to_delete if (entity_id := entity.get("entity_id"))},
    )

    return DeletionPlan(
        entities_to_delete=entities_to_delete,
        entities_to_preserve=entities_to_preserve,
        devices_to_delete=devices_to_delete,
        devices_to_preserve=devices_to_preserve,
        states_to_delete=states_to_delete,
        states_to_keep=states_to_keep,
    )


def log_summary(plan: DeletionPlan) -> None:
    """Log a human-readable summary of the planned deletions."""
    LOGGER.info("═════════════════ SUMMARY ═════════════════")
    LOGGER.info(
        "MQTT entities: %d total (delete %d, preserve %d)",
        len(plan.entities_to_delete) + len(plan.entities_to_preserve),
        len(plan.entities_to_delete),
        len(plan.entities_to_preserve),
    )
    LOGGER.info(
        "MQTT devices: %d total (delete %d, preserve %d)",
        len(plan.devices_to_delete) + len(plan.devices_to_preserve),
        len(plan.devices_to_delete),
        len(plan.devices_to_preserve),
    )
    LOGGER.info("Restore states to delete: %d", len(plan.states_to_delete))
    LOGGER.info("═════════════════════════════════════════════")


def confirm_deletion(plan: DeletionPlan) -> bool:
    """Prompt for confirmation before deleting."""
    entities = len(plan.entities_to_delete)
    devices = len(plan.devices_to_delete)
    states = len(plan.states_to_delete)
    prompt = f"Delete {entities} entities, {devices} devices, {states} states? (y/N): "
    response = input(prompt)
    return response.strip().lower() == "y"


def apply_deletions(registries: Registries, plan: DeletionPlan) -> None:
    """Apply deletions to in-memory registry structures."""
    entity_ids_to_delete = {entity_id for entity in plan.entities_to_delete if (entity_id := entity.get("entity_id"))}
    device_ids_to_delete = {device_id for device in plan.devices_to_delete if (device_id := device.get("id"))}

    registries.entity_registry["data"]["entities"] = [
        entity
        for entity in registries.entity_registry["data"]["entities"]
        if entity.get("entity_id") not in entity_ids_to_delete
    ]

    registries.device_registry["data"]["devices"] = [
        device
        for device in registries.device_registry["data"]["devices"]
        if device.get("id") not in device_ids_to_delete
    ]

    registries.restore_state["data"] = [
        state
        for state in registries.restore_state["data"]
        if state.get("state", {}).get("entity_id") not in entity_ids_to_delete
    ]


def save_registries(registries: Registries, paths: RegistryPaths) -> None:
    """Persist registry updates with backups."""
    LOGGER.info("Saving registry files...")
    save_json_file(paths.entity, registries.entity_registry)
    save_json_file(paths.device, registries.device_registry)
    save_json_file(paths.restore_state, registries.restore_state)


def main() -> None:
    """Run safe MQTT cleanup end-to-end."""
    configure_logging()
    LOGGER.info("Starting safe MQTT deletion")

    args = parse_args()
    raw_config_dir = args.config_dir
    dry_run = args.dry_run

    config_dir = resolve_config_dir(raw_config_dir)
    paths = build_paths(config_dir)

    registries = load_registries(paths)
    plan = build_plan(registries)
    log_summary(plan)

    if not plan.entities_to_delete:
        LOGGER.info("Nothing to delete.")
        return

    if dry_run:
        LOGGER.info("Dry run complete - no changes made.")
        return

    if not confirm_deletion(plan):
        LOGGER.info("Aborted.")
        return

    apply_deletions(registries, plan)
    save_registries(registries, paths)

    LOGGER.info("Deletion complete. Restart Home Assistant, then start the add-on.")


if __name__ == "__main__":
    main()
