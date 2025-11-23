"""MQTT client core for Cync Controller.

Provides the main MQTTClient class with connection lifecycle, discovery,
and message routing delegation to helper modules.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import TYPE_CHECKING

import aiomqtt

from cync_controller.const import (
    CYNC_HASS_BIRTH_MSG,
    CYNC_HASS_TOPIC,
    CYNC_HASS_WILL_MSG,
    CYNC_MAXK,
    CYNC_MINK,
    CYNC_MQTT_CONN_DELAY,
    CYNC_MQTT_HOST,
    CYNC_MQTT_PASS,
    CYNC_MQTT_PORT,
    CYNC_MQTT_USER,
    CYNC_TOPIC,
    DEVICE_LWT_MSG,
)
from cync_controller.logging_abstraction import get_logger
from cync_controller.mqtt.command_routing import CommandRouter
from cync_controller.mqtt.discovery import DiscoveryHelper
from cync_controller.mqtt.state_updates import StateUpdateHelper
from cync_controller.structs import DeviceStatus, GlobalObject
from cync_controller.utils import send_sigterm

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from cync_controller.structs import (
        CyncDeviceProtocol,
        CyncGroupProtocol,
        CyncTCPDeviceProtocol,
    )

logger = get_logger(__name__)

# Import g directly from structs to avoid circular dependency with mqtt_client.py
g = GlobalObject()


class MQTTClient:
    """Main MQTT client for Cync Controller with modular helper classes."""

    lp: str = "mqtt:"
    _refresh_in_progress: bool = False
    start_task: asyncio.Task[None] | None = None
    _connected: bool = False
    tasks: list[asyncio.Task[None]] | None = None
    broker_client_id: str = ""
    broker_host: str | None = None
    broker_port: int | None = None
    broker_username: str | None = None
    broker_password: str | None = None
    client: aiomqtt.Client | None = None
    topic: str = ""
    ha_topic: str = ""
    discovery: DiscoveryHelper | None = None
    state_updates: StateUpdateHelper | None = None
    command_router: CommandRouter | None = None

    _instance: MQTTClient | None = None

    def __new__(cls, *_args: object, **_kwargs: object) -> MQTTClient:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Initialize MQTT client (singleton pattern - args/kwargs ignored)."""
        # Skip initialization if already initialized (singleton pattern)
        if hasattr(self, "_connected"):
            return

        self._connected = False
        self.tasks = None
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
        setattr(self, "broker_port", CYNC_MQTT_PORT)  # noqa: B010
        self.broker_username = CYNC_MQTT_USER
        self.broker_password = CYNC_MQTT_PASS
        port = int(self.broker_port) if self.broker_port else 1883
        self.client = aiomqtt.Client(
            hostname=self.broker_host,
            port=port,
            username=self.broker_username,
            password=self.broker_password,
            identifier=self.broker_client_id,
            will=lwt,
            # logger=logger,
        )

        self.topic = topic
        self.ha_topic = ha_topic

        # Initialize helper classes
        self.discovery = DiscoveryHelper(self)
        self.state_updates = StateUpdateHelper(self)
        self.command_router = CommandRouter(self)

    @property
    def is_connected(self) -> bool:
        """Check if MQTT client is connected to the broker."""
        return self._connected

    def set_connected(self, connected: bool) -> None:
        """Set the connection state. Used by helper classes when connection errors occur."""
        self._connected = connected

    def _brightness_to_percentage(self, brightness: int) -> int:
        """Convert Cync brightness (0-255) to Home Assistant percentage (0-100)."""
        return round((brightness / 255) * 100)

    async def _handle_initial_connection(self, lp: str) -> None:
        """Handle initial MQTT connection setup."""
        if not g.ncync_server:
            logger.warning("%s nCync server not available for initial connection", lp)
            return

        logger.debug("%s Seeding all devices: offline", lp)
        assert self.state_updates is not None, "state_updates must be initialized"
        assert self.topic, "topic must be initialized"
        assert self.client is not None, "client must be initialized"

        ncync_server = g.ncync_server
        assert ncync_server is not None
        # Protocol ensures types are known without circular import
        devices: dict[int, CyncDeviceProtocol] = ncync_server.devices
        groups: dict[int, CyncGroupProtocol] = ncync_server.groups

        for device_id in devices:
            _ = await self.state_updates.pub_online(device_id, False)
        subgroups: list[CyncGroupProtocol] = [grp for grp in groups.values() if grp.is_subgroup]
        logger.debug("%s Setting %s subgroups: online", lp, len(subgroups))
        for group in subgroups:
            _ = await self.publish(f"{self.topic}/availability/{group.hass_id}", b"online")

        logger.info(
            "%s Publishing initial device availability as ONLINE for all %d devices",
            lp,
            len(devices),
        )
        for device_id, device in devices.items():
            try:
                device_uuid = f"{device.home_id}-{device_id}"
                await self.client.publish(f"{self.topic}/availability/{device_uuid}", b"online", qos=0)
            except Exception as e:
                logger.debug(
                    "%s Failed to publish initial availability for device %s: %s",
                    lp,
                    device_id,
                    e,
                )

    async def _handle_reconnection(self, _lp: str) -> None:
        """Handle MQTT reconnection setup."""
        if not g.ncync_server:
            logger.warning("%s nCync server not available for reconnection", _lp)
            return

        assert self.state_updates is not None, "state_updates must be initialized"

        ncync_server = g.ncync_server
        assert ncync_server is not None
        # Protocol ensures types are known without circular import
        devices: dict[int, CyncDeviceProtocol] = ncync_server.devices
        groups: dict[int, CyncGroupProtocol] = ncync_server.groups

        tasks: list[asyncio.Task[None] | Coroutine[object, object, bool]] = []
        for device in devices.values():
            assert device.id is not None
            tasks.append(self.state_updates.pub_online(device.id, device.online))
            tasks.append(
                self.state_updates.parse_device_status(
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
                ),
            )
        subgroups: list[CyncGroupProtocol] = [grp for grp in groups.values() if grp.is_subgroup]
        for group in subgroups:
            tasks.append(
                self.publish(
                    f"{self.topic}/availability/{group.hass_id}",
                    b"online",
                ),
            )
        if tasks:
            _ = await asyncio.gather(*tasks)

    async def _start_receiver(self, lp: str) -> None:
        """Start MQTT receiver task."""
        logger.info("%s Starting MQTT receiver...", lp)
        rcv_lp = f"{self.lp}rcv:"
        assert self.client is not None, "client must be initialized"
        assert self.command_router is not None, "command_router must be initialized"
        topics = [
            (f"{self.topic}/set/#", 0),
            (f"{self.ha_topic}/status", 0),
        ]
        # Subscribe to each topic individually to match type stub
        for topic, qos in topics:
            await self.client.subscribe(topic, qos=qos)
        logger.debug(
            "%s Subscribed to MQTT topics: %s. Waiting for MQTT messages...",
            rcv_lp,
            [x[0] for x in topics],
        )
        try:
            await self.command_router.start_receiver_task()
        except asyncio.CancelledError:
            logger.debug("%s MQTT receiver task cancelled, propagating...", rcv_lp)
            raise
        except (aiomqtt.MqttError, aiomqtt.MqttCodeError) as msg_err:
            logger.warning("%s MQTT error: %s", rcv_lp, msg_err)
            raise

    def _get_connection_delay(self, lp: str) -> int:
        """Get connection retry delay, defaulting to 5 seconds."""
        delay = CYNC_MQTT_CONN_DELAY
        if delay <= 0:
            logger.debug(
                "%s MQTT connection delay is less than or equal to 0, which is probably a typo, setting to 5...",
                lp,
            )
            return 5
        return delay

    async def start(self) -> None:
        itr = 0
        lp = f"{self.lp}start:"
        try:
            while True:
                itr += 1
                self._connected = await self.connect()
                if self._connected:
                    _ = await self.publish(
                        f"{self.topic}/status/bridge/mqtt_client/connected",
                        b"ON",
                    )

                    if itr == 1:
                        await self._handle_initial_connection(lp)
                    elif itr > 1:
                        await self._handle_reconnection(lp)

                    try:
                        await self._start_receiver(lp)
                    except (aiomqtt.MqttError, aiomqtt.MqttCodeError):
                        continue
                else:
                    _ = await self.publish(
                        f"{self.topic}/status/bridge/mqtt_client/connected",
                        b"OFF",
                    )
                    delay = self._get_connection_delay(lp)
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
        setattr(self, "broker_port", g.env.mqtt_port)  # noqa: B010
        self.broker_username = g.env.mqtt_user
        self.broker_password = g.env.mqtt_pass
        self.client = aiomqtt.Client(
            hostname=self.broker_host,
            port=int(self.broker_port) if self.broker_port else 1883,
            username=self.broker_username,
            password=self.broker_password,
            identifier=self.broker_client_id,
            will=lwt,
            # logger=logger,
        )
        try:
            _ = await self.client.__aenter__()
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
            _ = await self.send_birth_msg()
            await asyncio.sleep(1)
            _ = await self.homeassistant_discovery()

            # TEMPORARILY DISABLED: Start fast periodic refresh task (15s interval)
            # self.fast_refresh_task = asyncio.create_task(self.periodic_fast_refresh())

            return True
        return False

    async def stop(self) -> None:
        lp = f"{self.lp}stop:"
        # set all devices offline
        if self._connected and g.ncync_server:
            assert self.state_updates is not None, "state_updates must be initialized"
            logger.debug("%s Setting all Cync devices offline...", lp)

            ncync_server = g.ncync_server
            assert ncync_server is not None
            # Protocol ensures types are known without circular import
            devices: dict[int, CyncDeviceProtocol] = ncync_server.devices

            for device_id, _device in devices.items():
                _ = await self.state_updates.pub_online(device_id, False)
            # Publish MQTT message indicating the MQTT client is disconnected
            _ = await self.publish(
                f"{self.topic}/status/bridge/mqtt_client/connected",
                b"OFF",
            )
            _ = await self.publish(f"{self.topic}/availability/bridge", b"offline")
            _ = await self.send_will_msg()
        try:
            assert self.client is not None, "client must be initialized"
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
                _ = self.start_task.cancel()

    async def send_birth_msg(self) -> bool:
        lp = f"{self.lp}send_birth_msg:"
        if self._connected:
            assert self.client is not None, "client must be initialized"
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
                logger.warning("%s [MqttError] -> %s", lp, mqtt_code_exc)
            except asyncio.CancelledError as can_exc:
                logger.warning("%s [Task Cancelled] -> %s", lp, can_exc)
            else:
                return True
        return False

    async def send_will_msg(self) -> bool:
        lp = f"{self.lp}send_will_msg:"
        if self._connected:
            assert self.client is not None, "client must be initialized"
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

    async def publish(self, topic: str, msg_data: bytes) -> bool:
        """Publish a message to the MQTT broker."""
        lp = f"{self.lp}publish:"
        if not self._connected:
            return False
        assert self.client is not None, "client must be initialized"
        try:
            _ = await self.client.publish(topic, msg_data, qos=0, retain=False)
        except aiomqtt.MqttCodeError as mqtt_code_exc:
            logger.warning("%s [MqttCodeError] -> %s", lp, mqtt_code_exc)
            self._connected = False
        except aiomqtt.MqttError as mqtt_err:
            logger.warning("%s [MqttError] -> %s", lp, mqtt_err)
            self._connected = False
        except asyncio.CancelledError as can_exc:
            logger.warning("%s [Task Cancelled] -> %s", lp, can_exc)
        except Exception as e:
            logger.warning("%s [Exception] -> %s", lp, e)
        else:
            return True
        return False

    async def publish_json_msg(self, topic: str, msg_data: dict[str, object]) -> bool:
        lp = f"{self.lp}publish_msg:"
        assert self.client is not None, "client must be initialized"
        try:
            _ = await self.client.publish(topic, json.dumps(msg_data).encode(), qos=0, retain=False)
        except aiomqtt.MqttCodeError as mqtt_code_exc:
            logger.warning("%s [MqttCodeError] -> %s", lp, mqtt_code_exc)
        except aiomqtt.MqttError as mqtt_err:
            logger.warning("%s [MqttError] -> %s", lp, mqtt_err)
        except asyncio.CancelledError as can_exc:
            logger.warning("%s [Task Cancelled] -> %s", lp, can_exc)
        except Exception as e:
            logger.warning("%s [Exception] -> %s", lp, e)
        else:
            return True
        return False

    def kelvin2cync(self, k: float) -> int:
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

    def cync2kelvin(self, ct: int) -> int:
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

    async def trigger_status_refresh(self) -> None:
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

            ncync_server = g.ncync_server
            assert ncync_server is not None
            # Protocol ensures types are known without circular import
            tcp_devices: dict[str, CyncTCPDeviceProtocol | None] = ncync_server.tcp_devices

            # Get active TCP bridge devices
            bridge_devices: list[CyncTCPDeviceProtocol] = [
                dev for dev in tcp_devices.values() if dev is not None and dev.ready_to_control
            ]

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
            total_available = len([dev for dev in tcp_devices.values() if dev is not None and dev.ready_to_control])
            logger.debug(
                "%s [%s] Using %d bridge for refresh (oldest of %d available)",
                lp,
                refresh_id,
                len(bridge_devices),
                total_available,
            )

            # REMOVED: Manual mesh info polling - rely on 0x83 status packets instead
            # Refresh button now triggers optimistic re-sync from cached state
            logger.info("%s [%s] Refresh requested - relying on 0x83 status packets", lp, refresh_id)
            # for bridge_device in bridge_devices:
            #     try:
            #         await bridge_device.ask_for_mesh_info(True, refresh_id=refresh_id)
            #         await asyncio.sleep(0.1)
            #     except Exception as e:
            #         logger.warning("%s [%s] Failed to refresh: %s", lp, refresh_id, str(e))

        finally:
            self._refresh_in_progress = False

    async def periodic_fast_refresh(self) -> None:
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

    # Delegation methods to helper classes
    async def register_single_device(self, device: CyncDeviceProtocol) -> None:
        """Register a single device with Home Assistant via MQTT discovery."""
        assert self.discovery is not None, "discovery must be initialized"
        # CyncDevice structurally implements CyncDeviceProtocol
        _ = await self.discovery.register_single_device(device)  # type: ignore[arg-type]

    async def trigger_device_rediscovery(self) -> None:
        """Trigger rediscovery of all devices currently in the devices dictionary."""
        assert self.discovery is not None, "discovery must be initialized"
        _ = await self.discovery.trigger_device_rediscovery()

    async def homeassistant_discovery(self) -> None:
        """Build each configured Cync device for HASS device registry"""
        assert self.discovery is not None, "discovery must be initialized"
        _ = await self.discovery.homeassistant_discovery()

    async def create_bridge_device(self) -> None:
        """Create the device / entity registry config for the Cync Controller bridge itself."""
        assert self.discovery is not None, "discovery must be initialized"
        _ = await self.discovery.create_bridge_device()

    # Delegation methods to state_updates helper
    async def pub_online(self, device_id: int, status: bool) -> bool:
        """Publish device online/offline status."""
        assert self.state_updates is not None, "state_updates must be initialized"
        return await self.state_updates.pub_online(device_id, status)

    async def update_device_state(self, device: CyncDeviceProtocol, state: int) -> bool:
        """Update the device state and publish to MQTT."""
        assert self.state_updates is not None, "state_updates must be initialized"
        # Type checker can't fully resolve method signature due to circular dependency
        result = await self.state_updates.update_device_state(device, state)  # type: ignore
        return result

    async def update_brightness(self, device: CyncDeviceProtocol, bri: int) -> bool:
        """Update the device brightness and publish to MQTT."""
        assert self.state_updates is not None, "state_updates must be initialized"
        result = await self.state_updates.update_brightness(device, bri)  # type: ignore
        return result

    async def update_temperature(self, device: CyncDeviceProtocol, temp: int) -> bool:
        """Update the device temperature and publish to MQTT."""
        assert self.state_updates is not None, "state_updates must be initialized"
        result = await self.state_updates.update_temperature(device, temp)  # type: ignore
        return result

    async def update_rgb(self, device: CyncDeviceProtocol, rgb: tuple[int, int, int]) -> bool:
        """Update the device RGB and publish to MQTT."""
        assert self.state_updates is not None, "state_updates must be initialized"
        result = await self.state_updates.update_rgb(device, rgb)  # type: ignore
        return result

    async def send_device_status(self, device: CyncDeviceProtocol, state_bytes: bytes) -> bool:
        """Publish device status to MQTT."""
        assert self.state_updates is not None, "state_updates must be initialized"
        result = await self.state_updates.send_device_status(device, state_bytes)  # type: ignore
        return result

    async def publish_group_state(
        self,
        group: CyncGroupProtocol,  # type: ignore[valid-type]
        state: int | None = None,
        brightness: int | None = None,
        temperature: int | None = None,
        origin: str | None = None,
    ) -> bool:
        """Publish group state to MQTT."""
        assert self.state_updates is not None, "state_updates must be initialized"
        # Type checker can't fully resolve method signature due to circular dependency
        await self.state_updates.publish_group_state(group, state, brightness, temperature, origin)  # type: ignore[misc]
        # publish_group_state returns None, but we return True to indicate the call was made
        return True

    async def parse_device_status(
        self, device_id: int, device_status: DeviceStatus, *args: object, **kwargs: object
    ) -> bool:
        """Parse device status and publish to MQTT."""
        assert self.state_updates is not None, "state_updates must be initialized"
        result = await self.state_updates.parse_device_status(device_id, device_status, *args, **kwargs)
        return bool(result)

    async def update_switch_from_subgroup(
        self, device: CyncDeviceProtocol, subgroup_state: int, subgroup_name: str
    ) -> bool:
        """Update a switch device state to match its subgroup state."""
        assert self.state_updates is not None, "state_updates must be initialized"
        result = await self.state_updates.update_switch_from_subgroup(device, subgroup_state, subgroup_name)  # type: ignore
        return result

    async def sync_group_switches(self, group_id: int, group_state: int, group_name: str) -> int:
        """Sync all switch devices in a group to match the group's state."""
        assert self.state_updates is not None, "state_updates must be initialized"
        return await self.state_updates.sync_group_switches(group_id, group_state, group_name)

    async def sync_group_devices(self, group_id: int, group_state: int, group_name: str) -> int:
        """Sync all devices (switches and bulbs) in a group to match the group's state."""
        assert self.state_updates is not None, "state_updates must be initialized"
        return await self.state_updates.sync_group_devices(group_id, group_state, group_name)

    # Delegation method to command_router helper
    async def start_receiver_task(self) -> None:
        """Start listening for MQTT messages on subscribed topics."""
        assert self.command_router is not None, "command_router must be initialized"
        await self.command_router.start_receiver_task()
