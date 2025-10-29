import asyncio
import contextlib
import time

from cync_controller.logging_abstraction import get_logger
from cync_controller.structs import GlobalObject

logger = get_logger(__name__)
g = GlobalObject()


class CyncTCPDevice:
    """
    A class to represent a Cync TCP device (bridge) that handles communication with the Cync cloud.
    """

    lp = "CyncTCPDevice:"
    address: str = None
    port: int = None
    reader: asyncio.StreamReader | None = None
    writer: asyncio.StreamWriter | None = None
    connected: bool = False
    ready_to_control: bool = False
    queue_id: bytes = None
    known_device_ids: set[int] = None
    mesh_info: dict | None = None
    messages: dict = None
    last_heartbeat: float = 0
    heartbeat_interval: float = 30.0
    reconnect_interval: float = 5.0
    max_reconnect_attempts: int = 10
    reconnect_attempts: int = 0
    _reconnect_task: asyncio.Task | None = None
    _heartbeat_task: asyncio.Task | None = None
    _read_task: asyncio.Task | None = None
    _write_lock: asyncio.Lock = None

    def __init__(
        self,
        address: str,
        port: int = 443,
        queue_id: bytes | None = None,
        known_device_ids: set[int] | None = None,
        mesh_info: dict | None = None,
    ):
        self.address = address
        self.port = port
        self.queue_id = queue_id or bytes([0x00, 0x00, 0x00, 0x00])
        self.known_device_ids = known_device_ids or set()
        self.mesh_info = mesh_info or {}
        self.messages = {
            "control": {},
            "status": {},
        }
        self._write_lock = asyncio.Lock()
        self.lp = f"CyncTCPDevice:{self.address}:"

    async def connect(self) -> bool:
        """
        Establish TCP connection to the Cync bridge device.

        Returns:
            bool: True if connection successful, False otherwise
        """
        lp = f"{self.lp}connect:"
        try:
            logger.info("%s Connecting to %s:%s", lp, self.address, self.port)
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.address, self.port),
                timeout=10.0,
            )
            self.connected = True
            self.reconnect_attempts = 0
            logger.info("%s Connected successfully", lp)

            # Start background tasks
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self._read_task = asyncio.create_task(self._read_loop())

            return True
        except TimeoutError:
            logger.exception("%s Connection timeout", lp)
            return False
        except Exception:
            logger.exception("%s Connection failed", lp)
            return False

    async def disconnect(self):
        """Close TCP connection and cleanup resources."""
        lp = f"{self.lp}disconnect:"
        logger.info("%s Disconnecting", lp)

        # Cancel background tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task

        if self._read_task:
            self._read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._read_task

        # Close connection
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception as e:
                logger.warning("%s Error closing writer: %s", lp, e)

        self.connected = False
        self.ready_to_control = False
        self.reader = None
        self.writer = None

    async def write(self, data: bytes) -> bool:
        """
        Write data to the TCP connection.

        Args:
            data: Bytes to write

        Returns:
            bool: True if write successful, False otherwise
        """
        lp = f"{self.lp}write:"
        if not self.connected or not self.writer:
            logger.error("%s Not connected", lp)
            return False

        async with self._write_lock:
            try:
                self.writer.write(data)
                await self.writer.drain()
                logger.debug("%s Sent %s bytes", lp, len(data))
                return True
            except Exception as e:
                logger.exception("%s Write failed", lp)
                self.connected = False
                return False

    async def _read_loop(self):
        """Background task to continuously read data from the TCP connection."""
        lp = f"{self.lp}_read_loop:"
        logger.info("%s Starting read loop", lp)

        while self.connected and self.reader:
            try:
                # Read data with timeout
                data = await asyncio.wait_for(self.reader.read(4096), timeout=1.0)
                if not data:
                    logger.warning("%s Connection closed by remote", lp)
                    break

                logger.debug("%s Received %s bytes", lp, len(data))
                # Process received data here
                await self._process_received_data(data)

            except asyncio.TimeoutError:
                # Normal timeout, continue reading
                continue
            except Exception as e:
                logger.exception("%s Read error", lp)
                break

        logger.info("%s Read loop ended", lp)
        self.connected = False

    async def _process_received_data(self, data: bytes):
        """
        Process received data from the TCP connection.

        Args:
            data: Received bytes
        """
        lp = f"{self.lp}_process_received_data:"
        logger.debug("%s Processing %s bytes", lp, len(data))

        # TODO: Implement packet parsing and processing
        # This would typically involve:
        # 1. Parsing the Cync protocol packets
        # 2. Updating device states
        # 3. Handling control message acknowledgments
        # 4. Processing mesh info updates

    async def _heartbeat_loop(self):
        """Background task to send periodic heartbeat messages."""
        lp = f"{self.lp}_heartbeat_loop:"
        logger.info("%s Starting heartbeat loop", lp)

        while self.connected:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                if self.connected:
                    await self._send_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("%s Heartbeat error", lp)
                break

        logger.info("%s Heartbeat loop ended", lp)

    async def _send_heartbeat(self):
        """Send a heartbeat message to keep the connection alive."""
        lp = f"{self.lp}_send_heartbeat:"
        logger.debug("%s Sending heartbeat", lp)

        # TODO: Implement actual heartbeat message
        # This would typically be a simple ping/pong message
        # to keep the connection alive

    async def reconnect(self):
        """Attempt to reconnect to the TCP device."""
        lp = f"{self.lp}reconnect:"
        if self._reconnect_task and not self._reconnect_task.done():
            logger.debug("%s Reconnect already in progress", lp)
            return

        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self):
        """Background task to handle reconnection attempts."""
        lp = f"{self.lp}_reconnect_loop:"
        logger.info("%s Starting reconnect loop", lp)

        while self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                await asyncio.sleep(self.reconnect_interval)
                if await self.connect():
                    logger.info("%s Reconnected successfully", lp)
                    return
                self.reconnect_attempts += 1
                logger.warning("%s Reconnect attempt %s/%s failed", lp, self.reconnect_attempts, self.max_reconnect_attempts)
            except Exception as e:
                logger.exception("%s Reconnect error", lp)
                self.reconnect_attempts += 1

        logger.error("%s Max reconnect attempts reached", lp)
        self._reconnect_task = None

    def get_ctrl_msg_id_bytes(self) -> bytes:
        """
        Get the next control message ID as bytes.

        Returns:
            bytes: 2-byte control message ID
        """
        # Simple incrementing counter for message IDs
        # In a real implementation, this would be more sophisticated
        msg_id = (int(time.time() * 1000) % 65536) & 0xFFFF
        return msg_id.to_bytes(2, byteorder="big")

    def __repr__(self):
        return f"<CyncTCPDevice: {self.address}:{self.port}>"

    def __str__(self):
        return f"CyncTCPDevice:{self.address}:{self.port}"