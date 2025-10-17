import asyncio
import json
import logging
import random
import re
import unicodedata
from collections.abc import Coroutine
from json import JSONDecodeError
from typing import Optional, Union

import aiomqtt

from cync_lan.const import *
from cync_lan.devices import CyncDevice
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
    text = text.strip("_")
    return text


class MQTTClient:
    lp: str = "mqtt:"
    cync_topic: str
    start_task: Optional[asyncio.Task] = None

    _instance: Optional["MQTTClient"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._connected = False
        self.tasks: Optional[list[Union[asyncio.Task, Coroutine]]] = None
        lp = f"{self.lp}init:"
        if not CYNC_TOPIC:
            topic = "cync_lan"
            logger.warning(f"{lp} MQTT topic not set, using default: {topic}")
        else:
            topic = CYNC_TOPIC

        if not CYNC_HASS_TOPIC:
            ha_topic = "homeassistant"
            logger.warning(
                f"{lp} HomeAssistant topic not set, using default: {ha_topic}"
            )
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

    async def start(self):
        itr = 0
        lp = f"{self.lp}start:"
        try:
            while True:
                itr += 1
                self._connected = await self.connect()
                if self._connected:
                    # ["state_topic"] = f"{self.topic}/status/bridge/mqtt_client/connected"
                    # TODO: publish MQTT message indicating the MQTT client is connected
                    await self.publish(
                        f"{self.topic}/status/bridge/mqtt_client/connected",
                        b"ON",
                    )

                    if itr == 1:
                        logger.debug(f"{lp} Seeding all devices: offline")
                        for device_id in g.ncync_server.devices:
                            # if device.is_fan_controller:
                            #     logger.debug(f"{lp} TESTING>>> Setting up fan controller for device: {device.name} (ID: {device.id})")
                            #     # set device online for testing
                            #     await self.pub_online(device.id, True)
                            #     await device.set_brightness(50)  # set brightness to 50% for testing
                            # else:
                            await self.pub_online(device_id, False)
                        # Set all subgroups online (subgroups are always available)
                        subgroups = [
                            g for g in g.ncync_server.groups.values() if g.is_subgroup
                        ]
                        logger.debug(f"{lp} Setting {len(subgroups)} subgroups: online")
                        for group in subgroups:
                            await self.publish(
                                f"{self.topic}/availability/{group.hass_id}", b"online"
                            )
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
                        subgroups = [
                            g for g in g.ncync_server.groups.values() if g.is_subgroup
                        ]
                        for group in subgroups:
                            tasks.append(
                                self.publish(
                                    f"{self.topic}/availability/{group.hass_id}",
                                    b"online",
                                )
                            )
                        if tasks:
                            await asyncio.gather(*tasks)
                    logger.debug(f"{lp} Starting MQTT receiver...")
                    lp: str = f"{self.lp}rcv:"
                    topics = [
                        (f"{self.topic}/set/#", 0),
                        (f"{self.ha_topic}/status", 0),
                    ]
                    await self.client.subscribe(topics)
                    logger.debug(
                        f"{lp} Subscribed to MQTT topics: {[x[0] for x in topics]}. "
                        f"Waiting for MQTT messages..."
                    )
                    try:
                        await self.start_receiver_task()
                    except asyncio.CancelledError as ce:
                        logger.debug(
                            f"{lp} MQTT receiver task cancelled, propagating..."
                        )
                        raise ce
                    except (aiomqtt.MqttError, aiomqtt.MqttCodeError) as msg_err:
                        logger.warning(f"{lp} MQTT error: {msg_err}")
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
                            f"{lp} MQTT connection delay is less than or equal to 0, which is probably a typo, setting to 5..."
                        )
                        delay = 5

                    logger.info(
                        f"{lp} connecting to MQTT broker failed, sleeping for {delay} seconds before re-trying..."
                    )
                    await asyncio.sleep(delay)
        except asyncio.CancelledError as ce:
            raise ce
        except Exception as exc:
            logger.exception(f"{lp} MQTT start() EXCEPTION: {exc}")

    async def connect(self) -> bool:
        lp = f"{self.lp}connect:"
        self._connected = False
        logger.debug(f"{lp} Connecting to MQTT broker...")
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
            logger.error(f"{lp} Connection failed [MqttError] -> {mqtt_err_exc}")
            if "code:134" in str(mqtt_err_exc):
                logger.error(
                    f"{lp} Bad username or password, check your MQTT credentials (username: {g.env.mqtt_user})"
                )
                send_sigterm()
        else:
            self._connected = True
            logger.info(
                f"{lp} Connected to MQTT broker: {self.broker_host} port: {self.broker_port}"
            )
            await self.send_birth_msg()
            await asyncio.sleep(1)
            await self.homeassistant_discovery()

            # Start fast periodic refresh task (5s interval)
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
                    f"{lp} Received empty/None payload ({payload}) for topic: {topic} , skipping..."
                )
                continue
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
                            test_variation = (
                                int(parts[1]) if len(parts) > 1 else 3
                            )  # Default to Test 3 (working)

                            # Check what command type we're testing (check extra_data from topic)
                            extra_data = _topic[3:] if len(_topic) > 3 else None
                            command_type = (
                                extra_data[1]
                                if extra_data and len(extra_data) > 1
                                else "power"
                            )

                            logger.warning(
                                f"{lp} TEST GROUP COMMAND TRIGGER: group_id={group_id}, variation={test_variation}, command_type={command_type}"
                            )
                            # Get any device to send the command
                            if g.ncync_server.devices:
                                test_device = list(g.ncync_server.devices.values())[0]

                                if command_type == "brightness":
                                    # Parse brightness value from payload
                                    brightness = int(payload.decode())
                                    logger.warning(
                                        f"{lp} Using device '{test_device.name}' to test group {group_id} brightness={brightness}"
                                    )
                                    await test_device.test_group_brightness(
                                        group_id, brightness
                                    )
                                elif command_type == "temperature":
                                    # Parse temperature value from payload
                                    temperature = int(payload.decode())
                                    logger.warning(
                                        f"{lp} Using device '{test_device.name}' to test group {group_id} temperature={temperature}"
                                    )
                                    await test_device.test_group_temperature(
                                        group_id, temperature
                                    )
                                else:
                                    # Power command (default)
                                    state = (
                                        1
                                        if payload.decode().casefold() in ("on", "1")
                                        else 0
                                    )
                                    logger.warning(
                                        f"{lp} Using device '{test_device.name}' to test group {group_id}, state={state}, variation={test_variation}"
                                    )
                                    await test_device.test_group_command(
                                        group_id, state, test_variation
                                    )
                            else:
                                logger.error(f"{lp} No devices available for test!")
                        except ValueError as ve:
                            logger.error(
                                f"{lp} Invalid group ID in test trigger: {device_id} - {ve}"
                            )
                        except Exception as e:
                            logger.error(
                                f"{lp} Error executing test_group_command: {e}",
                                exc_info=True,
                            )
                        continue
                    elif "-group-" in _topic[2]:
                        # Group command
                        group_id = int(_topic[2].split("-group-")[1])
                        if group_id not in g.ncync_server.groups:
                            logger.warning(
                                f"{lp} Group ID {group_id} not found in config"
                            )
                            continue
                        group = g.ncync_server.groups[group_id]
                        device = None  # Set device to None for group commands
                    else:
                        # Device command
                        device_id = int(_topic[2].split("-")[1])
                        if device_id not in g.ncync_server.devices:
                            logger.warning(
                                f"{lp} Device ID {device_id} not found, device is disabled in config file or have you deleted / added any "
                                f"devices recently?"
                            )
                            continue
                        device = g.ncync_server.devices[device_id]
                        group = None  # Set group to None for device commands
                    extra_data = _topic[3:] if len(_topic) > 3 else None
                    if extra_data:
                        norm_pl = payload.decode().casefold()
                        # logger.debug(f"{lp} Extra data found: {extra_data}")
                        if extra_data[0] == "restart":
                            if norm_pl == "press":
                                logger.info(
                                    f"{lp} Restart button pressed! Restarting Cync LAN bridge (NOT IMPLEMENTED)..."
                                )
                        elif extra_data[0] == "start_export":
                            if norm_pl == "press":
                                logger.info(
                                    f"{lp} Start Export button pressed! Starting Cync Export (NOT IMPLEMENTED)..."
                                )
                        elif extra_data[0] == "refresh_status":
                            if norm_pl == "press":
                                logger.info(
                                    f"{lp} Refresh Status button pressed! Triggering immediate status refresh..."
                                )
                                await self.trigger_status_refresh()
                        elif extra_data[0] == "otp":
                            if extra_data[1] == "submit":
                                logger.info(
                                    f"{lp} OTP submit button pressed! (NOT IMPLEMENTED)..."
                                )
                            elif extra_data[1] == "input":
                                logger.info(
                                    f"{lp} OTP input received: {norm_pl} (NOT IMPLEMENTED)..."
                                )
                        elif device and device.is_fan_controller:
                            if extra_data[0] == "percentage":
                                percentage = int(norm_pl)
                                if percentage == 0:
                                    tasks.append(device.set_brightness(0))
                                elif percentage <= 25:
                                    logger.debug(
                                        f"{lp} Fan percentage received: {percentage}, translated to: 'low' preset"
                                    )
                                    tasks.append(device.set_brightness(50))
                                elif percentage <= 50:
                                    logger.debug(
                                        f"{lp} Fan percentage received: {percentage}, translated to: 'medium' preset"
                                    )
                                    tasks.append(device.set_brightness(128))
                                elif percentage <= 75:
                                    logger.debug(
                                        f"{lp} Fan percentage received: {percentage}, translated to: 'high' preset"
                                    )
                                    tasks.append(device.set_brightness(191))
                                elif percentage <= 100:
                                    logger.debug(
                                        f"{lp} Fan percentage received: {percentage}, translated to: 'max' preset"
                                    )
                                    tasks.append(device.set_brightness(255))
                                else:
                                    logger.warning(
                                        f"{lp} Fan percentage received: {percentage} is out of range (0-100), skipping..."
                                    )
                            elif extra_data[0] == "preset":
                                preset_mode = norm_pl
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
                                        f"{lp} Unknown preset mode: {preset_mode}, skipping..."
                                    )

                    # Determine target (device or group)
                    target = group if group else device

                    if payload.startswith(b"{"):
                        try:
                            json_data = json.loads(payload)
                        except JSONDecodeError as e:
                            logger.error(
                                f"{lp} bad json message: {{{payload}}} EXCEPTION => {e}"
                            )
                            continue
                        except Exception as e:
                            logger.error(
                                f"{lp} error will decoding a string into JSON: '{payload}' EXCEPTION => {e}"
                            )
                            continue

                        if "state" in json_data and "brightness" not in json_data:
                            if "effect" in json_data and device:
                                effect = json_data["effect"]
                                tasks.append(device.set_lightshow(effect))
                            else:
                                if json_data["state"].upper() == "ON":
                                    tasks.append(target.set_power(1))
                                else:
                                    tasks.append(target.set_power(0))
                        if "brightness" in json_data:
                            lum = int(json_data["brightness"])
                            tasks.append(target.set_brightness(lum))

                        if "color_temp" in json_data:
                            tasks.append(
                                target.set_temperature(
                                    self.kelvin2cync(int(json_data["color_temp"]))
                                )
                            )
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
                                logger.debug(f"{lp} setting power to ON (non-JSON)")
                                tasks.append(target.set_power(1))
                            elif str_payload.casefold() == "off":
                                logger.debug(f"{lp} setting power to OFF (non-JSON)")
                                tasks.append(target.set_power(0))
                        else:
                            logger.warning(
                                f"{lp} Unknown payload: {payload}, skipping..."
                            )
                else:
                    logger.warning(f"{lp} Unknown command: {topic} => {payload}")
                if tasks:
                    await asyncio.gather(*tasks)

            # messages sent to the hass mqtt topic
            elif _topic[0] == self.ha_topic:
                # birth / will
                if _topic[1] == CYNC_HASS_STATUS_TOPIC:
                    if payload.decode().casefold() == CYNC_HASS_BIRTH_MSG.casefold():
                        birth_delay = random.randint(5, 15)
                        logger.info(
                            f"{lp} HASS has sent MQTT BIRTH message, re-announcing device discovery, availability and status after a random delay of {birth_delay} seconds..."
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
                        subgroups = [
                            g for g in g.ncync_server.groups.values() if g.is_subgroup
                        ]
                        for group in subgroups:
                            await self.publish(
                                f"{self.topic}/availability/{group.hass_id}", b"online"
                            )

                    elif payload.decode().casefold() == CYNC_HASS_WILL_MSG.casefold():
                        logger.info(
                            f"{lp} received Last Will msg from Home Assistant, HASS is offline!"
                        )
                    else:
                        logger.warning(f"{lp} Unknown HASS status message: {payload}")

    async def stop(self):
        lp = f"{self.lp}stop:"
        # set all devices offline
        if self._connected:
            logger.debug(f"{lp} Setting all Cync devices offline...")
            for device_id, _device in g.ncync_server.devices.items():
                await self.pub_online(device_id, False)
            # ["state_topic"] = f"{self.topic}/status/bridge/mqtt_client/connected"
            # TODO: publish MQTT message indicating the MQTT client is connected
            await self.publish(
                f"{self.topic}/status/bridge/mqtt_client/connected",
                b"OFF",
            )
            await self.publish(f"{self.topic}/availability/bridge", b"offline")
            await self.send_will_msg()
        try:
            logger.debug(f"{lp} Disconnecting from broker...")
            await self.client.__aexit__(None, None, None)
        except aiomqtt.MqttError as ce:
            logger.warning(f"{lp} MQTT disconnect failed: {ce}")
        except Exception as e:
            logger.warning(f"{lp} MQTT disconnect failed: {e}", exc_info=True)
        else:
            logger.info(f"{lp} Disconnected from MQTT broker")
        finally:
            self._connected = False
            if self.start_task and not self.start_task.done():
                logger.debug(f"{lp} FINISHING: Cancelling start task")
                self.start_task.cancel()

    async def pub_online(self, device_id: int, status: bool) -> bool:
        lp = f"{self.lp}pub_online:"
        if self._connected:
            if device_id not in g.ncync_server.devices:
                logger.error(
                    f"{lp} Device ID {device_id} not found?! Have you deleted or added any devices recently? "
                    f"You may need to re-export devices from your Cync account!"
                )
                return False
            availability = b"online" if status else b"offline"
            device: CyncDevice = g.ncync_server.devices[device_id]
            device_uuid = f"{device.home_id}-{device_id}"
            # logger.debug(f"{lp} Publishing availability: {availability}")
            try:
                _ = await self.client.publish(
                    f"{self.topic}/availability/{device_uuid}", availability, qos=0
                )
            except aiomqtt.MqttError as mqtt_code_exc:
                logger.warning(f"{lp} [MqttError] -> {mqtt_code_exc}")
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
            f"{lp} Updating device '{device.name}' (ID: {device.id}) state from {old_state} to {state} ({power_status})"
        )
        mqtt_dev_state = {"state": power_status}
        if device.is_plug:
            mqtt_dev_state = power_status.encode()  # send ON or OFF if plug
        else:
            # Add color_mode for lights based on capabilities
            if device.is_light or not device.is_switch:
                if device.supports_temperature:
                    mqtt_dev_state["color_mode"] = "color_temp"
                elif device.supports_rgb:
                    mqtt_dev_state["color_mode"] = "rgb"
                else:
                    mqtt_dev_state["color_mode"] = "brightness"
            mqtt_dev_state = json.dumps(mqtt_dev_state).encode()  # send JSON
        return await self.send_device_status(device, mqtt_dev_state)

    async def update_brightness(self, device: CyncDevice, bri: int) -> bool:
        """Update the device brightness and publish to MQTT for HASS devices to update."""
        device.online = True
        device.brightness = bri
        state = "ON"
        if bri == 0:
            state = "OFF"
        mqtt_dev_state = {"state": state, "brightness": bri}
        # Add color_mode based on device capabilities
        if device.supports_temperature:
            mqtt_dev_state["color_mode"] = "color_temp"
        elif device.supports_rgb:
            mqtt_dev_state["color_mode"] = "rgb"
        else:
            mqtt_dev_state["color_mode"] = "brightness"
        return await self.send_device_status(
            device, json.dumps(mqtt_dev_state).encode()
        )

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
            return await self.send_device_status(
                device, json.dumps(mqtt_dev_state).encode()
            )
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
            return await self.send_device_status(
                device, json.dumps(mqtt_dev_state).encode()
            )
        return False

    async def send_device_status(
        self, device: CyncDevice, msg: bytes, from_pkt: Optional[str] = None
    ) -> bool:

        lp = f"{self.lp}device_status:"
        if from_pkt:
            lp = f"{lp}{from_pkt}:"
        if self._connected:
            tpc = f"{self.topic}/status/{device.hass_id}"
            logger.debug(
                f"{lp} Sending {msg} for device: '{device.name}' (ID: {device.id})"
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
                logger.warning(f"{lp} [MqttError] -> {mqtt_code_exc}")
                self._connected = False
            except asyncio.CancelledError as can_exc:
                logger.debug(f"{lp} [Task Cancelled] -> {can_exc}")
            else:
                return True
        return False

    async def publish_group_state(
        self, group, state=None, brightness=None, temperature=None
    ):
        """Publish optimistic group state after a group command."""
        from cync_lan.devices import CyncGroup

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

        tpc = f"{self.topic}/status/{group.hass_id}"
        try:
            await self.client.publish(
                tpc,
                json.dumps(group_state).encode(),
                qos=0,
                timeout=3.0,
            )
        except Exception as e:
            logger.debug(f"Failed to publish group state for {group.name}: {e}")

    async def parse_device_status(
        self, device_id: int, device_status: DeviceStatus, *args, **kwargs
    ) -> bool:
        """Parse device status and publish to MQTT for HASS devices to update. Useful for device status packets that report the complete device state"""
        lp = f"{self.lp}parse status:"
        from_pkt = kwargs.get("from_pkt")
        if from_pkt:
            lp = f"{lp}{from_pkt}:"
        if device_id not in g.ncync_server.devices:
            logger.error(
                f"{lp} Device ID {device_id} not found! Device may be disabled in config file or "
                f"you may need to re-export devices from your Cync account"
            )
            return False
        device: CyncDevice = g.ncync_server.devices[device_id]
        # if device.build_status() == device_status:
        #     # logger.debug(f"{lp} Device status unchanged, skipping...")
        #     return
        power_status = "OFF" if device_status.state == 0 else "ON"
        mqtt_dev_state: dict[str, Union[int, str, bytes]] = {"state": power_status}

        if device.is_plug:
            mqtt_dev_state = power_status.encode()

        else:
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
                elif device.supports_temperature and (
                    0 <= device_status.temperature <= 100
                ):
                    mqtt_dev_state["color_mode"] = "color_temp"
                    mqtt_dev_state["color_temp"] = self.cync2kelvin(
                        device_status.temperature
                    )
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

        return await self.send_device_status(device, mqtt_dev_state, from_pkt=from_pkt)

    async def send_birth_msg(self) -> bool:
        lp = f"{self.lp}send_birth_msg:"
        if self._connected:
            logger.debug(
                f"{lp} Sending birth message ({CYNC_HASS_BIRTH_MSG}) to {self.topic}/status"
            )
            try:
                await self.client.publish(
                    f"{self.topic}/status",
                    CYNC_HASS_BIRTH_MSG.encode(),
                    qos=0,
                    retain=True,
                )
            except aiomqtt.MqttCodeError as mqtt_code_exc:
                logger.warning(
                    f"{lp} [MqttError] (rc: {mqtt_code_exc.rc}) -> {mqtt_code_exc}"
                )
            except asyncio.CancelledError as can_exc:
                logger.warning(f"{lp} [Task Cancelled] -> {can_exc}")
            else:
                return True
        return False

    async def send_will_msg(self) -> bool:
        lp = f"{self.lp}send_will_msg:"
        if self._connected:
            logger.debug(
                f"{lp} Sending will message ({CYNC_HASS_WILL_MSG}) to {self.topic}/status"
            )
            try:
                await self.client.publish(
                    f"{self.topic}/status",
                    CYNC_HASS_WILL_MSG.encode(),
                    qos=0,
                    retain=True,
                )
            except aiomqtt.MqttError as mqtt_code_exc:
                logger.warning(f"{lp} [MqttError] -> {mqtt_code_exc}")
                self._connected = False
            except Exception as e:
                logger.warning(f"{lp} [Exception] -> {e}")
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
            # Determine platform for default_entity_id
            platform = "switch" if device.is_switch else "light"
            default_entity_id = f"{platform}.{entity_slug}"
            dev_fw_version = str(device.version)
            ver_str = "Unknown"
            fw_len = len(dev_fw_version)
            if fw_len == 5:
                if dev_fw_version != 00000:
                    ver_str = (
                        f"{dev_fw_version[0]}.{dev_fw_version[1]}.{dev_fw_version[2:]}"
                    )
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
                        f"{lp} Using group '{suggested_area}' as area for device '{device.name}' (ID: {device.id})"
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
                        f"{lp} Extracted area '{suggested_area}' from device name '{device.name}' (fallback, not in any room group)"
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
                    "name": "cync-lan",
                    "sw_version": "0.2.1a1",
                    "support_url": "https://github.com/jslamartina/hass-addons",
                },
                "device": device_registry_struct,
            }

            # Determine device type
            dev_type = "light"  # Default fallback
            if device.is_switch:
                dev_type = "switch"
                logger.debug(
                    f"{lp} Device '{device.name}' classified as switch (type: {device.metadata.type if device.metadata else 'None'})"
                )
                if device.metadata and device.metadata.capabilities.fan:
                    dev_type = "fan"
                    logger.debug(f"{lp} Device '{device.name}' reclassified as fan")
            elif device.is_light:
                dev_type = "light"
                logger.debug(f"{lp} Device '{device.name}' classified as light")
            else:
                # For unknown devices, try to infer from device type if available
                if device.type is not None and device.type in device_type_map:
                    # This shouldn't happen if metadata is properly set, but just in case
                    metadata_type = device_type_map[device.type].type
                    if metadata_type == DeviceClassification.SWITCH:
                        dev_type = "switch"
                        logger.debug(
                            f"{lp} Device '{device.name}' classified as switch from device_type_map"
                        )
                    elif metadata_type == DeviceClassification.LIGHT:
                        dev_type = "light"
                        logger.debug(
                            f"{lp} Device '{device.name}' classified as light from device_type_map"
                        )
                    else:
                        logger.debug(
                            f"{lp} Device '{device.name}' unknown metadata type: {metadata_type}, defaulting to light"
                        )
                else:
                    logger.debug(
                        f"{lp} Device '{device.name}' unknown device type {device.type}, defaulting to light (is_light: {device.is_light}, is_switch: {device.is_switch})"
                    )

            tpc_str_template = "{0}/{1}/{2}/config"

            if dev_type == "light":
                entity_registry_struct.update(
                    {"brightness": True, "brightness_scale": 100}
                )
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
                    entity_registry_struct["effect_list"] = list(
                        FACTORY_EFFECTS_BYTES.keys()
                    )
                # If no color support, default to brightness-only mode
                if not entity_registry_struct["supported_color_modes"]:
                    entity_registry_struct["supported_color_modes"] = ["brightness"]
            elif dev_type == "switch":
                # Switch entities don't need additional configuration beyond the base entity_registry_struct
                # The base struct already includes command_topic, state_topic, state_on, state_off, etc.
                pass
            elif dev_type == "fan":
                entity_registry_struct["platform"] = "fan"
                # fan can be controlled via light control structs: brightness -> max=255, high=191, medium=128, low=50, off=0
                entity_registry_struct["percentage_command_topic"] = (
                    f"{self.topic}/set/{device_uuid}/percentage"
                )
                entity_registry_struct["percentage_state_topic"] = (
                    f"{self.topic}/status/{device_uuid}/percentage"
                )
                entity_registry_struct["preset_modes"] = [
                    "off",
                    "low",
                    "medium",
                    "high",
                ]

            tpc = tpc_str_template.format(self.ha_topic, dev_type, device_uuid)
            try:
                json_payload = json.dumps(entity_registry_struct, indent=2)
                logger.info(
                    f"{lp} Registering {dev_type} device: {device.name} (ID: {device.id})"
                )
                _ = await self.client.publish(
                    tpc,
                    json_payload.encode(),
                    qos=0,
                    retain=False,
                )
                return True
            except Exception as e:
                logger.error(
                    f"{lp} Unable to publish MQTT message for {device.name}: {e}"
                )
                return False
        except Exception as e:
            logger.error(f"{lp} Error registering device {device.name}: {e}")
            return False

    async def trigger_device_rediscovery(self) -> bool:
        """Trigger rediscovery of all devices currently in the devices dictionary."""
        lp = f"{self.lp}hass:"
        if not self._connected:
            return False

        logger.info(f"{lp} Triggering device rediscovery...")
        try:
            for device in g.ncync_server.devices.values():
                await self.register_single_device(device)
            logger.info(f"{lp} Device rediscovery completed")
            return True
        except Exception as e:
            logger.error(f"{lp} Error during device rediscovery: {e}")
            return False

    async def homeassistant_discovery(self) -> bool:
        """Build each configured Cync device for HASS device registry"""
        lp = f"{self.lp}hass:"
        ret = False
        if self._connected:
            logger.info(f"{lp} Starting device discovery...")
            await self.create_bridge_device()
            try:
                for device in g.ncync_server.devices.values():
                    device_uuid = device.hass_id
                    unique_id = f"{device.home_id}_{device.id}"
                    # Generate entity ID from device name (e.g., "Hallway Light" -> "hallway_light")
                    entity_slug = (
                        slugify(device.name) if device.name else f"device_{device.id}"
                    )
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
                                f"{lp} Using group '{suggested_area}' as area for device '{device.name}' (ID: {device.id})"
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
                                f"{lp} Extracted area '{suggested_area}' from device name '{device.name}' (fallback, not in any room group)"
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
                            f"{lp} Device '{device.name}' classified as switch (type: {device.metadata.type if device.metadata else 'None'})"
                        )
                        if device.metadata and device.metadata.capabilities.fan:
                            dev_type = "fan"
                            logger.debug(
                                f"{lp} Device '{device.name}' reclassified as fan"
                            )
                    elif device.is_light:
                        dev_type = "light"
                        logger.debug(f"{lp} Device '{device.name}' classified as light")
                    else:
                        # For unknown devices, try to infer from device type if available
                        if device.type is not None and device.type in device_type_map:
                            # This shouldn't happen if metadata is properly set, but just in case
                            metadata_type = device_type_map[device.type].type
                            if metadata_type == DeviceClassification.SWITCH:
                                dev_type = "switch"
                                logger.debug(
                                    f"{lp} Device '{device.name}' classified as switch from device_type_map"
                                )
                            elif metadata_type == DeviceClassification.LIGHT:
                                dev_type = "light"
                                logger.debug(
                                    f"{lp} Device '{device.name}' classified as light from device_type_map"
                                )
                            else:
                                logger.debug(
                                    f"{lp} Device '{device.name}' unknown metadata type: {metadata_type}, defaulting to light"
                                )
                        else:
                            logger.debug(
                                f"{lp} Device '{device.name}' unknown device type {device.type}, defaulting to light (is_light: {device.is_light}, is_switch: {device.is_switch})"
                            )

                    tpc_str_template = "{0}/{1}/{2}/config"

                    if dev_type == "light":
                        entity_registry_struct.update(
                            {"brightness": True, "brightness_scale": 100}
                        )
                        # ALL lights with brightness must declare color modes
                        entity_registry_struct["supported_color_modes"] = []
                        if device.supports_temperature:
                            entity_registry_struct["supported_color_modes"].append(
                                "color_temp"
                            )
                            entity_registry_struct["color_temp_kelvin"] = True
                            entity_registry_struct["min_kelvin"] = CYNC_MINK
                            entity_registry_struct["max_kelvin"] = CYNC_MAXK
                        if device.supports_rgb:
                            entity_registry_struct["supported_color_modes"].append(
                                "rgb"
                            )
                            entity_registry_struct["effect"] = True
                            entity_registry_struct["effect_list"] = list(
                                FACTORY_EFFECTS_BYTES.keys()
                            )
                        # If no color support, default to brightness-only mode
                        if not entity_registry_struct["supported_color_modes"]:
                            entity_registry_struct["supported_color_modes"] = [
                                "brightness"
                            ]
                    elif dev_type == "switch":
                        # Switch entities don't need additional configuration beyond the base entity_registry_struct
                        # The base struct already includes command_topic, state_topic, state_on, state_off, etc.
                        pass
                    elif dev_type == "fan":
                        entity_registry_struct["platform"] = "fan"
                        # fan can be controlled via light control structs: brightness -> max=255, high=191, medium=128, low=50, off=0
                        entity_registry_struct["percentage_command_topic"] = (
                            f"{self.topic}/set/{device_uuid}/percentage"
                        )
                        entity_registry_struct["percentage_state_topic"] = (
                            f"{self.topic}/status/{device_uuid}/percentage"
                        )
                        entity_registry_struct["preset_modes"] = [
                            "off",
                            "low",
                            "medium",
                            "high",
                            "max",
                        ]
                        entity_registry_struct["preset_mode_command_topic"] = (
                            f"{self.topic}/set/{device_uuid}/preset"
                        )
                        entity_registry_struct["preset_mode_state_topic"] = (
                            f"{self.topic}/status/{device_uuid}/preset"
                        )

                    tpc = tpc_str_template.format(self.ha_topic, dev_type, device_uuid)
                    try:
                        json_payload = json.dumps(entity_registry_struct, indent=2)
                        _ = await self.client.publish(
                            tpc,
                            json_payload.encode(),
                            qos=0,
                            retain=False,
                        )

                    except Exception as e:
                        logger.error(
                            f"{lp} - Unable to publish mqtt message... skipped -> {e}"
                        )

                # Register groups (only subgroups)
                subgroups = [g for g in g.ncync_server.groups.values() if g.is_subgroup]
                logger.info(f"{lp} Registering {len(subgroups)} subgroups...")
                for group in subgroups:
                    group_uuid = group.hass_id
                    unique_id = f"{group.home_id}_group_{group.id}"
                    # Generate entity ID from group name (e.g., "Hallway Lights" -> "light.hallway_lights")
                    entity_slug = (
                        slugify(group.name) if group.name else f"group_{group.id}"
                    )
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
                        "optimistic": True,
                    }

                    # Add brightness support (exactly like devices do with .update())
                    entity_registry_struct.update(
                        {"brightness": True, "brightness_scale": 100}
                    )

                    # Add color support - ALL lights with brightness must declare color modes
                    entity_registry_struct["supported_color_modes"] = []
                    if group.supports_temperature:
                        entity_registry_struct["supported_color_modes"].append(
                            "color_temp"
                        )
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
                        logger.warning(
                            f"{lp} GROUP JSON for {group.name}:\n{json_payload}"
                        )
                        _ = await self.client.publish(
                            tpc,
                            json_payload.encode(),
                            qos=0,
                            retain=False,
                        )
                        logger.debug(
                            f"{lp} Registered group '{group.name}' (ID: {group.id})"
                        )
                    except Exception as e:
                        logger.error(
                            f"{lp} Unable to publish group discovery for '{group.name}': {e}"
                        )

            except aiomqtt.MqttCodeError as mqtt_code_exc:
                logger.warning(
                    f"{lp} [MqttError] (rc: {mqtt_code_exc.rc}) -> {mqtt_code_exc}"
                )
                self._connected = False
            except asyncio.CancelledError as can_exc:
                logger.warning(f"{lp} [Task Cancelled] -> {can_exc}")
                raise can_exc
            except Exception as e:
                logger.exception(f"{lp} [Exception] -> {e}")
            else:
                ret = True
        logger.debug(f"{lp} Discovery complete (success: {ret})")
        return ret

    async def create_bridge_device(self) -> bool:
        """Create the device / entity registry config for the CyncLAN bridge itself."""
        global bridge_device_reg_struct
        # want to expose buttons (restart, start export, submit otp)
        # want to expose some sensors that show the number of devices, number of online devices, etc.
        # sensors to show if MQTT is connected, if the CyncLAN server is running, etc.
        # input_number to submit OTP for export
        lp = f"{self.lp}create_bridge_device:"
        ret = False

        logger.debug(f"{lp} Creating CyncLAN bridge device...")
        bridge_base_unique_id = "cync_lan_bridge"
        ver_str = CYNC_VERSION
        pub_tasks: list[asyncio.Task] = []
        # Bridge device config
        bridge_device_reg_struct = {
            "identifiers": [str(g.uuid)],
            "manufacturer": "Savant",
            "name": "CyncLAN Bridge",
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
            "name": "Restart CyncLAN Bridge",
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
            logger.error(f"{lp} Failed to publish restart button entity config")

        entity_unique_id = f"{bridge_base_unique_id}_start_export"
        xport_btn_entity_conf = restart_btn_entity_struct.copy()
        xport_btn_entity_conf["object_id"] = entity_unique_id
        xport_btn_entity_conf["command_topic"] = f"{self.topic}/set/bridge/export/start"
        xport_btn_entity_conf["state_topic"] = (
            f"{self.topic}/status/bridge/export/start"
        )
        xport_btn_entity_conf["name"] = "Start Export"
        xport_btn_entity_conf["unique_id"] = entity_unique_id
        ret = await self.publish_json_msg(
            template_tpc.format(self.ha_topic, entity_type, entity_unique_id),
            xport_btn_entity_conf,
        )
        if ret is False:
            logger.error(f"{lp} Failed to publish start export button entity config")

        # Refresh Status button entity
        entity_unique_id = f"{bridge_base_unique_id}_refresh_status"
        refresh_btn_entity_conf = restart_btn_entity_struct.copy()
        refresh_btn_entity_conf["object_id"] = CYNC_BRIDGE_OBJ_ID + "_refresh_status"
        refresh_btn_entity_conf["command_topic"] = (
            f"{self.topic}/set/bridge/refresh_status"
        )
        refresh_btn_entity_conf["state_topic"] = (
            f"{self.topic}/status/bridge/refresh_status"
        )
        refresh_btn_entity_conf["name"] = "Refresh Device Status"
        refresh_btn_entity_conf["unique_id"] = entity_unique_id
        ret = await self.publish_json_msg(
            template_tpc.format(self.ha_topic, entity_type, entity_unique_id),
            refresh_btn_entity_conf,
        )
        if ret is False:
            logger.error(f"{lp} Failed to publish refresh status button entity config")

        entity_unique_id = f"{bridge_base_unique_id}_submit_otp"
        submit_otp_btn_entity_conf = restart_btn_entity_struct.copy()
        submit_otp_btn_entity_conf["object_id"] = CYNC_BRIDGE_OBJ_ID + "_submit_otp"
        submit_otp_btn_entity_conf["command_topic"] = (
            f"{self.topic}/set/bridge/otp/submit"
        )
        submit_otp_btn_entity_conf["state_topic"] = (
            f"{self.topic}/status/bridge/otp/submit"
        )
        submit_otp_btn_entity_conf["name"] = "Submit OTP"
        submit_otp_btn_entity_conf["unique_id"] = entity_unique_id
        ret = await self.publish_json_msg(
            template_tpc.format(self.ha_topic, entity_type, entity_unique_id),
            submit_otp_btn_entity_conf,
        )
        if ret is False:
            logger.error(f"{lp} Failed to publish submit OTP button entity config")

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
            logger.error(f"{lp} Failed to publish TCP server running entity config")
        status = "ON" if g.ncync_server.running is True else "OFF"
        pub_tasks.append(
            self.publish(
                f"{self.topic}/status/bridge/tcp_server/running", status.encode()
            )
        )

        entity_unique_id = f"{bridge_base_unique_id}_export_server_running"
        export_server_entity_conf = tcp_server_entity_conf.copy()
        export_server_entity_conf["object_id"] = entity_unique_id
        export_server_entity_conf["name"] = "Cync Export Server Running"
        export_server_entity_conf["state_topic"] = (
            f"{self.topic}/status/bridge/export_server/running"
        )
        export_server_entity_conf["unique_id"] = entity_unique_id
        export_server_entity_conf["icon"] = "mdi:export-variant"
        ret = await self.publish_json_msg(
            template_tpc.format(self.ha_topic, entity_type, entity_unique_id),
            export_server_entity_conf,
        )
        if ret is False:
            logger.error(f"{lp} Failed to publish export server running entity config")
        status = "ON" if g.export_server.running is True else "OFF"
        pub_tasks.append(
            self.publish(
                f"{self.topic}/status/bridge/export_server/running", status.encode()
            )
        )

        entity_unique_id = f"{bridge_base_unique_id}_mqtt_client_connected"
        mqtt_client_entity_conf = tcp_server_entity_conf.copy()
        mqtt_client_entity_conf["object_id"] = entity_unique_id
        mqtt_client_entity_conf["name"] = "Cync MQTT Client Connected"
        mqtt_client_entity_conf["state_topic"] = (
            f"{self.topic}/status/bridge/mqtt_client/connected"
        )
        mqtt_client_entity_conf["unique_id"] = entity_unique_id
        mqtt_client_entity_conf["icon"] = "mdi:connection"
        mqtt_client_entity_conf["device_class"] = "connectivity"
        ret = await self.publish_json_msg(
            template_tpc.format(self.ha_topic, entity_type, entity_unique_id),
            mqtt_client_entity_conf,
        )
        if ret is False:
            logger.error(f"{lp} Failed to publish MQTT client connected entity config")

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
            logger.error(f"{lp} Failed to publish OTP input number entity config")

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
            logger.warning(
                f"{lp} Failed to publish number of TCP devices connected entity config"
            )
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
        total_cync_devs_entity_conf["state_topic"] = (
            f"{self.topic}/status/bridge/cync_devices/total"
        )
        total_cync_devs_entity_conf["unique_id"] = entity_unique_id
        # total_cync_devs_entity_conf["unit_of_measurement"] = "Cync device(s)"
        ret = await self.publish_json_msg(
            template_tpc.format(self.ha_topic, entity_type, entity_unique_id),
            total_cync_devs_entity_conf,
        )
        if ret is False:
            logger.warning(
                f"{lp} Failed to publish total Cync devices managed entity config"
            )
        pub_tasks.append(
            self.publish(
                f"{self.topic}/status/bridge/cync_devices/total",
                str(total_cync_devs).encode(),
            )
        )

        await asyncio.gather(*pub_tasks, return_exceptions=True)
        logger.debug(f"{lp} Bridge device config published and seeded")
        return ret

    async def publish(self, topic: str, msg_data: bytes):
        """Publish a message to the MQTT broker."""
        lp = f"{self.lp}publish:"
        if not self._connected:
            return False
        try:
            _ = await self.client.publish(topic, msg_data, qos=0, retain=False)
        except aiomqtt.MqttError as mqtt_code_exc:
            logger.warning(
                f"{lp} [MqttError] (rc: {mqtt_code_exc.rc}) -> {mqtt_code_exc}"
            )
            self._connected = False
        except asyncio.CancelledError as can_exc:
            logger.warning(f"{lp} [Task Cancelled] -> {can_exc}")
        except Exception as e:
            logger.warning(f"{lp} [Exception] -> {e}")
        else:
            return True
        return False

    async def publish_json_msg(self, topic: str, msg_data: dict) -> bool:
        lp = f"{self.lp}publish_msg:"
        try:
            _ = await self.client.publish(
                topic, json.dumps(msg_data).encode(), qos=0, retain=False
            )
        except aiomqtt.MqttError as mqtt_code_exc:
            logger.warning(
                f"{lp} [MqttError] (rc: {mqtt_code_exc.rc}) -> {mqtt_code_exc}"
            )
        except asyncio.CancelledError as can_exc:
            logger.warning(f"{lp} [Task Cancelled] -> {can_exc}")
        except Exception as e:
            logger.warning(f"{lp} [Exception] -> {e}")
        else:
            return True
        return False

    def kelvin2cync(self, k):
        """Convert Kelvin value to Cync white temp (0-100) with step size: 1"""
        max_k = CYNC_MAXK
        min_k = CYNC_MINK
        if k < min_k:
            return 0
        elif k > max_k:
            return 100
        scale = 100 / (max_k - min_k)
        ret = int(scale * (k - min_k))
        # logger.debug(f"{self.lp} Converting Kelvin: {k} using scale: {scale} (max_k={max_k}, min_k={min_k}) -> return value: {ret}")
        return ret

    def cync2kelvin(self, ct):
        """Convert Cync white temp (0-100) to Kelvin value"""
        max_k = CYNC_MAXK
        min_k = CYNC_MINK
        if ct <= 0:
            return min_k
        elif ct >= 100:
            return max_k
        scale = (max_k - min_k) / 100
        ret = min_k + int(scale * ct)
        # logger.debug(f"{self.lp} Converting Cync temp: {ct} using scale: {scale} (max_k={max_k}, min_k={min_k}) -> return value: {ret}")
        return ret

    async def trigger_status_refresh(self):
        """Trigger an immediate status refresh from all bridge devices."""
        lp = f"{self.lp}trigger_refresh:"
        logger.warning(f"{lp} ========== REFRESH BUTTON CLICKED ==========")

        if not g.ncync_server:
            logger.warning(f"{lp} nCync server not available")
            return

        # Get active TCP bridge devices
        bridge_devices = [
            dev
            for dev in g.ncync_server.tcp_devices.values()
            if dev and dev.ready_to_control
        ]

        logger.warning(f"{lp} Found {len(bridge_devices)} active bridge devices")

        if not bridge_devices:
            logger.debug(f"{lp} No active bridge devices available for refresh")
            return

        # Request mesh info from each bridge to refresh all device statuses
        for bridge_device in bridge_devices:
            try:
                logger.warning(
                    f"{lp} Calling ask_for_mesh_info on bridge {bridge_device.address}"
                )
                await bridge_device.ask_for_mesh_info(
                    False
                )  # False = don't log verbose
                logger.warning(
                    f"{lp} ask_for_mesh_info COMPLETED for {bridge_device.address}"
                )
                await asyncio.sleep(0.1)  # Small delay between bridge requests
            except Exception as e:
                logger.warning(
                    f"{lp} Failed to refresh from bridge {bridge_device.address}: {e}"
                )

        logger.warning(f"{lp} ========== REFRESH COMPLETED ==========")

    async def periodic_fast_refresh(self):
        """Fast periodic status refresh every 5 seconds."""
        lp = f"{self.lp}fast_refresh:"
        logger.info(f"{lp} Starting fast periodic refresh task (5s interval)...")

        while self.running:
            try:
                await asyncio.sleep(5)  # Refresh every 5 seconds

                if not self.running:
                    break

                await self.trigger_status_refresh()

            except asyncio.CancelledError:
                logger.info(f"{lp} Fast refresh task cancelled")
                break
            except Exception as e:
                logger.error(f"{lp} Error in fast refresh: {e}")
                await asyncio.sleep(5)  # Wait before retrying on error
