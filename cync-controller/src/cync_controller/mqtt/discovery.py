import json

from cync_controller.const import *
from cync_controller.devices import CyncDevice
from cync_controller.logging_abstraction import get_logger
from cync_controller.metadata.model_info import DeviceClassification, device_type_map
from cync_controller.mqtt.commands import slugify
from cync_controller.structs import GlobalObject

logger = get_logger(__name__)
g = GlobalObject()


class HomeAssistantDiscovery:
    """Handles Home Assistant device discovery and configuration."""

    def __init__(self, mqtt_client):
        self.mqtt_client = mqtt_client
        self.lp = "HomeAssistantDiscovery:"

    async def trigger_device_rediscovery(self) -> bool:
        """Trigger rediscovery of all devices currently in the devices dictionary."""
        lp = f"{self.lp}trigger_device_rediscovery:"
        if not self.mqtt_client._connected:
            return False

        logger.info("%s Triggering device rediscovery...", lp)
        return await self.homeassistant_discovery()

    async def homeassistant_discovery(self) -> bool:
        """Build each configured Cync device for HASS device registry"""
        lp = f"{self.lp}homeassistant_discovery:"
        ret = False
        if self.mqtt_client._connected:
            logger.info("%s Starting device discovery...", lp)
            await self.create_bridge_device()
            try:
                for device in g.ncync_server.devices.values():
                    await self._discover_device(device)
                ret = True
            except Exception as e:
                logger.error("%s Error during device discovery: %s", lp, e)
        return ret

    async def _discover_device(self, device: CyncDevice):
        """Discover a single device for Home Assistant."""
        lp = f"{self.lp}_discover_device:"
        device_uuid = device.hass_id
        unique_id = f"{device.home_id}_{device.id}"

        # Generate entity ID from device name
        entity_slug = slugify(device.name) if device.name else f"device_{device.id}"
        platform = "switch" if device.is_switch else "light"
        default_entity_id = f"{platform}.{entity_slug}"

        # Parse firmware version
        dev_fw_version = str(device.version)
        ver_str = "Unknown"
        fw_len = len(dev_fw_version)
        if fw_len == 5:
            if dev_fw_version != "00000":
                ver_str = f"{dev_fw_version[0]}.{dev_fw_version[1]}.{dev_fw_version[2:]}"
        elif fw_len == 2:
            ver_str = f"{dev_fw_version[0]}.{dev_fw_version[1]}"

        # Get model string
        model_str = "Unknown"
        if device.type in device_type_map:
            model_str = device_type_map[device.type].model_string

        # Build device connections
        dev_connections = [("bluetooth", device.mac.casefold())]
        if not device.bt_only:
            dev_connections.append(("mac", device.wifi_mac.casefold()))

        # Extract suggested area from group membership
        suggested_area = self._extract_suggested_area(device)

        # Build device registry structure
        device_registry_struct = {
            "identifiers": [unique_id],
            "manufacturer": CYNC_MANUFACTURER,
            "connections": dev_connections,
            "name": device.name,
            "sw_version": ver_str,
            "model": model_str,
            "via_device": str(g.uuid),
        }

        if suggested_area:
            device_registry_struct["suggested_area"] = suggested_area

        # Build entity registry structure
        entity_registry_struct = {
            "default_entity_id": default_entity_id,
            "name": None,
            "command_topic": f"{self.mqtt_client.topic}/set/{device_uuid}",
            "state_topic": f"{self.mqtt_client.topic}/status/{device_uuid}",
            "avty_t": f"{self.mqtt_client.topic}/availability/{device_uuid}",
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

        # Determine device type and configure accordingly
        dev_type = self._determine_device_type(device)
        await self._configure_entity_for_type(entity_registry_struct, device, dev_type)

        # Publish discovery message
        tpc_str_template = "{0}/{1}/{2}/config"
        topic = tpc_str_template.format(self.mqtt_client.ha_topic, dev_type, device_uuid)

        await self.mqtt_client.publish(topic, json.dumps(entity_registry_struct), retain=True)
        logger.debug("%s Published discovery for %s: %s", lp, device.name, dev_type)

    def _extract_suggested_area(self, device: CyncDevice) -> str | None:
        """Extract suggested area from group membership or device name."""
        lp = f"{self.lp}_extract_suggested_area:"

        # First, check if device belongs to any non-subgroup (room group)
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
                return suggested_area

        # Fallback: Extract area from device name if not in any room group
        if device.name:
            suffixes = [
                "Switch", "Light", "Floodlight", "Lamp", "Bulb",
                "Dimmer", "Plug", "Outlet", "Fan"
            ]
            name_parts = device.name.strip().split()

            # Remove trailing numbers
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
                    "%s Extracted area '%s' from device name '%s' (fallback)",
                    lp,
                    suggested_area,
                    device.name,
                )
                return suggested_area

        return None

    def _determine_device_type(self, device: CyncDevice) -> str:
        """Determine the Home Assistant device type for a Cync device."""
        lp = f"{self.lp}_determine_device_type:"

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
        elif device.type is not None and device.type in device_type_map:
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
                dev_type = "light"
        else:
            logger.debug(
                "%s Device '%s' unknown device type %s, defaulting to light",
                lp,
                device.name,
                device.type,
            )
            dev_type = "light"

        return dev_type

    async def _configure_entity_for_type(self, entity_registry_struct: dict, device: CyncDevice, dev_type: str):
        """Configure entity registry structure based on device type."""
        if dev_type == "light":
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

            # If no color support, default to brightness-only mode
            if not entity_registry_struct["supported_color_modes"]:
                entity_registry_struct["supported_color_modes"] = ["brightness"]

        elif dev_type == "switch":
            # Switch entities should not declare JSON schema
            entity_registry_struct.pop("schema", None)

        elif dev_type == "fan":
            entity_registry_struct["platform"] = "fan"
            entity_registry_struct.pop("state_on", None)
            entity_registry_struct.pop("state_off", None)
            entity_registry_struct.pop("schema", None)
            entity_registry_struct["state_topic"] = f"{self.mqtt_client.topic}/status/{device.hass_id}"
            entity_registry_struct["command_topic"] = f"{self.mqtt_client.topic}/set/{device.hass_id}"
            entity_registry_struct["payload_on"] = "ON"
            entity_registry_struct["payload_off"] = "OFF"
            entity_registry_struct["preset_mode_command_topic"] = f"{self.mqtt_client.topic}/set/{device.hass_id}/preset"
            entity_registry_struct["preset_mode_state_topic"] = f"{self.mqtt_client.topic}/status/{device.hass_id}/preset"
            entity_registry_struct["preset_modes"] = [
                "off", "low", "medium", "high", "max"
            ]

    async def create_bridge_device(self):
        """Create the bridge device for Home Assistant."""
        lp = f"{self.lp}create_bridge_device:"

        bridge_device_registry_struct = {
            "identifiers": [str(g.uuid)],
            "manufacturer": CYNC_MANUFACTURER,
            "name": "Cync LAN Bridge",
            "sw_version": "1.0.0",
            "model": "Cync LAN Bridge",
        }

        bridge_entity_registry_struct = {
            "default_entity_id": "sensor.cync_lan_bridge_status",
            "name": "Bridge Status",
            "state_topic": f"{self.mqtt_client.topic}/status/bridge/mqtt_client/connected",
            "unique_id": str(g.uuid),
            "device": bridge_device_registry_struct,
        }

        topic = f"{self.mqtt_client.ha_topic}/sensor/{g.uuid}/config"
        await self.mqtt_client.publish(topic, json.dumps(bridge_entity_registry_struct), retain=True)
        logger.debug("%s Published bridge device discovery", lp)
