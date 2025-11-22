from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from functools import partial
from pathlib import Path
from typing import Any

import uvloop
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

# Optional dependency for .env file support
try:
    import dotenv

    _has_dotenv_value = True
except ImportError:
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


def _parse_device_from_config(
    device_id_str: str,
    device_data: dict[str, Any],
    home_id: int,
) -> tuple[int, CyncDevice] | None:
    """Parse a single device from config. Returns (device_id, device) or None."""
    enabled = device_data.get("enabled", True)
    if enabled is False or enabled == "False":
        logger.debug("Skipping disabled device: %s", device_id_str)
        return None

    try:
        device_id = int(device_id_str)
    except ValueError:
        logger.warning("Invalid device ID (not an integer): %s", device_id_str)
        return None

    mac = device_data.get("mac")
    if isinstance(mac, int):
        mac = str(mac)
        logger.warning("Device %s MAC converted from int to string: %s", device_id_str, mac)

    wifi_mac = device_data.get("wifi_mac")
    if isinstance(wifi_mac, int):
        wifi_mac = str(wifi_mac)
        logger.warning("Device %s WiFi MAC converted from int to string: %s", device_id_str, wifi_mac)

    try:
        device = CyncDevice(
            cync_id=device_id,
            cync_type=device_data.get("type"),
            name=device_data.get("name"),
            mac=mac,
            wifi_mac=wifi_mac,
            fw_version=device_data.get("fw"),
            home_id=home_id,
            hvac=device_data.get("hvac"),
        )
    except Exception:
        logger.exception("Failed to create device %s", device_id_str)
        return None
    else:
        return device_id, device


def _parse_group_from_config(
    group_id_str: str,
    group_data: dict[str, Any],
    home_id: int,
) -> tuple[int, CyncGroup] | None:
    """Parse a single group from config. Returns (group_id, group) or None."""
    try:
        group_id = int(group_id_str)
    except ValueError:
        logger.warning("Invalid group ID (not an integer): %s", group_id_str)
        return None

    try:
        group = CyncGroup(
            group_id=group_id,
            name=group_data.get("name", f"Group {group_id}"),
            member_ids=group_data.get("members", []),
            is_subgroup=group_data.get("is_subgroup", False),
            home_id=home_id,
        )
    except Exception:
        logger.exception("Failed to create group %s", group_id_str)
        return None
    else:
        return group_id, group


def _process_home_config(
    home_name: str,
    home_data: dict[str, Any],
    devices: dict[int, CyncDevice],
    groups: dict[int, CyncGroup],
) -> None:
    """Process a single home's config and add devices/groups."""
    home_id = home_data.get("id")
    if not home_id:
        logger.debug("Skipping home '%s' - no ID found", home_name)
        return

    home_devices = home_data.get("devices", {})
    if home_devices:
        for device_id_str, device_data in home_devices.items():
            if isinstance(device_data, dict):
                result = _parse_device_from_config(device_id_str, device_data, home_id)
                if result:
                    device_id, device = result
                    devices[device_id] = device

    home_groups = home_data.get("groups", {})
    if home_groups:
        for group_id_str, group_data in home_groups.items():
            if isinstance(group_data, dict):
                result = _parse_group_from_config(group_id_str, group_data, home_id)
                if result:
                    group_id, group = result
                    groups[group_id] = group


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
            config_data = yaml.safe_load(f)
    except Exception:
        logger.exception("Failed to parse config file: %s", config_file)
        raise

    if not config_data or "account data" not in config_data:
        logger.warning("No 'account data' section found in config file")
        return devices, groups

    account_data = config_data["account data"]
    for home_name, home_data in account_data.items():
        if isinstance(home_data, dict):
            _process_home_config(home_name, home_data, devices, groups)

    logger.info("Parsed config: %d devices, %d groups", len(devices), len(groups))
    return devices, groups


class CyncController:
    lp: str = "CyncController:"
    config_file: Path | None = None
    _instance: CyncController | None = None

    def __new__(cls, *args: object, **kwargs: object) -> CyncController:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        check_for_uuid()
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        g.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(g.loop)

        logger.info(
            " Initializing Cync Controller",
            extra={"version": CYNC_VERSION},
        )

        g.loop.add_signal_handler(signal.SIGINT, partial(signal_handler, signal.SIGINT))
        g.loop.add_signal_handler(signal.SIGTERM, partial(signal_handler, signal.SIGTERM))

        logger.debug("Signal handlers configured for SIGINT & SIGTERM")

    async def start(self):
        """Start the Cync Controller server, MQTT client, and Export server."""
        # Ensure correlation ID for async context
        _ = ensure_correlation_id()

        self.config_file = cfg_file = Path(CYNC_CONFIG_FILE_PATH).expanduser().resolve()
        tasks = []

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
            g.ncync_server = NCyncServer(devices, groups)
            g.mqtt_client = MQTTClient()

            # Create async tasks for services
            g.ncync_server.start_task = n_start = asyncio.Task(g.ncync_server.start(), name=NCYNC_START_TASK_NAME)
            g.mqtt_client.start_task = m_start = asyncio.Task(g.mqtt_client.start(), name=MQTT_CLIENT_START_TASK_NAME)
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
        if g.cli_args and g.cli_args.export_server is True:
            logger.info(" Starting export server...")
            g.cloud_api = CyncCloudAPI()
            g.export_server = ExportServer()
            if g.export_server is not None:
                g.export_server.start_task = x_start = asyncio.Task(
                    g.export_server.start(),
                    name=EXPORT_SRV_START_TASK_NAME,
                )
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
    parser = argparse.ArgumentParser(description="Cync Controller Server")

    parser.add_argument(
        "--export-server",
        "--enable-export-server",
        action="store_true",
        dest="export_server",
        help="Enable the Cync Export Server",
    )

    parser.add_argument(
        "-D",
        "--debug",
        action="store_true",
        help="Enable debug mode",
    )
    _ = parser.add_argument("--env", help="Path to the environment file", default=None, type=Path)
    g.cli_args = args = parser.parse_args()

    if args.debug:
        logger.set_level(logging.DEBUG)
        for handler in logger.handlers:
            handler.setLevel(logging.DEBUG)
        logger.info("Debug mode enabled via CLI argument")

    if args.env:
        env_path = args.env.expanduser().resolve()

        if not HAS_DOTENV:
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
    """Main entry point for Cync Controller."""
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
            for handler in logger.handlers:
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
