from __future__ import annotations

import asyncio
import datetime
import logging
import os
import time
from argparse import Namespace
from collections.abc import Coroutine
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

import uvloop
from pydantic import BaseModel, ConfigDict, computed_field
from pydantic.dataclasses import dataclass

from cync_lan.const import *

if TYPE_CHECKING:
    from cync_lan.cloud_api import CyncCloudAPI
    from cync_lan.exporter import ExportServer
    from cync_lan.main import CyncLAN
    from cync_lan.mqtt_client import MQTTClient
    from cync_lan.server import NCyncServer


logger = logging.getLogger(CYNC_LOG_NAME)


class GlobalObjEnv(BaseModel):
    """
    Environment variables for the global object.
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
    cync_lan: CyncLAN | None = None
    ncync_server: NCyncServer | None = None
    mqtt_client: MQTTClient | None = None
    loop: uvloop.Loop | asyncio.AbstractEventLoop | None = None
    export_server: ExportServer | None = None
    cloud_api: CyncCloudAPI | None = None
    tasks: ClassVar[list[asyncio.Task]] = []
    env: GlobalObjEnv = GlobalObjEnv()
    uuid: uuid.UUID | None = None
    cli_args: Namespace | None = None

    _instance: GlobalObject | None = None

    def __new__(cls, *_args, **_kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def reload_env(self):
        """Re-evaluate environment variables to update constants."""
        global CYNC_MQTT_HOST, CYNC_MQTT_PORT, CYNC_MQTT_USER, CYNC_MQTT_PASS  # noqa: PLW0603
        global CYNC_TOPIC, CYNC_HASS_TOPIC, CYNC_HASS_STATUS_TOPIC  # noqa: PLW0603
        global CYNC_HASS_BIRTH_MSG, CYNC_HASS_WILL_MSG, CYNC_SRV_HOST  # noqa: PLW0603
        global CYNC_SSL_CERT, CYNC_SSL_KEY, CYNC_ACCOUNT_USERNAME, CYNC_ACCOUNT_PASSWORD, PERSISTENT_BASE_DIR  # noqa: PLW0603

        self.env.account_username = CYNC_ACCOUNT_USERNAME = os.environ.get("CYNC_ACCOUNT_USERNAME", None)
        self.env.account_password = CYNC_ACCOUNT_PASSWORD = os.environ.get("CYNC_ACCOUNT_PASSWORD", None)
        self.env.mqtt_host = CYNC_MQTT_HOST = os.environ.get("CYNC_MQTT_HOST", "homeassistant.local")
        self.env.mqtt_port = CYNC_MQTT_PORT = int(os.environ.get("CYNC_MQTT_PORT", "1883"))
        self.env.mqtt_user = CYNC_MQTT_USER = os.environ.get("CYNC_MQTT_USER")
        self.env.mqtt_pass = CYNC_MQTT_PASS = os.environ.get("CYNC_MQTT_PASS")
        self.env.mqtt_topic = CYNC_TOPIC = os.environ.get("CYNC_TOPIC", "cync_lan_NEW")
        self.env.mqtt_hass_topic = CYNC_HASS_TOPIC = os.environ.get("CYNC_HASS_TOPIC", "homeassistant")
        self.env.mqtt_hass_status_topic = CYNC_HASS_STATUS_TOPIC = os.environ.get("CYNC_HASS_STATUS_TOPIC", "status")
        self.env.mqtt_hass_birth_msg = CYNC_HASS_BIRTH_MSG = os.environ.get("CYNC_HASS_BIRTH_MSG", "online")
        self.env.mqtt_hass_will_msg = CYNC_HASS_WILL_MSG = os.environ.get("CYNC_HASS_WILL_MSG", "offline")
        self.env.cync_srv_host = CYNC_SRV_HOST = os.environ.get("CYNC_SRV_HOST", "0.0.0.0")
        self.env.cync_srv_ssl_cert = CYNC_SSL_CERT = os.environ.get(
            "CYNC_SSL_CERT", f"{CYNC_BASE_DIR}/cync-lan/certs/cert.pem"
        )
        self.env.cync_srv_ssl_key = CYNC_SSL_KEY = os.environ.get(
            "CYNC_SSL_KEY", f"{CYNC_BASE_DIR}/cync-lan/certs/key.pem"
        )
        self.env.persistent_base_dir = PERSISTENT_BASE_DIR = os.environ.get(
            "CYNC_PERSISTENT_BASE_DIR", "/homeassistant/.storage/cync-controller/config"
        )

        # Cloud relay configuration
        self.env.cync_cloud_relay_enabled = CYNC_CLOUD_RELAY_ENABLED
        self.env.cync_cloud_forward = CYNC_CLOUD_FORWARD
        self.env.cync_cloud_server = CYNC_CLOUD_SERVER
        self.env.cync_cloud_port = CYNC_CLOUD_PORT
        self.env.cync_cloud_debug_logging = CYNC_CLOUD_DEBUG_LOGGING
        self.env.cync_cloud_disable_ssl_verify = CYNC_CLOUD_DISABLE_SSL_VERIFY


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class Tasks:
    receive: asyncio.Task | None = None
    send: asyncio.Task | None = None
    callback_cleanup: asyncio.Task | None = None

    def __iter__(self):
        return iter([self.receive, self.send, self.callback_cleanup])


class ControlMessageCallback:
    id: int
    message: None | str | bytes | list[int] = None
    sent_at: float | None = None
    callback: asyncio.Task | Coroutine | None = None
    device_id: int | None = None
    retry_count: int = 0
    max_retries: int = 3

    def __init__(
        self,
        msg_id: int,
        message: None | str | bytes | list[int],
        sent_at: float,
        callback: asyncio.Task | Coroutine,
        device_id: int | None = None,
        max_retries: int = 3,
    ):
        self.id = msg_id
        self.message = message
        self.sent_at = sent_at
        self.callback = callback
        self.device_id = device_id
        self.retry_count = 0
        self.max_retries = max_retries
        self.lp = f"CtrlMessageCallback:{self.id}:"

    @property
    def elapsed(self) -> float:
        return time.time() - self.sent_at

    def __str__(self):
        return f"CtrlMessageCallback ID: {self.id} elapsed: {self.elapsed:.5f}s"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other: int):
        return self.id == other

    def __hash__(self):
        return hash(self.id)

    def __call__(self):
        if self.callback:
            return self.callback
        logger.debug("%s No callback set, skipping...", self.lp)
        return None


class Messages:
    control: dict[int, ControlMessageCallback]

    def __init__(self):
        self.control = {}


@dataclass
class CacheData:
    all_data: bytes = b""
    timestamp: float = 0
    data: bytes = b""
    data_len: int = 0
    needed_len: int = 0


class DeviceStatus(BaseModel):
    """
    A class that represents a Cync devices status.
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
        auth_header: tuple[int] = (0x13, 0x00, 0x00, 0x00)
        connect_header: tuple[int] = (0xA3, 0x00, 0x00, 0x00)
        headers: tuple[int] = (0x13, 0xA3)

        def __iter__(self):
            return iter(self.headers)

    @dataclass
    class AppResponses:
        auth_resp: tuple[int] = (0x18, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00)
        headers: tuple[int] = 0x18

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
        """These are packets devices send to the server"""

        x23: tuple[int] = (0x23,)
        xc3: tuple[int] = (0xC3,)
        xd3: tuple[int] = (0xD3,)
        x83: tuple[int] = (0x83,)
        x73: tuple[int] = (0x73,)
        x7b: tuple[int] = (0x7B,)
        x43: tuple[int] = (0x43,)
        xa3: tuple[int] = (0xA3,)
        xab: tuple[int] = (0xAB,)
        headers: tuple[int] = (0x23, 0xC3, 0xD3, 0x83, 0x73, 0x7B, 0x43, 0xA3, 0xAB)

        def __iter__(self):
            return iter(self.headers)

    @dataclass
    class DeviceResponses:
        """These are the packets the server sends to the device"""

        auth_ack: tuple[int] = (0x28, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00)
        # NOTE: Connection acknowledgment bytes - may need protocol analysis to verify correctness
        connection_ack: tuple[int] = (
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
        x48_ack: tuple[int] = (0x48, 0x00, 0x00, 0x00, 0x03, 0x01, 0x01, 0x00)
        x88_ack: tuple[int] = (0x88, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00)
        ping_ack: tuple[int] = (0xD8, 0x00, 0x00, 0x00, 0x00)
        x78_base: tuple[int] = (0x78, 0x00, 0x00, 0x00)
        x7b_base: tuple[int] = (0x7B, 0x00, 0x00, 0x00, 0x07)

    requests: DeviceRequests = DeviceRequests()
    responses: DeviceResponses = DeviceResponses()
    headers: tuple[int] = (0x23, 0xC3, 0xD3, 0x83, 0x73, 0x7B, 0x43, 0xA3, 0xAB)

    @staticmethod
    def xab_generate_ack(queue_id: bytes, msg_id: bytes):
        """
        Respond to a 0xAB packet from the device, needs queue_id and msg_id to reply with.
        Has ascii 'xlink_dev' in reply
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
        """Respond to a 0x83 packet from the device, needs a msg_id to reply with"""
        _x = bytes([0x88, 0x00, 0x00, 0x00, 0x03])
        _x += msg_id
        return _x

    @staticmethod
    def x48_generate_ack(msg_id: bytes):
        """Respond to a 0x43 packet from the device, needs a queue and msg id to reply with"""
        # set last msg_id digit to 0
        msg_id = msg_id[:-1] + b"\x00"
        _x = bytes([0x48, 0x00, 0x00, 0x00, 0x03])
        _x += msg_id
        return _x

    @staticmethod
    def x7b_generate_ack(queue_id: bytes, msg_id: bytes):
        """
        Respond to a 0x73 packet from the device, needs a queue and msg id to reply with.
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


class RawTokenData(BaseModel):
    """
    Model for cloud token data.
    """

    # API Auth Response:
    # {
    # 'access_token': '1007d2ad150c4000-2407d4d081dbea53DAwQjkzNUM2RDE4QjE0QTIzMjNGRjAwRUU4ODNEQUE5RTFCMjhBOQ==',
    # 'refresh_token': 'REY3NjVENEQwQTM4NjE2OEM3QjNGMUZEQjQyQzU0MEIzRTU4NzMyRDdFQzZFRUYyQTUxNzE4RjAwNTVDQ0Y3Mw==',
    # 'user_id': 769963474,
    # 'expire_in': 604800,
    # 'authorize': '2207d2c8d2c9e406'
    # }
    access_token: str
    user_id: str | int
    expire_in: str | int
    refresh_token: str
    authorize: str


class ComputedTokenData(RawTokenData):
    issued_at: datetime.datetime

    @computed_field
    @property
    def expires_at(self) -> datetime.datetime | None:
        """
        Calculate the expiration time of the token based on the issued time and expires_in.
        Returns:
            datetime.datetime: The expiration time in UTC.
        """
        if self.issued_at and self.expire_in:
            return self.issued_at + datetime.timedelta(seconds=self.expire_in)
        return None

    # expires_at: Optional[datetime] = None

    # def model_post_init(self, __context) -> None:
    #     if self.expires_in:
    #         self.expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=self.expires_in)


class FanSpeed(StrEnum):
    OFF = "off"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"
