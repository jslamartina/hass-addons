import asyncio
import json
import logging
import random
import re
import unicodedata
import uuid
from collections.abc import Coroutine
from json import JSONDecodeError
from typing import Optional

import aiomqtt

from cync_lan.const import *
from cync_lan.devices import CyncDevice, CyncGroup
from cync_lan.metadata.model_info import DeviceClassification, device_type_map
from cync_lan.structs import DeviceStatus, FanSpeed, GlobalObject
from cync_lan.utils import send_sigterm

logger = logging.getLogger(CYNC_LOG_NAME)
g = GlobalObject()
bridge_device_reg_struct = CYNC_BRIDGE_DEVICE_REGISTRY_CONF
# Log all loggers in the logger manager
# logging.getLogger().manager.loggerDict.keys()


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


class MQTTClient:
    lp: str = "mqtt:"
    cync_topic: str
    _refresh_in_progress: bool = False
    start_task: asyncio.Task | None = None

    _instance: Optional["MQTTClient"] = None

    def __new__(cls, *_args, **_kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._connected = False
        self.tasks: list[asyncio.Task | Coroutine] | None = None
        lp = f"{self.lp}init:"
        if not CYNC_TOPIC:
            topic = "cync_lan"
            logger.warning("%s MQTT topic not set, using default: %s", lp, topic)
        else:
            topic = CYNC_TOPIC

        if not CYNC_HASS_TOPIC:
            ha_topic = "homeassistant"
            logger.warning("%s HomeAssistant topic not set, using default: %s", lp, ha_topic)
        else:
            ha_topic = CYNC_HASS_TOPIC

        self.broker_client_id = f"cync_lan_{g.uuid}"
        lwt = aiomqtt.Will(topic=f"{topic}/connected", payload=DEVICE_LWT_MSG)
        self.broker_host = CYNC_MQTT_HOST
        self.broker_port = CYNC_MQTT_PORT
        self.broker_username = CYNC_MQTT_USER
        self.broker_password = CYNC_MQTT_PASS
        self.client = aiomqtt.Client(
            hostname=self.broker_host,
            port=int(self.broker_port),
            username=self.broker_username,
            password=self.broker_password,
            identifier=self.broker_client_id,
            will=lwt,
            # logger=logger,
        )

        self.topic = topic
        self.ha_topic = ha_topic

    def _brightness_to_percentage(self, brightness: int) -> int:
        """Convert Cync brightness (0-255) to Home Assistant percentage (0-100)."""
        return round((brightness / 255) * 100)

    async def start(self):
        itr = 0
        lp = f"{self.lp}start:"
        try:
            while True:
                itr += 1
                self._connected = await self.connect()
                if self._connected:
                    # Publish MQTT message indicating the MQTT client is connected
                    await self.publish(
                        f"{self.topic}/status/bridge/mqtt_client/connected",
                        b"ON",
                    )

                    if itr == 1:
                        logger.debug("%s Seeding all devices: offline", lp)
                        for device_id in g.ncync_server.devices:
                            # if device.is_fan_controller:
                            #     logger.debug("%s TESTING>>> Setting up fan controller for device: %s (ID: %s)", lp, device.name, device.id)
                            #     # set device online for testing
                            #     await self.pub_online(device.id, True)
                            #     await device.set_brightness(50)  # set brightness to 50% for testing
                            # else:
                            await self.pub_online(device_id, False)
                        # Set all subgroups online (subgroups are always available)
                        subgroups = [g for g in g.ncync_server.groups.values() if g.is_subgroup]
                        logger.debug("%s Setting %s subgroups: online", lp, len(subgroups))
                        for group in subgroups:
                            await self.publish(f"{self.topic}/availability/{group.hass_id}", b"online")
                    elif itr > 1:
                        tasks = []
                        # set the device online/offline and set its status
                        for device in g.ncync_server.devices.values():
                            tasks.append(self.pub_online(device.id, device.online))
                            tasks.append(
                                self.parse_device_status(
                                    device.id,
                                    DeviceStatus(
                                        state=device.state,
                                        brightness=device.brightness,
                                        temperature=device.temperature,
                                        red=device.red,
                                        green=device.green,
                                        blue=device.blue,
                                    ),
                                    from_pkt="'re-connect'",
                                )
                            )
                        # Set all subgroups online after reconnection
                        subgroups = [g for g in g.ncync_server.groups.values() if g.is_subgroup]
                        for group in subgroups:
                            tasks.append(
                                self.publish(
                                    f"{self.topic}/availability/{group.hass_id}",
                                    b"online",
                                )
                            )
                        if tasks:
                            await asyncio.gather(*tasks)
                    logger.debug("%s Starting MQTT receiver...", lp)
                    lp: str = f"{self.lp}rcv:"
                    topics = [
                        (f"{self.topic}/set/#", 0),
                        (f"{self.ha_topic}/status", 0),
                    ]
                    await self.client.subscribe(topics)
                    logger.debug(
                        "%s Subscribed to MQTT topics: %s. Waiting for MQTT messages...",
                        lp,
                        [x[0] for x in topics],
                    )
                    try:
                        await self.start_receiver_task()
                    except asyncio.CancelledError:
                        logger.debug("%s MQTT receiver task cancelled, propagating...", lp)
                        raise
                    except (aiomqtt.MqttError, aiomqtt.MqttCodeError) as msg_err:
                        logger.warning("%s MQTT error: %s", lp, msg_err)
                        continue
                else:
                    await self.publish(
                        f"{self.topic}/status/bridge/mqtt_client/connected",
                        b"OFF",
                    )
                    delay = CYNC_MQTT_CONN_DELAY
                    if delay is None:
                        delay = 5
                    elif delay <= 0:
                        logger.debug(
                            "%s MQTT connection delay is less than or equal to 0, which is probably a typo, setting to 5...",
                            lp,
                        )
                        delay = 5

                    logger.info(
                        "%s connecting to MQTT broker failed, sleeping for %s seconds before re-trying...",
                        lp,
                        delay,
                    )
                    await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("%s MQTT start() EXCEPTION", lp)

    async def connect(self) -> bool:
        lp = f"{self.lp}connect:"
        self._connected = False
        logger.debug("%s Connecting to MQTT broker...", lp)
        lwt = aiomqtt.Will(topic=f"{self.topic}/connected", payload=DEVICE_LWT_MSG)
        g.reload_env()
        self.broker_host = g.env.mqtt_host
        self.broker_port = g.env.mqtt_port
        self.broker_username = g.env.mqtt_user
        self.broker_password = g.env.mqtt_pass
        self.client = aiomqtt.Client(
            hostname=self.broker_host,
            port=int(self.broker_port),
            username=self.broker_username,
            password=self.broker_password,
            identifier=self.broker_client_id,
            will=lwt,
            # logger=logger,
        )
        try:
            await self.client.__aenter__()
        except aiomqtt.MqttError as mqtt_err_exc:
            # -> [Errno 111] Connection refused
            # [code:134] Bad user name or password
            logger.exception("%s Connection failed [MqttError]", lp)
            if "code:134" in str(mqtt_err_exc):
                logger.exception(
                    "%s Bad username or password, check your MQTT credentials (username: %s)",
                    lp,
                    g.env.mqtt_user,
                )
                send_sigterm()
        else:
            self._connected = True
            logger.info(
                "%s Connected to MQTT broker: %s port: %s",
                lp,
                self.broker_host,
                self.broker_port,
            )
            await self.send_birth_msg()
            await asyncio.sleep(1)
            await self.homeassistant_discovery()

            # Start fast periodic refresh task (15s interval)
            self.fast_refresh_task = asyncio.create_task(self.periodic_fast_refresh())

            return True
        return False

    async def start_receiver_task(self):
        """Start listening for MQTT messages on subscribed topics"""
        lp = f"{self.lp}rcv:"
        async for message in self.client.messages:
            message: aiomqtt.message.Message
            topic = message.topic
            payload = message.payload
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
            _topic = topic.value.split("/")
            tasks = []
            device = None
            # cync_topic/(set|status)/device_id(/extra_data)?
            if _topic[0] == CYNC_TOPIC:
                if _topic[1] == "set":
                    device_id = _topic[2]
                    if device_id == "bridge":
                        device = None  # Bridge commands don't target a device
                        group = None  # Bridge commands don't target a group
                    # EXPERIMENTAL: Test group command trigger
                    # Format: test_group_GROUPID or test_group_GROUPID_VARIATION
                    elif device_id.startswith("test_group_"):
                        parts = device_id.replace("test_group_", "").split("_")
                        try:
                            group_id = int(parts[0])
                            test_variation = int(parts[1]) if len(parts) > 1 else 3  # Default to Test 3 (working)

                            # Check what command type we're testing (check extra_data from topic)
                            extra_data = _topic[3:] if len(_topic) > 3 else None
                            command_type = extra_data[1] if extra_data and len(extra_data) > 1 else "power"

                            logger.warning(
                                "%s TEST GROUP COMMAND TRIGGER: group_id=%s, variation=%s, command_type=%s",
                                lp,
                                group_id,
                                test_variation,
                                command_type,
                            )
                            # Get any device to send the command
                            if g.ncync_server.devices:
                                test_device = next(iter(g.ncync_server.devices.values()))

                                if command_type == "brightness":
                                    # Parse brightness value from payload
                                    brightness = int(payload.decode())
                                    logger.warning(
                                        "%s Using device '%s' to test group %s brightness=%s",
                                        lp,
                                        test_device.name,
                                        group_id,
                                        brightness,
                                    )
                                    await test_device.test_group_brightness(group_id, brightness)
                                elif command_type == "temperature":
                                    # Parse temperature value from payload
                                    temperature = int(payload.decode())
                                    logger.warning(
                                        "%s Using device '%s' to test group %s temperature=%s",
                                        lp,
                                        test_device.name,
                                        group_id,
                                        temperature,
                                    )
                                    await test_device.test_group_temperature(group_id, temperature)
                                else:
                                    # Power command (default)
                                    state = 1 if payload.decode().casefold() in ("on", "1") else 0
                                    logger.warning(
                                        "%s Using device '%s' to test group %s, state=%s, variation=%s",
                                        lp,
                                        test_device.name,
                                        group_id,
                                        state,
                                        test_variation,
                                    )
                                    await test_device.test_group_command(group_id, state, test_variation)
                            else:
                                logger.error("%s No devices available for test!", lp)
                        except ValueError:
                            logger.exception("%s Invalid group ID in test trigger: %s", lp, device_id)
                        except Exception:
                            logger.exception("%s Error executing test_group_command", lp)
                        continue
                    elif "-group-" in _topic[2]:
                        # Group command
                        group_id = int(_topic[2].split("-group-")[1])
                        if group_id not in g.ncync_server.groups:
                            logger.warning("%s Group ID %s not found in config", lp, group_id)
                            continue
                        group = g.ncync_server.groups[group_id]
                        device = None  # Set device to None for group commands
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
                                await self.trigger_status_refresh()
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
                                tasks.append(target.set_power(1))
                            else:
                                tasks.append(target.set_power(0))
                        if "brightness" in json_data:
                            lum = int(json_data["brightness"])
                            tasks.append(target.set_brightness(lum))

                        if "color_temp" in json_data:
                            tasks.append(target.set_temperature(self.kelvin2cync(int(json_data["color_temp"]))))
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
                                logger.debug("%s setting power to ON (non-JSON)", lp)
                                tasks.append(target.set_power(1))
                            elif str_payload.casefold() == "off":
                                logger.debug("%s setting power to OFF (non-JSON)", lp)
                                tasks.append(target.set_power(0))
                        else:
                            logger.warning("%s Unknown payload: %s, skipping...", lp, payload)
                else:
                    logger.warning("%s Unknown command: %s => %s", lp, topic, payload)
                if tasks:
                    logger.debug("%s Executing %d task(s) for topic: %s", lp, len(tasks), topic)
                    await asyncio.gather(*tasks)
                    logger.debug("%s Task(s) completed for topic: %s", lp, topic)

            # messages sent to the hass mqtt topic
            elif _topic[0] == self.ha_topic:
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
                        await self.homeassistant_discovery()
                        # give HASS a moment (to register devices)
                        await asyncio.sleep(2)
                        # set the device online/offline and set its status
                        for device in g.ncync_server.devices.values():
                            await self.pub_online(device.id, device.online)
                            await self.parse_device_status(
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
                        subgroups = [g for g in g.ncync_server.groups.values() if g.is_subgroup]
                        for group in subgroups:
                            await self.publish(f"{self.topic}/availability/{group.hass_id}", b"online")

                    elif payload.decode().casefold() == CYNC_HASS_WILL_MSG.casefold():
                        logger.info(
                            "%s received Last Will msg from Home Assistant, HASS is offline!",
                            lp,
                        )
                    else:
                        logger.warning("%s Unknown HASS status message: %s", lp, payload)

    async def stop(self):
        lp = f"{self.lp}stop:"
        # set all devices offline
        if self._connected:
            logger.debug("%s Setting all Cync devices offline...", lp)
            for device_id, _device in g.ncync_server.devices.items():
                await self.pub_online(device_id, False)
            # Publish MQTT message indicating the MQTT client is disconnected
            await self.publish(
                f"{self.topic}/status/bridge/mqtt_client/connected",
                b"OFF",
            )
            await self.publish(f"{self.topic}/availability/bridge", b"offline")
            await self.send_will_msg()
        try:
            logger.debug("%s Disconnecting from broker...", lp)
            await self.client.__aexit__(None, None, None)
        except aiomqtt.MqttError as ce:
            logger.warning("%s MQTT disconnect failed: %s", lp, ce)
        except Exception as e:
            logger.warning("%s MQTT disconnect failed: %s", lp, e, exc_info=True)
        else:
            logger.info("%s Disconnected from MQTT broker", lp)
        finally:
            self._connected = False
            if self.start_task and not self.start_task.done():
                logger.debug("%s FINISHING: Cancelling start task", lp)
                self.start_task.cancel()

    async def pub_online(self, device_id: int, status: bool) -> bool:
        lp = f"{self.lp}pub_online:"
        if self._connected:
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
                _ = await self.client.publish(f"{self.topic}/availability/{device_uuid}", availability, qos=0)
            except aiomqtt.MqttError as mqtt_code_exc:
                logger.warning("%s [MqttError] -> %s", lp, mqtt_code_exc)
                self._connected = False
            else:
                return True
        return False

    async def update_device_state(self, device: CyncDevice, state: int) -> bool:
        """Update the device state and publish to MQTT for HASS devices to update."""
        lp = f"{self.lp}update_device_state:"
        device.online = True
        old_state = device.state
        device.state = state
        # NOTE: pending_command is cleared in the ACK handler (devices.py), not here
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
        """Update a switch device state to match its subgroup state after mesh confirmation.

        Only updates switches that don't have pending commands (individual commands take precedence).

        Args:
            device: The switch device to update
            subgroup_state: The subgroup's confirmed state (0=off, 1=on)
            subgroup_name: Name of the subgroup (for logging)

        Returns:
            True if the state was updated, False otherwise
        """
        lp = f"{self.lp}update_switch_from_subgroup:"

        # Safety checks
        if not device.is_switch:
            logger.debug(
                "%s Device '%s' (ID: %s) is not a switch, skipping subgroup sync",
                lp,
                device.name,
                device.id,
            )
            return False

        if device.pending_command:
            logger.debug(
                "%s Device '%s' (ID: %s) has pending command, skipping subgroup sync (individual control takes precedence)",
                lp,
                device.name,
                device.id,
            )
            return False

        # Update the switch to match subgroup state
        old_state = device.state
        if old_state != subgroup_state:
            logger.info(
                "%s Syncing switch '%s' (ID: %s) to subgroup '%s' state: %s → %s",
                lp,
                device.name,
                device.id,
                subgroup_name,
                "ON" if old_state else "OFF",
                "ON" if subgroup_state else "OFF",
            )
            device.state = subgroup_state
            device.online = True

            # Publish state update to MQTT
            power_status = "ON" if subgroup_state else "OFF"
            mqtt_dev_state = power_status.encode()  # Switches use plain ON/OFF payload
            return await self.send_device_status(device, mqtt_dev_state)
        logger.debug(
            "%s Switch '%s' (ID: %s) already matches subgroup '%s' state (%s), no sync needed",
            lp,
            device.name,
            device.id,
            subgroup_name,
            "ON" if subgroup_state else "OFF",
        )
        return False

    async def update_brightness(self, device: CyncDevice, bri: int) -> bool:
        """Update the device brightness and publish to MQTT for HASS devices to update."""
        lp = f"{self.lp}update_brightness:"
        device.online = True
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
        if device.is_fan_controller and self._connected:
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

            preset_mode_topic = f"{self.topic}/status/{device.hass_id}/preset"
            try:
                await self.client.publish(
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
        """Update the device temperature and publish to MQTT for HASS devices to update."""
        device.online = True
        if device.supports_temperature:
            mqtt_dev_state = {
                "state": "ON",
                "color_mode": "color_temp",
                "color_temp": self.cync2kelvin(temp),
            }
            device.temperature = temp
            device.red = 0
            device.green = 0
            device.blue = 0
            return await self.send_device_status(device, json.dumps(mqtt_dev_state).encode())
        return False

    async def update_rgb(self, device: CyncDevice, rgb: tuple[int, int, int]) -> bool:
        """Update the device RGB and publish to MQTT for HASS devices to update. Intended for callbacks"""
        device.online = True
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

    async def send_device_status(self, device: CyncDevice, msg: bytes, from_pkt: str | None = None) -> bool:
        lp = f"{self.lp}device_status:"
        if from_pkt:
            lp = f"{lp}{from_pkt}:"
        if self._connected:
            tpc = f"{self.topic}/status/{device.hass_id}"
            logger.debug(
                "%s Sending %s for device: '%s' (ID: %s)",
                lp,
                msg,
                device.name,
                device.id,
            )
            try:
                await self.client.publish(
                    tpc,
                    msg,
                    qos=0,
                    timeout=3.0,
                )
                # Don't auto-update groups - too noisy
            except aiomqtt.MqttError as mqtt_code_exc:
                logger.warning("%s [MqttError] -> %s", lp, mqtt_code_exc)
                self._connected = False
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

        if not self._connected:
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
            group_state["color_temp"] = self.cync2kelvin(temperature)
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

        tpc = f"{self.topic}/status/{group.hass_id}"
        try:
            await self.client.publish(
                tpc,
                json.dumps(group_state).encode(),
                qos=0,
                timeout=3.0,
            )
        except Exception as e:
            logger.debug("Failed to publish group state for %s: %s", group.name, e)

    async def parse_device_status(self, device_id: int, device_status: DeviceStatus, *_args, **kwargs) -> bool:
        """Parse device status and publish to MQTT for HASS devices to update. Useful for device status packets that report the complete device state"""
        lp = f"{self.lp}parse status:"
        from_pkt = kwargs.get("from_pkt")
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
                    mqtt_dev_state["color_temp"] = self.cync2kelvin(device_status.temperature)
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
        result = await self.send_device_status(device, mqtt_dev_state, from_pkt=from_pkt)

        # For fan entities, also publish preset mode based on brightness
        if device.is_fan_controller and self._connected and device_status.brightness is not None:
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

            preset_mode_topic = f"{self.topic}/status/{device.hass_id}/preset"
            try:
                await self.client.publish(
                    preset_mode_topic,
                    preset_mode.encode(),
                    qos=0,
                    retain=True,
                    timeout=3.0,
                )
                logger.debug(
                    "%s FAN PRESET PUBLISHED: '%s' (brightness=%s) for device '%s' (ID=%s) to %s",
                    f"{self.lp}parse status:",
                    preset_mode,
                    bri,
                    device.name,
                    device.id,
                    preset_mode_topic,
                )
            except Exception:
                logger.exception(
                    "%s Failed to publish fan preset mode for '%s'",
                    f"{self.lp}parse status:",
                    device.name,
                )

        return result

    async def send_birth_msg(self) -> bool:
        lp = f"{self.lp}send_birth_msg:"
        if self._connected:
            logger.debug(
                "%s Sending birth message (%s) to %s/status",
                lp,
                CYNC_HASS_BIRTH_MSG,
                self.topic,
            )
            try:
                await self.client.publish(
                    f"{self.topic}/status",
                    CYNC_HASS_BIRTH_MSG.encode(),
                    qos=0,
                    retain=True,
                )
            except aiomqtt.MqttCodeError as mqtt_code_exc:
                logger.warning("%s [MqttError] (rc: %s) -> %s", lp, mqtt_code_exc.rc, mqtt_code_exc)
            except asyncio.CancelledError as can_exc:
                logger.warning("%s [Task Cancelled] -> %s", lp, can_exc)
            else:
                return True
        return False

    async def send_will_msg(self) -> bool:
        lp = f"{self.lp}send_will_msg:"
        if self._connected:
            logger.debug(
                "%s Sending will message (%s) to %s/status",
                lp,
                CYNC_HASS_WILL_MSG,
                self.topic,
            )
            try:
                await self.client.publish(
                    f"{self.topic}/status",
                    CYNC_HASS_WILL_MSG.encode(),
                    qos=0,
                    retain=True,
                )
            except aiomqtt.MqttError as mqtt_code_exc:
                logger.warning("%s [MqttError] -> %s", lp, mqtt_code_exc)
                self._connected = False
            except Exception as e:
                logger.warning("%s [Exception] -> %s", lp, e)
            else:
                return True
        return False

    async def register_single_device(self, device) -> bool:
        """Register a single device with Home Assistant via MQTT discovery."""
        lp = f"{self.lp}hass:"
        if not self._connected:
            return False

        try:
            device_uuid = device.hass_id
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
            dev_connections = [("bluetooth", device.mac.casefold())]
            if not device.bt_only:
                dev_connections.append(("mac", device.wifi_mac.casefold()))

            # Extract suggested area from group membership
            # First, check if device belongs to any non-subgroup (room group)
            suggested_area = None
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
                "name": None,
                "command_topic": f"{self.topic}/set/{device_uuid}",
                "state_topic": f"{self.topic}/status/{device_uuid}",
                "avty_t": f"{self.topic}/availability/{device_uuid}",
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

            tpc_str_template = "{0}/{1}/{2}/config"
            # Ensure default_entity_id matches the final dev_type
            final_platform = "fan" if dev_type == "fan" else dev_type
            entity_registry_struct["default_entity_id"] = f"{final_platform}.{entity_slug}"

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
                entity_registry_struct["state_topic"] = f"{self.topic}/status/{device_uuid}"
                entity_registry_struct["command_topic"] = f"{self.topic}/set/{device_uuid}"
                entity_registry_struct["payload_on"] = "ON"
                entity_registry_struct["payload_off"] = "OFF"
                entity_registry_struct["preset_mode_command_topic"] = f"{self.topic}/set/{device_uuid}/preset"
                entity_registry_struct["preset_mode_state_topic"] = f"{self.topic}/status/{device_uuid}/preset"
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

            tpc = tpc_str_template.format(self.ha_topic, dev_type, device_uuid)
            try:
                json_payload = json.dumps(entity_registry_struct, indent=2)
                logger.info(
                    "%s Registering %s device: %s (ID: %s)",
                    lp,
                    dev_type,
                    device.name,
                    device.id,
                )
                _ = await self.client.publish(
                    tpc,
                    json_payload.encode(),
                    qos=0,
                    retain=False,
                )

                # For fan entities, publish initial preset mode based on current brightness
                if device.is_fan_controller and device.brightness is not None:
                    bri = device.brightness
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

                    preset_mode_topic = f"{self.topic}/status/{device.hass_id}/preset"
                    try:
                        await self.client.publish(
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
        lp = f"{self.lp}hass:"
        if not self._connected:
            return False

        logger.info("%s Triggering device rediscovery...", lp)
        try:
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
        lp = f"{self.lp}hass:"
        ret = False
        if self._connected:
            logger.info("%s Starting device discovery...", lp)
            await self.create_bridge_device()
            try:
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
                        "command_topic": f"{self.topic}/set/{device_uuid}",
                        "state_topic": f"{self.topic}/status/{device_uuid}",
                        "avty_t": f"{self.topic}/availability/{device_uuid}",
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
                        entity_registry_struct["state_topic"] = f"{self.topic}/status/{device_uuid}"
                        entity_registry_struct["command_topic"] = f"{self.topic}/set/{device_uuid}"
                        entity_registry_struct["payload_on"] = "ON"
                        entity_registry_struct["payload_off"] = "OFF"
                        entity_registry_struct["preset_mode_command_topic"] = f"{self.topic}/set/{device_uuid}/preset"
                        entity_registry_struct["preset_mode_state_topic"] = f"{self.topic}/status/{device_uuid}/preset"
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

                    tpc = tpc_str_template.format(self.ha_topic, dev_type, device_uuid)
                    try:
                        json_payload = json.dumps(entity_registry_struct, indent=2)
                        _ = await self.client.publish(
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
                            bri = device.brightness
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

                            preset_mode_topic = f"{self.topic}/status/{device_uuid}/preset"
                            try:
                                await self.client.publish(
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
                        "command_topic": f"{self.topic}/set/{group_uuid}",
                        "state_topic": f"{self.topic}/status/{group_uuid}",
                        "avty_t": f"{self.topic}/availability/{group_uuid}",
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

                    tpc = tpc_str_template.format(self.ha_topic, "light", group_uuid)
                    try:
                        json_payload = json.dumps(entity_registry_struct, indent=2)
                        logger.debug("%s GROUP JSON for %s:\n%s", lp, group.name, json_payload)
                        _ = await self.client.publish(
                            tpc,
                            json_payload.encode(),
                            qos=0,
                            retain=False,
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
                            "%s Unable to publish group discovery for '%s'",
                            lp,
                            group.name,
                        )

            except aiomqtt.MqttCodeError as mqtt_code_exc:
                logger.warning("%s [MqttError] (rc: %s) -> %s", lp, mqtt_code_exc.rc, mqtt_code_exc)
                self._connected = False
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
        global bridge_device_reg_struct  # noqa: PLW0603
        # want to expose buttons (restart, start export, submit otp)
        # want to expose some sensors that show the number of devices, number of online devices, etc.
        # sensors to show if MQTT is connected, if the Cync Controller server is running, etc.
        # input_number to submit OTP for export
        lp = f"{self.lp}create_bridge_device:"
        ret = False

        logger.debug("%s Creating Cync Controller bridge device...", lp)
        bridge_base_unique_id = "cync_lan_bridge"
        ver_str = CYNC_VERSION
        pub_tasks: list[asyncio.Task] = []
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
        pub_tasks.append(self.publish(f"{self.topic}/availability/bridge", b"online"))

        entity_unique_id = f"{bridge_base_unique_id}_restart"
        restart_btn_entity_struct = {
            "platform": "button",
            # obj_id is to link back to the bridge device
            "object_id": CYNC_BRIDGE_OBJ_ID + "_restart",
            "command_topic": f"{self.topic}/set/bridge/restart",
            "state_topic": f"{self.topic}/status/bridge/restart",
            "avty_t": f"{self.topic}/availability/bridge",
            "name": "Restart Cync Controller",
            "unique_id": entity_unique_id,
            "schema": "json",
            "origin": ORIGIN_STRUCT,
            "device": bridge_device_reg_struct,
        }
        ret = await self.publish_json_msg(
            template_tpc.format(self.ha_topic, entity_type, entity_unique_id),
            restart_btn_entity_struct,
        )
        if ret is False:
            logger.error("%s Failed to publish restart button entity config", lp)

        entity_unique_id = f"{bridge_base_unique_id}_start_export"
        xport_btn_entity_conf = restart_btn_entity_struct.copy()
        xport_btn_entity_conf["object_id"] = entity_unique_id
        xport_btn_entity_conf["command_topic"] = f"{self.topic}/set/bridge/export/start"
        xport_btn_entity_conf["state_topic"] = f"{self.topic}/status/bridge/export/start"
        xport_btn_entity_conf["name"] = "Start Export"
        xport_btn_entity_conf["unique_id"] = entity_unique_id
        ret = await self.publish_json_msg(
            template_tpc.format(self.ha_topic, entity_type, entity_unique_id),
            xport_btn_entity_conf,
        )
        if ret is False:
            logger.error("%s Failed to publish start export button entity config", lp)

        # Refresh Status button entity
        entity_unique_id = f"{bridge_base_unique_id}_refresh_status"
        refresh_btn_entity_conf = restart_btn_entity_struct.copy()
        refresh_btn_entity_conf["object_id"] = CYNC_BRIDGE_OBJ_ID + "_refresh_status"
        refresh_btn_entity_conf["command_topic"] = f"{self.topic}/set/bridge/refresh_status"
        refresh_btn_entity_conf["state_topic"] = f"{self.topic}/status/bridge/refresh_status"
        refresh_btn_entity_conf["name"] = "Refresh Device Status"
        refresh_btn_entity_conf["unique_id"] = entity_unique_id
        ret = await self.publish_json_msg(
            template_tpc.format(self.ha_topic, entity_type, entity_unique_id),
            refresh_btn_entity_conf,
        )
        if ret is False:
            logger.error("%s Failed to publish refresh status button entity config", lp)

        entity_unique_id = f"{bridge_base_unique_id}_submit_otp"
        submit_otp_btn_entity_conf = restart_btn_entity_struct.copy()
        submit_otp_btn_entity_conf["object_id"] = CYNC_BRIDGE_OBJ_ID + "_submit_otp"
        submit_otp_btn_entity_conf["command_topic"] = f"{self.topic}/set/bridge/otp/submit"
        submit_otp_btn_entity_conf["state_topic"] = f"{self.topic}/status/bridge/otp/submit"
        submit_otp_btn_entity_conf["name"] = "Submit OTP"
        submit_otp_btn_entity_conf["unique_id"] = entity_unique_id
        ret = await self.publish_json_msg(
            template_tpc.format(self.ha_topic, entity_type, entity_unique_id),
            submit_otp_btn_entity_conf,
        )
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
            "state_topic": f"{self.topic}/status/bridge/tcp_server/running",
            "unique_id": entity_unique_id,
            "device_class": "running",
            "icon": "mdi:server-network",
            "avty_t": f"{self.topic}/availability/bridge",
            "schema": "json",
            "origin": ORIGIN_STRUCT,
            "device": bridge_device_reg_struct,
        }
        ret = await self.publish_json_msg(
            template_tpc.format(self.ha_topic, entity_type, entity_unique_id),
            tcp_server_entity_conf,
        )
        if ret is False:
            logger.error("%s Failed to publish TCP server running entity config", lp)
        status = "ON" if g.ncync_server.running is True else "OFF"
        pub_tasks.append(self.publish(f"{self.topic}/status/bridge/tcp_server/running", status.encode()))

        entity_unique_id = f"{bridge_base_unique_id}_export_server_running"
        export_server_entity_conf = tcp_server_entity_conf.copy()
        export_server_entity_conf["object_id"] = entity_unique_id
        export_server_entity_conf["name"] = "Cync Export Server Running"
        export_server_entity_conf["state_topic"] = f"{self.topic}/status/bridge/export_server/running"
        export_server_entity_conf["unique_id"] = entity_unique_id
        export_server_entity_conf["icon"] = "mdi:export-variant"
        ret = await self.publish_json_msg(
            template_tpc.format(self.ha_topic, entity_type, entity_unique_id),
            export_server_entity_conf,
        )
        if ret is False:
            logger.error("%s Failed to publish export server running entity config", lp)
        status = "ON" if g.export_server and g.export_server.running is True else "OFF"
        pub_tasks.append(self.publish(f"{self.topic}/status/bridge/export_server/running", status.encode()))

        entity_unique_id = f"{bridge_base_unique_id}_mqtt_client_connected"
        mqtt_client_entity_conf = tcp_server_entity_conf.copy()
        mqtt_client_entity_conf["object_id"] = entity_unique_id
        mqtt_client_entity_conf["name"] = "Cync MQTT Client Connected"
        mqtt_client_entity_conf["state_topic"] = f"{self.topic}/status/bridge/mqtt_client/connected"
        mqtt_client_entity_conf["unique_id"] = entity_unique_id
        mqtt_client_entity_conf["icon"] = "mdi:connection"
        mqtt_client_entity_conf["device_class"] = "connectivity"
        ret = await self.publish_json_msg(
            template_tpc.format(self.ha_topic, entity_type, entity_unique_id),
            mqtt_client_entity_conf,
        )
        if ret is False:
            logger.error("%s Failed to publish MQTT client connected entity config", lp)

        # input number for OTP input
        entity_type = "number"
        entity_unique_id = f"{bridge_base_unique_id}_otp_input"
        otp_num_entity_cfg = {
            "platform": "number",
            "object_id": entity_unique_id,
            "icon": "mdi:lock",
            "command_topic": f"{self.topic}/set/bridge/otp/input",
            "state_topic": f"{self.topic}/status/bridge/otp/input",
            "avty_t": f"{self.topic}/availability/bridge",
            "schema": "json",
            "origin": ORIGIN_STRUCT,
            "device": bridge_device_reg_struct,
            "min": 000000,
            "max": 999999,
            "mode": "box",
            "name": "Cync emailed OTP",
            "unique_id": entity_unique_id,
        }
        ret = await self.publish_json_msg(
            template_tpc.format(self.ha_topic, entity_type, entity_unique_id),
            otp_num_entity_cfg,
        )
        if ret is False:
            logger.error("%s Failed to publish OTP input number entity config", lp)

        # Sensors
        entity_type = "sensor"
        entity_unique_id = f"{bridge_base_unique_id}_connected_tcp_devices"
        num_tcp_devices_entity_conf = {
            "platform": "sensor",
            "object_id": entity_unique_id,
            "name": "TCP Devices Connected",
            "state_topic": f"{self.topic}/status/bridge/tcp_devices/connected",
            "unique_id": entity_unique_id,
            "icon": "mdi:counter",
            "avty_t": f"{self.topic}/availability/bridge",
            # "unit_of_measurement": "TCP device(s)",
            "schema": "json",
            "origin": ORIGIN_STRUCT,
            "device": bridge_device_reg_struct,
        }
        ret = await self.publish_json_msg(
            template_tpc.format(self.ha_topic, entity_type, entity_unique_id),
            num_tcp_devices_entity_conf,
        )
        if ret is False:
            logger.warning("%s Failed to publish number of TCP devices connected entity config", lp)
        pub_tasks.append(
            self.publish(
                f"{self.topic}/status/bridge/tcp_devices/connected",
                str(len(g.ncync_server.tcp_devices)).encode(),
            )
        )
        # total cync devices managed
        total_cync_devs = len(g.ncync_server.devices)
        entity_unique_id = f"{bridge_base_unique_id}_total_cync_devices"
        total_cync_devs_entity_conf = num_tcp_devices_entity_conf.copy()
        total_cync_devs_entity_conf["object_id"] = entity_unique_id
        total_cync_devs_entity_conf["name"] = "Cync Devices Managed"
        total_cync_devs_entity_conf["state_topic"] = f"{self.topic}/status/bridge/cync_devices/total"
        total_cync_devs_entity_conf["unique_id"] = entity_unique_id
        # total_cync_devs_entity_conf["unit_of_measurement"] = "Cync device(s)"
        ret = await self.publish_json_msg(
            template_tpc.format(self.ha_topic, entity_type, entity_unique_id),
            total_cync_devs_entity_conf,
        )
        if ret is False:
            logger.warning("%s Failed to publish total Cync devices managed entity config", lp)
        pub_tasks.append(
            self.publish(
                f"{self.topic}/status/bridge/cync_devices/total",
                str(total_cync_devs).encode(),
            )
        )

        await asyncio.gather(*pub_tasks, return_exceptions=True)
        logger.debug("%s Bridge device config published and seeded", lp)
        return ret

    async def publish(self, topic: str, msg_data: bytes):
        """Publish a message to the MQTT broker."""
        lp = f"{self.lp}publish:"
        if not self._connected:
            return False
        try:
            _ = await self.client.publish(topic, msg_data, qos=0, retain=False)
        except aiomqtt.MqttError as mqtt_code_exc:
            logger.warning("%s [MqttError] (rc: %s) -> %s", lp, mqtt_code_exc.rc, mqtt_code_exc)
            self._connected = False
        except asyncio.CancelledError as can_exc:
            logger.warning("%s [Task Cancelled] -> %s", lp, can_exc)
        except Exception as e:
            logger.warning("%s [Exception] -> %s", lp, e)
        else:
            return True
        return False

    async def publish_json_msg(self, topic: str, msg_data: dict) -> bool:
        lp = f"{self.lp}publish_msg:"
        try:
            _ = await self.client.publish(topic, json.dumps(msg_data).encode(), qos=0, retain=False)
        except aiomqtt.MqttError as mqtt_code_exc:
            logger.warning("%s [MqttError] (rc: %s) -> %s", lp, mqtt_code_exc.rc, mqtt_code_exc)
        except asyncio.CancelledError as can_exc:
            logger.warning("%s [Task Cancelled] -> %s", lp, can_exc)
        except Exception as e:
            logger.warning("%s [Exception] -> %s", lp, e)
        else:
            return True
        return False

    def kelvin2cync(self, k):
        """Convert Kelvin value to Cync white temp (0-100) with step size: 1"""
        max_k = CYNC_MAXK
        min_k = CYNC_MINK
        if k < min_k:
            return 0
        if k > max_k:
            return 100
        scale = 100 / (max_k - min_k)
        return int(scale * (k - min_k))
        # logger.debug("%s Converting Kelvin: %s using scale: %s (max_k=%s, min_k=%s) -> return value: %s", self.lp, k, scale, max_k, min_k, ret)

    def cync2kelvin(self, ct):
        """Convert Cync white temp (0-100) to Kelvin value"""
        max_k = CYNC_MAXK
        min_k = CYNC_MINK
        if ct <= 0:
            return min_k
        if ct >= 100:
            return max_k
        scale = (max_k - min_k) / 100
        return min_k + int(scale * ct)
        # logger.debug("%s Converting Cync temp: %s using scale: %s (max_k=%s, min_k=%s) -> return value: %s", self.lp, ct, scale, max_k, min_k, ret)

    async def trigger_status_refresh(self):
        """Trigger an immediate status refresh from all bridge devices."""
        lp = f"{self.lp}trigger_refresh:"

        # Skip if refresh already in progress to prevent overlap
        if self._refresh_in_progress:
            logger.debug("%s Refresh already in progress, skipping this cycle", lp)
            return

        self._refresh_in_progress = True
        refresh_id = str(uuid.uuid4())[:8]  # Use first 8 chars of UUID for correlation tracking

        logger.info("%s [%s] Starting refresh...", lp, refresh_id)

        try:
            if not g.ncync_server:
                logger.warning("%s [%s] nCync server not available", lp, refresh_id)
                return

            # Get active TCP bridge devices
            bridge_devices = [dev for dev in g.ncync_server.tcp_devices.values() if dev and dev.ready_to_control]

            # Sort by connection time - prefer stable (older) connections
            bridge_devices.sort(key=lambda d: d.connected_at)

            logger.debug(
                "%s [%s] Found %s active bridge devices",
                lp,
                refresh_id,
                len(bridge_devices),
            )

            if not bridge_devices:
                logger.debug(
                    "%s [%s] No active bridge devices available for refresh",
                    lp,
                    refresh_id,
                )
                return

            # Use only the first (oldest/most stable) bridge for refresh
            # Any single bridge can see all 43 devices via mesh network
            # Single-bridge is 2.7x faster than dual-bridge (0.2s vs 0.6s average)
            bridge_devices = bridge_devices[:1]
            total_available = len([dev for dev in g.ncync_server.tcp_devices.values() if dev and dev.ready_to_control])
            logger.debug(
                "%s [%s] Using %d bridge for refresh (oldest of %d available)",
                lp,
                refresh_id,
                len(bridge_devices),
                total_available,
            )

            # Request mesh info from each bridge to refresh all device statuses
            for bridge_device in bridge_devices:
                try:
                    logger.info(
                        "%s [%s] Requesting mesh info from bridge %s",
                        lp,
                        refresh_id,
                        bridge_device.address,
                    )
                    # Pass correlation ID for tracking mesh responses in logs
                    # Parse=True to update device AND group states from mesh_info
                    await bridge_device.ask_for_mesh_info(True, refresh_id=refresh_id)
                    await asyncio.sleep(0.1)  # Small delay between bridge requests
                except Exception as e:
                    logger.warning(
                        "%s [%s] Failed to refresh from bridge %s: %s",
                        lp,
                        refresh_id,
                        bridge_device.address,
                        e,
                    )

        finally:
            self._refresh_in_progress = False

    async def periodic_fast_refresh(self):
        """Fast periodic status refresh every 15 seconds."""
        lp = f"{self.lp}fast_refresh:"
        logger.info("%s Starting fast periodic refresh task (15s interval)...", lp)

        while self._connected:
            try:
                await asyncio.sleep(15)  # Refresh every 15 seconds

                if not self._connected:
                    break

                await self.trigger_status_refresh()

            except asyncio.CancelledError:
                logger.info("%s Fast refresh task cancelled", lp)
                break
            except Exception:
                logger.exception("%s Error in fast refresh", lp)
                await asyncio.sleep(15)  # Wait before retrying on error
