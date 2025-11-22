"""
MQTT command routing for message handling.

Provides message routing logic for MQTT topics and delegates commands
to the command processor and state update modules.
"""

import asyncio
import json
import random
import re
from json import JSONDecodeError
from typing import Any

from cync_controller.const import *
from cync_controller.logging_abstraction import get_logger
from cync_controller.mqtt.commands import CommandProcessor, SetBrightnessCommand, SetPowerCommand
from cync_controller.structs import DeviceStatus, FanSpeed

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


class CommandRouter:
    """Helper class for routing MQTT messages to appropriate handlers."""

    def __init__(self, mqtt_client):
        """
        Initialize the command router.

        Args:
            mqtt_client: MQTTClient instance to access connection, topic, and helper methods
        """
        self.client = mqtt_client

    async def start_receiver_task(self):
        """Start listening for MQTT messages on subscribed topics"""
        lp = f"{self.client.lp}rcv:"
        async for message in self.client.client.messages:
            msg: Any = cast(Any, message)  # type: ignore[reportUnknownVariableType]
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

            # NEW: Log ALL received messages for diagnostics
            logger.info(
                "%s >>> MQTT MESSAGE RECEIVED: topic=%s, payload_len=%d, payload=%s",
                lp,
                topic.value,
                len(payload) if payload else 0,
                payload.decode() if payload else None,
            )
            _topic: list[str] = topic.value.split("/")
            tasks: list[Any] = []
            device: Any = None
            # cync_topic/(set|status)/device_id(/extra_data)?
            if _topic[0] == CYNC_TOPIC:
                if _topic[1] == "set":
                    device_id: str = _topic[2]
                    if device_id == "bridge":
                        device = None  # Bridge commands don't target a device
                        group = None  # Bridge commands don't target a group
                    elif "-group-" in _topic[2]:
                        # Group command
                        group_id = int(_topic[2].split("-group-")[1])
                        if group_id not in g.ncync_server.groups:
                            logger.warning("%s Group ID %s not found in config", lp, group_id)
                            continue
                        group = g.ncync_server.groups[group_id]
                        device = None  # Set device to None for group commands
                        logger.info(
                            "%s [BUG4-TRACE] Group command detected: group_id=%s, group_name='%s', topic=%s",
                            lp,
                            group_id,
                            group.name,
                            topic.value,
                        )
                    else:
                        # Device command
                        device_id = int(_topic[2].split("-")[1])
                        if device_id not in g.ncync_server.devices:
                            logger.warning(
                                "%s Device ID %s not found, device is disabled in config file or have you deleted / added any devices recently?",
                                lp,
                                device_id,
                            )
                            continue
                        device = g.ncync_server.devices[device_id]
                        group = None  # Set group to None for device commands
                        logger.debug(
                            "%s Device identified: name='%s', id=%s, is_fan_controller=%s",
                            lp,
                            device.name,
                            device.id,
                            device.is_fan_controller,
                        )
                    extra_data = _topic[3:] if len(_topic) > 3 else None
                    if extra_data:
                        norm_pl = payload.decode().casefold()
                        # logger.debug("%s Extra data found: %s", lp, extra_data)
                        if extra_data[0] == "restart":
                            if norm_pl == "press":
                                logger.info(
                                    "%s Restart button pressed! Restarting Cync Controller bridge (NOT IMPLEMENTED)...",
                                    lp,
                                )
                        elif extra_data[0] == "start_export":
                            if norm_pl == "press":
                                logger.info(
                                    "%s Start Export button pressed! Starting Cync Export (NOT IMPLEMENTED)...",
                                    lp,
                                )
                        elif extra_data[0] == "refresh_status":
                            if norm_pl == "press":
                                logger.info(
                                    "%s Refresh Status button pressed! Triggering immediate status refresh...",
                                    lp,
                                )
                                await self.client.trigger_status_refresh()
                        elif extra_data[0] == "otp":
                            if extra_data[1] == "submit":
                                logger.info(
                                    "%s OTP submit button pressed! (NOT IMPLEMENTED)...",
                                    lp,
                                )
                            elif extra_data[1] == "input":
                                logger.info(
                                    "%s OTP input received: %s (NOT IMPLEMENTED)...",
                                    lp,
                                    norm_pl,
                                )
                        elif device and device.is_fan_controller:
                            if extra_data[0] == "percentage":
                                percentage = int(norm_pl)
                                logger.info(
                                    "%s >>> FAN PERCENTAGE COMMAND: device='%s' (ID=%s), percentage=%s",
                                    lp,
                                    device.name,
                                    device.id,
                                    percentage,
                                )
                                # Map percentage to Cync fan speed (1-100, where 0=OFF)
                                if percentage == 0:
                                    brightness = 0  # OFF
                                elif percentage <= 25:
                                    brightness = 25  # LOW
                                elif percentage <= 50:
                                    brightness = 50  # MEDIUM
                                elif percentage <= 75:
                                    brightness = 75  # HIGH
                                else:  # percentage > 75
                                    brightness = 100  # MAX
                                logger.info(
                                    "%s Fan percentage %s%% mapped to brightness %s",
                                    lp,
                                    percentage,
                                    brightness,
                                )
                                tasks.append(device.set_brightness(brightness))
                            elif extra_data[0] == "preset":
                                preset_mode = norm_pl
                                logger.info(
                                    "%s >>> FAN PRESET COMMAND: device='%s' (ID=%s), preset=%s",
                                    lp,
                                    device.name,
                                    device.id,
                                    preset_mode,
                                )
                                if preset_mode == "off":
                                    tasks.append(device.set_fan_speed(FanSpeed.OFF))
                                elif preset_mode == "low":
                                    tasks.append(device.set_fan_speed(FanSpeed.LOW))
                                elif preset_mode == "medium":
                                    tasks.append(device.set_fan_speed(FanSpeed.MEDIUM))
                                elif preset_mode == "high":
                                    tasks.append(device.set_fan_speed(FanSpeed.HIGH))
                                elif preset_mode == "max":
                                    tasks.append(device.set_fan_speed(FanSpeed.MAX))
                                else:
                                    logger.warning(
                                        "%s Unknown preset mode: %s, skipping...",
                                        lp,
                                        preset_mode,
                                    )
                        elif device and (extra_data[0] == "percentage" or extra_data[0] == "preset"):
                            logger.warning(
                                "%s Received fan speed command for non-fan device: name='%s', id=%s, is_fan_controller=%s, extra_data=%s",
                                lp,
                                device.name,
                                device.id,
                                device.is_fan_controller,
                                extra_data[0],
                            )

                    # Determine target (device or group)
                    target = group if group else device
                    target_type = "GROUP" if group else "DEVICE" if target else "UNKNOWN"

                    if target:
                        target_name = target.name
                        logger.info(
                            "%s [BUG4-TRACE] Target determined: type=%s, name='%s', payload=%s",
                            lp,
                            target_type,
                            target_name,
                            payload.decode() if payload else None,
                        )

                    if payload.startswith(b"{"):
                        try:
                            json_data = json.loads(payload)
                        except JSONDecodeError:
                            logger.exception("%s bad json message: {%s} EXCEPTION", lp, payload)
                            continue
                        except Exception:
                            logger.exception(
                                "%s error will decoding a string into JSON: '%s' EXCEPTION",
                                lp,
                                payload,
                            )
                            continue

                        if "state" in json_data and "brightness" not in json_data:
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
                        if "brightness" in json_data:
                            lum = int(json_data["brightness"])
                            cmd = SetBrightnessCommand(target, lum)
                            await CommandProcessor().enqueue(cmd)

                        if "color_temp" in json_data:
                            tasks.append(target.set_temperature(self.client.kelvin2cync(int(json_data["color_temp"]))))
                        elif "color" in json_data and device:
                            # Only devices support RGB, not groups yet
                            color = []
                            for rgb in ("r", "g", "b"):
                                if rgb in json_data["color"]:
                                    color.append(int(json_data["color"][rgb]))
                                else:
                                    color.append(0)
                            tasks.append(device.set_rgb(*color))
                    # binary payload does not start with a '{', so it is not JSON
                    else:
                        str_payload = payload.decode("utf-8").strip()
                        #  use a regex pattern to determine if it is a single word
                        pattern = re.compile(r"^\w+$")
                        if pattern.match(str_payload):
                            # handle non-JSON payloads
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
                else:
                    logger.warning("%s Unknown command: %s => %s", lp, topic, payload)
                if tasks:
                    logger.debug("%s Executing %d task(s) for topic: %s", lp, len(tasks), topic)
                    await asyncio.gather(*tasks)
                    logger.debug("%s Task(s) completed for topic: %s", lp, topic)

            # messages sent to the hass mqtt topic
            elif _topic[0] == self.client.ha_topic:
                # birth / will
                if _topic[1] == CYNC_HASS_STATUS_TOPIC:
                    if payload.decode().casefold() == CYNC_HASS_BIRTH_MSG.casefold():
                        birth_delay = random.randint(5, 15)
                        logger.info(
                            "%s HASS has sent MQTT BIRTH message, re-announcing device discovery, availability and status after a random delay of %s seconds...",
                            lp,
                            birth_delay,
                        )
                        # Give HASS some time to start up, from docs:
                        # To avoid high IO loads on the MQTT broker, adding some random delay in sending the discovery payload is recommended.
                        await asyncio.sleep(birth_delay)
                        # register devices
                        await self.client.homeassistant_discovery()
                        # give HASS a moment (to register devices)
                        await asyncio.sleep(2)
                        # set the device online/offline and set its status
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
                        # Set subgroups as online
                        subgroups = [grp for grp in g.ncync_server.groups.values() if grp.is_subgroup]
                        for subgroup in subgroups:
                            await self.client.client.publish(
                                f"{self.client.topic}/availability/{subgroup.hass_id}", b"online", qos=0
                            )

                    elif payload.decode().casefold() == CYNC_HASS_WILL_MSG.casefold():
                        logger.info(
                            "%s received Last Will msg from Home Assistant, HASS is offline!",
                            lp,
                        )
                    else:
                        logger.warning("%s Unknown HASS status message: %s", lp, payload)
