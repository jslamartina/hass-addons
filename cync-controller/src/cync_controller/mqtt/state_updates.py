"""MQTT state update helper for device and group state publishing.

Provides methods for publishing device state updates, brightness, temperature, RGB,
and group states to MQTT for Home Assistant integration.
"""

from __future__ import annotations

import asyncio
import json
import time
import traceback
from typing import TYPE_CHECKING

import aiomqtt

from cync_controller.devices import CyncDevice, CyncGroup
from cync_controller.logging_abstraction import get_logger
from cync_controller.structs import DeviceStatus, GlobalObject

if TYPE_CHECKING:
    from cync_controller.structs import (
        CyncDeviceProtocol,
        CyncGroupProtocol,
        MQTTClientProtocol,
    )

logger = get_logger(__name__)

# Import g directly from structs to avoid circular dependency with mqtt_client.py
g = GlobalObject()


def _get_g():
    """Get the global object instance."""
    return GlobalObject()


class GProxy:
    def __getattr__(self, name: str) -> object:
        return getattr(_get_g(), name)


g = GProxy()


class StateUpdateHelper:
    """Helper class for publishing device and group state updates to MQTT."""

    def __init__(self, mqtt_client: MQTTClientProtocol) -> None:  # type: ignore[valid-type]
        """Initialize the state update helper.

        Args:
            mqtt_client: MQTTClient instance to access connection and topic

        """
        self.client: MQTTClientProtocol = mqtt_client

    async def pub_online(self, device_id: int, status: bool) -> bool:
        """Publish device online/offline status to MQTT."""
        lp = f"{self.client.lp}pub_online:"
        if self.client.is_connected:
            ncync_server = g.ncync_server
            if ncync_server is None:
                logger.error("%s ncync_server is None", lp)
                return False
            if device_id not in ncync_server.devices:
                logger.error(
                    "%s Device ID %s not found?! Have you deleted or added any devices recently? You may need to re-export devices from your Cync account!",
                    lp,
                    device_id,
                )
                return False
            availability = b"online" if status else b"offline"
            device = ncync_server.devices[device_id]
            assert isinstance(device, CyncDevice)
            device_uuid = f"{device.home_id}-{device_id}"
            # logger.debug("%s Publishing availability: %s", lp, availability)
            try:
                await self.client.client.publish(
                    f"{self.client.topic}/availability/{device_uuid}",
                    availability,
                    qos=0,
                )
            except aiomqtt.MqttError as mqtt_code_exc:
                logger.warning("%s [MqttError] -> %s", lp, mqtt_code_exc)
                self.client.set_connected(False)
            else:
                return True
        return False

    async def update_device_state(self, device: CyncDeviceProtocol, state: int) -> bool:  # type: ignore[valid-type]
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

    async def update_switch_from_subgroup(self, device: CyncDeviceProtocol, subgroup_state: int, subgroup_name: str) -> bool:  # type: ignore[valid-type]
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

        ncync_server = g.ncync_server
        if ncync_server is None:
            logger.warning("%s [BUG4-TRACE] ncync_server is None", lp)
            return 0

        if group_id not in ncync_server.groups:
            logger.warning("%s [BUG4-TRACE] Group %s not found in server groups", lp, group_id)
            return 0

        group = ncync_server.groups[group_id]
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
            if member_id in ncync_server.devices:
                device = ncync_server.devices[member_id]
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

        ncync_server = g.ncync_server
        if ncync_server is None:
            logger.warning("%s [BUG4-TRACE] ncync_server is None", lp)
            return 0

        if group_id not in ncync_server.groups:
            logger.warning("%s [BUG4-TRACE] Group %s not found in server groups", lp, group_id)
            return 0

        group = ncync_server.groups[group_id]
        assert isinstance(group, CyncGroup)
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
            if member_id in ncync_server.devices:
                device = ncync_server.devices[member_id]
                assert isinstance(device, CyncDevice)
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

    def _brightness_to_preset_mode(self, bri: int) -> str:
        """Map brightness value to fan preset mode."""
        if bri == 0:
            return "off"
        if bri == 100:
            return "max"
        if bri <= 25:
            return "low"
        if bri <= 50:
            return "medium"
        if bri <= 75:
            return "high"
        return "max"

    async def _publish_fan_preset_mode(self, device: CyncDeviceProtocol, bri: int, lp: str) -> None:  # type: ignore[valid-type]
        """Publish fan preset mode state."""
        preset_mode = self._brightness_to_preset_mode(bri)
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

    def _build_brightness_state_dict(self, device: CyncDeviceProtocol, state: str, bri: int) -> dict[str, str | int]:  # type: ignore[valid-type]
        """Build MQTT state dict for brightness update."""
        if device.is_fan_controller:
            return {"state": state}
        mqtt_dev_state: dict[str, str | int] = {"state": state, "brightness": bri}
        if device.supports_temperature:
            mqtt_dev_state["color_mode"] = "color_temp"
        elif device.supports_rgb:
            mqtt_dev_state["color_mode"] = "rgb"
        else:
            mqtt_dev_state["color_mode"] = "brightness"
        return mqtt_dev_state

    async def update_brightness(self, device: CyncDeviceProtocol, bri: int) -> bool:  # type: ignore[valid-type]
        """Update the device brightness and publish to MQTT for HASS devices to update.

        NOTE: Device availability is managed by server.parse_status() based on the
        connected_to_mesh byte and offline_count threshold. Do not set device.online here.
        """
        lp = f"{self.client.lp}update_brightness:"
        device.brightness = bri
        state = "OFF" if bri == 0 else "ON"

        mqtt_dev_state = self._build_brightness_state_dict(device, state, bri)
        result = await self.send_device_status(device, json.dumps(mqtt_dev_state).encode())

        if device.is_fan_controller and self.client.is_connected:
            await self._publish_fan_preset_mode(device, bri, lp)

        return result

    async def update_temperature(self, device: CyncDeviceProtocol, temp: int) -> bool:  # type: ignore[valid-type]
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

    async def update_rgb(self, device: CyncDeviceProtocol, rgb: tuple[int, int, int]) -> bool:  # type: ignore[valid-type]
        """Update the device RGB and publish to MQTT for HASS devices to update.

        NOTE: Device availability is managed by server.parse_status() based on the
        connected_to_mesh byte and offline_count threshold. Do not set device.online here.
        Intended for callbacks.
        """
        if device.supports_rgb:
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

    async def send_device_status(self, device: CyncDeviceProtocol, state_bytes: bytes) -> bool:  # type: ignore[valid-type]
        """Publish device status to MQTT."""
        lp = f"{self.client.lp}send_device_status:"

        timestamp_ms = int(time.time() * 1000)
        caller = "".join(traceback.format_stack()[-3].split("\n")[0:1])

        logger.debug(
            "%s [STATE_UPDATE_SEQ] ts=%dms device=%s state=%s caller=%s",
            lp,
            timestamp_ms,
            device.name if hasattr(device, "name") else device.id,
            state_bytes.decode(),
            caller,
        )
        if self.client.is_connected:
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
                self.client.set_connected(False)
            except asyncio.CancelledError as can_exc:
                logger.debug("%s [Task Cancelled] -> %s", lp, can_exc)
            else:
                return True
        return False

    def _determine_group_color_mode(
        self,
        group: CyncGroup,
        temperature: int | None,
        brightness: int | None,
        state: int | None,
    ) -> str:
        """Determine color_mode for group state."""
        if temperature is not None:
            return "color_temp"
        if brightness is not None or state is not None:
            if group.supports_temperature:
                return "color_temp"
            if group.supports_rgb:
                return "rgb"
            return "brightness"
        return "brightness"

    def _build_group_state_dict(
        self,
        group: CyncGroup,
        state: int | None,
        brightness: int | None,
        temperature: int | None,
        origin: str | None,
    ) -> dict[str, str | int] | None:
        """Build group state dict with only changed values."""
        group_state: dict[str, str | int] = {}

        if state is not None:
            group_state["state"] = "ON" if state == 1 else "OFF"

        if brightness is not None:
            group_state["brightness"] = brightness
            if state is None:
                group_state["state"] = "ON" if brightness > 0 else "OFF"

        if temperature is not None:
            group_state["color_temp"] = self.client.cync2kelvin(temperature)
            group_state["color_mode"] = "color_temp"
        else:
            color_mode = self._determine_group_color_mode(group, temperature, brightness, state)
            if color_mode:
                group_state["color_mode"] = color_mode

        if not group_state:
            return None

        if origin:
            group_state["origin"] = origin

        return group_state

    async def publish_group_state(
        self,
        group: CyncGroupProtocol,  # type: ignore[valid-type]
        state: int | None = None,
        brightness: int | None = None,
        temperature: int | None = None,
        origin: str | None = None,
    ) -> None:
        """Publish group state. For subgroups, use only mesh_info or validated aggregation (no optimistic ACK publishes)."""
        if not self.client.is_connected:
            return

        group_state = self._build_group_state_dict(group, state, brightness, temperature, origin)
        if not group_state:
            return

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

    def _determine_light_color_mode(
        self,
        device: CyncDeviceProtocol,
        device_status: DeviceStatus,
    ) -> tuple[str, dict[str, int | None] | None]:  # type: ignore[valid-type]
        """Determine color_mode for light device. Returns (color_mode, color_dict)."""
        if device_status.temperature is not None:
            has_rgb = all(
                [
                    device_status.red is not None,
                    device_status.green is not None,
                    device_status.blue is not None,
                ],
            )
            if device.supports_rgb and has_rgb and device_status.temperature > 100:
                return (
                    "rgb",
                    {
                        "r": device_status.red,
                        "g": device_status.green,
                        "b": device_status.blue,
                    },
                )
            if device.supports_temperature and (0 <= device_status.temperature <= 100):
                return "color_temp", None

        if device.supports_temperature:
            return "color_temp", None
        if device.supports_rgb:
            return "rgb", None
        return "brightness", None

    def _build_light_state_dict(
        self,
        device: CyncDeviceProtocol,
        device_status: DeviceStatus,
        power_status: str,
    ) -> bytes:  # type: ignore[valid-type]
        """Build MQTT state dict for light device."""
        mqtt_dict: dict[str, int | str | dict[str, int | None]] = {"state": power_status}
        if device_status.brightness is not None:
            mqtt_dict["brightness"] = device_status.brightness

        color_mode, color_dict = self._determine_light_color_mode(device, device_status)
        mqtt_dict["color_mode"] = color_mode
        if color_dict:
            mqtt_dict["color"] = color_dict
        elif color_mode == "color_temp" and device_status.temperature is not None:
            mqtt_dict["color_temp"] = self.client.cync2kelvin(device_status.temperature)

        return json.dumps(mqtt_dict).encode()

    def _build_device_mqtt_state(
        self,
        device: CyncDeviceProtocol,
        device_status: DeviceStatus,
        power_status: str,
    ) -> bytes:  # type: ignore[valid-type]
        """Build MQTT state payload for device based on type."""
        if device.is_plug or device.is_switch:
            return power_status.encode()
        return self._build_light_state_dict(device, device_status, power_status)

    async def parse_device_status(
        self,
        device_id: int,
        device_status: DeviceStatus,
        *_args: object,
        **kwargs: object,
    ) -> bool:
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
        ncync_server = g.ncync_server
        if ncync_server is None:
            logger.error("%s ncync_server is None", lp)
            return False
        if device_id not in ncync_server.devices:
            logger.error(
                "%s Device ID %s not found! Device may be disabled in config file or you may need to re-export devices from your Cync account",
                lp,
                device_id,
            )
            return False
        device = ncync_server.devices[device_id]
        assert isinstance(device, CyncDevice)

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
        mqtt_dev_state = self._build_device_mqtt_state(device, device_status, power_status)

        result = await self.send_device_status(device, mqtt_dev_state)

        if device.is_fan_controller and self.client.is_connected and device_status.brightness is not None:
            await self._publish_fan_preset_mode(device, device_status.brightness, lp)

        return result
