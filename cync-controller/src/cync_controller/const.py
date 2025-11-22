import logging
import os
import zoneinfo
from typing import Any

import tzlocal

from cync_controller import __version__

__all__ = [
    "CYNC_ACCOUNT_LANGUAGE",
    "CYNC_ACCOUNT_PASSWORD",
    "CYNC_ACCOUNT_USERNAME",
    "CYNC_API_BASE",
    "CYNC_BASE_DIR",
    "CYNC_BRIDGE_DEVICE_REGISTRY_CONF",
    "CYNC_BRIDGE_OBJ_ID",
    "CYNC_CHUNK_SIZE",
    "CYNC_CLOUD_AUTH_PATH",
    "CYNC_CLOUD_DEBUG_LOGGING",
    "CYNC_CLOUD_DISABLE_SSL_VERIFY",
    "CYNC_CLOUD_FORWARD",
    "CYNC_CLOUD_PORT",
    "CYNC_CLOUD_RELAY_ENABLED",
    "CYNC_CLOUD_SERVER",
    "CYNC_CMD_BROADCASTS",
    "CYNC_CONFIG_FILE_PATH",
    "CYNC_CORP_ID",
    "CYNC_DEBUG",
    "CYNC_EXPOSE_DEVICE_LIGHTS",
    "CYNC_HASS_BIRTH_MSG",
    "CYNC_HASS_STATUS_TOPIC",
    "CYNC_HASS_TOPIC",
    "CYNC_HASS_WILL_MSG",
    "CYNC_LOG_CORRELATION_ENABLED",
    "CYNC_LOG_FORMAT",
    "CYNC_LOG_HUMAN_OUTPUT",
    "CYNC_LOG_JSON_FILE",
    "CYNC_LOG_NAME",
    "CYNC_MANUFACTURER",
    "CYNC_MAXK",
    "CYNC_MAX_TCP_CONN",
    "CYNC_MINK",
    "CYNC_MQTT_CONN_DELAY",
    "CYNC_MQTT_HOST",
    "CYNC_MQTT_PASS",
    "CYNC_MQTT_PORT",
    "CYNC_MQTT_USER",
    "CYNC_PERF_THRESHOLD_MS",
    "CYNC_PERF_TRACKING",
    "CYNC_PORT",
    "CYNC_RAW",
    "CYNC_SRV_HOST",
    "CYNC_SSL_CERT",
    "CYNC_SSL_KEY",
    "CYNC_STATIC_DIR",
    "CYNC_TCP_WHITELIST",
    "CYNC_TOPIC",
    "CYNC_UUID_PATH",
    "CYNC_UUID_PATH",
    "CYNC_VERSION",
    "DATA_BOUNDARY",
    "DEVICE_LWT_MSG",
    "ENABLE_EXPORTER",
    "EXPORT_SRV_START_TASK_NAME",
    "FACTORY_EFFECTS_BYTES",
    "FOREIGN_LOG_FORMATTER",
    "INGRESS_PORT",
    "LOCAL_TZ",
    "LOCAL_TZ",
    "LOG_FORMATTER",
    "MQTT_CLIENT_START_TASK_NAME",
    "NCYNC_START_TASK_NAME",
    "ORIGIN_STRUCT",
    "PERSISTENT_BASE_DIR",
    "RAW_MSG",
    "SRC_REPO_URL",
    "TCP_BLACKHOLE_DELAY",
    "YES_ANSWER",
]

YES_ANSWER = ("true", "1", "yes", "y", "t", 1, "on", "o")
LOCAL_TZ = zoneinfo.ZoneInfo(str(tzlocal.get_localzone()))
CYNC_LOG_NAME: str = "cync_lan"

LOG_FORMATTER = logging.Formatter(
    "%(asctime)s.%(msecs)d %(levelname)s [%(module)s:%(lineno)d] > %(message)s",
    "%m/%d/%y %H:%M:%S",
)
# adds logger name
FOREIGN_LOG_FORMATTER = logging.Formatter(
    "%(asctime)s.%(msecs)d %(levelname)s <%(name)s> [%(module)s:%(lineno)d] > %(message)s",
    "%m/%d/%y %H:%M:%S",
)
CYNC_VERSION: str = __version__
SRC_REPO_URL: str = "https://github.com/jslamartina/hass-addons"
CYNC_API_BASE: str = "https://api.gelighting.com/v2/"
DEVICE_LWT_MSG: bytes = b"offline"

CYNC_SRV_HOST = os.environ.get("CYNC_SRV_HOST", "0.0.0.0")
CYNC_ACCOUNT_LANGUAGE: str = os.environ.get("CYNC_ACCOUNT_LANGUAGE", "en-us").casefold()
_username = os.environ.get("CYNC_ACCOUNT_USERNAME")
CYNC_ACCOUNT_USERNAME: str | None = _username if _username else None
_password = os.environ.get("CYNC_ACCOUNT_PASSWORD")
CYNC_ACCOUNT_PASSWORD: str | None = _password if _password else None

_cmd_broadcasts = os.environ.get("CYNC_CMD_BROADCASTS", "2")
if not _cmd_broadcasts:
    _cmd_broadcasts_value: int = 2
else:
    try:
        _cmd_broadcasts_value = int(_cmd_broadcasts)
    except ValueError:
        _cmd_broadcasts_value = 2
CYNC_CMD_BROADCASTS: int = _cmd_broadcasts_value
_max_tcp_conn = os.environ.get("CYNC_MAX_TCP_CONN", "8")
if not _max_tcp_conn:
    _max_tcp_conn_value: int = 8
else:
    try:
        _max_tcp_conn_value = int(_max_tcp_conn)
    except ValueError:
        _max_tcp_conn_value = 8
CYNC_MAX_TCP_CONN: int = _max_tcp_conn_value
_tcp_whitelist_env = os.environ.get("CYNC_TCP_WHITELIST")
if _tcp_whitelist_env:
    # split into a list using comma
    _whitelist_split = _tcp_whitelist_env.split(",")
    _tcp_whitelist_value: list[str] | None = [x.strip() for x in _whitelist_split if x]
else:
    _tcp_whitelist_value: list[str] | None = None
CYNC_TCP_WHITELIST: list[str] | None = _tcp_whitelist_value

CYNC_MQTT_HOST = os.environ.get("CYNC_MQTT_HOST", "homeassistant.local")
CYNC_MQTT_PORT = os.environ.get("CYNC_MQTT_PORT", "1883")
CYNC_MQTT_USER = os.environ.get("CYNC_MQTT_USER")
CYNC_MQTT_PASS = os.environ.get("CYNC_MQTT_PASS")
CYNC_TOPIC = os.environ.get("CYNC_TOPIC", "cync_lan")
CYNC_HASS_TOPIC = os.environ.get("CYNC_HASS_TOPIC", "homeassistant")
CYNC_HASS_STATUS_TOPIC = os.environ.get("CYNC_HASS_STATUS_TOPIC", "status")
CYNC_HASS_BIRTH_MSG = os.environ.get("CYNC_HASS_BIRTH_MSG", "online")
CYNC_HASS_WILL_MSG = os.environ.get("CYNC_HASS_WILL_MSG", "offline")
CYNC_MQTT_CONN_DELAY: int = int(os.environ.get("CYNC_MQTT_CONN_DELAY", "10"))

CYNC_RAW = os.environ.get("CYNC_RAW_DEBUG", "0").casefold() in YES_ANSWER
CYNC_DEBUG = os.environ.get("CYNC_DEBUG", "0").casefold() in YES_ANSWER

# Feature flags
CYNC_EXPOSE_DEVICE_LIGHTS: bool = os.environ.get("CYNC_EXPOSE_DEVICE_LIGHTS", "true").casefold() in YES_ANSWER

CYNC_BASE_DIR: str = "/root"
CYNC_STATIC_DIR: str = "/root/cync-controller/www"

PERSISTENT_BASE_DIR: str = os.environ.get("CYNC_PERSISTENT_BASE_DIR", "/homeassistant/.storage/cync-controller/config")
CYNC_CONFIG_FILE_PATH: str = f"{PERSISTENT_BASE_DIR}/cync_mesh.yaml"
CYNC_UUID_PATH: str = f"{PERSISTENT_BASE_DIR}/uuid.txt"
CYNC_CLOUD_AUTH_PATH: str = f"{PERSISTENT_BASE_DIR}/.cloud_auth.yaml"
CYNC_SSL_CERT: str = os.environ.get("CYNC_DEVICE_CERT", f"{CYNC_BASE_DIR}/cync-controller/certs/cert.pem")
CYNC_SSL_KEY: str = os.environ.get("CYNC_DEVICE_KEY", f"{CYNC_BASE_DIR}/cync-controller/certs/key.pem")

CYNC_BRIDGE_DEVICE_REGISTRY_CONF: dict[str, Any] = {}

CYNC_PORT = 23779
INGRESS_PORT = 23778
CYNC_CHUNK_SIZE = 2048
CYNC_CORP_ID: str = "1007d2ad150c4000"
DATA_BOUNDARY = 0x7E
RAW_MSG = " Set the CYNC_RAW_DEBUG env var to 1 to see the data" if CYNC_RAW is False else ""
ENABLE_EXPORTER: bool = os.environ.get("CYNC_ENABLE_EXPORTER", "0").casefold() in YES_ANSWER
# hardcoded: internally cync uses 0-100. So, no matter the bulbs actual kelvin range, it will work out.
CYNC_MINK: int = 2000
CYNC_MAXK: int = 7000
CYNC_BRIDGE_OBJ_ID: str = "cync_lan_bridge"
EXPORT_SRV_START_TASK_NAME = "ExportServer_START"
MQTT_CLIENT_START_TASK_NAME = "MQTTClient_START"
NCYNC_START_TASK_NAME = "CyncLanServer_START"

FACTORY_EFFECTS_BYTES: dict[str, tuple[int, int]] = {
    "candle": (0x01, 0xF1),
    "cyber": (0x43, 0x9F),
    "rainbow": (0x02, 0x7A),
    "fireworks": (0x3A, 0xDA),
    "volcanic": (0x04, 0xF4),
    "aurora": (0x05, 0x1C),
    "happy_holidays": (0x06, 0x54),
    "red_white_blue": (0x07, 0x4F),
    "vegas": (0x08, 0xE3),
    "party_time": (0x09, 0x06),
}

ORIGIN_STRUCT = {
    "name": "cync-controller",
    "sw_version": CYNC_VERSION,
    "support_url": SRC_REPO_URL,
}

CYNC_MANUFACTURER = "Savant"
_blackhole_delay = os.environ.get("CYNC_TCP_BLACKHOLE_DELAY", "14.75")
try:
    _blackhole_delay_value: float = float(_blackhole_delay) if _blackhole_delay else 14.75
except (ValueError, TypeError):
    _blackhole_delay_value: float = 14.75
TCP_BLACKHOLE_DELAY: float = _blackhole_delay_value

# Cloud Relay Configuration
CYNC_CLOUD_RELAY_ENABLED: bool = os.environ.get("CYNC_CLOUD_RELAY_ENABLED", "false").casefold() in YES_ANSWER
CYNC_CLOUD_FORWARD: bool = os.environ.get("CYNC_CLOUD_FORWARD", "true").casefold() in YES_ANSWER
_cloud_server = os.environ.get("CYNC_CLOUD_SERVER", "35.196.85.236")
CYNC_CLOUD_SERVER: str = _cloud_server if _cloud_server and _cloud_server.lower() != "null" else "35.196.85.236"
_cloud_port = os.environ.get("CYNC_CLOUD_PORT", "23779")
CYNC_CLOUD_PORT: int = int(_cloud_port) if _cloud_port and _cloud_port.lower() != "null" else 23779
CYNC_CLOUD_DEBUG_LOGGING: bool = os.environ.get("CYNC_CLOUD_DEBUG_LOGGING", "false").casefold() in YES_ANSWER
CYNC_CLOUD_DISABLE_SSL_VERIFY: bool = os.environ.get("CYNC_CLOUD_DISABLE_SSL_VERIFY", "false").casefold() in YES_ANSWER

# Logging Configuration
CYNC_LOG_FORMAT: str = os.environ.get("CYNC_LOG_FORMAT", "both")  # "json", "human", or "both"
CYNC_LOG_JSON_FILE: str = os.environ.get("CYNC_LOG_JSON_FILE", "/var/log/cync_controller.json")
CYNC_LOG_HUMAN_OUTPUT: str = os.environ.get("CYNC_LOG_HUMAN_OUTPUT", "stdout")  # "stdout", "stderr", or file path
CYNC_LOG_CORRELATION_ENABLED: bool = os.environ.get("CYNC_LOG_CORRELATION_ENABLED", "true").casefold() in YES_ANSWER

# Performance Instrumentation
CYNC_PERF_TRACKING: bool = os.environ.get("CYNC_PERF_TRACKING", "true").casefold() in YES_ANSWER
_perf_threshold = os.environ.get("CYNC_PERF_THRESHOLD_MS", "100")
CYNC_PERF_THRESHOLD_MS: int = int(_perf_threshold) if _perf_threshold and _perf_threshold.isdigit() else 100
