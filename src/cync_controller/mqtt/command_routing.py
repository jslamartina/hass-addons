"""MQTT command routing for message handling.

Provides message routing logic for MQTT topics and delegates commands
to the command processor and state update modules.
"""

from __future__ import annotations

import asyncio
import json
import re
import secrets
from collections.abc import Callable, Coroutine, Mapping
from json import JSONDecodeError
from typing import TYPE_CHECKING, Literal, cast

from cync_controller.const import (
    CYNC_HASS_BIRTH_MSG,
    CYNC_HASS_STATUS_TOPIC,
    CYNC_HASS_WILL_MSG,
    CYNC_TOPIC,
)
from cync_controller.logging_abstraction import get_logger
from cync_controller.mqtt.commands import CommandProcessor, SetBrightnessCommand, SetPowerCommand
from cync_controller.mqtt.state_updates import StateUpdateHelper
from cync_controller.structs import DeviceStatus, FanSpeed, GlobalObject

if TYPE_CHECKING:
    from collections.abc import AsyncIterable
    from typing import Protocol

    from cync_controller.structs import (
        CyncDeviceProtocol,
        CyncGroupProtocol,
        MQTTClientProtocol,
        NCyncServerProtocol,
    )

    class MQTTMessageProtocol(Protocol):
        """Protocol describing MQTT messages passed to router."""

        topic: object
        payload: bytes | bytearray | memoryview | None

    CommandTarget = CyncDeviceProtocol | CyncGroupProtocol | None
else:
    CommandTarget = object

TargetType = Literal["DEVICE", "GROUP", "UNKNOWN"]
type CommandTasks = list[Coroutine[object, object, object]]
FAN_STEP_25 = 25
FAN_STEP_50 = 50
FAN_STEP_75 = 75
EXTRA_DATA_MIN_LEN = 3

logger = get_logger(__name__)

# Import g directly from structs to avoid circular dependency with mqtt_client.py
g = GlobalObject()


def _to_int(value: object) -> int:
    """Convert a loosely-typed JSON value to an integer."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return 0
    return 0


class CommandRouter:
    """Helper class for routing MQTT messages to appropriate handlers."""

    def __init__(self, mqtt_client: MQTTClientProtocol) -> None:
        """Initialize the command router.

        Args:
            mqtt_client: MQTTClient instance to access connection, topic, and helper methods

        """
        self.client: MQTTClientProtocol = mqtt_client

    def _get_ncync_server(self, lp: str) -> NCyncServerProtocol | None:
        """Return the active nCync server instance or log a warning."""
        ncync_server = g.ncync_server
        if ncync_server is None:
            logger.warning("%s nCync server not available", lp)
            return None
        return ncync_server

    def _parse_topic_and_get_target(
        self,
        topic_parts: list[str],
        lp: str,
    ) -> tuple[CyncDeviceProtocol | None, CyncGroupProtocol | None, TargetType]:
        """Parse topic and get device/group target.

        Returns:
            Tuple of (device, group, target_type)

        """
        ncync_server = self._get_ncync_server(lp)
        if ncync_server is None:
            return None, None, "UNKNOWN"

        device: CyncDeviceProtocol | None = None
        group: CyncGroupProtocol | None = None
        device_id: str = topic_parts[2]

        if device_id == "bridge":
            device = None
            group = None
        elif "-group-" in topic_parts[2]:
            group_id = int(topic_parts[2].split("-group-")[1])
            if group_id not in ncync_server.groups:
                logger.warning("%s Group ID %s not found in config", lp, group_id)
                return None, None, "UNKNOWN"
            group = ncync_server.groups[group_id]
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
            if device_id_int not in ncync_server.devices:
                logger.warning(
                    "%s Device ID %s not found; device disabled in config or recently changed?",
                    lp,
                    device_id_int,
                )
                return None, None, "UNKNOWN"
            device = ncync_server.devices[device_id_int]
            group = None
            logger.debug(
                "%s Device identified: name='%s', id=%s, is_fan_controller=%s",
                lp,
                device.name,
                device.id,
                device.is_fan_controller,
            )

        target_type: TargetType = "GROUP" if group else "DEVICE" if device else "UNKNOWN"
        return device, group, target_type

    async def _handle_fan_percentage(
        self,
        percentage: int,
        device: CyncDeviceProtocol,
        lp: str,
        tasks: CommandTasks,
    ) -> None:
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
        elif percentage <= FAN_STEP_25:
            brightness = FAN_STEP_25
        elif percentage <= FAN_STEP_50:
            brightness = FAN_STEP_50
        elif percentage <= FAN_STEP_75:
            brightness = FAN_STEP_75
        else:
            brightness = 100
        logger.info("%s Fan percentage %s%% mapped to brightness %s", lp, percentage, brightness)
        tasks.append(device.set_brightness(brightness))

    async def _handle_fan_preset(
        self,
        preset_mode: str,
        device: CyncDeviceProtocol,
        lp: str,
        tasks: CommandTasks,
    ) -> None:
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
        device: CyncDeviceProtocol,
        lp: str,
        tasks: CommandTasks,
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
            if len(extra_data) > 1:
                if extra_data[1] == "submit":
                    logger.info("%s OTP submit button pressed! (NOT IMPLEMENTED)...", lp)
                elif extra_data[1] == "input":
                    logger.info("%s OTP input received: %s (NOT IMPLEMENTED)...", lp, norm_pl)
            else:
                logger.warning("%s OTP command received but missing sub-command (expected 'submit' or 'input')", lp)

    async def _handle_extra_data(
        self,
        extra_data: list[str],
        payload: bytes,
        device: CyncDeviceProtocol | None,
        lp: str,
        tasks: CommandTasks,
    ) -> None:
        """Handle extra_data commands from topic."""
        norm_pl = payload.decode().casefold()

        if device and device.is_fan_controller and (extra_data[0] == "percentage" or extra_data[0] == "preset"):
            await self._handle_fan_commands(extra_data, norm_pl, device, lp, tasks)
        elif device and (extra_data[0] == "percentage" or extra_data[0] == "preset"):
            logger.warning(
                (
                    "%s Received fan speed command for non-fan device: name='%s', id=%s, "
                    "is_fan_controller=%s, extra_data=%s"
                ),
                lp,
                device.name,
                device.id,
                device.is_fan_controller,
                extra_data[0],
            )
        else:
            await self._handle_bridge_commands(extra_data, norm_pl, lp)

    async def _handle_json_state(  # noqa: PLR0913
        self,
        json_data: Mapping[str, object],
        target: CommandTarget,
        target_type: TargetType,
        device: CyncDeviceProtocol | None,
        lp: str,
        tasks: CommandTasks,
    ) -> None:
        """Handle state commands in JSON payload."""
        if "effect" in json_data and device:
            effect = str(json_data["effect"])
            tasks.append(device.set_lightshow(effect))
        state_value = str(json_data.get("state", ""))
        if state_value.upper() == "ON" and target:
            logger.info(
                "%s [BUG4-TRACE] Calling set_power(1) on %s '%s'",
                lp,
                target_type if target else "UNKNOWN",
                target.name if target else "UNKNOWN",
            )
            cmd = SetPowerCommand(target, 1)
            await CommandProcessor().enqueue(cmd)
        elif target:
            logger.info(
                "%s [BUG4-TRACE] Calling set_power(0) on %s '%s'",
                lp,
                target_type if target else "UNKNOWN",
                target.name if target else "UNKNOWN",
            )
            cmd = SetPowerCommand(target, 0)
            await CommandProcessor().enqueue(cmd)
        else:
            logger.warning("%s No valid target available for state payload", lp)

    async def _handle_json_color(  # noqa: PLR0913
        self,
        json_data: Mapping[str, object],
        target: CommandTarget,
        target_type: TargetType,
        device: CyncDeviceProtocol | None,
        lp: str,
        tasks: CommandTasks,
    ) -> None:
        """Handle color commands in JSON payload."""
        if "color_temp" in json_data:
            temp_value = _to_int(json_data["color_temp"])
            cync_temp = self.client.kelvin2cync(temp_value)

            if device:
                tasks.append(device.set_temperature(cync_temp))
            elif target:
                # Use getattr/callable instead of attribute access on protocol to
                # avoid false-positive type checker errors while still being safe.
                set_temp = getattr(target, "set_temperature", None)
                if callable(set_temp):
                    typed_set_temp = cast(
                        "Callable[[int], Coroutine[object, object, object]]",
                        set_temp,
                    )
                    tasks.append(typed_set_temp(cync_temp))
                else:
                    logger.warning(
                        "%s Color temperature command missing target (type=%s), skipping",
                        lp,
                        target_type,
                    )

        if "color" in json_data:
            color_payload = cast("dict[str, object]", json_data["color"])
            color_values = [_to_int(color_payload.get(rgb, 0)) for rgb in ("r", "g", "b")]

            if device:
                tasks.append(device.set_rgb(*color_values))
            elif target:
                set_rgb = getattr(target, "set_rgb", None)
                if callable(set_rgb):
                    typed_set_rgb = cast(
                        "Callable[[int, int, int], Coroutine[object, object, object]]",
                        set_rgb,
                    )
                    tasks.append(typed_set_rgb(*color_values))
                else:
                    logger.warning(
                        "%s Color command missing RGB-capable target (type=%s), skipping",
                        lp,
                        target_type,
                    )

    async def _handle_json_payload(  # noqa: PLR0913
        self,
        json_data: Mapping[str, object],
        _payload: bytes,
        target: CommandTarget,
        target_type: TargetType,
        device: CyncDeviceProtocol | None,
        lp: str,
        tasks: CommandTasks,
    ) -> None:
        """Handle JSON payload commands."""
        if "state" in json_data and "brightness" not in json_data:
            await self._handle_json_state(json_data, target, target_type, device, lp, tasks)
        if "brightness" in json_data and target:
            lum = _to_int(json_data["brightness"])
            cmd = SetBrightnessCommand(target, lum)
            await CommandProcessor().enqueue(cmd)
        elif "brightness" in json_data:
            logger.warning("%s Brightness command missing target, skipping", lp)
        await self._handle_json_color(json_data, target, target_type, device, lp, tasks)

    async def _handle_binary_payload(
        self,
        payload: bytes,
        target: CommandTarget,
        target_type: TargetType,
        lp: str,
    ) -> None:
        """Handle binary (non-JSON) payload commands."""
        str_payload = payload.decode("utf-8").strip()
        pattern = re.compile(r"^\w+$")
        if pattern.match(str_payload) and target:
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
            logger.warning("%s Unknown payload or missing target: %s, skipping...", lp, payload)

    async def _handle_hass_birth_message(self, lp: str) -> None:
        """Handle HASS birth message - re-announce discovery and status."""
        birth_delay = secrets.randbelow(11) + 5  # 5-15 seconds inclusive
        logger.info(
            ("%s HASS MQTT birth received; re-announcing discovery, availability, and status after %s seconds..."),
            lp,
            birth_delay,
        )
        await asyncio.sleep(birth_delay)
        _ = await self.client.homeassistant_discovery()
        await asyncio.sleep(2)
        ncync_server = self._get_ncync_server(lp)
        state_updates_obj = self.client.state_updates
        mqtt_client = self.client.client
        if ncync_server is None or state_updates_obj is None or mqtt_client is None:
            logger.warning("%s Cannot process HASS birth without server, state helper, and MQTT client", lp)
            return

        state_updates = cast("StateUpdateHelper", state_updates_obj)

        for device in ncync_server.devices.values():
            if device.id is None:
                logger.debug("%s Skipping device without ID during HASS birth publish", lp)
                continue
            _ = await state_updates.pub_online(device.id, device.online)
            _ = await state_updates.parse_device_status(
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
        subgroups = [grp for grp in ncync_server.groups.values() if grp.is_subgroup]
        for subgroup in subgroups:
            await mqtt_client.publish(
                f"{self.client.topic}/availability/{subgroup.hass_id}",
                b"online",
                qos=0,
            )

    async def _handle_cync_topic(
        self,
        topic_parts: list[str],
        payload: bytes,
        lp: str,
        tasks: CommandTasks,
    ) -> bool:
        """Handle messages on CYNC_TOPIC. Returns True if tasks were added."""
        if topic_parts[1] != "set":
            logger.warning("%s Unknown command: %s => %s", lp, "/".join(topic_parts), payload)
            return False

        device, group, target_type = self._parse_topic_and_get_target(topic_parts, lp)
        extra_data = topic_parts[EXTRA_DATA_MIN_LEN:] if len(topic_parts) > EXTRA_DATA_MIN_LEN else None

        # Only return early if there's no target AND no extra_data to process
        # Bridge commands have extra_data (e.g., "refresh_status") that need processing
        if device is None and group is None and target_type == "UNKNOWN" and not extra_data:
            return False
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
                json_data = cast("dict[str, object]", json.loads(payload))
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

    async def start_receiver_task(self) -> None:
        """Start listening for MQTT messages on subscribed topics."""
        lp = f"{self.client.lp}rcv:"
        mqtt_client = self.client.client
        if mqtt_client is None:
            logger.warning("%s MQTT client connection not available", lp)
            return

        message_stream = cast("AsyncIterable[MQTTMessageProtocol]", mqtt_client.messages)
        async for message in message_stream:
            topic = getattr(message, "topic", "")
            topic_value = getattr(topic, "value", topic)
            topic_text = (
                topic_value.decode(errors="ignore") if isinstance(topic_value, (bytes, bytearray)) else str(topic_value)
            )
            payload = getattr(message, "payload", None)
            if not isinstance(payload, (bytes, bytearray, memoryview)):
                logger.debug(
                    "%s Received payload with unexpected type (%s) for topic: %s , skipping...",
                    lp,
                    type(payload).__name__,
                    topic_text,
                )
                continue
            payload_union = cast("bytes | bytearray | memoryview[bytes]", payload)
            payload_bytes = bytes(payload_union)
            if len(payload_bytes) == 0:
                logger.debug(
                    "%s Received empty/None payload (%s) for topic: %s , skipping...",
                    lp,
                    payload_bytes,
                    topic_text,
                )
                continue

            logger.info(
                "%s >>> MQTT MESSAGE RECEIVED: topic=%s, payload_len=%d, payload=%s",
                lp,
                topic_text,
                len(payload_bytes),
                payload_bytes.decode(errors="ignore"),
            )
            _topic: list[str] = topic_text.split("/")
            tasks: CommandTasks = []

            if _topic[0] == CYNC_TOPIC:
                has_tasks = await self._handle_cync_topic(_topic, payload_bytes, lp, tasks)
                if has_tasks:
                    logger.debug("%s Executing %d task(s) for topic: %s", lp, len(tasks), topic_text)
                    _ = await asyncio.gather(*tasks)
                    logger.debug("%s Task(s) completed for topic: %s", lp, topic_text)
            elif _topic[0] == self.client.ha_topic:
                await self._handle_hass_topic(_topic, payload_bytes, lp)
