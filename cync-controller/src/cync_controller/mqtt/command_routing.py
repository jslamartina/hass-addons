"""MQTT command routing for message handling.

Provides message routing logic for MQTT topics and delegates commands
to the command processor and state update modules.
"""

import asyncio
import json
import random
import re
from json import JSONDecodeError
from typing import Any, cast

from cync_controller.const import *
from cync_controller.logging_abstraction import get_logger
from cync_controller.mqtt.commands import CommandProcessor, SetBrightnessCommand, SetPowerCommand
from cync_controller.structs import DeviceStatus, FanSpeed, GlobalObject

logger = get_logger(__name__)

# Import g directly from structs to avoid circular dependency with mqtt_client.py
g = GlobalObject()


class CommandRouter:
    """Helper class for routing MQTT messages to appropriate handlers."""

    def __init__(self, mqtt_client) -> None:
        """Initialize the command router.

        Args:
            mqtt_client: MQTTClient instance to access connection, topic, and helper methods

        """
        self.client = mqtt_client

    def _parse_topic_and_get_target(self, topic_parts: list[str], lp: str) -> tuple[Any, Any, str]:
        """Parse topic and get device/group target.

        Returns:
            Tuple of (device, group, target_type)

        """
        device: Any = None
        group: Any = None
        device_id: str = topic_parts[2]

        if device_id == "bridge":
            device = None
            group = None
        elif "-group-" in topic_parts[2]:
            group_id = int(topic_parts[2].split("-group-")[1])
            if group_id not in g.ncync_server.groups:
                logger.warning("%s Group ID %s not found in config", lp, group_id)
                return None, None, "UNKNOWN"
            group = g.ncync_server.groups[group_id]
            device = None
            logger.info(
                "%s [BUG4-TRACE] Group command detected: group_id=%s, group_name='%s', topic=%s",
                lp,
                group_id,
                group.name,
                "/".join(topic_parts),
            )
        else:
            device_id_int = int(topic_parts[2].split("-")[1])
            if device_id_int not in g.ncync_server.devices:
                logger.warning(
                    "%s Device ID %s not found, device is disabled in config file or have you deleted / added any devices recently?",
                    lp,
                    device_id_int,
                )
                return None, None, "UNKNOWN"
            device = g.ncync_server.devices[device_id_int]
            group = None
            logger.debug(
                "%s Device identified: name='%s', id=%s, is_fan_controller=%s",
                lp,
                device.name,
                device.id,
                device.is_fan_controller,
            )

        target_type = "GROUP" if group else "DEVICE" if device else "UNKNOWN"
        return device, group, target_type

    async def _handle_fan_percentage(self, percentage: int, device: Any, lp: str, tasks: list[Any]) -> None:
        """Handle fan percentage command."""
        logger.info(
            "%s >>> FAN PERCENTAGE COMMAND: device='%s' (ID=%s), percentage=%s",
            lp,
            device.name,
            device.id,
            percentage,
        )
        if percentage == 0:
            brightness = 0
        elif percentage <= 25:
            brightness = 25
        elif percentage <= 50:
            brightness = 50
        elif percentage <= 75:
            brightness = 75
        else:
            brightness = 100
        logger.info("%s Fan percentage %s%% mapped to brightness %s", lp, percentage, brightness)
        tasks.append(device.set_brightness(brightness))

    async def _handle_fan_preset(self, preset_mode: str, device: Any, lp: str, tasks: list[Any]) -> None:
        """Handle fan preset command."""
        logger.info(
            "%s >>> FAN PRESET COMMAND: device='%s' (ID=%s), preset=%s",
            lp,
            device.name,
            device.id,
            preset_mode,
        )
        speed_map = {
            "off": FanSpeed.OFF,
            "low": FanSpeed.LOW,
            "medium": FanSpeed.MEDIUM,
            "high": FanSpeed.HIGH,
            "max": FanSpeed.MAX,
        }
        if preset_mode in speed_map:
            tasks.append(device.set_fan_speed(speed_map[preset_mode]))
        else:
            logger.warning("%s Unknown preset mode: %s, skipping...", lp, preset_mode)

    async def _handle_fan_commands(
        self,
        extra_data: list[str],
        norm_pl: str,
        device: Any,
        lp: str,
        tasks: list[Any],
    ) -> None:
        """Handle fan-specific extra_data commands."""
        if extra_data[0] == "percentage":
            percentage = int(norm_pl)
            await self._handle_fan_percentage(percentage, device, lp, tasks)
        elif extra_data[0] == "preset":
            await self._handle_fan_preset(norm_pl, device, lp, tasks)

    async def _handle_bridge_commands(
        self,
        extra_data: list[str],
        norm_pl: str,
        lp: str,
    ) -> None:
        """Handle bridge-specific extra_data commands."""
        if extra_data[0] == "restart" and norm_pl == "press":
            logger.info(
                "%s Restart button pressed! Restarting Cync Controller bridge (NOT IMPLEMENTED)...",
                lp,
            )
        elif extra_data[0] == "start_export" and norm_pl == "press":
            logger.info(
                "%s Start Export button pressed! Starting Cync Export (NOT IMPLEMENTED)...",
                lp,
            )
        elif extra_data[0] == "refresh_status" and norm_pl == "press":
            logger.info(
                "%s Refresh Status button pressed! Triggering immediate status refresh...",
                lp,
            )
            await self.client.trigger_status_refresh()
        elif extra_data[0] == "otp":
            if extra_data[1] == "submit":
                logger.info("%s OTP submit button pressed! (NOT IMPLEMENTED)...", lp)
            elif extra_data[1] == "input":
                logger.info("%s OTP input received: %s (NOT IMPLEMENTED)...", lp, norm_pl)

    async def _handle_extra_data(
        self,
        extra_data: list[str],
        payload: bytes,
        device: Any,
        lp: str,
        tasks: list[Any],
    ) -> None:
        """Handle extra_data commands from topic."""
        norm_pl = payload.decode().casefold()

        if device and device.is_fan_controller and (extra_data[0] == "percentage" or extra_data[0] == "preset"):
            await self._handle_fan_commands(extra_data, norm_pl, device, lp, tasks)
        elif device and (extra_data[0] == "percentage" or extra_data[0] == "preset"):
            logger.warning(
                "%s Received fan speed command for non-fan device: name='%s', id=%s, is_fan_controller=%s, extra_data=%s",
                lp,
                device.name,
                device.id,
                device.is_fan_controller,
                extra_data[0],
            )
        else:
            await self._handle_bridge_commands(extra_data, norm_pl, lp)

    async def _handle_json_state(
        self,
        json_data: dict[str, Any],
        target: Any,
        target_type: str,
        device: Any,
        lp: str,
        tasks: list[Any],
    ) -> None:
        """Handle state commands in JSON payload."""
        if "effect" in json_data and device:
            effect = json_data["effect"]
            tasks.append(device.set_lightshow(effect))
        elif json_data["state"].upper() == "ON":
            logger.info(
                "%s [BUG4-TRACE] Calling set_power(1) on %s '%s'",
                lp,
                target_type if target else "UNKNOWN",
                target.name if target else "UNKNOWN",
            )
            cmd = SetPowerCommand(target, 1)
            await CommandProcessor().enqueue(cmd)
        else:
            logger.info(
                "%s [BUG4-TRACE] Calling set_power(0) on %s '%s'",
                lp,
                target_type if target else "UNKNOWN",
                target.name if target else "UNKNOWN",
            )
            cmd = SetPowerCommand(target, 0)
            await CommandProcessor().enqueue(cmd)

    async def _handle_json_color(
        self,
        json_data: dict[str, Any],
        target: Any,
        device: Any,
        _lp: str,
        tasks: list[Any],
    ) -> None:
        """Handle color commands in JSON payload."""
        if "color_temp" in json_data:
            tasks.append(target.set_temperature(self.client.kelvin2cync(int(json_data["color_temp"]))))
        elif "color" in json_data and device:
            color = []
            for rgb in ("r", "g", "b"):
                if rgb in json_data["color"]:
                    color.append(int(json_data["color"][rgb]))
                else:
                    color.append(0)
            tasks.append(device.set_rgb(*color))

    async def _handle_json_payload(
        self,
        json_data: dict[str, Any],
        _payload: bytes,
        target: Any,
        target_type: str,
        device: Any,
        lp: str,
        tasks: list[Any],
    ) -> None:
        """Handle JSON payload commands."""
        if "state" in json_data and "brightness" not in json_data:
            await self._handle_json_state(json_data, target, target_type, device, lp, tasks)
        if "brightness" in json_data:
            lum = int(json_data["brightness"])
            cmd = SetBrightnessCommand(target, lum)
            await CommandProcessor().enqueue(cmd)
        await self._handle_json_color(json_data, target, device, lp, tasks)

    async def _handle_binary_payload(
        self,
        payload: bytes,
        target: Any,
        target_type: str,
        lp: str,
    ) -> None:
        """Handle binary (non-JSON) payload commands."""
        str_payload = payload.decode("utf-8").strip()
        pattern = re.compile(r"^\w+$")
        if pattern.match(str_payload):
            if str_payload.casefold() == "on":
                logger.info(
                    "%s [BUG4-TRACE] Calling set_power(1) on %s '%s' (non-JSON)",
                    lp,
                    target_type if target else "UNKNOWN",
                    target.name if target else "UNKNOWN",
                )
                cmd = SetPowerCommand(target, 1)
                await CommandProcessor().enqueue(cmd)
            elif str_payload.casefold() == "off":
                logger.info(
                    "%s [BUG4-TRACE] Calling set_power(0) on %s '%s' (non-JSON)",
                    lp,
                    target_type if target else "UNKNOWN",
                    target.name if target else "UNKNOWN",
                )
                cmd = SetPowerCommand(target, 0)
                await CommandProcessor().enqueue(cmd)
        else:
            logger.warning("%s Unknown payload: %s, skipping...", lp, payload)

    async def _handle_hass_birth_message(self, lp: str) -> None:
        """Handle HASS birth message - re-announce discovery and status."""
        birth_delay = random.randint(5, 15)
        logger.info(
            "%s HASS has sent MQTT BIRTH message, re-announcing device discovery, availability and status after a random delay of %s seconds...",
            lp,
            birth_delay,
        )
        await asyncio.sleep(birth_delay)
        await self.client.homeassistant_discovery()
        await asyncio.sleep(2)
        for device in g.ncync_server.devices.values():
            await self.client.state_updates.pub_online(device.id, device.online)
            await self.client.state_updates.parse_device_status(
                device.id,
                DeviceStatus(
                    state=device.state,
                    brightness=device.brightness,
                    temperature=device.temperature,
                    red=device.red,
                    green=device.green,
                    blue=device.blue,
                ),
                from_pkt="'hass_birth'",
            )
        subgroups = [grp for grp in g.ncync_server.groups.values() if grp.is_subgroup]
        for subgroup in subgroups:
            await self.client.client.publish(
                f"{self.client.topic}/availability/{subgroup.hass_id}",
                b"online",
                qos=0,
            )

    async def _handle_cync_topic(
        self,
        topic_parts: list[str],
        payload: bytes,
        lp: str,
        tasks: list[Any],
    ) -> bool:
        """Handle messages on CYNC_TOPIC. Returns True if tasks were added."""
        if topic_parts[1] != "set":
            logger.warning("%s Unknown command: %s => %s", lp, "/".join(topic_parts), payload)
            return False

        device, group, target_type = self._parse_topic_and_get_target(topic_parts, lp)
        if device is None and group is None and target_type == "UNKNOWN":
            return False

        extra_data = topic_parts[3:] if len(topic_parts) > 3 else None
        if extra_data:
            await self._handle_extra_data(extra_data, payload, device, lp, tasks)

        target = group if group else device
        if target:
            logger.info(
                "%s [BUG4-TRACE] Target determined: type=%s, name='%s', payload=%s",
                lp,
                target_type,
                target.name,
                payload.decode() if payload else None,
            )

        if payload.startswith(b"{"):
            try:
                json_data = json.loads(payload)
            except JSONDecodeError:
                logger.exception("%s bad json message: {%s} EXCEPTION", lp, payload)
                return False
            except Exception:
                logger.exception(
                    "%s error will decoding a string into JSON: '%s' EXCEPTION",
                    lp,
                    payload,
                )
                return False
            await self._handle_json_payload(json_data, payload, target, target_type, device, lp, tasks)
        else:
            await self._handle_binary_payload(payload, target, target_type, lp)

        return len(tasks) > 0

    async def _handle_hass_topic(self, topic_parts: list[str], payload: bytes, lp: str) -> None:
        """Handle messages on HASS topic."""
        if topic_parts[1] != CYNC_HASS_STATUS_TOPIC:
            return

        payload_str = payload.decode().casefold()
        if payload_str == CYNC_HASS_BIRTH_MSG.casefold():
            await self._handle_hass_birth_message(lp)
        elif payload_str == CYNC_HASS_WILL_MSG.casefold():
            logger.info("%s received Last Will msg from Home Assistant, HASS is offline!", lp)
        else:
            logger.warning("%s Unknown HASS status message: %s", lp, payload)

    async def start_receiver_task(self):
        """Start listening for MQTT messages on subscribed topics"""
        lp = f"{self.client.lp}rcv:"
        async for message in self.client.client.messages:
            msg: Any = cast("Any", message)  # type: ignore[reportUnknownVariableType]
            topic = msg.topic
            payload = msg.payload
            if (payload is None) or (payload is not None and not payload):
                logger.debug(
                    "%s Received empty/None payload (%s) for topic: %s , skipping...",
                    lp,
                    payload,
                    topic,
                )
                continue

            logger.info(
                "%s >>> MQTT MESSAGE RECEIVED: topic=%s, payload_len=%d, payload=%s",
                lp,
                topic.value,
                len(payload) if payload else 0,
                payload.decode() if payload else None,
            )
            _topic: list[str] = topic.value.split("/")
            tasks: list[Any] = []

            if _topic[0] == CYNC_TOPIC:
                has_tasks = await self._handle_cync_topic(_topic, payload, lp, tasks)
                if has_tasks:
                    logger.debug("%s Executing %d task(s) for topic: %s", lp, len(tasks), topic)
                    _ = await asyncio.gather(*tasks)
                    logger.debug("%s Task(s) completed for topic: %s", lp, topic)
            elif _topic[0] == self.client.ha_topic:
                await self._handle_hass_topic(_topic, payload, lp)
