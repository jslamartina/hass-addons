from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from functools import partial
from pathlib import Path

import uvloop

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
from cync_controller.exporter import ExportServer
from cync_controller.logging_abstraction import get_logger
from cync_controller.mqtt_client import MQTTClient
from cync_controller.server import NCyncServer
from cync_controller.structs import GlobalObject
from cync_controller.utils import check_for_uuid, check_python_version, parse_config, send_sigterm, signal_handler

# Optional dependency for .env file support
try:
    import dotenv

    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False

# Initialize new logging system
logger = get_logger(__name__)

# Configure third-party loggers (uvicorn, mqtt) to reduce noise
uv_handler = logging.StreamHandler(sys.stdout)
uv_handler.setLevel(logging.INFO)
uv_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s.%(msecs)d %(levelname)s (%(name)s) > %(message)s",
        "%m/%d/%y %H:%M:%S",
    )
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


class CyncController:
    lp: str = "CyncController:"
    config_file: Path | None = None
    _instance: CyncController | None = None

    def __new__(cls, *_args, **_kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        check_for_uuid()
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        g.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(g.loop)

        logger.info(
            "→ Initializing Cync Controller",
            extra={"version": CYNC_VERSION},
        )

        g.loop.add_signal_handler(signal.SIGINT, partial(signal_handler, signal.SIGINT))
        g.loop.add_signal_handler(signal.SIGTERM, partial(signal_handler, signal.SIGTERM))

        logger.debug("Signal handlers configured for SIGINT & SIGTERM")

    async def start(self):
        """Start the Cync Controller server, MQTT client, and Export server."""
        # Ensure correlation ID for async context
        ensure_correlation_id()

        self.config_file = cfg_file = Path(CYNC_CONFIG_FILE_PATH).expanduser().resolve()
        tasks = []

        if cfg_file.exists():
            logger.info(
                "→ Loading configuration",
                extra={"config_path": str(cfg_file)},
            )
            devices, groups = await parse_config(cfg_file)

            logger.info(
                "✓ Configuration loaded",
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

            logger.info("→ Starting TCP server and MQTT client...")
        else:
            logger.error(
                "✗ Configuration file not found",
                extra={
                    "config_path": str(cfg_file),
                    "action_required": "migrate existing config or export devices via ingress page",
                },
            )

        # Start export server if enabled
        if g.cli_args.export_server is True:
            logger.info("→ Starting export server...")
            g.cloud_api = CyncCloudAPI()
            g.export_server = ExportServer()
            g.export_server.start_task = x_start = asyncio.Task(
                g.export_server.start(), name=EXPORT_SRV_START_TASK_NAME
            )
            tasks.append(x_start)

        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.exception(
                "✗ Service startup failed",
                extra={"error": str(e)},
            )
            await self.stop()
            raise

    async def stop(self):
        """Stop the nCync server, MQTT client, and Export server."""
        logger.info("→ Shutting down Cync Controller...")
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
    parser.add_argument("--env", help="Path to the environment file", default=None, type=Path)
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
                        "✓ Environment variables loaded",
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
            "═══════════════════════════════════════════════════",
        )
        logger.info(
            "Starting Cync Controller",
            extra={"version": CYNC_VERSION},
        )
        logger.info(
            "═══════════════════════════════════════════════════",
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
                "✗ Fatal error in main loop",
                extra={"error": str(e)},
            )
        else:
            logger.info("✓ Cync Controller stopped gracefully")
        finally:
            if not g.loop.is_closed():
                g.loop.close()
            logger.info("═══════════════════════════════════════════════════")
            logger.info("Cync Controller shutdown complete")
            logger.info("═══════════════════════════════════════════════════")
