"""
MQTT state update helper for device and group state publishing.

Provides methods for publishing device state updates, brightness, temperature, RGB,
and group states to MQTT for Home Assistant integration.
"""

import asyncio
import json
import time
import traceback

import aiomqtt

from cync_controller.devices import CyncDevice, CyncGroup
from cync_controller.logging_abstraction import get_logger
from cync_controller.structs import DeviceStatus

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


class StateUpdateHelper:
    """Helper class for publishing device and group state updates to MQTT."""

    def __init__(self, mqtt_client):
        """
        Initialize the state update helper.

        Args:
            mqtt_client: MQTTClient instance to access connection and topic
        """
        self.client = mqtt_client

    async def pub_online(self, device_id: int, status: bool) -> bool:
        lp = f"{self.client.lp}pub_online:"
        if self.client._connected:
            if device_id not in g.ncync_server.devices:
                logger.error(
                    "%s Device ID %s not found?! Have you deleted or added any devices recently? You may need to re-export devices from your Cync account!",
                    lp,
                    device_id,
                )
                return False
            availability = b"online" if status else b"offline"
            device: CyncDevice = g.ncync_server.devices[device_id]
            device_uuid = f"{device.home_id}-{device_id}"
            # logger.debug("%s Publishing availability: %s", lp, availability)
            try:
                _ = await self.client.client.publish(
                    f"{self.client.topic}/availability/{device_uuid}", availability, qos=0
                )
            except aiomqtt.MqttError as mqtt_code_exc:
                logger.warning("%s [MqttError] -> %s", lp, mqtt_code_exc)
                self.client._connected = False
            else:
                return True
        return False

    async def update_device_state(self, device: CyncDevice, state: int) -> bool:
        """Update the device state and publish to MQTT for HASS devices to update.

        NOTE: Device availability is managed by server.parse_status() based on the
        connected_to_mesh byte and offline_count threshold. Do not set device.online here.
        """
        lp = f"{self.client.lp}update_device_state:"
        old_state = device.state
        device.state = state
        power_status = "OFF" if state == 0 else "ON"
        logger.info(
            "%s Updating device '%s' (ID: %s) state from %s to %s (%s)",
            lp,
            device.name,
            device.id,
            old_state,
            state,
            power_status,
        )
        mqtt_dev_state = {"state": power_status}
        if device.is_plug:
            mqtt_dev_state = power_status.encode()  # send ON or OFF if plug
        elif device.is_switch:
            # Switches only need plain ON/OFF payload (no JSON)
            mqtt_dev_state = power_status.encode()
        else:
            # Lights need color_mode
            if device.supports_temperature:
                mqtt_dev_state["color_mode"] = "color_temp"
            elif device.supports_rgb:
                mqtt_dev_state["color_mode"] = "rgb"
            else:
                mqtt_dev_state["color_mode"] = "brightness"
            mqtt_dev_state = json.dumps(mqtt_dev_state).encode()  # send JSON
        return await self.send_device_status(device, mqtt_dev_state)

    async def update_switch_from_subgroup(self, device: CyncDevice, subgroup_state: int, subgroup_name: str) -> bool:
        """Update a switch device state to match its subgroup state.

        Only updates switches that don't have pending commands (individual commands take precedence).
        Only publishes to MQTT when state actually changes (no redundant updates).

        Args:
            device: The switch device to update
            subgroup_state: The subgroup's confirmed state (0=off, 1=on)
            subgroup_name: Name of the subgroup (for logging)

        Returns:
            True if the state was updated and published, False otherwise
        """
        lp = f"{self.client.lp}update_switch_from_subgroup:"

        # Safety checks
        if not device.is_switch:
            logger.debug(
                "%s Device '%s' (ID: %s) is not a switch, skipping subgroup sync",
                lp,
                device.name,
                device.id,
            )
            return False

        # Update the switch to match subgroup state
        old_state = device.state
        logger.info(
            "%s Syncing switch '%s' (ID: %s) to subgroup '%s' state: %s",
            lp,
            device.name,
            device.id,
            subgroup_name,
            "ON" if subgroup_state else "OFF",
        )

        # Always publish for optimistic feedback on group commands
        # (this function is now only called after explicit group commands, never from aggregation)
        logger.debug(
            "%s Publishing optimistic state update: %s  %s",
            lp,
            "ON" if old_state else "OFF",
            "ON" if subgroup_state else "OFF",
        )
        device.state = subgroup_state

        # Publish state update to MQTT
        power_status = "ON" if subgroup_state else "OFF"
        mqtt_dev_state = power_status.encode()  # Switches use plain ON/OFF payload
        return await self.send_device_status(device, mqtt_dev_state)

    async def sync_group_switches(self, group_id: int, group_state: int, group_name: str) -> int:
        """Sync all switch devices in a group to match the group's state.

        This is called after a group command is executed to ensure switches
        that control the same lights show the correct state in Home Assistant.

        Args:
            group_id: The group ID
            group_state: The group's state (0=off, 1=on)
            group_name: Name of the group (for logging)

        Returns:
            Number of switches synced
        """
        lp = f"{self.client.lp}sync_group_switches:"

        if group_id not in g.ncync_server.groups:
            logger.warning("%s [BUG4-TRACE] Group %s not found in server groups", lp, group_id)
            return 0

        group = g.ncync_server.groups[group_id]
        synced_count = 0

        logger.info(
            "%s Syncing %d switches for group '%s' (ID: %s) to state: %s",
            lp,
            len(group.member_ids),
            group_name,
            group_id,
            "ON" if group_state else "OFF",
        )

        for member_id in group.member_ids:
            if member_id in g.ncync_server.devices:
                device = g.ncync_server.devices[member_id]
                logger.debug(
                    "%s Processing member: id=%d, name='%s', is_switch=%s",
                    lp,
                    member_id,
                    device.name,
                    device.is_switch,
                )
                # Sync switch to group state (will only publish if state actually changed)
                if await self.update_switch_from_subgroup(device, group_state, group_name):
                    synced_count += 1
            else:
                logger.debug(
                    "%s Member ID %d not found in devices",
                    lp,
                    member_id,
                )

        logger.info("%s Synced %s switches for group '%s'", lp, synced_count, group_name)
        return synced_count

    async def sync_group_devices(self, group_id: int, group_state: int, group_name: str) -> int:
        """Sync all devices (switches and bulbs) in a group to match the group's state.

        This is called after a group command is executed to provide immediate optimistic
        feedback for all devices in the group.

        Args:
            group_id: The group ID
            group_state: The group's state (0=off, 1=on)
            group_name: Name of the group (for logging)

        Returns:
            Number of devices synced
        """
        lp = f"{self.client.lp}sync_group_devices:"

        if group_id not in g.ncync_server.groups:
            logger.warning("%s [BUG4-TRACE] Group %s not found in server groups", lp, group_id)
            return 0

        group = g.ncync_server.groups[group_id]
        synced_count = 0

        logger.info(
            "%s Syncing %d devices for group '%s' (ID: %s) to state: %s",
            lp,
            len(group.member_ids),
            group_name,
            group_id,
            "ON" if group_state else "OFF",
        )

        for member_id in group.member_ids:
            if member_id in g.ncync_server.devices:
                device = g.ncync_server.devices[member_id]
                logger.debug(
                    "%s Processing member: id=%d, name='%s', is_switch=%s, is_bulb=%s",
                    lp,
                    member_id,
                    device.name,
                    device.is_switch,
                    not device.is_switch,
                )

                if device.is_switch:
                    # Sync switch to group state
                    if await self.update_switch_from_subgroup(device, group_state, group_name):
                        synced_count += 1
                # Sync bulb/light to group state (optimistic update)
                elif await self.update_device_state(device, group_state):
                    synced_count += 1
            else:
                logger.debug(
                    "%s Member ID %d not found in devices",
                    lp,
                    member_id,
                )

        logger.info("%s Synced %s devices for group '%s'", lp, synced_count, group_name)
        return synced_count

    async def update_brightness(self, device: CyncDevice, bri: int) -> bool:
        """Update the device brightness and publish to MQTT for HASS devices to update.

        NOTE: Device availability is managed by server.parse_status() based on the
        connected_to_mesh byte and offline_count threshold. Do not set device.online here.
        """
        lp = f"{self.client.lp}update_brightness:"
        device.brightness = bri
        state = "ON"
        if bri == 0:
            state = "OFF"

        # For fan entities, publish state separately (ON/OFF only, no brightness in JSON)
        if device.is_fan_controller:
            mqtt_dev_state = {"state": state}
        else:
            # For lights/switches, include brightness
            mqtt_dev_state = {"state": state, "brightness": bri}
            # Add color_mode based on device capabilities
            if device.supports_temperature:
                mqtt_dev_state["color_mode"] = "color_temp"
            elif device.supports_rgb:
                mqtt_dev_state["color_mode"] = "rgb"
            else:
                mqtt_dev_state["color_mode"] = "brightness"

        result = await self.send_device_status(device, json.dumps(mqtt_dev_state).encode())

        # For fan entities, also publish preset mode state
        if device.is_fan_controller and self.client._connected:
            # Publish preset mode state based on brightness (1-100 scale)
            # Map brightness to preset mode
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
                logger.debug(
                    "%s Published fan preset mode '%s' (brightness=%s) for '%s' to %s",
                    lp,
                    preset_mode,
                    bri,
                    device.name,
                    preset_mode_topic,
                )
            except Exception:
                logger.exception("%s Failed to publish fan preset mode for '%s'", lp, device.name)

        return result

    async def update_temperature(self, device: CyncDevice, temp: int) -> bool:
        """Update the device temperature and publish to MQTT for HASS devices to update.

        NOTE: Device availability is managed by server.parse_status() based on the
        connected_to_mesh byte and offline_count threshold. Do not set device.online here.
        """
        if device.supports_temperature:
            mqtt_dev_state = {
                "state": "ON",
                "color_mode": "color_temp",
                "color_temp": self.client.cync2kelvin(temp),
            }
            device.temperature = temp
            device.red = 0
            device.green = 0
            device.blue = 0
            return await self.send_device_status(device, json.dumps(mqtt_dev_state).encode())
        return False

    async def update_rgb(self, device: CyncDevice, rgb: tuple[int, int, int]) -> bool:
        """Update the device RGB and publish to MQTT for HASS devices to update.

        NOTE: Device availability is managed by server.parse_status() based on the
        connected_to_mesh byte and offline_count threshold. Do not set device.online here.
        Intended for callbacks.
        """
        if device.supports_rgb and (
            any(
                [
                    rgb[0] is not None,
                    rgb[1] is not None,
                    rgb[2] is not None,
                ]
            )
        ):
            mqtt_dev_state = {
                "state": "ON",
                "color_mode": "rgb",
                "color": {"r": rgb[0], "g": rgb[1], "b": rgb[2]},
            }
            device.red = rgb[0]
            device.green = rgb[1]
            device.blue = rgb[2]
            device.temperature = 254
            return await self.send_device_status(device, json.dumps(mqtt_dev_state).encode())
        return False

    async def send_device_status(self, device: CyncDevice, state_bytes: bytes) -> bool:
        """Publish device status to MQTT."""
        lp = f"{self.client.lp}send_device_status:"

        timestamp_ms = int(time.time() * 1000)
        caller = "".join(traceback.format_stack()[-3].split("\n")[0:1])

        logger.debug(
            "%s [STATE_UPDATE_SEQ] ts=%dms device=%s state=%s caller=%s",
            lp,
            timestamp_ms,
            device.name if hasattr(device, "name") else device.id,
            state_bytes.decode() if isinstance(state_bytes, bytes) else state_bytes,
            caller,
        )
        if self.client._connected:
            tpc = f"{self.client.topic}/status/{device.hass_id}"
            logger.debug(
                "%s Sending %s for device: '%s' (ID: %s)",
                lp,
                state_bytes,
                device.name,
                device.id,
            )
            try:
                await self.client.client.publish(
                    tpc,
                    state_bytes,
                    qos=0,
                    timeout=3.0,
                )
                # Don't auto-update groups - too noisy
            except aiomqtt.MqttError as mqtt_code_exc:
                logger.warning("%s [MqttError] -> %s", lp, mqtt_code_exc)
                self.client._connected = False
            except asyncio.CancelledError as can_exc:
                logger.debug("%s [Task Cancelled] -> %s", lp, can_exc)
            else:
                return True
        return False

    async def publish_group_state(
        self,
        group,
        state=None,
        brightness=None,
        temperature=None,
        origin: str | None = None,
    ):
        """Publish group state. For subgroups, use only mesh_info or validated aggregation (no optimistic ACK publishes)."""
        if not isinstance(group, CyncGroup):
            return

        if not self.client._connected:
            return

        # Build state dict with only changed values
        group_state = {}

        if state is not None:
            group_state["state"] = "ON" if state == 1 else "OFF"

        if brightness is not None:
            group_state["brightness"] = brightness
            if state is None:  # Brightness command implies ON
                group_state["state"] = "ON" if brightness > 0 else "OFF"

        if temperature is not None:
            group_state["color_temp"] = self.client.cync2kelvin(temperature)
            group_state["color_mode"] = "color_temp"
        elif brightness is not None or state is not None:
            # If no color temp specified, set color_mode based on group capabilities
            if group.supports_temperature:
                group_state["color_mode"] = "color_temp"
            elif group.supports_rgb:
                group_state["color_mode"] = "rgb"
            else:
                group_state["color_mode"] = "brightness"

        if not group_state:
            return

        # annotate origin for visibility
        if origin:
            group_state["origin"] = origin

        tpc = f"{self.client.topic}/status/{group.hass_id}"
        try:
            await self.client.client.publish(
                tpc,
                json.dumps(group_state).encode(),
                qos=0,
                timeout=3.0,
            )
        except Exception as e:
            logger.warning("Failed to publish group state for %s: %s", group.name, e)

    async def parse_device_status(self, device_id: int, device_status: DeviceStatus, *_args, **kwargs) -> bool:
        """Parse device status and publish to MQTT for HASS devices to update. Useful for device status packets that report the complete device state"""
        lp = f"{self.client.lp}parse status:"
        from_pkt = kwargs.get("from_pkt")
        ts_ms = int(time.time() * 1000)
        logger.debug(
            "[PUBLISH_STATE] ts=%dms device_id=%s state=%s source=%s",
            ts_ms,
            device_id,
            "ON" if device_status.state else "OFF",
            from_pkt if from_pkt else "unknown",
        )
        if from_pkt:
            lp = f"{lp}{from_pkt}:"
        if device_id not in g.ncync_server.devices:
            logger.error(
                "%s Device ID %s not found! Device may be disabled in config file or you may need to re-export devices from your Cync account",
                lp,
                device_id,
            )
            return False
        device: CyncDevice = g.ncync_server.devices[device_id]

        # CRITICAL: Skip publishing switch state from mesh packets (0x83 and mesh info from 0x73)
        # Switches are CONTROL OUTPUTS, not status inputs. They should only be updated
        # from explicit group/device commands, not from mesh broadcasts.
        # This prevents the flicker where incoming mesh packets show stale switch state
        # that overwrites our optimistic command updates.
        # Only skip mesh info for switches - trust direct 0x83 packets
        if device.is_switch and from_pkt == "mesh info":
            logger.info(
                "%s Skipping mesh info status update for switch (control output, stale): %s",
                lp,
                device.name,
            )
            return False

        # if device.build_status() == device_status:
        #     # logger.debug("%s Device status unchanged, skipping...", lp)
        #     return
        power_status = "OFF" if device_status.state == 0 else "ON"
        mqtt_dev_state: dict[str, int | str | bytes] = {"state": power_status}

        if device.is_plug:
            mqtt_dev_state = power_status.encode()

        elif device.is_switch:
            # Switches only need plain ON/OFF payload (no JSON)
            mqtt_dev_state = power_status.encode()

        else:
            # Lights get brightness and color_mode
            if device_status.brightness is not None:
                mqtt_dev_state["brightness"] = device_status.brightness

            # Determine and set color_mode
            color_mode_set = False
            if device_status.temperature is not None:
                if device.supports_rgb and (
                    any(
                        [
                            device_status.red is not None,
                            device_status.green is not None,
                            device_status.blue is not None,
                        ]
                    )
                    and device_status.temperature > 100
                ):
                    mqtt_dev_state["color_mode"] = "rgb"
                    mqtt_dev_state["color"] = {
                        "r": device_status.red,
                        "g": device_status.green,
                        "b": device_status.blue,
                    }
                    color_mode_set = True
                elif device.supports_temperature and (0 <= device_status.temperature <= 100):
                    mqtt_dev_state["color_mode"] = "color_temp"
                    mqtt_dev_state["color_temp"] = self.client.cync2kelvin(device_status.temperature)
                    color_mode_set = True

            # If color_mode not set yet, add default based on capabilities
            if not color_mode_set:
                if device.supports_temperature:
                    mqtt_dev_state["color_mode"] = "color_temp"
                elif device.supports_rgb:
                    mqtt_dev_state["color_mode"] = "rgb"
                else:
                    mqtt_dev_state["color_mode"] = "brightness"

            mqtt_dev_state = json.dumps(mqtt_dev_state).encode()

        # Publish device status
        # NOTE: Subgroup state aggregation is now handled in server.parse_status() after device updates
        # (subgroups do NOT report their own state in mesh_info, so aggregation from members is required)
        result = await self.send_device_status(device, mqtt_dev_state)

        # For fan entities, also publish preset mode based on brightness
        if device.is_fan_controller and self.client._connected and device_status.brightness is not None:
            bri = device_status.brightness
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
                logger.debug(
                    "%s FAN PRESET PUBLISHED: '%s' (brightness=%s) for device '%s' (ID=%s) to %s",
                    f"{self.client.lp}parse status:",
                    preset_mode,
                    bri,
                    device.name,
                    device.id,
                    preset_mode_topic,
                )
            except Exception:
                logger.exception(
                    "%s Failed to publish fan preset mode for '%s'",
                    f"{self.client.lp}parse status:",
                    device.name,
                )

        return result
