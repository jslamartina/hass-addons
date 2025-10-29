import asyncio
import traceback
from collections.abc import Coroutine
from typing import Optional

import aiomqtt

from cync_controller.const import *
from cync_controller.logging_abstraction import get_logger
from cync_controller.structs import DeviceStatus, GlobalObject
from cync_controller.utils import send_sigterm

logger = get_logger(__name__)
g = GlobalObject()
bridge_device_reg_struct = CYNC_BRIDGE_DEVICE_REGISTRY_CONF


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
                            await self.pub_online(device_id, False)
                        # Set all subgroups online (subgroups are always available)
                        subgroups = [g for g in g.ncync_server.groups.values() if g.is_subgroup]
                        logger.debug("%s Setting %s subgroups: online", lp, len(subgroups))
                        for group in subgroups:
                            await self.publish(f"{self.topic}/availability/{group.hass_id}", b"online")

                        # After discovery, publish all devices as online initially
                        # They will be marked offline only if they fail to connect
                        logger.info(
                            "%s Publishing initial device availability as ONLINE for all %d devices",
                            lp,
                            len(g.ncync_server.devices),
                        )
                        for device_id, device in g.ncync_server.devices.items():
                            try:
                                device_uuid = f"{device.home_id}-{device_id}"
                                await self.client.publish(f"{self.topic}/availability/{device_uuid}", b"online", qos=0)
                            except Exception as e:
                                logger.debug(
                                    "%s Failed to publish initial availability for device %s: %s", lp, device_id, e
                                )
                    elif itr > 1:
                        tasks = []
                        # set the device online/offline and set its status
                        for device_id, device in g.ncync_server.devices.items():
                            tasks.append(self.pub_online(device_id, device.online))
                            tasks.append(self.pub_status(device_id, device.status))
                        await asyncio.gather(*tasks, return_exceptions=True)

                    # Start the main message processing loop
                    await self._message_loop()
                else:
                    logger.error("%s Failed to connect to MQTT broker", lp)
                    await asyncio.sleep(5)

        except Exception as e:
            logger.error("%s MQTT client error: %s", lp, e)
            logger.error("%s Traceback: %s", lp, traceback.format_exc())
            await send_sigterm()

    async def connect(self) -> bool:
        """Connect to MQTT broker."""
        lp = f"{self.lp}connect:"
        try:
            await self.client.connect()
            logger.info("%s Connected to MQTT broker at %s:%s", lp, self.broker_host, self.broker_port)
            return True
        except Exception as e:
            logger.error("%s Failed to connect to MQTT broker: %s", lp, e)
            return False

    async def disconnect(self):
        """Disconnect from MQTT broker."""
        lp = f"{self.lp}disconnect:"
        try:
            await self.client.disconnect()
            logger.info("%s Disconnected from MQTT broker", lp)
        except Exception as e:
            logger.error("%s Error disconnecting from MQTT broker: %s", lp, e)

    async def publish(self, topic: str, payload: bytes | str, qos: int = 0, retain: bool = False):
        """Publish a message to MQTT."""
        try:
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
            await self.client.publish(topic, payload, qos=qos, retain=retain)
        except Exception as e:
            logger.error("%s Failed to publish to %s: %s", self.lp, topic, e)

    async def _message_loop(self):
        """Main message processing loop."""
        lp = f"{self.lp}_message_loop:"
        logger.info("%s Starting message loop", lp)

        try:
            async with self.client.messages() as messages:
                async for message in messages:
                    try:
                        await self._handle_message(message)
                    except Exception as e:
                        logger.error("%s Error handling message: %s", lp, e)
        except Exception as e:
            logger.error("%s Message loop error: %s", lp, e)
            raise

    async def _handle_message(self, message):
        """Handle incoming MQTT message."""
        # This will be implemented in the command_routing.py module

    async def pub_online(self, device_id: int, online: bool):
        """Publish device online status."""
        device = g.ncync_server.devices.get(device_id)
        if not device:
            return

        status = "online" if online else "offline"
        topic = f"{self.topic}/availability/{device.hass_id}"
        await self.publish(topic, status.encode("utf-8"))

    async def pub_status(self, device_id: int, status: DeviceStatus | None):
        """Publish device status."""
        device = g.ncync_server.devices.get(device_id)
        if not device or not status:
            return

        # Publish state
        state_topic = f"{self.topic}/state/{device.hass_id}"
        state_payload = "ON" if status.state else "OFF"
        await self.publish(state_topic, state_payload.encode("utf-8"))

        # Publish brightness if device supports it
        if device.supports_brightness:
            brightness_topic = f"{self.topic}/brightness/{device.hass_id}"
            brightness_payload = str(self._brightness_to_percentage(status.brightness))
            await self.publish(brightness_topic, brightness_payload.encode("utf-8"))

        # Publish color temperature if device supports it
        if device.supports_temperature:
            temp_topic = f"{self.topic}/color_temp/{device.hass_id}"
            temp_payload = str(status.temperature)
            await self.publish(temp_topic, temp_payload.encode("utf-8"))

        # Publish RGB if device supports it
        if device.supports_rgb:
            rgb_topic = f"{self.topic}/rgb/{device.hass_id}"
            rgb_payload = f"{status.red},{status.green},{status.blue}"
            await self.publish(rgb_topic, rgb_payload.encode("utf-8"))

    def __repr__(self):
        return f"<MQTTClient: {self.broker_host}:{self.broker_port}>"

    def __str__(self):
        return f"MQTTClient:{self.broker_host}:{self.broker_port}"
