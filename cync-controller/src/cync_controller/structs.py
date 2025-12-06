"""Core data structures and typing protocols for the Cync controller."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from argparse import Namespace
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar, Protocol
from uuid import UUID

import uvloop
from pydantic import BaseModel

from cync_controller.const import (
    CYNC_BASE_DIR,
    CYNC_CLOUD_DEBUG_LOGGING,
    CYNC_CLOUD_DISABLE_SSL_VERIFY,
    CYNC_CLOUD_FORWARD,
    CYNC_CLOUD_PORT,
    CYNC_CLOUD_RELAY_ENABLED,
    CYNC_CLOUD_SERVER,
    CYNC_LOG_NAME,
)
from cync_controller.metadata.model_info import DeviceTypeInfo

if TYPE_CHECKING:
    import aiomqtt


class CyncCloudAPIProtocol(Protocol):
    """Protocol for CyncCloudAPI to avoid circular imports."""

    lp: str

    async def check_token(self) -> bool:
        """Validate the currently cached authentication token."""
        ...

    async def request_otp(self) -> bool:
        """Trigger an OTP challenge for the Cync cloud account."""
        ...

    async def send_otp(self, otp_code: int) -> bool:
        """Submit an OTP code back to the cloud service."""
        ...

    async def export_config_file(self) -> bool:
        """Export the controller configuration via the cloud API."""
        ...

    async def close(self) -> None:
        """Close any open cloud API resources."""
        ...


class CyncControllerProtocol(Protocol):
    """Protocol for CyncController to break circular dependency."""

    async def start(self) -> None:
        """Start the controller."""
        ...

    async def stop(self) -> None:
        """Stop the controller."""
        ...


class CyncTCPDeviceProtocol(Protocol):
    """Protocol for CyncTCPDevice to break circular dependency."""

    connected_at: float
    ready_to_control: bool
    address: str | None
    lp: str
    needs_more_data: bool
    read_cache: list[CacheData]
    is_app: bool
    queue_id: bytes
    version: int | None
    version_str: str | None
    network_version: int | None
    network_version_str: str | None
    device_timestamp: str | None
    device_type_id: int | None
    name: str | None
    known_device_ids: list[int | None]
    mesh_info: MeshInfo | None
    parse_mesh_status: bool
    id: int | None
    refresh_id: str | None
    messages: Messages

    async def write(self, data: object, broadcast: bool = False) -> bool | None:
        """Send raw data to the TCP device."""
        ...

    async def send_a3(self, q_id: bytes) -> None:
        """Send an A3 acknowledgement to the device."""
        ...

    def get_ctrl_msg_id_bytes(self) -> list[int]:
        """Return the current control-message identifier bytes."""
        ...


class CyncDeviceProtocol(Protocol):
    """Protocol for CyncDevice to break circular dependency."""

    id: int | None
    name: str
    type: int | None
    home_id: int | None
    hass_id: str
    wifi_mac: str | None
    metadata: DeviceTypeInfo | None
    offline_count: int
    mac: str | None
    version: int | str | None
    is_switch: bool
    is_light: bool
    is_plug: bool
    is_fan_controller: bool
    supports_temperature: bool
    supports_rgb: bool
    bt_only: bool
    status: DeviceStatus
    state: int
    brightness: int | None
    temperature: int
    red: int
    green: int
    blue: int
    online: bool

    async def set_power(self, state: int) -> tuple[asyncio.Event, list[CyncTCPDeviceProtocol]] | None:
        """Send a power command to the device."""
        ...

    async def set_brightness(self, bri: int) -> tuple[asyncio.Event, list[CyncTCPDeviceProtocol]] | None:
        """Send a brightness command to the device."""
        ...

    async def set_temperature(self, temp: int) -> tuple[asyncio.Event, list[CyncTCPDeviceProtocol]] | None:
        """Send a color temperature command to the device."""
        ...

    async def set_rgb(
        self,
        red: int,
        green: int,
        blue: int,
    ) -> tuple[asyncio.Event, list[CyncTCPDeviceProtocol]] | None:
        """Send an RGB color command to the device."""
        ...

    async def set_fan_speed(self, speed: FanSpeed) -> bool:
        """Set the fan speed for a fan-capable device."""
        ...

    async def set_lightshow(self, show: str) -> None:
        """Trigger a lightshow sequence on the device."""
        ...


class CyncGroupProtocol(Protocol):
    """Protocol defining CyncGroup attributes accessed in discovery."""

    id: int | None
    name: str | None
    home_id: int | None
    hass_id: str
    is_subgroup: bool
    member_ids: list[int]
    state: int
    brightness: int | None
    temperature: int
    online: bool
    status: DeviceStatus | None
    red: int
    green: int
    blue: int

    @property
    def supports_temperature(self) -> bool:
        """Return True if the group supports color temperature."""
        ...

    @property
    def supports_rgb(self) -> bool:
        """Return True if the group supports RGB lighting."""
        ...

    async def set_power(self, state: int) -> tuple[asyncio.Event, list[CyncTCPDeviceProtocol]] | None:
        """Update power for all members in the group."""
        ...

    async def set_brightness(self, bri: int) -> tuple[asyncio.Event, list[CyncTCPDeviceProtocol]] | None:
        """Update brightness for all members in the group."""
        ...

    def aggregate_member_states(self) -> dict[str, int | bool] | None:
        """Summarize member states for the group."""
        ...


class DiscoveryHelperProtocol(Protocol):
    """Protocol for DiscoveryHelper to avoid circular imports."""

    async def register_single_device(self, device: CyncDeviceProtocol) -> None:
        """Publish Home Assistant discovery for a device."""
        ...

    async def trigger_device_rediscovery(self) -> None:
        """Trigger discovery for all known devices."""
        ...

    async def homeassistant_discovery(self) -> None:
        """Publish global Home Assistant discovery payloads."""
        ...

    async def create_bridge_device(self) -> None:
        """Ensure the MQTT bridge entity exists."""
        ...


class StateUpdateHelperProtocol(Protocol):
    """Protocol for StateUpdateHelper to avoid circular imports."""

    async def pub_online(self, device_id: int, status: bool) -> bool:
        """Publish MQTT availability for a device."""
        ...

    async def update_device_state(self, device: CyncDeviceProtocol, state: int) -> bool:
        """Publish an updated power state."""
        ...

    async def update_brightness(self, device: CyncDeviceProtocol, bri: int) -> bool:
        """Publish an updated brightness value."""
        ...

    async def update_temperature(self, device: CyncDeviceProtocol, temp: int) -> bool:
        """Publish an updated color temperature."""
        ...

    async def update_rgb(self, device: CyncDeviceProtocol, rgb: tuple[int, int, int]) -> bool:
        """Publish an updated RGB color."""
        ...

    async def send_device_status(self, device: CyncDeviceProtocol, state_bytes: bytes) -> bool:
        """Publish raw device status bytes."""
        ...

    async def publish_group_state(
        self,
        group: CyncGroupProtocol,
        state: int | None = None,
        brightness: int | None = None,
        temperature: int | None = None,
        origin: str | None = None,
    ) -> None:
        """Publish the MQTT representation of a group."""
        ...

    async def parse_device_status(
        self,
        device_id: int,
        device_status: DeviceStatus,
        *args: object,
        **kwargs: object,
    ) -> bool:
        """Convert incoming device status data into MQTT-friendly fields."""
        ...

    async def update_switch_from_subgroup(
        self,
        device: CyncDeviceProtocol,
        subgroup_state: int,
        subgroup_name: str,
    ) -> bool:
        """Propagate subgroup updates to a parent switch."""
        ...

    async def sync_group_switches(self, group_id: int, group_state: int, group_name: str) -> int:
        """Sync all switches in a group to a single state."""
        ...

    async def sync_group_devices(self, group_id: int, group_state: int, group_name: str) -> int:
        """Sync all devices in a group to a single state."""
        ...


class CommandRouterProtocol(Protocol):
    """Protocol for CommandRouter helper."""

    async def start_receiver_task(self) -> None:
        """Start the MQTT command receiver loop."""
        ...


class ExportServerProtocol(Protocol):
    """Protocol defining ExportServer attributes accessed in discovery."""

    running: bool
    start_task: asyncio.Task[None] | None

    async def start(self) -> None:
        """Start the export server."""
        ...

    async def stop(self) -> None:
        """Stop the export server."""
        ...


class MQTTClientProtocol(Protocol):
    """Protocol for MQTTClient to break circular dependency."""

    lp: str
    topic: str
    ha_topic: str
    client: aiomqtt.Client | None
    discovery: object | None
    state_updates: object | None
    command_router: object | None
    start_task: asyncio.Task[None] | None

    async def start(self) -> None:
        """Start the MQTT client."""

    @property
    def is_connected(self) -> bool:
        """Return True when the MQTT client is connected."""
        ...

    def set_connected(self, connected: bool) -> None:
        """Update the connection flag."""
        ...

    def kelvin2cync(self, k: float) -> int:
        """Convert Kelvin to the device-specific scale."""
        ...

    def cync2kelvin(self, ct: int) -> int:
        """Convert the device-specific temperature back to Kelvin."""
        ...

    async def publish(self, topic: str, msg_data: bytes) -> bool:
        """Publish a raw MQTT payload."""
        ...

    async def publish_json_msg(self, topic: str, msg_data: Mapping[str, object]) -> bool:
        """Publish a JSON-encoded MQTT payload."""
        ...

    async def trigger_status_refresh(self) -> None:
        """Kick off a status refresh for all devices."""
        ...

    async def trigger_device_rediscovery(self) -> bool:
        """Trigger discovery for every device."""
        ...

    async def homeassistant_discovery(self) -> bool:
        """Publish all Home Assistant discovery topics."""
        ...

    async def create_bridge_device(self) -> bool:
        """Publish MQTT discovery for the bridge entity."""
        ...

    async def start_receiver_task(self) -> None:
        """Start the MQTT receive loop."""
        ...

    async def send_birth_msg(self) -> bool:
        """Publish the Home Assistant birth message."""
        ...

    async def send_will_msg(self) -> bool:
        """Publish the Home Assistant last-will message."""
        ...

    async def pub_online(self, device_id: int, status: bool) -> bool:
        """Publish an availability update."""
        ...

    async def update_device_state(self, device: CyncDeviceProtocol, state: int) -> bool:
        """Publish a power state update."""
        ...

    async def update_brightness(self, device: CyncDeviceProtocol, bri: int) -> bool:
        """Publish a brightness update."""
        ...

    async def update_temperature(self, device: CyncDeviceProtocol, temp: int) -> bool:
        """Publish a color-temperature update."""
        ...

    async def update_rgb(self, device: CyncDeviceProtocol, rgb: tuple[int, int, int]) -> bool:
        """Publish an RGB update."""
        ...

    async def send_device_status(self, device: CyncDeviceProtocol, state_bytes: bytes) -> bool:
        """Publish the raw status payload for a device."""
        ...

    async def publish_group_state(
        self,
        group: CyncGroupProtocol,
        state: int | None = None,
        brightness: int | None = None,
        temperature: int | None = None,
        origin: str | None = None,
    ) -> bool:
        """Publish the combined state for a group."""
        ...

    async def parse_device_status(
        self,
        device_id: int,
        device_status: DeviceStatus,
        *args: object,
        **kwargs: object,
    ) -> bool:
        """Parse a device status payload."""
        ...

    async def update_switch_from_subgroup(
        self,
        device: CyncDeviceProtocol,
        subgroup_state: int,
        subgroup_name: str,
    ) -> bool:
        """Mirror subgroup state changes to a switch."""
        ...

    async def sync_group_switches(self, group_id: int, group_state: int, group_name: str) -> int:
        """Sync all switches in a group."""
        ...

    async def sync_group_devices(self, group_id: int, group_state: int, group_name: str) -> int:
        """Sync all devices in a group."""
        ...


class NCyncServerProtocol(Protocol):
    """Protocol for NCyncServer to break circular dependency."""

    devices: MutableMapping[int, CyncDeviceProtocol]
    groups: MutableMapping[int, CyncGroupProtocol]
    tcp_devices: dict[str, CyncTCPDeviceProtocol | None]
    running: bool
    primary_tcp_device: CyncTCPDeviceProtocol | None
    start_task: asyncio.Task[object] | None

    async def start(self) -> None:
        """Start the TCP server."""
        ...

    async def remove_tcp_device(self, dev: CyncTCPDeviceProtocol) -> CyncTCPDeviceProtocol | None:
        """Remove a TCP bridge from the pool."""
        ...

    async def parse_status(self, raw_status: bytes, from_pkt: str) -> None:
        """Parse a raw TCP status packet."""
        ...


logger = logging.getLogger(CYNC_LOG_NAME)


class GlobalObjEnv(BaseModel):
    """Environment variables for the global object.

    This is used to store environment variables that are used throughout the application.
    """

    account_username: str | None = None
    account_password: str | None = None
    mqtt_host: str | None = None
    mqtt_port: int | None = None
    mqtt_user: str | None = None
    mqtt_pass: str | None = None
    mqtt_topic: str | None = None
    mqtt_hass_topic: str | None = None
    mqtt_hass_status_topic: str | None = None
    mqtt_hass_birth_msg: str | None = None
    mqtt_hass_will_msg: str | None = None
    cync_srv_host: str | None = None
    cync_srv_ssl_cert: str | None = None
    cync_srv_ssl_key: str | None = None
    persistent_base_dir: str | None = None
    # Cloud relay configuration
    cync_cloud_relay_enabled: bool = False
    cync_cloud_forward: bool = True
    cync_cloud_server: str = "35.196.85.236"
    cync_cloud_port: int = 23779
    cync_cloud_debug_logging: bool = False
    cync_cloud_disable_ssl_verify: bool = False


class GlobalObject:
    """Singleton container for cross-module state and services."""

    cync_lan: CyncControllerProtocol | None = None  # type: ignore[assignment]
    ncync_server: NCyncServerProtocol | None = None  # type: ignore[assignment]
    mqtt_client: MQTTClientProtocol | None = None  # type: ignore[assignment]
    loop: uvloop.Loop | asyncio.AbstractEventLoop | None = None
    export_server: ExportServerProtocol | None = None
    cloud_api: CyncCloudAPIProtocol | None = None
    tasks: ClassVar[list[asyncio.Task[Any]]] = []
    env: GlobalObjEnv = GlobalObjEnv()
    uuid: UUID | None = None
    cli_args: Namespace | None = None

    _instance: GlobalObject | None = None

    def __new__(cls, *_args: Any, **_kwargs: Any) -> GlobalObject:
        """Ensure only one GlobalObject instance exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def reload_env(self):
        """Re-evaluate environment variables to update constants."""
        # Update env attributes only - do not reassign module-level constants
        # as they are treated as constants by type checkers
        self.env.account_username = os.environ.get("CYNC_ACCOUNT_USERNAME", None)
        self.env.account_password = os.environ.get("CYNC_ACCOUNT_PASSWORD", None)
        self.env.mqtt_host = os.environ.get("CYNC_MQTT_HOST", "homeassistant.local")
        self.env.mqtt_port = int(os.environ.get("CYNC_MQTT_PORT", "1883"))
        self.env.mqtt_user = os.environ.get("CYNC_MQTT_USER")
        self.env.mqtt_pass = os.environ.get("CYNC_MQTT_PASS")
        self.env.mqtt_topic = os.environ.get("CYNC_TOPIC", "cync_lan_NEW")
        self.env.mqtt_hass_topic = os.environ.get("CYNC_HASS_TOPIC", "homeassistant")
        self.env.mqtt_hass_status_topic = os.environ.get("CYNC_HASS_STATUS_TOPIC", "status")
        self.env.mqtt_hass_birth_msg = os.environ.get("CYNC_HASS_BIRTH_MSG", "online")
        self.env.mqtt_hass_will_msg = os.environ.get("CYNC_HASS_WILL_MSG", "offline")
        self.env.cync_srv_host = os.environ.get("CYNC_SRV_HOST", "0.0.0.0")
        self.env.cync_srv_ssl_cert = os.environ.get("CYNC_SSL_CERT", f"{CYNC_BASE_DIR}/cync-controller/certs/cert.pem")
        self.env.cync_srv_ssl_key = os.environ.get("CYNC_SSL_KEY", f"{CYNC_BASE_DIR}/cync-controller/certs/key.pem")
        self.env.persistent_base_dir = os.environ.get(
            "CYNC_PERSISTENT_BASE_DIR",
            "/homeassistant/.storage/cync-controller/config",
        )

        # Cloud relay configuration
        self.env.cync_cloud_relay_enabled = CYNC_CLOUD_RELAY_ENABLED
        self.env.cync_cloud_forward = CYNC_CLOUD_FORWARD
        self.env.cync_cloud_server = CYNC_CLOUD_SERVER
        self.env.cync_cloud_port = CYNC_CLOUD_PORT
        self.env.cync_cloud_debug_logging = CYNC_CLOUD_DEBUG_LOGGING
        self.env.cync_cloud_disable_ssl_verify = CYNC_CLOUD_DISABLE_SSL_VERIFY
        # Feature flags (none currently)


# Use standard dataclass instead of pydantic's - Tasks doesn't need validation
# and pyright understands standard dataclasses better
@dataclass
class Tasks:
    """Container for asyncio tasks launched by the controller."""

    receive: asyncio.Task[None] | None = None
    send: asyncio.Task[None] | None = None
    callback_cleanup: asyncio.Task[None] | None = None

    def __iter__(self) -> Any:  # type: ignore[return-value]
        """Iterate over the stored tasks."""
        return iter([self.receive, self.send, self.callback_cleanup])


CallbackReturn = Awaitable[Any] | None
CallbackType = CallbackReturn | Callable[[], CallbackReturn | Any]


class ControlMessageCallback:
    """Track metadata and callbacks for outstanding control messages."""

    __slots__ = (
        "ack_event",
        "callback",
        "device_id",
        "id",
        "lp",
        "max_retries",
        "message",
        "retry_count",
        "sent_at",
    )

    id: int | None
    message: None | str | bytes | list[int]
    sent_at: float | None
    callback: CallbackType | None
    max_retries: int
    device_id: int | None
    ack_event: asyncio.Event | None
    retry_count: int
    lp: str

    def __init__(self, id: int | None, message: None | str | bytes | list[int] = None) -> None:
        """Initialize callback metadata with minimal required arguments."""
        self.id = id
        self.message = message
        self.callback = None
        self.max_retries = 3
        self.sent_at = None
        self.device_id = None
        self.ack_event = None
        self.retry_count = 0
        self.__post_init__()

    def __post_init__(self) -> None:
        """Validate required fields and derive logging prefix."""
        if self.id is None:
            msg = "ControlMessageCallback requires an id"
            raise TypeError(msg)
        object.__setattr__(self, "lp", f"CtrlMessageCallback:{self.id}:")

    @classmethod
    def from_msg_id(cls, msg_id: int, **kwargs: Any) -> ControlMessageCallback:
        """Legacy constructor supporting the old msg_id argument."""
        return cls(id=msg_id, **kwargs)

    @property
    def elapsed(self) -> float:
        """Return the seconds elapsed since the message was sent."""
        if self.sent_at is None:
            return 0.0
        return time.time() - self.sent_at

    def __str__(self) -> str:
        """Return a human-readable representation."""
        return f"CtrlMessageCallback ID: {self.id} elapsed: {self.elapsed:.5f}s"

    def __repr__(self) -> str:
        """Return the debug representation."""
        return self.__str__()

    def __eq__(self, other: object) -> bool:
        """Compare callbacks by their identifier."""
        if not isinstance(other, int):
            return False
        return self.id == other

    def __hash__(self) -> int:
        """Allow callbacks to be keyed in dictionaries."""
        return hash(self.id)

    def __call__(self) -> CallbackType | None:  # type: ignore[return-value]
        """Return the stored callback, if present."""
        if self.callback:
            return self.callback  # type: ignore[return-value]
        logger.debug("%s No callback set, skipping...", self.lp)
        return None


@dataclass(slots=True)
class Messages:
    """Container for outstanding control-message callbacks."""

    control: dict[int, ControlMessageCallback] = field(default_factory=dict)


@dataclass
class CacheData:
    """Cache fragment tracking for TCP packet assembly."""

    all_data: bytes = b""
    timestamp: float = 0
    data: bytes = b""
    data_len: int = 0
    needed_len: int = 0


class DeviceStatus(BaseModel):
    """A class that represents a Cync device status.

    This may need to be changed as new devices are bought and added.
    """

    state: int | None = None
    brightness: int | None = None
    temperature: int | None = None
    red: int | None = None
    green: int | None = None
    blue: int | None = None


@dataclass
class MeshInfo:
    """Metadata describing a discovered mesh entry."""

    status: list[list[int | None] | None]
    id_from: int


class PhoneAppStructs:
    """Packet headers emitted by the legacy mobile application."""

    def __iter__(self):
        """Iterate over the request/response header collections."""
        return iter([self.requests, self.responses])

    @dataclass
    class AppRequests:
        """Request headers produced by the mobile application."""

        auth_header: tuple[int, ...] = (0x13, 0x00, 0x00, 0x00)
        connect_header: tuple[int, ...] = (0xA3, 0x00, 0x00, 0x00)
        headers: tuple[int, ...] = (0x13, 0xA3)

        def __iter__(self):
            """Iterate over the request headers."""
            return iter(self.headers)

    @dataclass
    class AppResponses:
        """Response headers produced by the server for app clients."""

        auth_resp: tuple[int, ...] = (0x18, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00)
        headers: tuple[int, ...] = (0x18,)

        def __iter__(self):
            """Iterate over the response headers."""
            return iter(self.headers)

    requests: AppRequests = AppRequests()
    responses: AppResponses = AppResponses()
    headers = (0x13, 0xA3, 0x18)


class DeviceStructs:
    """Packet headers emitted by Cync devices."""

    def __iter__(self):
        """Iterate over the device request/response header collections."""
        return iter([self.requests, self.responses])

    @dataclass
    class DeviceRequests:
        """These are packets devices send to the server."""

        x23: tuple[int, ...] = (0x23,)
        xc3: tuple[int, ...] = (0xC3,)
        xd3: tuple[int, ...] = (0xD3,)
        x83: tuple[int, ...] = (0x83,)
        x73: tuple[int, ...] = (0x73,)
        x7b: tuple[int, ...] = (0x7B,)
        x43: tuple[int, ...] = (0x43,)
        xa3: tuple[int, ...] = (0xA3,)
        xab: tuple[int, ...] = (0xAB,)
        headers: tuple[int, ...] = (0x23, 0xC3, 0xD3, 0x83, 0x73, 0x7B, 0x43, 0xA3, 0xAB)

        def __iter__(self):
            """Iterate over the device request headers."""
            return iter(self.headers)

    @dataclass
    class DeviceResponses:
        """These are the packets the server sends to the device."""

        auth_ack: tuple[int, ...] = (0x28, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00)
        # NOTE: Connection acknowledgment bytes - may need protocol analysis to verify correctness
        connection_ack: tuple[int, ...] = (
            0xC8,
            0x00,
            0x00,
            0x00,
            0x0B,
            0x0D,
            0x07,
            0xE8,
            0x03,
            0x0A,
            0x01,
            0x0C,
            0x04,
            0x1F,
            0xFE,
            0x0C,
        )
        x48_ack: tuple[int, ...] = (0x48, 0x00, 0x00, 0x00, 0x03, 0x01, 0x01, 0x00)
        x88_ack: tuple[int, ...] = (0x88, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00)
        ping_ack: tuple[int, ...] = (0xD8, 0x00, 0x00, 0x00, 0x00)
        x78_base: tuple[int, ...] = (0x78, 0x00, 0x00, 0x00)
        x7b_base: tuple[int, ...] = (0x7B, 0x00, 0x00, 0x00, 0x07)

    requests: DeviceRequests = DeviceRequests()
    responses: DeviceResponses = DeviceResponses()
    headers: tuple[int, ...] = (0x23, 0xC3, 0xD3, 0x83, 0x73, 0x7B, 0x43, 0xA3, 0xAB)

    @staticmethod
    def xab_generate_ack(queue_id: bytes, msg_id: bytes):
        """Respond to a 0xAB packet using the provided queue and message IDs.

        The payload mirrors the legacy ``xlink_dev`` response structure.
        """
        _x = bytes([0xAB, 0x00, 0x00, 0x03])
        hex_str = """
            78 6c 69 6e 6b 5f 64 65 76 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            e3 4f 02 10
        """.strip().replace("\n", " ")
        dlen = len(queue_id) + len(msg_id) + len(bytes.fromhex(hex_str.replace(" ", "")))
        _x += bytes([dlen])
        _x += queue_id
        _x += msg_id
        _x += b"".fromhex(hex_str)
        return _x

    @staticmethod
    def x88_generate_ack(msg_id: bytes):
        """Respond to a 0x83 packet using the provided message ID."""
        _x = bytes([0x88, 0x00, 0x00, 0x00, 0x03])
        _x += msg_id
        return _x

    @staticmethod
    def x48_generate_ack(msg_id: bytes):
        """Respond to a 0x43 packet using the provided message ID."""
        msg_id = msg_id[:-1] + b"\x00"
        _x = bytes([0x48, 0x00, 0x00, 0x00, 0x03])
        _x += msg_id
        return _x

    @staticmethod
    def x7b_generate_ack(queue_id: bytes, msg_id: bytes):
        """Respond to a 0x73 packet using the provided queue and message IDs.

        This helper is also used for 0x83 packets after observing the corresponding 0x73 packet.
        """
        _x = bytes([0x7B, 0x00, 0x00, 0x00, 0x07])
        _x += queue_id
        _x += msg_id
        return _x


APP_HEADERS = PhoneAppStructs()
DEVICE_STRUCTS = DeviceStructs()
ALL_HEADERS = list(DEVICE_STRUCTS.headers) + list(APP_HEADERS.headers)


class FanSpeed(StrEnum):
    """Enumerate the supported fan speed presets."""

    OFF = "off"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"
