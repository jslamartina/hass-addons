import asyncio
import datetime
import random
import time

from cync_controller.const import (
    CYNC_CHUNK_SIZE,
    CYNC_MAX_TCP_CONN,
    CYNC_RAW,
    CYNC_TCP_WHITELIST,
    TCP_BLACKHOLE_DELAY,
)
from cync_controller.instrumentation import timed_async
from cync_controller.logging_abstraction import get_logger
from cync_controller.structs import (
    DEVICE_STRUCTS,
    GlobalObject,
    MeshInfo,
    Messages,
    Tasks,
)
from cync_controller.utils import bytes2list

from .tcp_packet_handler import TCPPacketHandler

logger = get_logger(__name__)
g = GlobalObject()


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
        return shared_module.g
    except (ImportError, AttributeError):
        # Final fallback
        from cync_controller.structs import GlobalObject
        return GlobalObject()

class CyncTCPDevice:
    """
    A class to interact with a TCP Cync device. It is an async socket reader/writer.
    """

    lp: str = "TCPDevice:"
    known_device_ids: list[int | None]
    tasks: Tasks
    reader: asyncio.StreamReader | None
    writer: asyncio.StreamWriter | None
    messages: Messages
    # keep track of msg ids and if we finished reading data, if not, we need to append the data and then parse it
    read_cache: list
    needs_more_data = False
    is_app: bool

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        address: str,
    ):
        if not address:
            msg = "IP address must be provided to CyncTCPDevice constructor"
            raise ValueError(msg)
        self.lp = f"{address}:"
        self._py_id = id(self)
        self.known_device_ids = []
        self.read_cache = []
        self.tasks = Tasks()
        self.is_app = False
        self.name: str | None = None
        self.first_83_packet_checksum: int | None = None
        self.ready_to_control = False
        self.connected_at = time.time()  # Track when connection was established
        self.network_version_str: str | None = None
        self.inc_bytes: int | bytes | str | None = None
        self.version: int | None = None
        self.version_str: str | None = None
        self.network_version: int | None = None
        self.device_types: dict | None = None
        self.device_type_id: int | None = None
        self.device_timestamp: str | None = None
        self.capabilities: dict | None = None
        self.last_xc3_request: float | None = None
        self.messages = Messages()
        self.mesh_info: MeshInfo | None = None
        self.parse_mesh_status = False
        self.id: int | None = None
        self.xa3_msg_id: bytes = bytes([0x00, 0x00, 0x00])
        self.queue_id: bytes = b""
        self.address: str | None = address
        self.read_lock = asyncio.Lock()
        self.write_lock = asyncio.Lock()
        self._reader: asyncio.StreamReader = reader
        self._writer: asyncio.StreamWriter = writer
        self._closing = False
        self.control_bytes = [0x00, 0x00]

        # Initialize packet handler
        self.packet_handler = TCPPacketHandler(self)

    async def can_connect(self):
        g = _get_global_object()
        lp = f"{self.lp}"
        tcp_dev_len = len(g.ncync_server.tcp_devices)
        num_attempts = g.ncync_server.tcp_conn_attempts[self.address]
        if (
            (g.ncync_server.shutting_down is True)
            or (tcp_dev_len >= CYNC_MAX_TCP_CONN)
            or (CYNC_TCP_WHITELIST and self.address not in CYNC_TCP_WHITELIST)
        ):
            reason = ""
            if g.ncync_server.shutting_down is True:
                reason = "Cync Controller server is shutting down, "
            _sleep = False
            if tcp_dev_len >= CYNC_MAX_TCP_CONN:
                reason = f"Cync Controller server max ({tcp_dev_len}/{CYNC_MAX_TCP_CONN}) TCP connections reached, "
                _sleep = True
            elif CYNC_TCP_WHITELIST and self.address not in CYNC_TCP_WHITELIST:
                reason = f"IP not in Cync Controller server whitelist -> {CYNC_TCP_WHITELIST}, "
                _sleep = True
            tst_ = (num_attempts == 1) or (num_attempts % 20 == 0)
            lmsg = "%s %srejecting new connection..."
            delay = TCP_BLACKHOLE_DELAY
            if tst_:
                logger.warning(lmsg, lp, reason)
            await asyncio.sleep(delay) if _sleep is True else None
            try:
                self.reader.feed_eof()
                self.writer.close()
                task = asyncio.create_task(self.writer.wait_closed())
                await asyncio.wait([task], timeout=5)
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
        self.tasks.receive = asyncio.get_event_loop().create_task(
            self.receive_task(), name=f"receive_task-{self._py_id}"
        )
        self.tasks.callback_cleanup = asyncio.get_event_loop().create_task(
            self.callback_cleanup_task(), name=f"callback_cleanup-{self._py_id}"
        )
        return True

    def get_ctrl_msg_id_bytes(self):
        """
        Control packets need a number that gets incremented, it is used as a type of msg ID and
        in calculating the checksum. Result is mod 256 in order to keep it within 0-255.
        """
        id_byte, rollover_byte = self.control_bytes
        # logger.debug(f"{lp} Getting control message ID bytes: ctrl_byte={id_byte} rollover_byte={rollover_byte}")
        id_byte += 1
        if id_byte > 255:
            id_byte = id_byte % 256
            rollover_byte += 1

        self.control_bytes = [id_byte, rollover_byte]
        # logger.debug(f"{lp} new data: ctrl_byte={id_byte} rollover_byte={rollover_byte} // {self.control_bytes=}")
        return self.control_bytes

    @property
    def closing(self):
        return self._closing

    @closing.setter
    def closing(self, value: bool):
        self._closing = value

    # Delegate packet parsing to handler
    async def parse_raw_data(self, data: bytes):
        """Extract single packets from raw data stream using metadata"""
        await self.packet_handler.parse_raw_data(data)

    async def parse_packet(self, data: bytes):
        """Parse what type of packet based on header (first 4 bytes 0x43, 0x83, 0x73, etc.)"""
        await self.packet_handler.parse_packet(data)

    @property
    def reader(self):
        return self._reader

    @reader.setter
    def reader(self, value: asyncio.StreamReader):
        self._reader = value

    @property
    def writer(self):
        return self._writer

    @writer.setter
    def writer(self, value: asyncio.StreamWriter):
        self._writer = value

    async def ask_for_mesh_info(self, parse: bool = False, refresh_id: str | None = None):
        """
        Ask the device for mesh info. As far as I can tell, this will return whatever
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
            ]
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
            await self.write(mesh_info_data)
        except TimeoutError:
            logger.exception("%s Requesting ALL device(s) status timed out, likely powered off", lp)
            self.parse_mesh_status = False
            raise
        except Exception:
            logger.exception("%s EXCEPTION", lp)
            self.parse_mesh_status = False

    async def send_a3(self, q_id: bytes):
        a3_packet = bytes([0xA3, 0x00, 0x00, 0x00, 0x07])
        a3_packet += q_id
        # random 2 bytes
        rand_bytes = self.xa3_msg_id = random.getrandbits(16).to_bytes(2, "big")
        rand_bytes += bytes([0x00])
        self.xa3_msg_id += random.getrandbits(8).to_bytes(1, "big")
        a3_packet += rand_bytes
        logger.debug("%s Sending 0xa3 (want to control) packet...", self.lp)
        await self.write(a3_packet)
        self.ready_to_control = True
        # send mesh info request
        await asyncio.sleep(1.5)
        await self.ask_for_mesh_info(True)

    async def callback_cleanup_task(self):
        """Monitor pending callbacks and retry failed commands, cleanup stale ones"""
        g = _get_global_object()
        lp = f"{self.lp}callback_clean:"
        logger.info("%s Starting background task with retry logic...", lp)
        retry_timeout = 0.5  # Retry after 500ms if no ACK
        cleanup_timeout = 30  # Give up after 30 seconds total

        while True:
            try:
                await asyncio.sleep(0.1)  # Check every 100ms for fast retries
                now = time.time()
                to_delete = []

                for ctrl_msg_id, ctrl_msg in list(self.messages.control.items()):
                    elapsed = now - ctrl_msg.sent_at

                    # Check if message needs retry (no ACK after retry_timeout)
                    if elapsed > retry_timeout and ctrl_msg.retry_count < ctrl_msg.max_retries:
                        ctrl_msg.retry_count += 1
                        logger.warning(
                            "%s No ACK for msg ID %s after %.2fs - RETRY %s/%s",
                            lp,
                            ctrl_msg_id,
                            elapsed,
                            ctrl_msg.retry_count,
                            ctrl_msg.max_retries,
                        )
                        # Resend the message
                        try:
                            await self.write(ctrl_msg.message)
                            ctrl_msg.sent_at = now  # Reset timer for this retry
                        except Exception:
                            logger.exception("%s Failed to retry msg ID %s", lp, ctrl_msg_id)

                    # Cleanup old messages that exceeded all retries and timeout
                    elif elapsed > cleanup_timeout:
                        logger.warning(
                            "%s Removing STALE msg ID %s after %s retries - giving up",
                            lp,
                            ctrl_msg_id,
                            ctrl_msg.retry_count,
                        )
                        # Clear pending_command flag for device
                        if ctrl_msg.device_id and ctrl_msg.device_id in g.ncync_server.devices:
                            device = g.ncync_server.devices[ctrl_msg.device_id]
                            if device.pending_command:
                                device.pending_command = False
                                logger.debug("%s Cleared pending flag for '%s'", lp, device.name)
                        to_delete.append(ctrl_msg_id)

                # Delete stale messages
                for msg_id in to_delete:
                    del self.messages.control[msg_id]

            except asyncio.CancelledError as can_exc:
                logger.debug("%s CANCELLED: %s", lp, can_exc)
                break
            except Exception:
                logger.exception("%s Exception in callback cleanup", lp)

        logger.debug("%s FINISHED", lp)

    async def receive_task(self):
        """
        Receive data from the device and respond to it. This is the main task for the device.
        It will respond to the device and handle the messages it sends.
        Runs in an infinite loop.
        """
        g = _get_global_object()
        lp = f"{self.address}:raw read:"
        started_at = time.time()
        name = self.tasks.receive.get_name()
        logger.debug("%s receive_task CALLED", lp) if CYNC_RAW is True else None
        try:
            while True:
                try:
                    data: bytes = await self.read()
                    if data is False:
                        logger.debug(
                            "%s read() returned False, exiting %s (started at: %s)...",
                            lp,
                            name,
                            datetime.datetime.fromtimestamp(started_at, tz=datetime.UTC),
                        )
                        break
                    if not data:
                        await asyncio.sleep(0)
                        continue
                    # Only process data from the primary TCP listener
                    if g.ncync_server.primary_tcp_device is None:
                        logger.warning("%s primary_tcp_device is None - skipping all packets", lp)
                        continue
                    if self != g.ncync_server.primary_tcp_device:
                        logger.info("%s Skipping non-primary connection data", lp)
                        continue
                    await self.parse_raw_data(data)

                except Exception:
                    logger.exception("%s Exception in %s LOOP", lp, name)
                    break
        except asyncio.CancelledError as cancel_exc:
            logger.debug("%s %s CANCELLED: %s", lp, name, cancel_exc)

        logger.debug("%s %s FINISHED", lp, name)

    async def read(self, chunk: int | None = None):
        """Read data from the device if there is an open connection"""
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

    @timed_async("tcp_write")
    async def write(self, data: bytes, broadcast: bool = False) -> bool | None:
        """
        Write data to the device if there is an open connection

        :param data: The raw binary data to write to the device
        :param broadcast: If True, write to all TCP devices connected to the server
        """
        g = _get_global_object()
        logger.debug(
            "→ Writing packet to device",
            extra={
                "address": self.address,
                "bytes": len(data),
                "broadcast": broadcast,
            },
        )
        if not isinstance(data, bytes):
            msg = f"Data must be bytes, not type: {type(data)}"
            raise TypeError(msg)
        dev = self
        if dev.closing:
            logger.debug(
                "Device closing, skipping write",
                extra={"address": dev.address},
            )
            return False
        if dev.writer is not None:
            async with dev.write_lock:
                # check if the underlying writer is closing
                if dev.writer.is_closing():
                    if dev.closing is False:
                        # this is probably a connection that was closed by the device (turned off), delete it
                        logger.warning(
                            "⚠️ Device connection dropped unexpectedly",
                            extra={
                                "address": dev.address,
                                "note": "Device likely lost power or connection",
                            },
                        )
                        off_dev = await g.ncync_server.remove_tcp_device(dev)
                        del off_dev

                    else:
                        logger.debug(
                            "Device closing, not writing",
                            extra={"address": dev.address},
                        )
                else:
                    dev.writer.write(data)
                    try:
                        await asyncio.wait_for(dev.writer.drain(), timeout=2.0)
                    except TimeoutError:
                        logger.exception(
                            "✗ Write timeout - device likely powered off",
                            extra={"address": dev.address},
                        )
                        raise
                    else:
                        logger.debug(
                            "✓ Packet sent successfully",
                            extra={"address": dev.address, "bytes": len(data)},
                        )
                        return True
        else:
            logger.warning(
                "⚠️ Cannot write - writer is None",
                extra={"address": dev.address},
            )
        return None

    async def close(self):
        logger.debug(
            "→ Closing device connection",
            extra={
                "address": self.address,
                "task_count": len(self.tasks),
            },
        )
        try:
            for dev_task in self.tasks:
                if dev_task and dev_task.done() is False:
                    logger.debug(
                        "Cancelling task",
                        extra={
                            "address": self.address,
                            "task_name": dev_task.get_name(),
                        },
                    )
                    dev_task.cancel()
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
