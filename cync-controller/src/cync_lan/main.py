from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from functools import partial
from pathlib import Path

import uvloop

from cync_lan.cloud_api import CyncCloudAPI
from cync_lan.const import (
    CYNC_CONFIG_FILE_PATH,
    CYNC_DEBUG,
    CYNC_LOG_NAME,
    CYNC_VERSION,
    EXPORT_SRV_START_TASK_NAME,
    FOREIGN_LOG_FORMATTER,
    LOG_FORMATTER,
    MQTT_CLIENT_START_TASK_NAME,
    NCYNC_START_TASK_NAME,
)
from cync_lan.exporter import ExportServer
from cync_lan.mqtt_client import MQTTClient
from cync_lan.server import NCyncServer
from cync_lan.structs import GlobalObject
from cync_lan.utils import (
    check_for_uuid,
    check_python_version,
    parse_config,
    send_sigterm,
    signal_handler,
)

# Optional dependency for .env file support
try:
    import dotenv

    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False

logger = logging.getLogger(CYNC_LOG_NAME)
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.INFO)
stdout_handler.setFormatter(LOG_FORMATTER)
foreign_handler = logging.StreamHandler(sys.stderr)
foreign_handler.setLevel(logging.INFO)
foreign_handler.setFormatter(FOREIGN_LOG_FORMATTER)
uv_handler = logging.StreamHandler(sys.stdout)
uv_handler.setLevel(logging.INFO)
uv_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s.%(msecs)d %(levelname)s (%(name)s) > %(message)s",
        "%m/%d/%y %H:%M:%S",
    )
)
logger.addHandler(stdout_handler)
logger.setLevel(logging.INFO)
# Control uvicorn logging, what a mess!
uvi_logger = logging.getLogger("uvicorn")
uvi_error_logger = logging.getLogger("uvicorn.error")
uvi_access_logger = logging.getLogger("uvicorn.access")
uvi_loggers = (uvi_logger, uvi_error_logger, uvi_access_logger)
for _ul in uvi_loggers:
    _ul.setLevel(logging.INFO)
    _ul.propagate = False
    _ul.addHandler(uv_handler)
mqtt_logger = logging.getLogger("mqtt")
# shut off the 'There are x pending publish calls.' from the mqtt logger (WARNING level)
mqtt_logger.setLevel(logging.ERROR)
mqtt_logger.propagate = False
mqtt_logger.addHandler(foreign_handler)
# logger.debug("%s Logging all registered loggers: %s", lp, logging.getLogger().manager.loggerDict.keys())
g = GlobalObject()


class CyncLAN:
    lp: str = "CyncLAN:"
    config_file: Path | None = None
    _instance: CyncLAN | None = None

    def __new__(cls, *_args, **_kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        lp = f"{self.lp}init:"
        check_for_uuid()
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        g.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(g.loop)
        logger.debug(
            "%s CyncLAN (version: %s) stack initializing, "
            "setting up event loop signal handlers for SIGINT & SIGTERM...",
            lp,
            CYNC_VERSION,
        )
        g.loop.add_signal_handler(signal.SIGINT, partial(signal_handler, signal.SIGINT))
        g.loop.add_signal_handler(signal.SIGTERM, partial(signal_handler, signal.SIGTERM))

    async def start(self):
        """Start the Cync LAN server, MQTT client, and Export server."""
        lp = f"{self.lp}start:"
        self.config_file = cfg_file = Path(CYNC_CONFIG_FILE_PATH).expanduser().resolve()
        tasks = []
        if cfg_file.exists():
            devices, groups = await parse_config(cfg_file)
            g.ncync_server = NCyncServer(devices, groups)
            g.mqtt_client = MQTTClient()
            g.ncync_server.start_task = n_start = asyncio.Task(g.ncync_server.start(), name=NCYNC_START_TASK_NAME)
            g.mqtt_client.start_task = m_start = asyncio.Task(g.mqtt_client.start(), name=MQTT_CLIENT_START_TASK_NAME)
            tasks.extend([n_start, m_start])
        else:
            logger.error(
                "%s Cync config file not found at %s. Please migrate "
                "an existing config file or visit the ingress page and perform a device export.",
                lp,
                cfg_file.as_posix(),
            )
        if g.cli_args.export_server is True:
            g.cloud_api = CyncCloudAPI()
            g.export_server = ExportServer()
            g.export_server.start_task = x_start = asyncio.Task(
                g.export_server.start(), name=EXPORT_SRV_START_TASK_NAME
            )
            tasks.append(x_start)

        try:
            # the components start() methods have long running tasks of their own
            # NOTE: Future improvement - implement better task monitoring and control mechanisms
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            logger.exception("%s Exception occurred while starting services", lp)
            # Stop all services if any service fails to start
            await self.stop()
            raise

    async def stop(self):
        """Stop the nCync server, MQTT client, and Export server."""
        lp = f"{self.lp}stop:"
        # send sigterm
        logger.info("%s Bringing software stack down using SIGTERM...", lp)
        send_sigterm()


def parse_cli():
    parser = argparse.ArgumentParser(description="Cync LAN Server")

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
        logger.setLevel(logging.DEBUG)
        for handler in logger.handlers:
            handler.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled via CLI argument")
    if args.env:
        env_path = args.env
        env_path = env_path.expanduser().resolve()
        if not HAS_DOTENV:
            logger.error("dotenv module is not installed. Please install it with 'pip install python-dotenv'")
        else:
            try:
                loaded_any = dotenv.load_dotenv(env_path, override=True)
            except Exception:
                logger.exception("Failed to read environment file %s", env_path)
            else:
                if not env_path.exists():
                    logger.error("Environment file %s does not exist", env_path)
                if loaded_any:
                    logger.info("Environment variables loaded from %s", env_path)
                    g.reload_env()
                else:
                    logger.warning("No environment variables were loaded from %s", env_path)


def main():
    lp = "main:"
    parse_cli()
    if CYNC_DEBUG:
        logger.info("%s Add-on config has set logging level to: Debug", lp)
        logger.setLevel(logging.DEBUG)
        for handler in logger.handlers:
            handler.setLevel(logging.DEBUG)
    check_python_version()
    g.cync_lan = CyncLAN()
    try:
        asyncio.get_event_loop().run_until_complete(g.cync_lan.start())
    except asyncio.CancelledError as e:
        logger.info("%s CyncLAN async stack cancelled: %s", lp, e)
    except KeyboardInterrupt:
        logger.info("%s Caught KeyboardInterrupt, exiting...", lp)
    except Exception:
        logger.exception("%s Caught exception", lp)
    else:
        logger.info("%s CyncLAN stack stopped gracefully, bye!", lp)
    finally:
        if not g.loop.is_closed():
            g.loop.close()
