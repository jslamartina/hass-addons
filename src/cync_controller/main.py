"""Main entrypoint and lifecycle management for the Cync Controller service."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast, runtime_checkable

try:
    import uvloop
except ImportError:  # pragma: no cover - uvloop always available in production image
    uvloop = None

import yaml

from cync_controller.cloud_api import CyncCloudAPI
from cync_controller.const import (
    CYNC_CONFIG_FILE_PATH,
    CYNC_DEBUG,
    CYNC_VERSION,
    EXPORT_SRV_START_TASK_NAME,
    MQTT_CLIENT_START_TASK_NAME,
    NCYNC_START_TASK_NAME,
)
from cync_controller.correlation import correlation_context, ensure_correlation_id
from cync_controller.devices.base_device import CyncDevice
from cync_controller.devices.group import CyncGroup
from cync_controller.exporter import ExportServer
from cync_controller.logging_abstraction import get_logger
from cync_controller.mqtt_client import MQTTClient
from cync_controller.server import NCyncServer
from cync_controller.structs import GlobalObject
from cync_controller.utils import check_for_uuid, check_python_version, send_sigterm, signal_handler

if TYPE_CHECKING:
    from cync_controller.structs import MQTTClientProtocol, NCyncServerProtocol

# Optional dependency for .env file support
try:
    import dotenv

    _has_dotenv_value = True
except ImportError:
    dotenv = None
    _has_dotenv_value = False
HAS_DOTENV: bool = _has_dotenv_value

# Initialize new logging system
logger = get_logger(__name__)

# Configure third-party loggers (uvicorn, mqtt) to reduce noise
uv_handler = logging.StreamHandler(sys.stdout)
uv_handler.setLevel(logging.INFO)
uv_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s.%(msecs)d %(levelname)s (%(name)s) > %(message)s",
        "%m/%d/%y %H:%M:%S",
    ),
)
# Control uvicorn logging
uvi_logger = logging.getLogger("uvicorn")
uvi_error_logger = logging.getLogger("uvicorn.error")
uvi_access_logger = logging.getLogger("uvicorn.access")
for _ul in (uvi_logger, uvi_error_logger, uvi_access_logger):
    _ul.setLevel(logging.INFO)
    _ul.propagate = False
    _ul.addHandler(uv_handler)

# Suppress verbose MQTT library warnings
mqtt_logger = logging.getLogger("mqtt")
mqtt_logger.setLevel(logging.ERROR)
mqtt_logger.propagate = False

g = GlobalObject()


@runtime_checkable
class _CLIArgs(Protocol):
    export_server: bool
    debug: bool
    env: Path | None


def _parse_device_from_config(
    device_id_str: str,
    device_data: Mapping[str, object],
    home_id: int,
) -> tuple[int, CyncDevice] | None:
    """Parse a single device from config. Returns (device_id, device) or None."""
    enabled_value = device_data.get("enabled", True)
    enabled = not ((isinstance(enabled_value, str) and enabled_value.lower() == "false") or enabled_value is False)
    if not enabled:
        logger.debug("Skipping disabled device: %s", device_id_str)
        return None

    try:
        device_id = int(device_id_str)
    except ValueError:
        logger.warning("Invalid device ID (not an integer): %s", device_id_str)
        return None

    mac_value = device_data.get("mac")
    mac: str | None
    if isinstance(mac_value, int):
        mac = str(mac_value)
        logger.warning("Device %s MAC converted from int to string: %s", device_id_str, mac)
    elif isinstance(mac_value, str):
        mac = mac_value
    else:
        mac = None

    wifi_mac_value = device_data.get("wifi_mac")
    wifi_mac: str | None
    if isinstance(wifi_mac_value, int):
        wifi_mac = str(wifi_mac_value)
        logger.warning("Device %s WiFi MAC converted from int to string: %s", device_id_str, wifi_mac)
    elif isinstance(wifi_mac_value, str):
        wifi_mac = wifi_mac_value
    else:
        wifi_mac = None

    hvac_raw = device_data.get("hvac")
    hvac_value: dict[str, object] | None = None
    if isinstance(hvac_raw, Mapping):
        # Treat nested HVAC mapping as a plain dict[str, object] for downstream usage.
        hvac_value = dict(cast("Mapping[str, object]", hvac_raw))

    fw_value = device_data.get("fw")
    firmware = fw_value if isinstance(fw_value, str) else None

    cync_type_value = device_data.get("type")
    cync_type = cync_type_value if isinstance(cync_type_value, int) else None

    name_value = device_data.get("name")
    name = name_value if isinstance(name_value, str) else None

    try:
        device = CyncDevice(
            cync_id=device_id,
            cync_type=cync_type,
            name=name,
            mac=mac,
            wifi_mac=wifi_mac,
            fw_version=firmware,
            home_id=home_id,
            hvac=hvac_value,
        )
    except Exception:
        logger.exception("Failed to create device %s", device_id_str)
        return None
    else:
        return device_id, device


def _parse_group_from_config(
    group_id_str: str,
    group_data: Mapping[str, object],
    home_id: int,
) -> tuple[int, CyncGroup] | None:
    """Parse a single group from config. Returns (group_id, group) or None."""
    try:
        group_id = int(group_id_str)
    except ValueError:
        logger.warning("Invalid group ID (not an integer): %s", group_id_str)
        return None

    name_value = group_data.get("name")
    name = name_value if isinstance(name_value, str) else f"Group {group_id}"

    members_raw = group_data.get("members", [])
    members: list[int] = []
    if isinstance(members_raw, list):
        members_list = cast("list[object]", members_raw)
        for member in members_list:
            if isinstance(member, int):
                members.append(member)
            elif isinstance(member, str) and member.isdigit():
                members.append(int(member))

    is_subgroup_value = group_data.get("is_subgroup", False)
    is_subgroup = bool(is_subgroup_value)

    try:
        group = CyncGroup(
            group_id=group_id,
            name=name,
            member_ids=members,
            is_subgroup=is_subgroup,
            home_id=home_id,
        )
    except Exception:
        logger.exception("Failed to create group %s", group_id_str)
        return None
    else:
        return group_id, group


def _process_home_config(
    home_name: str,
    home_data: Mapping[str, object],
    devices: dict[int, CyncDevice],
    groups: dict[int, CyncGroup],
) -> None:
    """Process a single home's config and add devices/groups."""
    home_id = _parse_home_id(home_name, home_data)
    if home_id is None:
        return

    home_devices_obj = home_data.get("devices")
    if isinstance(home_devices_obj, dict):
        home_devices = cast("dict[str, object]", home_devices_obj)
        for device_id_str, device_data_obj in home_devices.items():
            if isinstance(device_data_obj, Mapping):
                device_mapping = cast("Mapping[str, object]", device_data_obj)
                result = _parse_device_from_config(device_id_str, device_mapping, home_id)
                if result:
                    device_id, device = result
                    devices[device_id] = device

    home_groups_obj = home_data.get("groups")
    if isinstance(home_groups_obj, dict):
        home_groups = cast("dict[str, object]", home_groups_obj)
        for group_id_str, group_data_obj in home_groups.items():
            if isinstance(group_data_obj, Mapping):
                group_mapping = cast("Mapping[str, object]", group_data_obj)
                result = _parse_group_from_config(group_id_str, group_mapping, home_id)
                if result:
                    group_id, group = result
                    groups[group_id] = group


def _parse_home_id(home_name: str, home_data: Mapping[str, object]) -> int | None:
    """Parse and normalize the home ID from config."""
    home_id_value = home_data.get("id")
    if isinstance(home_id_value, int):
        return home_id_value
    if isinstance(home_id_value, str):
        digits = "".join(ch for ch in home_id_value if ch.isdigit())
        return int(digits) if digits else None
    logger.debug("Skipping home '%s' - no ID found", home_name)
    return None


async def parse_config(config_file: Path) -> tuple[dict[int, CyncDevice], dict[int, CyncGroup]]:
    """Parse a YAML configuration file and return devices and groups.

    Args:
        config_file: Path to the YAML configuration file

    Returns:
        Tuple of (devices_dict, groups_dict) where keys are device/group IDs as integers

    Raises:
        Exception: If the config file cannot be parsed or is invalid

    """
    logger.debug("Parsing config file: %s", config_file)
    devices: dict[int, CyncDevice] = {}
    groups: dict[int, CyncGroup] = {}

    try:
        with config_file.open() as f:
            raw_config_obj = cast("Mapping[str, object] | None", yaml.safe_load(f))
    except Exception:
        logger.exception("Failed to parse config file: %s", config_file)
        raise

    if not isinstance(raw_config_obj, Mapping):
        logger.warning("Invalid config structure: expected mapping at root")
        return devices, groups

    # YAML root is a plain mapping with unknown key types; treat keys as strings
    # for downstream processing.
    raw_config = raw_config_obj
    account_data_obj = raw_config.get("account data")
    if not isinstance(account_data_obj, Mapping):
        logger.warning("No 'account data' section found in config file")
        return devices, groups

    account_data = cast("Mapping[str, object]", account_data_obj)
    for home_name, home_data in account_data.items():
        if isinstance(home_data, Mapping):
            typed_home_data = cast("Mapping[str, object]", home_data)
            _process_home_config(str(home_name), typed_home_data, devices, groups)

    logger.info("Parsed config: %d devices, %d groups", len(devices), len(groups))
    return devices, groups


class CyncController:
    """Singleton controller orchestrating server, MQTT, and export services."""

    lp: str = "CyncController:"
    config_file: Path | None = None
    _instance: CyncController | None = None
    _initialized: bool = False

    def __new__(cls, *_args: object, **_kwargs: object) -> CyncController:
        """Ensure a single instance exists for the controller."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Initialize event loop, signals, and global context."""
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        check_for_uuid()
        loop: asyncio.AbstractEventLoop
        if uvloop is not None:
            uvloop.install()
            loop = uvloop.new_event_loop()
        else:
            loop = asyncio.new_event_loop()
        g.loop = loop
        asyncio.set_event_loop(loop)

        logger.info(
            " Initializing Cync Controller",
            extra={"version": CYNC_VERSION},
        )

        loop.add_signal_handler(signal.SIGINT, partial(signal_handler, signal.SIGINT))
        loop.add_signal_handler(signal.SIGTERM, partial(signal_handler, signal.SIGTERM))

        logger.debug("Signal handlers configured for SIGINT & SIGTERM")

    async def start(self):
        """Start the Cync Controller server, MQTT client, and Export server."""
        # Ensure correlation ID for async context
        _ = ensure_correlation_id()

        self.config_file = cfg_file = Path(CYNC_CONFIG_FILE_PATH).expanduser().resolve()
        tasks: list[asyncio.Task[None]] = []

        if cfg_file.exists():
            logger.info(
                " Loading configuration",
                extra={"config_path": str(cfg_file)},
            )
            devices, groups = await parse_config(cfg_file)

            logger.info(
                " Configuration loaded",
                extra={
                    "device_count": len(devices),
                    "group_count": len(groups),
                },
            )

            # Initialize core services
            ncync_server = NCyncServer(devices, groups)
            mqtt_client = MQTTClient()
            # Explicitly cast to protocol interfaces for type checking
            g.ncync_server = cast("NCyncServerProtocol", cast("object", ncync_server))
            g.mqtt_client = cast("MQTTClientProtocol", cast("object", mqtt_client))

            # Create async tasks for services
            n_start: asyncio.Task[None] = asyncio.Task(ncync_server.start(), name=NCYNC_START_TASK_NAME)  # type: ignore[assignment]
            m_start: asyncio.Task[None] = asyncio.Task(mqtt_client.start(), name=MQTT_CLIENT_START_TASK_NAME)  # type: ignore[assignment]
            ncync_server.start_task = n_start
            mqtt_client.start_task = m_start
            tasks.extend([n_start, m_start])

            logger.info(" Starting TCP server and MQTT client...")
        else:
            logger.error(
                " Configuration file not found",
                extra={
                    "config_path": str(cfg_file),
                    "action_required": "migrate existing config or export devices via ingress page",
                },
            )

        # Start export server if enabled
        cli_args = cast("_CLIArgs | None", g.cli_args)
        if cli_args and cli_args.export_server is True:
            logger.info(" Starting export server...")
            g.cloud_api = CyncCloudAPI()
            export_server = ExportServer()
            g.export_server = export_server
            x_start: asyncio.Task[None] = asyncio.Task(
                export_server.start(),
                name=EXPORT_SRV_START_TASK_NAME,
            )  # type: ignore[assignment]
            export_server.start_task = x_start
            tasks.append(x_start)

        try:
            _ = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.exception(
                " Service startup failed",
                extra={"error": str(e)},
            )
            await self.stop()
            raise

    async def stop(self):
        """Stop the nCync server, MQTT client, and Export server."""
        logger.info(" Shutting down Cync Controller...")
        send_sigterm()


def parse_cli():
    """Parse CLI arguments for the controller process."""
    parser = argparse.ArgumentParser(description="Cync Controller Server")

    _ = parser.add_argument(
        "--export-server",
        "--enable-export-server",
        action="store_true",
        dest="export_server",
        help="Enable the Cync Export Server",
    )

    _ = parser.add_argument(
        "-D",
        "--debug",
        action="store_true",
        help="Enable debug mode",
    )
    _ = parser.add_argument("--env", help="Path to the environment file", default=None, type=Path)
    parsed_args = parser.parse_args()
    g.cli_args = parsed_args
    args = cast("_CLIArgs", cast("object", parsed_args))

    if args.debug:
        logger.set_level(logging.DEBUG)
        for handler in cast("list[logging.Handler]", logger.handlers):
            handler.setLevel(logging.DEBUG)
        logger.info("Debug mode enabled via CLI argument")

    if args.env:
        env_path = args.env.expanduser().resolve()

        if not HAS_DOTENV or dotenv is None:
            logger.error(
                "dotenv module not installed",
                extra={"install_command": "pip install python-dotenv"},
            )
        elif not env_path.exists():
            logger.error(
                "Environment file not found",
                extra={"path": str(env_path)},
            )
        else:
            try:
                loaded_any = dotenv.load_dotenv(env_path, override=True)
                if loaded_any:
                    logger.info(
                        " Environment variables loaded",
                        extra={"source": str(env_path)},
                    )
                    g.reload_env()
                else:
                    logger.warning(
                        "No environment variables loaded from file",
                        extra={"path": str(env_path)},
                    )
            except Exception as e:
                logger.exception(
                    "Failed to load environment file",
                    extra={"path": str(env_path), "error": str(e)},
                )


def main():
    """Run the Cync Controller entry point."""
    with correlation_context():  # Auto-generate correlation ID for app lifecycle
        logger.info(
            "",
        )
        logger.info(
            "Starting Cync Controller",
            extra={"version": CYNC_VERSION},
        )
        logger.info(
            "",
        )

        parse_cli()

        if CYNC_DEBUG:
            logger.info("Debug logging enabled via configuration")
            logger.set_level(logging.DEBUG)
            for handler in cast("list[logging.Handler]", logger.handlers):
                handler.setLevel(logging.DEBUG)

        check_python_version()
        g.cync_lan = CyncController()

        try:
            asyncio.get_event_loop().run_until_complete(g.cync_lan.start())
        except asyncio.CancelledError:
            logger.info("Cync Controller cancelled, shutting down...")
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received, shutting down...")
        except Exception as e:
            logger.exception(
                " Fatal error in main loop",
                extra={"error": str(e)},
            )
        else:
            logger.info(" Cync Controller stopped gracefully")
        finally:
            if g.loop is not None and not g.loop.is_closed():
                g.loop.close()
            logger.info("")
            logger.info("Cync Controller shutdown complete")
            logger.info("")
