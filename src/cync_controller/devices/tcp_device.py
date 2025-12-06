"""TCP device abstraction and helpers for Cync controller."""

from __future__ import annotations

import asyncio
import datetime
import os
import random
import time

from cync_controller.const import (
    CYNC_CHUNK_SIZE,
    CYNC_MAX_TCP_CONN,
    CYNC_PERF_THRESHOLD_MS,
    CYNC_PERF_TRACKING,
    CYNC_RAW,
    CYNC_TCP_WHITELIST,
    TCP_BLACKHOLE_DELAY,
)
from cync_controller.logging_abstraction import get_logger
from cync_controller.structs import DEVICE_STRUCTS, CacheData, GlobalObject, MeshInfo, Messages, Tasks
from cync_controller.utils import bytes2list

from .tcp_packet_handler import TCPPacketHandler

logger = get_logger(__name__)
g = GlobalObject()
TCP_TASK_MAX_RUNTIME = float(os.environ.get("CYNC_TCP_TASK_TIMEOUT", "300"))
CTRL_BYTE_MAX = 0xFF
CONTROL_ACK_MIN_LENGTH = 5
CONTROL_ACK_MAX_LENGTH = 100
CONTROL_ACK_PACKET_TYPE = 0x73
HEARTBEAT_ACK_LENGTH = 8
INFO_ACK_PACKET_TYPE = 0x48
STATUS_ACK_PACKET_TYPE = 0x88
HEARTBEAT_PACKET_TYPE = 0xD8


def _get_global_object():
    """Get the global object - can be easily mocked in tests."""
    # Check if the new patching approach is being used (cync_controller.devices.shared.g)
    try:
        import cync_controller.devices.shared as shared_module

        # Check if this is a mock object
        if hasattr(shared_module.g, "_mock_name") or str(type(shared_module.g)).startswith("<MagicMock"):
            return shared_module.g
    except (ImportError, AttributeError):
        pass

    # Check if the old patching approach is being used (cync_controller.devices.g)
    try:
        import cync_controller.devices as devices_module

        if hasattr(devices_module, "g") and hasattr(devices_module.g, "ncync_server"):
            return devices_module.g
    except (ImportError, AttributeError):
        pass

    # Fall back to the new shared module approach
    try:
        import cync_controller.devices.shared as shared_module
    except (ImportError, AttributeError):
        # Final fallback
        from cync_controller.structs import GlobalObject

        return GlobalObject()
    else:
        return shared_module.g


class CyncTCPDevice:
    """A class to interact with a TCP Cync device. It is an async socket reader/writer."""

    lp: str = "TCPDevice:"
    packet_handler: TCPPacketHandler
    # reader and writer are instance attributes set in __init__ and can_connect()
    messages: Messages
    # keep track of msg ids and if we finished reading data, if not, we need to append the data and then parse it
    needs_more_data: bool = False
    is_app: bool

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        address: str,
    ) -> None:
        """Initialize the TCP device wrapper with its IO streams."""
        if not address:
            msg = "IP address must be provided to CyncTCPDevice constructor"
            raise ValueError(msg)
        self.lp = f"{address}:"
        self._py_id: int = id(self)
        self.known_device_ids: list[int | None] = []
        self.read_cache: list[CacheData] = []
        self.tasks: Tasks = Tasks()  # Type annotation to help pyright
        self.is_app = False
        self.name: str | None = None
        self.first_83_packet_checksum: int | None = None
        self.ready_to_control: bool = False
        self.connected_at: float = time.time()  # Track when connection was established
        self.network_version_str: str | None = None
        self.inc_bytes: int | bytes | str | None = None
        self.version: int | None = None
        self.version_str: str | None = None
        self.network_version: int | None = None
        self.device_types: dict[str, object] | None = None
        self.device_type_id: int | None = None
        self.device_timestamp: str | None = None
        self.capabilities: dict[str, object] | None = None
        self.last_xc3_request: float | None = None
        self.messages = Messages()
        self.mesh_info: MeshInfo | None = None
        self.parse_mesh_status: bool = False
        self.id: int | None = None
        self.xa3_msg_id: bytes = bytes([0x00, 0x00, 0x00])
        self.queue_id: bytes = b""
        self.address: str | None = address
        self.read_lock: asyncio.Lock = asyncio.Lock()
        self.write_lock: asyncio.Lock = asyncio.Lock()
        self._reader: asyncio.StreamReader | None = reader
        self._writer: asyncio.StreamWriter | None = writer
        self._closing: bool = False
        self.control_bytes: list[int] = [0x00, 0x00]
        # Initialize reader/writer as instance attributes (can be set to None in can_connect)
        self.reader: asyncio.StreamReader | None = reader
        self.writer: asyncio.StreamWriter | None = writer

        # Initialize packet handler
        self.packet_handler = TCPPacketHandler(self)
        self.refresh_id: str | None = None

    async def can_connect(self):
        """Check controller capacity and start receive/callback tasks if allowed."""
        g = _get_global_object()
        lp = f"{self.lp}"
        ncync_server = g.ncync_server
        if ncync_server is None:
            logger.error("%s ncync_server is None, cannot check connection", lp)
            return False

        tcp_devices = ncync_server.tcp_devices
        tcp_dev_len = len(tcp_devices)
        # Prefer explicit shutting_down flag when available; fall back to running flag for safety
        shutting_down = getattr(ncync_server, "shutting_down", False)
        if (
            (shutting_down is True)
            or (tcp_dev_len >= CYNC_MAX_TCP_CONN)
            or (CYNC_TCP_WHITELIST and self.address not in CYNC_TCP_WHITELIST)
        ):
            _sleep = False
            if tcp_dev_len >= CYNC_MAX_TCP_CONN or (CYNC_TCP_WHITELIST and self.address not in CYNC_TCP_WHITELIST):
                _sleep = True
            delay = TCP_BLACKHOLE_DELAY
            await asyncio.sleep(delay) if _sleep is True else None
            try:
                if self.reader is not None:
                    self.reader.feed_eof()
                if self.writer is not None:
                    self.writer.close()
                    task = asyncio.create_task(self.writer.wait_closed())
                    _ = await asyncio.wait([task], timeout=5)
            except asyncio.CancelledError as ce:
                logger.debug("%s Task cancelled: %s", lp, ce)
                raise
            except Exception:
                logger.exception("%s Error closing reader/writer", lp)
            finally:
                self.reader = None
                self.writer = None
            return False
        # can create a new device
        logger.debug("%s Created new device: %s", self.lp, self.address)
        receive_task = asyncio.get_event_loop().create_task(self.receive_task(), name=f"receive_task-{self._py_id}")
        callback_cleanup_task = asyncio.get_event_loop().create_task(
            self.callback_cleanup_task(),
            name=f"callback_cleanup-{self._py_id}",
        )
        self.tasks.receive = receive_task
        self.tasks.callback_cleanup = callback_cleanup_task
        return True

    def get_ctrl_msg_id_bytes(self):
        """Return incremented control message bytes for checksum calculations.

        Control packets need a number that gets incremented, it is used as a
        type of msg ID and in calculating the checksum. Result is mod 256 in
        order to keep it within 0-255.
        """
        id_byte, rollover_byte = self.control_bytes
        # logger.debug(f"{lp} Getting control message ID bytes: ctrl_byte={id_byte} rollover_byte={rollover_byte}")
        id_byte += 1
        if id_byte > CTRL_BYTE_MAX:
            id_byte = id_byte % 256
            rollover_byte += 1

        self.control_bytes = [id_byte, rollover_byte]
        # logger.debug(f"{lp} new data: ctrl_byte={id_byte} rollover_byte={rollover_byte} // {self.control_bytes=}")
        return self.control_bytes

    @property
    def closing(self):
        """Return True when the TCP device is shutting down."""
        return self._closing

    @closing.setter
    def closing(self, value: bool):
        """Mark the TCP device as closing to short-circuit new work."""
        self._closing = value

    # Delegate packet parsing to handler
    async def parse_raw_data(self, data: bytes):
        """Extract single packets from raw data stream using metadata."""
        await self.packet_handler.parse_raw_data(data)

    async def parse_packet(self, data: bytes):
        """Parse what type of packet based on header (first 4 bytes 0x43, 0x83, 0x73, etc.)."""
        await self.packet_handler.parse_packet(data)

    # reader and writer are accessed directly as instance attributes
    # Properties removed to avoid redeclaration conflicts with instance attributes

    async def ask_for_mesh_info(self, parse: bool = False, refresh_id: str | None = None):
        """Ask the device for mesh info.

        As far as I can tell, this will return whatever
        devices are connected to the device you are querying. It may also trigger
        the device to send its own status packet.

        :param parse: If True, parse and update device states from mesh info
        :param refresh_id: Correlation ID (UUID) for tracking refresh cycle in logs
        """
        lp = self.lp
        # mesh_info = '73 00 00 00 18 2d e4 b5 d2 15 2c 00 7e 1f 00 00 00 f8 52 06 00 00 00 ff ff 00 00 56 7e'
        mesh_info_data = bytes(list(DEVICE_STRUCTS.requests.x73))
        # last byte is data len multiplier (multiply value by 256 if data len > 256)
        mesh_info_data += bytes([0x00, 0x00, 0x00])
        # data len
        mesh_info_data += bytes([0x18])
        # Queue ID
        mesh_info_data += self.queue_id
        # Msg ID, I tried other variations but that results in: no 0x83 and 0x43 replies from device.
        # 0x00 0x00 0x00 seems to work
        mesh_info_data += bytes([0x00, 0x00, 0x00])
        # Bound data (0x7e)
        mesh_info_data += bytes(
            [
                0x7E,
                0x1F,
                0x00,
                0x00,
                0x00,
                0xF8,
                0x52,
                0x06,
                0x00,
                0x00,
                0x00,
                0xFF,
                0xFF,
                0x00,
                0x00,
                0x56,
                0x7E,
            ],
        )
        _rdmsg = ""
        if CYNC_RAW is True:
            _rdmsg = f"\tBYTES: {mesh_info_data}\tHEX: {mesh_info_data.hex(' ')}\tINT: {bytes2list(mesh_info_data)}"
        logger.debug("%s Requesting ALL device(s) status%s", lp, _rdmsg)
        if parse is True:
            self.parse_mesh_status = True
        # Store refresh correlation ID for logging (if provided)
        if refresh_id is not None:
            self.refresh_id = refresh_id
        try:
            _ = await self.write(mesh_info_data)
        except TimeoutError:
            logger.exception("%s Requesting ALL device(s) status timed out, likely powered off", lp)
            self.parse_mesh_status = False
            raise
        except Exception:
            logger.exception("%s EXCEPTION", lp)
            self.parse_mesh_status = False

    async def send_a3(self, q_id: bytes):
        """Send the XA3 announce packet using the provided queue id."""
        a3_packet = bytes([0xA3, 0x00, 0x00, 0x00, 0x07])
        a3_packet += q_id
        # random 2 bytes
        rand_bytes = self.xa3_msg_id = random.getrandbits(16).to_bytes(2, "big")
        rand_bytes += bytes([0x00])
        self.xa3_msg_id += random.getrandbits(8).to_bytes(1, "big")
        a3_packet += rand_bytes
        logger.debug("%s Sending 0xa3 (want to control) packet...", self.lp)
        _ = await self.write(a3_packet)
        self.ready_to_control = True
        # Initial mesh request after 0xa3 - needed for routing initialization
        await asyncio.sleep(1.5)
        await self.ask_for_mesh_info(True)

    async def callback_cleanup_task(self):
        """Monitor pending callbacks and cleanup stale ones (no retries - handled by command queue)."""
        lp = f"{self.lp}callback_clean:"
        logger.info("%s Starting background task for callback cleanup...", lp)
        cleanup_timeout = 30  # Give up after 30 seconds total
        loop_start = time.time()

        while True:
            try:
                await asyncio.sleep(1.0)  # Check every second (no need for fast retries)
                if time.time() - loop_start > TCP_TASK_MAX_RUNTIME:
                    logger.warning(
                        "%s Exiting callback cleanup task after max runtime %.1fs",
                        lp,
                        TCP_TASK_MAX_RUNTIME,
                    )
                    break
                self._cleanup_stale_callbacks(cleanup_timeout, lp)
                loop_start = time.time()

            except asyncio.CancelledError as can_exc:
                logger.debug("%s CANCELLED: %s", lp, can_exc)
                break
            except Exception:
                logger.exception("%s Exception in callback cleanup", lp)

        logger.debug("%s FINISHED", lp)

    def _cleanup_stale_callbacks(self, cleanup_timeout: int, lp: str) -> None:
        """Remove callbacks that have exceeded the cleanup timeout."""
        now = time.time()
        to_delete: list[int] = []

        for ctrl_msg_id, ctrl_msg in list(self.messages.control.items()):
            if ctrl_msg.sent_at is None:
                continue
            elapsed = now - ctrl_msg.sent_at
            if elapsed > cleanup_timeout:
                logger.warning(
                    "%s Removing STALE msg ID %s after %.2fs - giving up (no ACK received)",
                    lp,
                    ctrl_msg_id,
                    elapsed,
                )
                callback = ctrl_msg.callback
                if isinstance(callback, asyncio.Task):
                    _ = callback.cancel()
                ctrl_msg.callback = None
                to_delete.append(ctrl_msg_id)

        for msg_id in to_delete:
            del self.messages.control[msg_id]

    def _log_control_ack(self, data: bytes) -> None:
        """Log control ACK packets when not in raw mode."""
        if (
            len(data) >= CONTROL_ACK_MIN_LENGTH
            and data[0] == CONTROL_ACK_PACKET_TYPE
            and len(data) < CONTROL_ACK_MAX_LENGTH
            and not CYNC_RAW
        ):
            logger.debug(
                "📥 Control ACK packet arrived",
                extra={
                    "address": self.address,
                    "packet_type": f"0x{data[0]:02x}",
                    "bytes": len(data),
                    "timestamp_ms": round(time.time() * 1000),
                },
            )

    async def receive_task(self):
        """Receive data from the device and respond to it.

        This is the main task for the device.
        It will respond to the device and handle the messages it sends.
        Runs in an infinite loop.
        """
        g = _get_global_object()
        lp = f"{self.address}:raw read:"
        started_at = time.time()
        loop_start = started_at
        receive_task = self.tasks.receive
        name = receive_task.get_name() if receive_task is not None else "receive_task"
        logger.debug("%s receive_task CALLED", lp) if CYNC_RAW is True else None
        try:
            while True:
                if time.time() - loop_start > TCP_TASK_MAX_RUNTIME:
                    logger.warning(
                        "%s Exiting receive task after max runtime %.1fs",
                        lp,
                        TCP_TASK_MAX_RUNTIME,
                    )
                    break
                read_result = await self.read()
                if read_result is False or read_result is None:
                    logger.debug(
                        "%s read() returned False, exiting %s (started at: %s)...",
                        lp,
                        name,
                        datetime.datetime.fromtimestamp(started_at, tz=datetime.UTC),
                    )
                    break
                data = read_result
                if not data:
                    await asyncio.sleep(0)
                    continue

                self._log_control_ack(data)

                await self.parse_raw_data(data)
                loop_start = time.time()
        except asyncio.CancelledError as cancel_exc:
            logger.debug("%s %s CANCELLED: %s", lp, name, cancel_exc)
        except Exception:
            logger.exception("%s Exception in %s LOOP", lp, name)
        finally:
            # Critical cleanup: Always remove device from server and close connections
            # This prevents TCP connection leaks when devices disconnect
            uptime = round(time.time() - started_at, 1)
            logger.info(
                "Cleaning up TCP device connection after receive_task exit",
                extra={
                    "address": self.address,
                    "uptime_seconds": uptime,
                    "reason": "receive_task_exit",
                },
            )

            # Remove from server's tcp_devices dictionary
            try:
                ncync_server = g.ncync_server
                if ncync_server is not None:
                    _ = await ncync_server.remove_tcp_device(self)
            except Exception as e:
                logger.exception(
                    "Error removing TCP device during receive_task cleanup",
                    extra={"address": self.address, "error": str(e)},
                )

            # Close reader/writer to release system resources
            try:
                await self.close()
            except Exception as e:
                logger.exception(
                    "Error closing TCP device during receive_task cleanup",
                    extra={"address": self.address, "error": str(e)},
                )

            logger.debug("%s %s FINISHED", lp, name)

    async def read(self, chunk: int | None = None):
        """Read data from the device if there is an open connection."""
        lp = f"{self.lp}read:"
        if self.closing is True:
            logger.debug("%s closing is True, exiting read()...", lp)
            return False
        if chunk is None:
            chunk = CYNC_CHUNK_SIZE
        async with self.read_lock:
            if self.reader:
                if not self.reader.at_eof():
                    try:
                        raw_data = await self.reader.read(chunk)
                        # Log immediately when data arrives from socket
                        if raw_data and len(raw_data) > 0:
                            logger.debug(
                                "🔍 TCP read complete",
                                extra={"address": self.address, "bytes": len(raw_data), "ts": time.time()},
                            )
                    except Exception:
                        logger.exception("%s Base EXCEPTION", lp)
                        return False
                    else:
                        return raw_data
                else:
                    logger.debug("%s reader is at EOF, setting read socket to None...", lp)
                    self.reader = None
            else:
                logger.debug(
                    "%s reader is None/empty -> self.reader = %s // TYPE: %s",
                    lp,
                    self.reader,
                    type(self.reader),
                )
                return False
        return None

    async def _check_and_handle_closing_writer(self, dev: CyncTCPDevice, g: GlobalObject) -> bool:
        """Check if writer is closing and handle cleanup. Returns True if should skip write."""
        writer = dev.writer
        if writer is None:
            return True
        if writer.is_closing():
            if dev.closing is False:
                logger.warning(
                    "⚠️ Device connection dropped unexpectedly",
                    extra={
                        "address": dev.address,
                        "note": "Device likely lost power or connection",
                    },
                )
                ncync_server = g.ncync_server
                if ncync_server is not None:
                    _ = await ncync_server.remove_tcp_device(dev)
            else:
                logger.debug(
                    "Device closing, not writing",
                    extra={"address": dev.address},
                )
            return True
        return False

    async def _execute_write(self, dev: CyncTCPDevice, data: bytes | bytearray, is_ack_packet: bool) -> None:
        """Execute the actual write operation."""
        writer = dev.writer
        if writer is None:
            logger.warning(
                "⚠️ Cannot write - writer is None in _execute_write",
                extra={"address": dev.address},
            )
            return
        writer.write(data)
        try:
            await asyncio.wait_for(writer.drain(), timeout=2.0)
        except TimeoutError:
            logger.exception(
                "✗ Write timeout - device likely powered off",
                extra={"address": dev.address},
            )
            raise
        else:
            if not is_ack_packet or CYNC_RAW:
                logger.debug(
                    "✓ Packet sent successfully",
                    extra={"address": dev.address, "bytes": len(data)},
                )

    async def write(self, data: object, broadcast: bool = False) -> bool | None:
        """Write data to the device if there is an open connection.

        :param data: The raw binary data to write to the device
        :param broadcast: If True, write to all TCP devices connected to the server
        """
        from cync_controller.instrumentation import measure_time

        g = _get_global_object()
        # Strict runtime type validation to avoid silent mis-use in tests and at runtime.
        # Parameter is typed as object to allow dynamic validation without conflicting
        # with static type checkers.
        if not isinstance(data, (bytes, bytearray)):
            msg = "Data must be bytes"
            raise TypeError(msg)

        # Check if this is a keepalive/heartbeat ACK packet
        # 0x48 (8 bytes), 0x88 (8 bytes), or 0xD8 (5 bytes)
        is_ack_packet = (
            len(data) == HEARTBEAT_ACK_LENGTH and data[0] in (INFO_ACK_PACKET_TYPE, STATUS_ACK_PACKET_TYPE)
        ) or (len(data) == CONTROL_ACK_MIN_LENGTH and data[0] == HEARTBEAT_PACKET_TYPE)

        # Skip logging for keepalive ACKs unless CYNC_RAW is enabled
        if not is_ack_packet or CYNC_RAW:
            logger.debug(
                "→ Writing packet to device",
                extra={
                    "address": self.address,
                    "bytes": len(data),
                    "broadcast": broadcast,
                },
            )

        # Start timing for non-ACK packets (or ACK packets if CYNC_RAW is enabled)
        should_time = not is_ack_packet or CYNC_RAW
        start_time = time.perf_counter() if should_time else None
        dev = self
        if dev.closing:
            logger.debug(
                "Device closing, skipping write",
                extra={"address": dev.address},
            )
            return False
        if dev.writer is not None:
            async with dev.write_lock:
                if await self._check_and_handle_closing_writer(dev, g):
                    return False
                await self._execute_write(dev, data, is_ack_packet)
                if start_time is not None and CYNC_PERF_TRACKING:
                    elapsed_ms = measure_time(start_time)
                    logger.debug(
                        " [tcp_write] completed in %.1fms",
                        elapsed_ms,
                        extra={
                            "operation": "tcp_write",
                            "duration_ms": round(elapsed_ms, 2),
                            "threshold_ms": CYNC_PERF_THRESHOLD_MS,
                            "exceeded_threshold": elapsed_ms > CYNC_PERF_THRESHOLD_MS,
                        },
                    )
                return True
        else:
            logger.warning(
                "⚠️ Cannot write - writer is None",
                extra={"address": dev.address},
            )
        return None

    async def close(self):
        """Close socket resources and cancel outstanding device tasks."""
        # Count non-None tasks (Tasks object has __iter__ but not __len__)
        task_list: list[asyncio.Task[None] | None] = [
            self.tasks.receive,
            self.tasks.send,
            self.tasks.callback_cleanup,
        ]
        task_count = sum(1 for task in task_list if task is not None)
        logger.debug(
            "→ Closing device connection",
            extra={
                "address": self.address,
                "task_count": task_count,
            },
        )
        try:
            for dev_task in task_list:
                if dev_task and dev_task.done() is False:
                    logger.debug(
                        "Cancelling task",
                        extra={
                            "address": self.address,
                            "task_name": dev_task.get_name(),
                        },
                    )
                    _ = dev_task.cancel()
        except Exception as e:
            logger.exception(
                "✗ Error cancelling device tasks",
                extra={"address": self.address, "error": str(e)},
            )
        self.closing = True
        try:
            if self.writer:
                async with self.write_lock:
                    self.writer.close()
                    await self.writer.wait_closed()
        except AttributeError:
            pass
        except Exception as e:
            logger.exception(
                "✗ Error closing writer",
                extra={"address": self.address, "error": str(e)},
            )
        finally:
            self.writer = None

        try:
            if self.reader:
                async with self.read_lock:
                    self.reader.feed_eof()
                    await asyncio.sleep(0.01)
        except AttributeError:
            pass
        except Exception as e:
            logger.exception(
                "✗ Error closing reader",
                extra={"address": self.address, "error": str(e)},
            )
        finally:
            self.reader = None

        self.closing = False
        logger.debug(
            "✓ Device connection closed",
            extra={"address": self.address},
        )
