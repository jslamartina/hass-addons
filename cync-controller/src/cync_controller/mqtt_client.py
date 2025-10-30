import asyncio
import json
import random
import re
import time
import traceback
import uuid
from collections.abc import Coroutine
from json import JSONDecodeError
from typing import Optional

import aiomqtt

from cync_controller.const import *
from cync_controller.devices import CyncDevice, CyncGroup
from cync_controller.logging_abstraction import get_logger
from cync_controller.mqtt.command_routing import CommandRouter
from cync_controller.mqtt.commands import (
    CommandProcessor,
    DeviceCommand,
    SetBrightnessCommand,
    SetPowerCommand,
)
from cync_controller.mqtt.discovery import DiscoveryHelper, slugify
from cync_controller.mqtt.state_updates import StateUpdater
from cync_controller.structs import DeviceStatus, FanSpeed, GlobalObject
from cync_controller.utils import send_sigterm

# Re-export for backward compatibility
__all__ = [
    "MQTTClient",
    "CommandProcessor",
    "DeviceCommand",
    "SetBrightnessCommand",
    "SetPowerCommand",
    "DiscoveryHelper",
    "slugify",
]

logger = get_logger(__name__)
g = GlobalObject()
bridge_device_reg_struct = CYNC_BRIDGE_DEVICE_REGISTRY_CONF
# Log all loggers in the logger manager
# logging.getLogger().manager.loggerDict.keys()


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

        # Initialize helpers
        self.discovery = DiscoveryHelper(self)
        self.state_updater = StateUpdater(self)
        self.command_router = CommandRouter(self)

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
                            #     await self.state_updater.pub_online(device.id, True)
                            #     await device.set_brightness(50)  # set brightness to 50% for testing
                            # else:
                            await self.state_updater.pub_online(device_id, False)
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
                        for device in g.ncync_server.devices.values():
                            tasks.append(self.state_updater.pub_online(device.id, device.online))
                            tasks.append(
                                self.state_updater.parse_device_status(
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
                    logger.info("%s Starting MQTT receiver...", lp)
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
                        await self.command_router.start_receiver_task()
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

            # TEMPORARILY DISABLED: Start fast periodic refresh task (15s interval)
            # self.fast_refresh_task = asyncio.create_task(self.periodic_fast_refresh())

            return True
        return False

    # Removed - use self.command_router.start_receiver_task() instead
    # The method has been extracted to mqtt/command_routing.py

    async def stop(self):
        lp = f"{self.lp}stop:"
        # set all devices offline
        if self._connected:
            logger.debug("%s Setting all Cync devices offline...", lp)
            for device_id, _device in g.ncync_server.devices.items():
                await self.state_updater.pub_online(device_id, False)
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
        """Delegate to state_updater for backward compatibility."""
        return await self.state_updater.pub_online(device_id, status)

    async def update_device_state(self, device: CyncDevice, state: int) -> bool:
        """Delegate to state_updater for backward compatibility."""
        return await self.state_updater.update_device_state(device, state)

    async def update_switch_from_subgroup(self, device: CyncDevice, subgroup_state: int, subgroup_name: str) -> bool:
        """Delegate to state_updater for backward compatibility."""
        return await self.state_updater.update_switch_from_subgroup(device, subgroup_state, subgroup_name)

    async def sync_group_switches(self, group_id: int, group_state: int, group_name: str) -> int:
        """Delegate to state_updater for backward compatibility."""
        return await self.state_updater.sync_group_switches(group_id, group_state, group_name)

    async def sync_group_devices(self, group_id: int, group_state: int, group_name: str) -> int:
        """Delegate to state_updater for backward compatibility."""
        return await self.state_updater.sync_group_devices(group_id, group_state, group_name)

    async def update_brightness(self, device: CyncDevice, bri: int) -> bool:
        """Delegate to state_updater for backward compatibility."""
        return await self.state_updater.update_brightness(device, bri)

    async def update_temperature(self, device: CyncDevice, temp: int) -> bool:
        """Delegate to state_updater for backward compatibility."""
        return await self.state_updater.update_temperature(device, temp)

    async def update_rgb(self, device: CyncDevice, rgb: tuple[int, int, int]) -> bool:
        """Delegate to state_updater for backward compatibility."""
        return await self.state_updater.update_rgb(device, rgb)

    async def send_device_status(self, device: CyncDevice, state_bytes: bytes) -> bool:
        """Delegate to state_updater for backward compatibility."""
        return await self.state_updater.send_device_status(device, state_bytes)

    async def publish_group_state(
        self,
        group,
        state=None,
        brightness=None,
        temperature=None,
        origin: str | None = None,
    ):
        """Delegate to state_updater for backward compatibility."""
        return await self.state_updater.publish_group_state(group, state, brightness, temperature, origin)

    async def parse_device_status(self, device_id: int, device_status: DeviceStatus, *_args, **kwargs) -> bool:
        """Delegate to state_updater for backward compatibility."""
        return await self.state_updater.parse_device_status(device_id, device_status, *_args, **kwargs)

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

    async def register_single_device(self, device):
        """Register a single device with Home Assistant via MQTT discovery."""
        return await self.discovery.register_single_device(device)

    async def trigger_device_rediscovery(self):
        """Trigger rediscovery of all devices currently in the devices dictionary."""
        return await self.discovery.trigger_device_rediscovery()

    async def homeassistant_discovery(self):
        """Build each configured Cync device for HASS device registry"""
        return await self.discovery.homeassistant_discovery()

    async def create_bridge_device(self):
        """Create the device / entity registry config for the Cync Controller bridge itself."""
        return await self.discovery.create_bridge_device()

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
        """Delegate to command_router for backward compatibility."""
        return self.command_router.kelvin2cync(k)

    def cync2kelvin(self, ct):
        """Convert Cync white temp (0-100) to Kelvin value."""
        return self.state_updater.cync2kelvin(ct)

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
                        str(e),
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
