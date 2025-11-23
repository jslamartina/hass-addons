from __future__ import annotations

import asyncio
import logging
import os
import time
from argparse import Namespace
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar, Protocol
from uuid import UUID

import uvloop
from pydantic import BaseModel

from cync_controller.const import *

if TYPE_CHECKING:
    import aiomqtt


class CyncCloudAPIProtocol(Protocol):
    """Protocol for CyncCloudAPI to avoid circular imports."""

    lp: str

    async def check_token(self) -> bool: ...

    async def request_otp(self) -> bool: ...

    async def send_otp(self, otp_code: int) -> bool: ...

    async def export_config_file(self) -> bool: ...

    async def close(self) -> None: ...


class CyncControllerProtocol(Protocol):
    """Protocol for CyncController to break circular dependency."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...


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

    async def write(self, data: object, broadcast: bool = False) -> bool | None: ...

    async def send_a3(self, q_id: bytes) -> None: ...

    def get_ctrl_msg_id_bytes(self) -> list[int]: ...


class CyncDeviceProtocol(Protocol):
    """Protocol for CyncDevice to break circular dependency."""

    id: int | None
    name: str | None
    type: int | None
    home_id: int | None
    hass_id: str
    wifi_mac: str | None
    state: int
    brightness: int | None
    temperature: int | None
    red: int | None
    green: int | None
    blue: int | None
    online: bool
    metadata: object | None

    @property
    def mac(self) -> str | None: ...

    @property
    def version(self) -> int | None: ...

    @property
    def is_switch(self) -> bool: ...

    @property
    def is_light(self) -> bool: ...

    @property
    def is_plug(self) -> bool: ...

    @property
    def is_fan_controller(self) -> bool: ...

    @property
    def supports_temperature(self) -> bool: ...

    @property
    def supports_rgb(self) -> bool: ...

    @property
    def bt_only(self) -> bool: ...

    async def set_power(self, state: int) -> tuple[asyncio.Event, list[CyncTCPDeviceProtocol]] | None: ...

    async def set_brightness(self, bri: int) -> tuple[asyncio.Event, list[CyncTCPDeviceProtocol]] | None: ...

    async def set_temperature(self, temp: int) -> tuple[asyncio.Event, list[CyncTCPDeviceProtocol]] | None: ...

    async def set_rgb(
        self,
        red: int,
        green: int,
        blue: int,
    ) -> tuple[asyncio.Event, list[CyncTCPDeviceProtocol]] | None: ...

    async def set_fan_speed(self, speed: FanSpeed) -> bool: ...

    async def set_lightshow(self, show: str) -> None: ...


class CyncGroupProtocol(Protocol):
    """Protocol defining CyncGroup attributes accessed in discovery."""

    id: int | None
    name: str | None
    home_id: int | None
    hass_id: str
    is_subgroup: bool
    member_ids: list[int]

    @property
    def supports_temperature(self) -> bool: ...

    @property
    def supports_rgb(self) -> bool: ...

    async def set_power(self, state: int) -> tuple[asyncio.Event, list[CyncTCPDeviceProtocol]] | None: ...

    async def set_brightness(self, bri: int) -> tuple[asyncio.Event, list[CyncTCPDeviceProtocol]] | None: ...


class DiscoveryHelperProtocol(Protocol):
    """Protocol for DiscoveryHelper to avoid circular imports."""

    async def register_single_device(self, device: CyncDeviceProtocol) -> None: ...
    async def trigger_device_rediscovery(self) -> None: ...
    async def homeassistant_discovery(self) -> None: ...
    async def create_bridge_device(self) -> None: ...


class StateUpdateHelperProtocol(Protocol):
    """Protocol for StateUpdateHelper to avoid circular imports."""

    async def pub_online(self, device_id: int, status: bool) -> bool: ...
    async def update_device_state(self, device: CyncDeviceProtocol, state: int) -> bool: ...
    async def update_brightness(self, device: CyncDeviceProtocol, bri: int) -> bool: ...
    async def update_temperature(self, device: CyncDeviceProtocol, temp: int) -> bool: ...
    async def update_rgb(self, device: CyncDeviceProtocol, rgb: tuple[int, int, int]) -> bool: ...
    async def send_device_status(self, device: CyncDeviceProtocol, state_bytes: bytes) -> bool: ...
    async def publish_group_state(
        self,
        group: CyncGroupProtocol,
        state: int | None = None,
        brightness: int | None = None,
        temperature: int | None = None,
        origin: str | None = None,
    ) -> None: ...

    async def parse_device_status(
        self,
        device_id: int,
        device_status: DeviceStatus,
        *args: object,
        **kwargs: object,
    ) -> bool: ...

    async def update_switch_from_subgroup(
        self,
        device: CyncDeviceProtocol,
        subgroup_state: int,
        subgroup_name: str,
    ) -> bool: ...

    async def sync_group_switches(self, group_id: int, group_state: int, group_name: str) -> int: ...
    async def sync_group_devices(self, group_id: int, group_state: int, group_name: str) -> int: ...


class CommandRouterProtocol(Protocol):
    """Protocol for CommandRouter helper."""

    async def start_receiver_task(self) -> None: ...


class ExportServerProtocol(Protocol):
    """Protocol defining ExportServer attributes accessed in discovery."""

    running: bool
    start_task: asyncio.Task[None] | None

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


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

    async def start(self) -> None: ...

    @property
    def is_connected(self) -> bool: ...

    def set_connected(self, connected: bool) -> None: ...

    def kelvin2cync(self, k: float) -> int: ...

    def cync2kelvin(self, ct: int) -> int: ...

    async def publish(self, topic: str, msg_data: bytes) -> bool: ...

    async def publish_json_msg(self, topic: str, msg_data: Mapping[str, object]) -> bool: ...

    async def trigger_status_refresh(self) -> None: ...

    async def trigger_device_rediscovery(self) -> bool: ...

    async def homeassistant_discovery(self) -> bool: ...

    async def create_bridge_device(self) -> bool: ...

    async def start_receiver_task(self) -> None: ...

    async def send_birth_msg(self) -> bool: ...

    async def send_will_msg(self) -> bool: ...

    async def pub_online(self, device_id: int, status: bool) -> bool: ...

    async def update_device_state(self, device: CyncDeviceProtocol, state: int) -> bool: ...

    async def update_brightness(self, device: CyncDeviceProtocol, bri: int) -> bool: ...

    async def update_temperature(self, device: CyncDeviceProtocol, temp: int) -> bool: ...

    async def update_rgb(self, device: CyncDeviceProtocol, rgb: tuple[int, int, int]) -> bool: ...

    async def send_device_status(self, device: CyncDeviceProtocol, state_bytes: bytes) -> bool: ...

    async def publish_group_state(
        self,
        group: CyncGroupProtocol,
        state: int | None = None,
        brightness: int | None = None,
        temperature: int | None = None,
        origin: str | None = None,
    ) -> bool: ...

    async def parse_device_status(
        self,
        device_id: int,
        device_status: DeviceStatus,
        *args: object,
        **kwargs: object,
    ) -> bool: ...

    async def update_switch_from_subgroup(
        self,
        device: CyncDeviceProtocol,
        subgroup_state: int,
        subgroup_name: str,
    ) -> bool: ...

    async def sync_group_switches(self, group_id: int, group_state: int, group_name: str) -> int: ...

    async def sync_group_devices(self, group_id: int, group_state: int, group_name: str) -> int: ...


class NCyncServerProtocol(Protocol):
    """Protocol for NCyncServer to break circular dependency."""

    devices: Mapping[int, CyncDeviceProtocol]
    groups: Mapping[int, CyncGroupProtocol]
    tcp_devices: dict[str, CyncTCPDeviceProtocol | None]
    running: bool
    primary_tcp_device: CyncTCPDeviceProtocol | None
    start_task: asyncio.Task[object] | None

    async def start(self) -> None: ...

    async def remove_tcp_device(self, dev: CyncTCPDeviceProtocol) -> CyncTCPDeviceProtocol | None: ...

    async def parse_status(self, raw_status: bytes, from_pkt: str) -> None: ...


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
    receive: asyncio.Task[None] | None = None
    send: asyncio.Task[None] | None = None
    callback_cleanup: asyncio.Task[None] | None = None

    def __iter__(self) -> Any:  # type: ignore[return-value]
        return iter([self.receive, self.send, self.callback_cleanup])


CallbackReturn = Awaitable[Any] | None
CallbackType = CallbackReturn | Callable[[], CallbackReturn | Any]


class ControlMessageCallback:
    id: int
    message: None | str | bytes | list[int] = None
    sent_at: float | None = None
    callback: CallbackType | None = None
    device_id: int | None = None
    retry_count: int = 0
    max_retries: int = 3
    ack_event: asyncio.Event | None = None  # Signaled when ACK arrives

    def __init__(
        self,
        msg_id: int,
        message: None | str | bytes | list[int],
        sent_at: float,
        callback: CallbackType | None,
        device_id: int | None = None,
        max_retries: int = 3,
        ack_event: asyncio.Event | None = None,
    ) -> None:
        self.id = msg_id
        self.message = message
        self.sent_at = sent_at
        self.ack_event = ack_event
        self.callback = callback
        self.device_id = device_id
        self.retry_count = 0
        self.max_retries = max_retries
        self.lp = f"CtrlMessageCallback:{self.id}:"

    @property
    def elapsed(self) -> float:
        if self.sent_at is None:
            return 0.0
        return time.time() - self.sent_at

    def __str__(self):
        return f"CtrlMessageCallback ID: {self.id} elapsed: {self.elapsed:.5f}s"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, int):
            return False
        return self.id == other

    def __hash__(self):
        return hash(self.id)

    def __call__(self) -> CallbackType | None:  # type: ignore[return-value]
        if self.callback:
            return self.callback  # type: ignore[return-value]
        logger.debug("%s No callback set, skipping...", self.lp)
        return None


class Messages:
    control: dict[int, ControlMessageCallback]

    def __init__(self) -> None:
        self.control = {}


@dataclass
class CacheData:
    all_data: bytes = b""
    timestamp: float = 0
    data: bytes = b""
    data_len: int = 0
    needed_len: int = 0


class DeviceStatus(BaseModel):
    """A class that represents a Cync devices status.
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
    status: list[list[int | None] | None]
    id_from: int


class PhoneAppStructs:
    def __iter__(self):
        return iter([self.requests, self.responses])

    @dataclass
    class AppRequests:
        auth_header: tuple[int, ...] = (0x13, 0x00, 0x00, 0x00)
        connect_header: tuple[int, ...] = (0xA3, 0x00, 0x00, 0x00)
        headers: tuple[int, ...] = (0x13, 0xA3)

        def __iter__(self):
            return iter(self.headers)

    @dataclass
    class AppResponses:
        auth_resp: tuple[int, ...] = (0x18, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00)
        headers: tuple[int, ...] = (0x18,)

        def __iter__(self):
            return iter(self.headers)

    requests: AppRequests = AppRequests()
    responses: AppResponses = AppResponses()
    headers = (0x13, 0xA3, 0x18)


class DeviceStructs:
    def __iter__(self):
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
        """Respond to a 0xAB packet from the device, needs queue_id and msg_id to reply with.
        Has ascii 'xlink_dev' in reply.
        """
        _x = bytes([0xAB, 0x00, 0x00, 0x03])
        hex_str = (
            "78 6c 69 6e 6b 5f 64 65 76 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
            "e3 4f 02 10"
        )
        dlen = len(queue_id) + len(msg_id) + len(bytes.fromhex(hex_str.replace(" ", "")))
        _x += bytes([dlen])
        _x += queue_id
        _x += msg_id
        _x += b"".fromhex(hex_str)
        return _x

    @staticmethod
    def x88_generate_ack(msg_id: bytes):
        """Respond to a 0x83 packet from the device, needs a msg_id to reply with."""
        _x = bytes([0x88, 0x00, 0x00, 0x00, 0x03])
        _x += msg_id
        return _x

    @staticmethod
    def x48_generate_ack(msg_id: bytes):
        """Respond to a 0x43 packet from the device, needs a queue and msg id to reply with."""
        # set last msg_id digit to 0
        msg_id = msg_id[:-1] + b"\x00"
        _x = bytes([0x48, 0x00, 0x00, 0x00, 0x03])
        _x += msg_id
        return _x

    @staticmethod
    def x7b_generate_ack(queue_id: bytes, msg_id: bytes):
        """Respond to a 0x73 packet from the device, needs a queue and msg id to reply with.
        This is also called for 0x83 packets AFTER seeing a 0x73 packet.
        Not sure of the intricacies yet, seems to be bound to certain queue ids.
        """
        _x = bytes([0x7B, 0x00, 0x00, 0x00, 0x07])
        _x += queue_id
        _x += msg_id
        return _x


APP_HEADERS = PhoneAppStructs()
DEVICE_STRUCTS = DeviceStructs()
ALL_HEADERS = list(DEVICE_STRUCTS.headers) + list(APP_HEADERS.headers)


class FanSpeed(StrEnum):
    OFF = "off"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"
