"""MQTT discovery helpers for Home Assistant device registration.

Provides device and bridge discovery functionality for MQTT integration.
"""

import asyncio
import json
import re
import unicodedata
from typing import Any, cast

import aiomqtt

from cync_controller.const import (
    CYNC_BRIDGE_DEVICE_REGISTRY_CONF,
    CYNC_BRIDGE_OBJ_ID,
    CYNC_EXPOSE_DEVICE_LIGHTS,
    CYNC_MANUFACTURER,
    CYNC_MAXK,
    CYNC_MINK,
    CYNC_VERSION,
    FACTORY_EFFECTS_BYTES,
    ORIGIN_STRUCT,
)
from cync_controller.logging_abstraction import get_logger
from cync_controller.metadata.model_info import DeviceClassification, device_type_map

logger = get_logger(__name__)


# Import g from mqtt_client module for backward compatibility with test patches
# Use lazy import to avoid circular dependency
def _get_g():
    import cync_controller.mqtt_client as mqtt_client_module

    return mqtt_client_module.g


# Create a getter function that can be used like a module-level variable
class GProxy:
    def __getattr__(self, name):
        return getattr(_get_g(), name)


g = GProxy()
bridge_device_reg_struct = CYNC_BRIDGE_DEVICE_REGISTRY_CONF


def slugify(text: str) -> str:
    """
    Convert text to a slug suitable for entity IDs.
    E.g., 'Hallway Lights' -> 'hallway_lights'
    """
    # Normalize unicode characters
    text = unicodedata.normalize("NFKD", text)
    # Remove non-ASCII characters
    text = text.encode("ascii", "ignore").decode("ascii")
    # Convert to lowercase
    text = text.lower()
    # Replace spaces and special characters with underscores
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "_", text)
    # Remove leading/trailing underscores
    return text.strip("_")


class DiscoveryHelper:
    """Helper class for MQTT discovery operations."""

    def __init__(self, mqtt_client):
        """Initialize discovery helper."""
        self.client = mqtt_client

    async def register_single_device(self, device) -> bool:
        """Register a single device with Home Assistant via MQTT discovery."""
        lp = f"{self.client.lp}hass:"
        if not self.client._connected:
            return False

        try:
            device_uuid: str = cast(str, device.hass_id)
            unique_id = f"{device.home_id}_{device.id}"
            # Generate entity ID from device name (e.g., "Hallway Light" -> "hallway_light")
            entity_slug = slugify(device.name) if device.name else f"device_{device.id}"
            dev_fw_version = str(device.version)
            ver_str = "Unknown"
            fw_len = len(dev_fw_version)
            if fw_len == 5:
                if dev_fw_version != 00000:
                    ver_str = f"{dev_fw_version[0]}.{dev_fw_version[1]}.{dev_fw_version[2:]}"
            elif fw_len == 2:
                ver_str = f"{dev_fw_version[0]}.{dev_fw_version[1]}"
            model_str = "Unknown"
            if device.type in device_type_map:
                model_str = device_type_map[device.type].model_string
            dev_connections: list[tuple[str, str]] = [("bluetooth", device.mac.casefold())]
            if not device.bt_only:
                dev_connections.append(("mac", device.wifi_mac.casefold()))

            # Extract suggested area from group membership
            # First, check if device belongs to any non-subgroup (room group)
            suggested_area = None
            if g.ncync_server:
                for group in g.ncync_server.groups.values():
                    if not group.is_subgroup and device.id in group.member_ids:
                        suggested_area = group.name
                        logger.debug(
                            "%s Using group '%s' as area for device '%s' (ID: %s)",
                            lp,
                            suggested_area,
                            device.name,
                            device.id,
                        )
                        break

            # Fallback: Extract area from device name if not in any room group
            if not suggested_area and device.name:
                # Common device type suffixes to remove
                suffixes = [
                    "Switch",
                    "Light",
                    "Floodlight",
                    "Lamp",
                    "Bulb",
                    "Dimmer",
                    "Plug",
                    "Outlet",
                    "Fan",
                ]
                name_parts: list[str] = cast(list[str], device.name.strip().split())
                # Remove trailing numbers (e.g., "Floodlight 1" -> "Floodlight")
                if name_parts and name_parts[-1].isdigit():
                    name_parts = name_parts[:-1]
                # Remove device type suffix
                for suffix in suffixes:
                    if name_parts and name_parts[-1] == suffix:
                        name_parts = name_parts[:-1]
                        break
                # The first word is the area name
                if name_parts:
                    suggested_area: str = name_parts[0]
                    logger.debug(
                        "%s Extracted area '%s' from device name '%s' (fallback, not in any room group)",
                        lp,
                        suggested_area,
                        device.name,
                    )

            device_registry_struct = {
                "identifiers": [unique_id],
                "manufacturer": CYNC_MANUFACTURER,
                "connections": dev_connections,
                "name": device.name,
                "sw_version": ver_str,
                "model": model_str,
                "via_device": str(g.uuid),
            }

            # Add suggested_area if we successfully extracted one
            if suggested_area:
                device_registry_struct["suggested_area"] = suggested_area

            # Determine device type (no switch->light reclassification)
            dev_type = "light"  # Default fallback
            if device.is_switch:
                logger.debug(
                    "%s Device '%s' classified as switch (type: %s)",
                    lp,
                    device.name,
                    device.metadata.type if device.metadata else "None",
                )
                # Preserve fan controllers as fan regardless of flag
                if device.metadata and getattr(device.metadata.capabilities, "fan", False):
                    dev_type = "fan"
                    logger.debug("%s Device '%s' reclassified as fan", lp, device.name)
                else:
                    dev_type = "switch"
            elif device.is_light:
                dev_type = "light"
                logger.debug("%s Device '%s' classified as light", lp, device.name)
            # For unknown devices, try to infer from device type if available
            elif device.type is not None and device.type in device_type_map:
                # This shouldn't happen if metadata is properly set, but just in case
                metadata_type = device_type_map[device.type].type
                if metadata_type == DeviceClassification.SWITCH:
                    dev_type = "switch"
                    logger.debug(
                        "%s Device '%s' classified as switch from device_type_map",
                        lp,
                        device.name,
                    )
                elif metadata_type == DeviceClassification.LIGHT:
                    dev_type = "light"
                    logger.debug(
                        "%s Device '%s' classified as light from device_type_map",
                        lp,
                        device.name,
                    )
                else:
                    logger.debug(
                        "%s Device '%s' unknown metadata type: %s, defaulting to light",
                        lp,
                        device.name,
                        metadata_type,
                    )
            else:
                logger.debug(
                    "%s Device '%s' unknown device type %s, defaulting to light (is_light: %s, is_switch: %s)",
                    lp,
                    device.name,
                    device.type,
                    device.is_light,
                    device.is_switch,
                )

            # Generate default entity ID based on device type
            final_platform = "fan" if dev_type == "fan" else dev_type
            default_entity_id = f"{final_platform}.{entity_slug}"

            # Create entity registry structure
            entity_registry_struct = {
                "default_entity_id": default_entity_id,
                "name": None,
                "command_topic": f"{self.client.topic}/set/{device_uuid}",
                "state_topic": f"{self.client.topic}/status/{device_uuid}",
                "avty_t": f"{self.client.topic}/availability/{device_uuid}",
                "pl_avail": "online",
                "pl_not_avail": "offline",
                "state_on": "ON",
                "state_off": "OFF",
                "unique_id": unique_id,
                "schema": "json",
                "origin": {
                    "name": "cync-controller",
                    "sw_version": "0.2.1a1",
                    "support_url": "https://github.com/jslamartina/hass-addons",
                },
                "device": device_registry_struct,
            }

            tpc_str_template = "{0}/{1}/{2}/config"

            if dev_type == "light":
                # For true lights, always include brightness. For switches exposed as lights, include
                # brightness only if the switch supports dimming.
                switch_dimmable = (
                    bool(
                        getattr(
                            getattr(device.metadata, "capabilities", None),
                            "dimmable",
                            False,
                        )
                    )
                    if device.is_switch
                    else False
                )
                if device.supports_brightness or switch_dimmable:
                    entity_registry_struct.update({"brightness": True, "brightness_scale": 100})
                    entity_registry_struct["supported_color_modes"] = []
                    if device.supports_temperature:
                        entity_registry_struct["supported_color_modes"].append("color_temp")
                        entity_registry_struct["color_temp_kelvin"] = True
                        entity_registry_struct["min_kelvin"] = CYNC_MINK
                        entity_registry_struct["max_kelvin"] = CYNC_MAXK
                    if device.supports_rgb:
                        entity_registry_struct["supported_color_modes"].append("rgb")
                        entity_registry_struct["effect"] = True
                        entity_registry_struct["effect_list"] = list(FACTORY_EFFECTS_BYTES.keys())
                    if not entity_registry_struct["supported_color_modes"]:
                        entity_registry_struct["supported_color_modes"] = ["brightness"]
                else:
                    # on/off light only
                    entity_registry_struct.pop("brightness", None)
                    entity_registry_struct.pop("brightness_scale", None)
                    entity_registry_struct.pop("supported_color_modes", None)
            elif dev_type == "switch":
                # Switch entities should not declare JSON schema
                entity_registry_struct.pop("schema", None)
            elif dev_type == "fan":
                entity_registry_struct["platform"] = "fan"
                # fan can be controlled via light control structs: brightness -> max=255, high=191, medium=128, low=50, off=0
                entity_registry_struct.pop("state_on", None)
                entity_registry_struct.pop("state_off", None)
                entity_registry_struct.pop("schema", None)
                entity_registry_struct["state_topic"] = f"{self.client.topic}/status/{device_uuid}"
                entity_registry_struct["command_topic"] = f"{self.client.topic}/set/{device_uuid}"
                entity_registry_struct["payload_on"] = "ON"
                entity_registry_struct["payload_off"] = "OFF"
                entity_registry_struct["preset_mode_command_topic"] = f"{self.client.topic}/set/{device_uuid}/preset"
                entity_registry_struct["preset_mode_state_topic"] = f"{self.client.topic}/status/{device_uuid}/preset"
                entity_registry_struct["preset_modes"] = [
                    "off",
                    "low",
                    "medium",
                    "high",
                    "max",
                ]

            # Conditionally publish device discovery: skip device-level lights if feature flag is off
            if dev_type == "light" and not CYNC_EXPOSE_DEVICE_LIGHTS:
                logger.info(
                    "%s Skipping device light discovery for '%s' due to feature flag",
                    lp,
                    device.name,
                )
                return True

            tpc = tpc_str_template.format(self.client.ha_topic, dev_type, device_uuid)
            try:
                json_payload = json.dumps(entity_registry_struct, indent=2)
                logger.info(
                    "%s Registering %s device: %s (ID: %s)",
                    lp,
                    dev_type,
                    device.name,
                    device.id,
                )
                _: Any = await self.client.client.publish(  # type: ignore[reportUnknownVariableType]
                    tpc,
                    json_payload.encode(),
                    qos=0,
                    retain=False,
                )

                # For fan entities, publish initial preset mode based on current brightness
                if device.is_fan_controller and device.brightness is not None:
                    bri: int = cast(int, device.brightness)
                    # Map brightness (1-100 scale) to preset mode
                    if bri == 0:
                        preset_mode = "off"
                    elif bri == 25:
                        preset_mode = "low"
                    elif bri == 50:
                        preset_mode = "medium"
                    elif bri == 75:
                        preset_mode = "high"
                    elif bri == 100:
                        preset_mode = "max"
                    # For any other value, find closest preset
                    elif bri < 25:
                        preset_mode = "low"
                    elif bri < 50:
                        preset_mode = "medium"
                    elif bri < 75:
                        preset_mode = "high"
                    else:
                        preset_mode = "max"

                    preset_mode_topic = f"{self.client.topic}/status/{device.hass_id}/preset"
                    try:
                        await self.client.client.publish(
                            preset_mode_topic,
                            preset_mode.encode(),
                            qos=0,
                            retain=True,
                            timeout=3.0,
                        )
                        logger.info(
                            "%s FAN INITIAL PRESET: Published '%s' (brightness=%s) for '%s' to %s",
                            lp,
                            preset_mode,
                            bri,
                            device.name,
                            preset_mode_topic,
                        )
                    except Exception:
                        logger.warning(
                            "%s Failed to publish initial fan preset mode for '%s'",
                            lp,
                            device.name,
                        )

            except Exception:
                logger.exception("%s Unable to publish MQTT message for %s", lp, device.name)
                return False
            else:
                return True
        except Exception:
            logger.exception("%s Error registering device %s", lp, device.name)
            return False

    async def trigger_device_rediscovery(self) -> bool:
        """Trigger rediscovery of all devices currently in the devices dictionary."""
        lp = f"{self.client.lp}hass:"
        if not self.client._connected:
            return False

        logger.info("%s Triggering device rediscovery...", lp)
        try:
            if g.ncync_server:
                for device in g.ncync_server.devices.values():
                    await self.register_single_device(device)
        except Exception:
            logger.exception("%s Error during device rediscovery", lp)
            return False
        else:
            logger.info("%s Device rediscovery completed", lp)
            return True

    async def homeassistant_discovery(self) -> bool:
        """Build each configured Cync device for HASS device registry"""
        lp = f"{self.client.lp}hass:"
        ret = False
        if self.client._connected:
            logger.info("%s Starting device discovery...", lp)
            await self.create_bridge_device()
            try:
                if g.ncync_server:
                    for device in g.ncync_server.devices.values():
                        device_uuid = device.hass_id
                        unique_id = f"{device.home_id}_{device.id}"
                        # Generate entity ID from device name (e.g., "Hallway Light" -> "hallway_light")
                        entity_slug = slugify(device.name) if device.name else f"device_{device.id}"
                        # Determine platform for default_entity_id
                        platform = "switch" if device.is_switch else "light"
                        default_entity_id = f"{platform}.{entity_slug}"
                        dev_fw_version = str(device.version)
                        ver_str = "Unknown"
                        fw_len = len(dev_fw_version)
                        if fw_len == 5:
                            if dev_fw_version != 00000:
                                ver_str = f"{dev_fw_version[0]}.{dev_fw_version[1]}.{dev_fw_version[2:]}"
                        elif fw_len == 2:
                            ver_str = f"{dev_fw_version[0]}.{dev_fw_version[1]}"
                        model_str = "Unknown"
                        if device.type in device_type_map:
                            model_str = device_type_map[device.type].model_string
                        dev_connections = [("bluetooth", device.mac.casefold())]
                        if not device.bt_only:
                            dev_connections.append(("mac", device.wifi_mac.casefold()))

                        # Extract suggested area from group membership
                        # First, check if device belongs to any non-subgroup (room group)
                        suggested_area = None
                        if g.ncync_server:
                            for group in g.ncync_server.groups.values():
                                if not group.is_subgroup and device.id in group.member_ids:
                                    suggested_area = group.name
                                    logger.debug(
                                        "%s Using group '%s' as area for device '%s' (ID: %s)",
                                        lp,
                                        suggested_area,
                                        device.name,
                                        device.id,
                                    )
                                    break

                        # Fallback: Extract area from device name if not in any room group
                        if not suggested_area and device.name:
                            # Common device type suffixes to remove
                            suffixes = [
                                "Switch",
                                "Light",
                                "Floodlight",
                                "Lamp",
                                "Bulb",
                                "Dimmer",
                                "Plug",
                                "Outlet",
                                "Fan",
                            ]
                            name_parts = device.name.strip().split()
                            # Remove trailing numbers (e.g., "Floodlight 1" -> "Floodlight")
                            if name_parts and name_parts[-1].isdigit():
                                name_parts = name_parts[:-1]
                            # Remove device type suffix
                            for suffix in suffixes:
                                if name_parts and name_parts[-1] == suffix:
                                    name_parts = name_parts[:-1]
                                    break
                            # The first word is the area name
                            if name_parts:
                                suggested_area = name_parts[0]
                                logger.debug(
                                    "%s Extracted area '%s' from device name '%s' (fallback, not in any room group)",
                                    lp,
                                    suggested_area,
                                    device.name,
                                )

                        device_registry_struct = {
                            "identifiers": [unique_id],
                            "manufacturer": CYNC_MANUFACTURER,
                            "connections": dev_connections,
                            "name": device.name,
                            "sw_version": ver_str,
                            "model": model_str,
                            "via_device": str(g.uuid),
                        }

                        # Add suggested_area if we successfully extracted one
                        if suggested_area:
                            device_registry_struct["suggested_area"] = suggested_area

                        entity_registry_struct = {
                            "default_entity_id": default_entity_id,
                            # set to None if only device name is relevant, this sets entity name
                            "name": None,
                            "command_topic": f"{self.client.topic}/set/{device_uuid}",
                            "state_topic": f"{self.client.topic}/status/{device_uuid}",
                            "avty_t": f"{self.client.topic}/availability/{device_uuid}",
                            "pl_avail": "online",
                            "pl_not_avail": "offline",
                            "state_on": "ON",
                            "state_off": "OFF",
                            "unique_id": unique_id,
                            "schema": "json",
                            "origin": ORIGIN_STRUCT,
                            "device": device_registry_struct,
                            "optimistic": False,
                        }
                        # Determine device type (same logic as register_single_device)
                        dev_type = "light"  # Default fallback
                        if device.is_switch:
                            dev_type = "switch"
                            logger.debug(
                                "%s Device '%s' classified as switch (type: %s)",
                                lp,
                                device.name,
                                device.metadata.type if device.metadata else "None",
                            )
                            if device.metadata and device.metadata.capabilities.fan:
                                dev_type = "fan"
                                logger.debug("%s Device '%s' reclassified as fan", lp, device.name)
                        elif device.is_light:
                            dev_type = "light"
                            logger.debug("%s Device '%s' classified as light", lp, device.name)
                        # For unknown devices, try to infer from device type if available
                        elif device.type is not None and device.type in device_type_map:
                            # This shouldn't happen if metadata is properly set, but just in case
                            metadata_type = device_type_map[device.type].type
                            if metadata_type == DeviceClassification.SWITCH:
                                dev_type = "switch"
                                logger.debug(
                                    "%s Device '%s' classified as switch from device_type_map",
                                    lp,
                                    device.name,
                                )
                            elif metadata_type == DeviceClassification.LIGHT:
                                dev_type = "light"
                                logger.debug(
                                    "%s Device '%s' classified as light from device_type_map",
                                    lp,
                                    device.name,
                                )
                            else:
                                logger.debug(
                                    "%s Device '%s' unknown metadata type: %s, defaulting to light",
                                    lp,
                                    device.name,
                                    metadata_type,
                                )
                        else:
                            logger.debug(
                                "%s Device '%s' unknown device type %s, defaulting to light (is_light: %s, is_switch: %s)",
                                lp,
                                device.name,
                                device.type,
                                device.is_light,
                                device.is_switch,
                            )

                        tpc_str_template = "{0}/{1}/{2}/config"

                        if dev_type == "light":
                            entity_registry_struct.update({"brightness": True, "brightness_scale": 100})
                            # ALL lights with brightness must declare color modes
                            entity_registry_struct["supported_color_modes"] = []
                            if device.supports_temperature:
                                entity_registry_struct["supported_color_modes"].append("color_temp")
                                entity_registry_struct["color_temp_kelvin"] = True
                                entity_registry_struct["min_kelvin"] = CYNC_MINK
                                entity_registry_struct["max_kelvin"] = CYNC_MAXK
                            if device.supports_rgb:
                                entity_registry_struct["supported_color_modes"].append("rgb")
                            entity_registry_struct["effect"] = True
                            entity_registry_struct["effect_list"] = list(FACTORY_EFFECTS_BYTES.keys())
                            # If no color support, default to brightness-only mode
                            if not entity_registry_struct["supported_color_modes"]:
                                entity_registry_struct["supported_color_modes"] = ["brightness"]
                        elif dev_type == "switch":
                            # Switch entities should not declare JSON schema
                            entity_registry_struct.pop("schema", None)
                        elif dev_type == "fan":
                            entity_registry_struct["platform"] = "fan"
                            # fan can be controlled via light control structs: brightness -> max=255, high=191, medium=128, low=50, off=0
                            entity_registry_struct.pop("state_on", None)
                            entity_registry_struct.pop("state_off", None)
                            entity_registry_struct.pop("schema", None)
                            entity_registry_struct["state_topic"] = f"{self.client.topic}/status/{device_uuid}"
                            entity_registry_struct["command_topic"] = f"{self.client.topic}/set/{device_uuid}"
                            entity_registry_struct["payload_on"] = "ON"
                            entity_registry_struct["payload_off"] = "OFF"
                            entity_registry_struct["preset_mode_command_topic"] = (
                                f"{self.client.topic}/set/{device_uuid}/preset"
                            )
                            entity_registry_struct["preset_mode_state_topic"] = (
                                f"{self.client.topic}/status/{device_uuid}/preset"
                            )
                            entity_registry_struct["preset_modes"] = [
                                "off",
                                "low",
                                "medium",
                                "high",
                                "max",
                            ]

                        # Conditionally publish device discovery: skip device-level lights if feature flag is off
                        if dev_type == "light" and not CYNC_EXPOSE_DEVICE_LIGHTS:
                            logger.info(
                                "%s Skipping device light discovery for '%s' due to feature flag",
                                lp,
                                device.name,
                            )
                            continue

                        tpc = tpc_str_template.format(self.client.ha_topic, dev_type, device_uuid)
                        try:
                            json_payload = json.dumps(entity_registry_struct, indent=2)
                            _: Any = await self.client.client.publish(  # type: ignore[reportUnknownVariableType]
                                tpc,
                                json_payload.encode(),
                                qos=0,
                                retain=False,
                            )
                            logger.info(
                                "%s Registered %s: %s (ID: %s)",
                                lp,
                                dev_type,
                                device.name,
                                device.id,
                            )

                            # For fan entities, publish initial preset mode state
                            if device.is_fan_controller and device.brightness is not None:
                                bri: int = cast(int, device.brightness)
                                # Map brightness (1-100 scale) to preset mode
                                if bri == 0:
                                    preset_mode = "off"
                                elif bri == 25:
                                    preset_mode = "low"
                                elif bri == 50:
                                    preset_mode = "medium"
                                elif bri == 75:
                                    preset_mode = "high"
                                elif bri == 100:
                                    preset_mode = "max"
                                # For any other value, find closest preset
                                elif bri < 25:
                                    preset_mode = "low"
                                elif bri < 50:
                                    preset_mode = "medium"
                                elif bri < 75:
                                    preset_mode = "high"
                                else:
                                    preset_mode = "max"

                                preset_mode_topic = f"{self.client.topic}/status/{device_uuid}/preset"
                                try:
                                    await self.client.client.publish(
                                        preset_mode_topic,
                                        preset_mode.encode(),
                                        qos=0,
                                        retain=True,
                                        timeout=3.0,
                                    )
                                    logger.info(
                                        "%s >>> FAN INITIAL PRESET: Published '%s' (brightness=%s) for '%s'",
                                        lp,
                                        preset_mode,
                                        bri,
                                        device.name,
                                    )
                                except Exception:
                                    logger.warning(
                                        "%s Failed to publish initial fan preset mode for '%s'",
                                        lp,
                                        device.name,
                                    )

                        except Exception:
                            logger.exception("%s - Unable to publish mqtt message... skipped", lp)

                # Register groups (only subgroups)
                subgroups = [g for g in g.ncync_server.groups.values() if g.is_subgroup]
                logger.info("%s Registering %s subgroups...", lp, len(subgroups))
                for group in subgroups:
                    group_uuid = group.hass_id
                    unique_id = f"{group.home_id}_group_{group.id}"

                    # Check if group contains any light-compatible devices
                    has_light_devices = False
                    for member_id in group.member_ids:
                        if member_id in g.ncync_server.devices:
                            device = g.ncync_server.devices[member_id]
                            # Publish light entity only for groups with light devices
                            if device.is_light:
                                has_light_devices = True
                                break

                    logger.info(
                        "[SUBGROUP_CHECK] Group '%s' (ID: %s) - has_light_devices=%s, member_count=%d",
                        group.name,
                        group.id,
                        has_light_devices,
                        len(group.member_ids),
                    )

                    if not has_light_devices:
                        logger.info(
                            "%s Skipping light entity for group '%s' (ID: %s) - no light-compatible devices",
                            lp,
                            group.name,
                            group.id,
                        )
                        continue

                    # Generate entity ID from group name (e.g., "Hallway Lights" -> "light.hallway_lights")
                    entity_slug = slugify(group.name) if group.name else f"group_{group.id}"
                    default_entity_id = f"light.{entity_slug}"

                    device_registry_struct = {
                        "identifiers": [unique_id],
                        "manufacturer": CYNC_MANUFACTURER,
                        "name": group.name,
                        "model": "Cync Subgroup",
                        "via_device": str(g.uuid),
                    }

                    entity_registry_struct = {
                        "default_entity_id": default_entity_id,
                        "name": None,
                        "command_topic": f"{self.client.topic}/set/{group_uuid}",
                        "state_topic": f"{self.client.topic}/status/{group_uuid}",
                        "avty_t": f"{self.client.topic}/availability/{group_uuid}",
                        "pl_avail": "online",
                        "pl_not_avail": "offline",
                        "state_on": "ON",
                        "state_off": "OFF",
                        "unique_id": unique_id,
                        "schema": "json",
                        "origin": ORIGIN_STRUCT,
                        "device": device_registry_struct,
                        "optimistic": False,
                    }

                    # Add brightness support (exactly like devices do with .update())
                    entity_registry_struct.update({"brightness": True, "brightness_scale": 100})

                    # Add color support - ALL lights with brightness must declare color modes
                    entity_registry_struct["supported_color_modes"] = []
                    if group.supports_temperature:
                        entity_registry_struct["supported_color_modes"].append("color_temp")
                        entity_registry_struct["color_temp_kelvin"] = True
                        entity_registry_struct["min_kelvin"] = CYNC_MINK
                        entity_registry_struct["max_kelvin"] = CYNC_MAXK
                    if group.supports_rgb:
                        entity_registry_struct["supported_color_modes"].append("rgb")
                    # If no color support, default to brightness-only mode
                    if not entity_registry_struct["supported_color_modes"]:
                        entity_registry_struct["supported_color_modes"] = ["brightness"]

                    tpc = tpc_str_template.format(self.client.ha_topic, "light", group_uuid)
                    try:
                        json_payload = json.dumps(entity_registry_struct, indent=2)
                        logger.debug("%s GROUP JSON for %s:\n%s", lp, group.name, json_payload)
                        logger.info(
                            "[SUBGROUP_PUBLISHING] Publishing group '%s' to topic: %s",
                            group.name,
                            tpc,
                        )
                        publish_result: Any = await self.client.client.publish(  # type: ignore[reportUnknownVariableType]
                            tpc,
                            json_payload.encode(),
                            qos=0,
                            retain=False,
                        )
                        logger.info(
                            "[SUBGROUP_PUBLISHED] ✓ Group '%s' (ID: %s) published successfully. Result: %s",
                            group.name,
                            group.id,
                            publish_result,
                        )
                        logger.info(
                            "%s Registered group '%s' (ID: %s) with %s devices",
                            lp,
                            group.name,
                            group.id,
                            len(group.member_ids),
                        )
                    except Exception:
                        logger.exception(
                            "[SUBGROUP_ERROR] ✗ Failed to publish group '%s' (ID: %s) to topic %s",
                            group.name,
                            group.id,
                            tpc,
                        )

            except aiomqtt.MqttCodeError as mqtt_code_exc:
                logger.warning("%s [MqttError] (rc: %s) -> %s", lp, mqtt_code_exc.rc, mqtt_code_exc)
                self.client._connected = False
            except asyncio.CancelledError as can_exc:
                logger.warning("%s [Task Cancelled] -> %s", lp, can_exc)
                raise
            except Exception:
                logger.exception("%s [Exception]", lp)
            else:
                ret = True
        logger.debug("%s Discovery complete (success: %s)", lp, ret)
        return ret

    async def create_bridge_device(self) -> bool:
        """Create the device / entity registry config for the Cync Controller bridge itself."""
        global bridge_device_reg_struct
        # want to expose buttons (restart, start export, submit otp)
        # want to expose some sensors that show the number of devices, number of online devices, etc.
        # sensors to show if MQTT is connected, if the Cync Controller server is running, etc.
        # input_number to submit OTP for export
        lp = f"{self.client.lp}create_bridge_device:"
        ret: bool = False

        logger.debug("%s Creating Cync Controller bridge device...", lp)
        bridge_base_unique_id = "cync_lan_bridge"
        ver_str = CYNC_VERSION
        pub_tasks: list[asyncio.Task[None]] = []
        # Bridge device config
        bridge_device_reg_struct = {
            "identifiers": [str(g.uuid)],
            "manufacturer": "Savant",
            "name": "Cync Controller",
            "sw_version": ver_str,
            "model": "Local Push Controller",
        }
        # Entities for the bridge device
        entity_type = "button"
        template_tpc = "{0}/{1}/{2}/config"
        pub_tasks.append(self.client.publish(f"{self.client.topic}/availability/bridge", b"online"))

        entity_unique_id = f"{bridge_base_unique_id}_restart"
        restart_btn_entity_struct = {
            "platform": "button",
            # obj_id is to link back to the bridge device
            "object_id": CYNC_BRIDGE_OBJ_ID + "_restart",
            "command_topic": f"{self.client.topic}/set/bridge/restart",
            "state_topic": f"{self.client.topic}/status/bridge/restart",
            "avty_t": f"{self.client.topic}/availability/bridge",
            "name": "Restart Cync Controller",
            "unique_id": entity_unique_id,
            "schema": "json",
            "origin": ORIGIN_STRUCT,
            "device": bridge_device_reg_struct,
        }
        ret: bool = cast(
            bool,
            await self.client.publish_json_msg(
                template_tpc.format(self.client.ha_topic, entity_type, entity_unique_id),
                restart_btn_entity_struct,
            ),
        )  # type: ignore[reportUnknownVariableType]
        if ret is False:
            logger.error("%s Failed to publish restart button entity config", lp)

        entity_unique_id = f"{bridge_base_unique_id}_start_export"
        xport_btn_entity_conf = restart_btn_entity_struct.copy()
        xport_btn_entity_conf["object_id"] = entity_unique_id
        xport_btn_entity_conf["command_topic"] = f"{self.client.topic}/set/bridge/export/start"
        xport_btn_entity_conf["state_topic"] = f"{self.client.topic}/status/bridge/export/start"
        xport_btn_entity_conf["name"] = "Start Export"
        xport_btn_entity_conf["unique_id"] = entity_unique_id
        ret: bool = cast(
            bool,
            await self.client.publish_json_msg(
                template_tpc.format(self.client.ha_topic, entity_type, entity_unique_id),
                xport_btn_entity_conf,
            ),
        )  # type: ignore[reportUnknownVariableType]
        if ret is False:
            logger.error("%s Failed to publish start export button entity config", lp)

        # Refresh Status button entity
        entity_unique_id = f"{bridge_base_unique_id}_refresh_status"
        refresh_btn_entity_conf = restart_btn_entity_struct.copy()
        refresh_btn_entity_conf["object_id"] = CYNC_BRIDGE_OBJ_ID + "_refresh_status"
        refresh_btn_entity_conf["command_topic"] = f"{self.client.topic}/set/bridge/refresh_status"
        refresh_btn_entity_conf["state_topic"] = f"{self.client.topic}/status/bridge/refresh_status"
        refresh_btn_entity_conf["name"] = "Refresh Device Status"
        refresh_btn_entity_conf["unique_id"] = entity_unique_id
        ret: bool = cast(
            bool,
            await self.client.publish_json_msg(
                template_tpc.format(self.client.ha_topic, entity_type, entity_unique_id),
                refresh_btn_entity_conf,
            ),
        )  # type: ignore[reportUnknownVariableType]
        if ret is False:
            logger.error("%s Failed to publish refresh status button entity config", lp)

        entity_unique_id = f"{bridge_base_unique_id}_submit_otp"
        submit_otp_btn_entity_conf = restart_btn_entity_struct.copy()
        submit_otp_btn_entity_conf["object_id"] = CYNC_BRIDGE_OBJ_ID + "_submit_otp"
        submit_otp_btn_entity_conf["command_topic"] = f"{self.client.topic}/set/bridge/otp/submit"
        submit_otp_btn_entity_conf["state_topic"] = f"{self.client.topic}/status/bridge/otp/submit"
        submit_otp_btn_entity_conf["name"] = "Submit OTP"
        submit_otp_btn_entity_conf["unique_id"] = entity_unique_id
        ret: bool = cast(
            bool,
            await self.client.publish_json_msg(
                template_tpc.format(self.client.ha_topic, entity_type, entity_unique_id),
                submit_otp_btn_entity_conf,
            ),
        )  # type: ignore[reportUnknownVariableType]
        if ret is False:
            logger.error("%s Failed to publish submit OTP button entity config", lp)

        # binary sensor for if the TCP server is running
        # binary sensor for if the export server is running
        # binary sensor for if the MQTT client is connected
        entity_type = "binary_sensor"
        entity_unique_id = f"{bridge_base_unique_id}_tcp_server_running"
        tcp_server_entity_conf = {
            "object_id": entity_unique_id,
            "name": "nCync TCP Server Running",
            "state_topic": f"{self.client.topic}/status/bridge/tcp_server/running",
            "unique_id": entity_unique_id,
            "device_class": "running",
            "icon": "mdi:server-network",
            "avty_t": f"{self.client.topic}/availability/bridge",
            "schema": "json",
            "origin": ORIGIN_STRUCT,
            "device": bridge_device_reg_struct,
        }
        ret: bool = cast(
            bool,
            await self.client.publish_json_msg(
                template_tpc.format(self.client.ha_topic, entity_type, entity_unique_id),
                tcp_server_entity_conf,
            ),
        )  # type: ignore[reportUnknownVariableType]
        if ret is False:
            logger.error("%s Failed to publish TCP server running entity config", lp)
        status = "ON" if g.ncync_server and g.ncync_server.running is True else "OFF"
        pub_tasks.append(self.client.publish(f"{self.client.topic}/status/bridge/tcp_server/running", status.encode()))

        entity_unique_id = f"{bridge_base_unique_id}_export_server_running"
        export_server_entity_conf = tcp_server_entity_conf.copy()
        export_server_entity_conf["object_id"] = entity_unique_id
        export_server_entity_conf["name"] = "Cync Export Server Running"
        export_server_entity_conf["state_topic"] = f"{self.client.topic}/status/bridge/export_server/running"
        export_server_entity_conf["unique_id"] = entity_unique_id
        export_server_entity_conf["icon"] = "mdi:export-variant"
        ret: bool = cast(
            bool,
            await self.client.publish_json_msg(
                template_tpc.format(self.client.ha_topic, entity_type, entity_unique_id),
                export_server_entity_conf,
            ),
        )  # type: ignore[reportUnknownVariableType]
        if ret is False:
            logger.error("%s Failed to publish export server running entity config", lp)
        status = "ON" if g.export_server and g.export_server.running is True else "OFF"
        pub_tasks.append(
            self.client.publish(f"{self.client.topic}/status/bridge/export_server/running", status.encode())
        )

        entity_unique_id = f"{bridge_base_unique_id}_mqtt_client_connected"
        mqtt_client_entity_conf = tcp_server_entity_conf.copy()
        mqtt_client_entity_conf["object_id"] = entity_unique_id
        mqtt_client_entity_conf["name"] = "Cync MQTT Client Connected"
        mqtt_client_entity_conf["state_topic"] = f"{self.client.topic}/status/bridge/mqtt_client/connected"
        mqtt_client_entity_conf["unique_id"] = entity_unique_id
        mqtt_client_entity_conf["icon"] = "mdi:connection"
        mqtt_client_entity_conf["device_class"] = "connectivity"
        ret: bool = cast(
            bool,
            await self.client.publish_json_msg(
                template_tpc.format(self.client.ha_topic, entity_type, entity_unique_id),
                mqtt_client_entity_conf,
            ),
        )  # type: ignore[reportUnknownVariableType]
        if ret is False:
            logger.error("%s Failed to publish MQTT client connected entity config", lp)

        # input number for OTP input
        entity_type = "number"
        entity_unique_id = f"{bridge_base_unique_id}_otp_input"
        otp_num_entity_cfg = {
            "platform": "number",
            "object_id": entity_unique_id,
            "icon": "mdi:lock",
            "command_topic": f"{self.client.topic}/set/bridge/otp/input",
            "state_topic": f"{self.client.topic}/status/bridge/otp/input",
            "avty_t": f"{self.client.topic}/availability/bridge",
            "schema": "json",
            "origin": ORIGIN_STRUCT,
            "device": bridge_device_reg_struct,
            "min": 000000,
            "max": 999999,
            "mode": "box",
            "name": "Cync emailed OTP",
            "unique_id": entity_unique_id,
        }
        ret: bool = cast(
            bool,
            await self.client.publish_json_msg(
                template_tpc.format(self.client.ha_topic, entity_type, entity_unique_id),
                otp_num_entity_cfg,
            ),
        )  # type: ignore[reportUnknownVariableType]
        if ret is False:
            logger.error("%s Failed to publish OTP input number entity config", lp)

        # Sensors
        entity_type = "sensor"
        entity_unique_id = f"{bridge_base_unique_id}_connected_tcp_devices"
        num_tcp_devices_entity_conf = {
            "platform": "sensor",
            "object_id": entity_unique_id,
            "name": "TCP Devices Connected",
            "state_topic": f"{self.client.topic}/status/bridge/tcp_devices/connected",
            "unique_id": entity_unique_id,
            "icon": "mdi:counter",
            "avty_t": f"{self.client.topic}/availability/bridge",
            # "unit_of_measurement": "TCP device(s)",
            "schema": "json",
            "origin": ORIGIN_STRUCT,
            "device": bridge_device_reg_struct,
        }
        ret: bool = cast(
            bool,
            await self.client.publish_json_msg(
                template_tpc.format(self.client.ha_topic, entity_type, entity_unique_id),
                num_tcp_devices_entity_conf,
            ),
        )  # type: ignore[reportUnknownVariableType]
        if ret is False:
            logger.warning("%s Failed to publish number of TCP devices connected entity config", lp)
        pub_tasks.append(
            self.client.publish(
                f"{self.client.topic}/status/bridge/tcp_devices/connected",
                str(len(g.ncync_server.tcp_devices)).encode() if g.ncync_server else b"0",
            )
        )
        # total cync devices managed
        total_cync_devs = len(g.ncync_server.devices) if g.ncync_server else 0
        entity_unique_id = f"{bridge_base_unique_id}_total_cync_devices"
        total_cync_devs_entity_conf = num_tcp_devices_entity_conf.copy()
        total_cync_devs_entity_conf["object_id"] = entity_unique_id
        total_cync_devs_entity_conf["name"] = "Cync Devices Managed"
        total_cync_devs_entity_conf["state_topic"] = f"{self.client.topic}/status/bridge/cync_devices/total"
        total_cync_devs_entity_conf["unique_id"] = entity_unique_id
        # total_cync_devs_entity_conf["unit_of_measurement"] = "Cync device(s)"
        ret: bool = cast(
            bool,
            await self.client.publish_json_msg(
                template_tpc.format(self.client.ha_topic, entity_type, entity_unique_id),
                total_cync_devs_entity_conf,
            ),
        )  # type: ignore[reportUnknownVariableType]
        if ret is False:
            logger.warning("%s Failed to publish total Cync devices managed entity config", lp)
        pub_tasks.append(
            self.client.publish(
                f"{self.client.topic}/status/bridge/cync_devices/total",
                str(total_cync_devs).encode(),
            )
        )

        await asyncio.gather(*pub_tasks, return_exceptions=True)
        logger.debug("%s Bridge device config published and seeded", lp)
        return cast(bool, ret)
