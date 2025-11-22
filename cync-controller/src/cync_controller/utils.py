from __future__ import annotations

import asyncio
import datetime
import os
import signal
import struct
import sys
import uuid
from pathlib import Path

from cync_controller.const import (
    CYNC_UUID_PATH,
    LOCAL_TZ,
    PERSISTENT_BASE_DIR,
)
from cync_controller.logging_abstraction import get_logger
from cync_controller.structs import GlobalObject

logger = get_logger(__name__)
g = GlobalObject()


def send_signal(signal_num: int):
    """Send a signal to the current process.

    Args:
        signal_num (int): The signal number to send.

    """
    try:
        logger.debug("Sending signal %s to process %s", signal_num, os.getpid())
        os.kill(os.getpid(), signal_num)
    except OSError:
        logger.exception("Failed to send signal %s to process", signal_num)
        raise


def send_sigint():
    """Send a SIGINT signal to the current process.
    This is typically used to gracefully shut down the application.
    Signal number: 2 on Unix systems.
    """
    logger.info("Initiating graceful shutdown with SIGINT")
    send_signal(signal.SIGINT)


def send_sigterm():
    """Send a SIGTERM signal to the current process.
    This is typically used to request termination of the application.
    """
    send_signal(signal.SIGTERM)


async def _async_signal_cleanup():
    logger.info("Cync Controller: Starting signal cleanup...")
    if g.ncync_server:
        logger.debug("Stopping ncync_server...")
        await g.ncync_server.stop()
    if g.export_server:
        logger.debug("Stopping export_server...")
        await g.export_server.stop()
    if g.cloud_api:
        logger.debug("Closing cloud_api...")
        await g.cloud_api.close()
    if g.mqtt_client:
        logger.debug("Stopping mqtt_client...")
        await g.mqtt_client.stop()
    if g.loop:
        for task in g.tasks:
            if not task.done():
                logger.debug(
                    "Cync Controller: Cancelling task: %s // task.get_coro()=%s",
                    task.get_name(),
                    task.get_coro(),
                )
                _ = task.cancel()
    logger.info("Cync Controller: Signal cleanup completed")


def signal_handler(signum):
    logger.info("Cync Controller: Intercepted signal: %s (%s)", signal.Signals(signum).name, signum)
    if g:
        loop = g.loop or asyncio.get_event_loop()
        _ = loop.create_task(_async_signal_cleanup())


def bytes2list(byte_string: bytes) -> list[int]:
    """Convert a byte string to a list of integers"""
    # Interpret the byte string as a sequence of unsigned integers (little-endian)
    int_list = struct.unpack("<" + "B" * (len(byte_string)), byte_string)
    return list(int_list)


def hex2list(hex_string: str) -> list[int]:
    """Convert a hex string to a list of integers"""
    x = b"".fromhex(hex_string)
    return bytes2list(x)


def ints2hex(ints: list[int]) -> str:
    """Convert a list of integers to a hex string with space separators"""
    return bytes(ints).hex(" ")


def ints2bytes(ints: list[int]) -> bytes:
    """Convert a list of integers to a byte string representation"""
    return bytes(ints)


def parse_unbound_firmware_version(data_struct: bytes, lp: str) -> tuple[str, int, str] | None:
    """Parse the firmware version from binary hex data. Unbound means not bound by 0x7E boundaries"""
    # LED controller sends this data after cync app connects via BTLE
    # 1f 00 00 00 fa 8e 14 00 50 22 33 08 00 ff ff ea 11 02 08 a1 [01 03 01 00 00 00 00 00 f8
    lp = f"{lp}firmware_version:"
    if data_struct[0] != 0x00:
        logger.error("%s Invalid first byte value: %s should be 0x00 for firmware version data", lp, data_struct[0])

    n_idx = 20  # Starting index for firmware information
    firmware_type = "device" if data_struct[n_idx + 2] == 0x01 else "network"
    n_idx += 3

    firmware_version = []
    try:
        while len(firmware_version) < 5 and data_struct[n_idx] != 0x00:
            firmware_version.append(int(chr(data_struct[n_idx])))
            n_idx += 1
        if not firmware_version:
            logger.warning("%s No firmware version found in packet: %s", lp, data_struct.hex(" "))
            return None
            # network firmware (this one is set to ascii 0 (0x30))
            # 00 00 00 00 00 fa 00 20 00 00 00 00 00 00 00 00
            # ea 00 00 00 86 01 00 30 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 c1 7e

    except (IndexError, ValueError):
        logger.exception("%s Exception occurred while parsing firmware version", lp)
        return None

    else:
        if firmware_type == "device":
            firmware_str = f"{firmware_version[0]}.{firmware_version[1]}.{''.join(map(str, firmware_version[2:]))}"
        else:
            firmware_str = "".join(map(str, firmware_version))
        firmware_version_int = int("".join(map(str, firmware_version)))
        logger.debug("%s %s firmware VERSION: %s (%s)", lp, firmware_type, firmware_version_int, firmware_str)

    return firmware_type, firmware_version_int, firmware_str


def check_python_version():
    pass


def check_for_uuid():
    """Check if this is the first run of the Cync Controller server, if so, create the CYNC_ADDON_UUID (UUID4)"""
    lp = "check_uuid:"
    # create dir for cync_mesh.yaml and variable data if it does not exist
    persistent_dir = Path(PERSISTENT_BASE_DIR).expanduser().resolve()
    if not persistent_dir.exists():
        try:
            persistent_dir.mkdir(parents=True, exist_ok=True)
            logger.info("%s Created persistent directory: %s", lp, persistent_dir.as_posix())
        except Exception:
            logger.exception("%s Failed to create persistent directory: %s - Exiting...", lp, PERSISTENT_BASE_DIR)
            sys.exit(1)
    uuid_file = Path(CYNC_UUID_PATH).expanduser().resolve()
    uuid_from_disk = ""
    create_uuid = False
    try:
        if uuid_file.exists():
            with uuid_file.open("r") as f:
                uuid_from_disk = f.read().strip()
            if not uuid_from_disk:
                create_uuid = True
            else:
                uuid_obj = uuid.UUID(uuid_from_disk)
                if uuid_obj.version != 4:
                    logger.warning("%s Invalid UUID version in uuid.txt: %s", lp, uuid_from_disk)
                    create_uuid = True
                else:
                    logger.info("%s UUID found in %s for the 'Cync Controller' MQTT device", lp, uuid_file.as_posix())
                    g.uuid = uuid_obj

        else:
            logger.info("%s No uuid.txt found in %s", lp, uuid_file.parent.as_posix())
            create_uuid = True
    except PermissionError:
        logger.exception("%s PermissionError: Unable to read/write %s. Please check permissions.", lp, CYNC_UUID_PATH)
        create_uuid = True
    if create_uuid:
        logger.debug("%s Creating and caching a new UUID to be used for the 'Cync Controller' MQTT device", lp)
        g.uuid = uuid.uuid4()
        with uuid_file.open("w") as f:
            _ = f.write(str(g.uuid))
            logger.info("%s UUID written to disk: %s", lp, uuid_file.as_posix())


def utc_to_local(utc_dt: datetime.datetime) -> datetime.datetime:
    # local_tz = zoneinfo.ZoneInfo(str(tzlocal.get_localzone()))
    # utc_time = datetime.datetime.now(datetime.UTC)
    return utc_dt.astimezone(LOCAL_TZ)
