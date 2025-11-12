"""Asyncio TCP socket abstraction with deadlines and instrumentation."""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class TCPConnection:
    """Async TCP connection with timeouts and instrumentation."""

    def __init__(
        self,
        host: str,
        port: int,
        connect_timeout: float = 1.0,
        io_timeout: float = 1.5,
        max_read_size: int = 65536,
    ):
        """
        Initialize TCP connection parameters.

        Args:
            host: Target host
            port: Target port
            connect_timeout: Connection timeout in seconds
            io_timeout: Read/write timeout in seconds
            max_read_size: Maximum bytes to read in one operation
        """
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self.io_timeout = io_timeout
        self.max_read_size = max_read_size
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self._connected = False

    async def connect(self) -> bool:
        """
        Establish TCP connection with timeout.

        Returns:
            True if connected successfully, False otherwise
        """
        start_time = time.perf_counter()
        try:
            logger.info(
                "Connecting to %s:%d (timeout: %.1fs)",
                self.host,
                self.port,
                self.connect_timeout,
                extra={"host": self.host, "port": self.port, "timeout": self.connect_timeout},
            )
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.connect_timeout,
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._connected = True
            logger.info(
                "Connected to %s:%d in %.1fms",
                self.host,
                self.port,
                elapsed_ms,
                extra={"host": self.host, "port": self.port, "elapsed_ms": elapsed_ms},
            )
        except TimeoutError:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "Connection to %s:%d timed out after %.1fms",
                self.host,
                self.port,
                elapsed_ms,
                extra={
                    "host": self.host,
                    "port": self.port,
                    "elapsed_ms": elapsed_ms,
                    "error": "timeout",
                },
            )
            return False
        except OSError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "Connection to %s:%d failed after %.1fms",
                self.host,
                self.port,
                elapsed_ms,
                extra={
                    "host": self.host,
                    "port": self.port,
                    "elapsed_ms": elapsed_ms,
                    "error": str(e),
                },
            )
            return False
        else:
            return True

    async def send(self, data: bytes) -> bool:
        """
        Send data with timeout.

        Args:
            data: Bytes to send

        Returns:
            True if sent successfully, False otherwise
        """
        if not self._connected or not self.writer:
            logger.error(
                "Cannot send: not connected",
                extra={"host": self.host, "port": self.port},
            )
            return False

        start_time = time.perf_counter()
        try:
            logger.debug(
                "Sending %d bytes to %s:%d",
                len(data),
                self.host,
                self.port,
                extra={"bytes": len(data), "host": self.host, "port": self.port},
            )
            self.writer.write(data)
            await asyncio.wait_for(self.writer.drain(), timeout=self.io_timeout)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.debug(
                "Sent %d bytes to %s:%d in %.1fms",
                len(data),
                self.host,
                self.port,
                elapsed_ms,
                extra={
                    "bytes": len(data),
                    "host": self.host,
                    "port": self.port,
                    "elapsed_ms": elapsed_ms,
                },
            )
        except TimeoutError:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "Send to %s:%d timed out after %.1fms",
                self.host,
                self.port,
                elapsed_ms,
                extra={
                    "host": self.host,
                    "port": self.port,
                    "elapsed_ms": elapsed_ms,
                    "error": "timeout",
                },
            )
            return False
        except OSError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "Send to %s:%d failed after %.1fms",
                self.host,
                self.port,
                elapsed_ms,
                extra={
                    "host": self.host,
                    "port": self.port,
                    "elapsed_ms": elapsed_ms,
                    "error": str(e),
                },
            )
            return False
        else:
            return True

    async def recv(self, max_bytes: int | None = None) -> bytes | None:
        """
        Receive data with timeout.

        Args:
            max_bytes: Maximum bytes to read (default: self.max_read_size)

        Returns:
            Received bytes, or None on error/timeout
        """
        if not self._connected or not self.reader:
            logger.error(
                "Cannot receive: not connected",
                extra={"host": self.host, "port": self.port},
            )
            return None

        if max_bytes is None:
            max_bytes = self.max_read_size

        start_time = time.perf_counter()
        try:
            logger.debug(
                "Receiving up to %d bytes from %s:%d",
                max_bytes,
                self.host,
                self.port,
                extra={"max_bytes": max_bytes, "host": self.host, "port": self.port},
            )
            data = await asyncio.wait_for(
                self.reader.read(max_bytes),
                timeout=self.io_timeout,
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            if not data:
                logger.warning(
                    "Connection closed by %s:%d after %.1fms",
                    self.host,
                    self.port,
                    elapsed_ms,
                    extra={"host": self.host, "port": self.port, "elapsed_ms": elapsed_ms},
                )
                self._connected = False
                return None
            logger.debug(
                "Received %d bytes from %s:%d in %.1fms",
                len(data),
                self.host,
                self.port,
                elapsed_ms,
                extra={
                    "bytes": len(data),
                    "host": self.host,
                    "port": self.port,
                    "elapsed_ms": elapsed_ms,
                },
            )
        except TimeoutError:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "Receive from %s:%d timed out after %.1fms",
                self.host,
                self.port,
                elapsed_ms,
                extra={
                    "host": self.host,
                    "port": self.port,
                    "elapsed_ms": elapsed_ms,
                    "error": "timeout",
                },
            )
            return None
        except OSError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "Receive from %s:%d failed after %.1fms",
                self.host,
                self.port,
                elapsed_ms,
                extra={
                    "host": self.host,
                    "port": self.port,
                    "elapsed_ms": elapsed_ms,
                    "error": str(e),
                },
            )
            return None
        else:
            return data

    async def close(self) -> None:
        """Close the connection."""
        if self.writer:
            logger.info(
                "Closing connection to %s:%d",
                self.host,
                self.port,
                extra={"host": self.host, "port": self.port},
            )
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except (OSError, ConnectionError) as e:
                logger.warning(
                    "Error closing connection: %s",
                    e,
                    extra={
                        "host": self.host,
                        "port": self.port,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
            except Exception as e:
                # Cleanup operations should not fail - log but continue
                # This is best-effort cleanup, so we don't re-raise unexpected errors.
                # Broad catch is intentional: writer.close()/wait_closed() can raise various
                # exceptions (OSError, RuntimeError, AttributeError) and we want to ensure
                # cleanup completes even if close fails.
                logger.warning(
                    "Unexpected error during connection close (non-fatal): %s",
                    e,
                    extra={
                        "host": self.host,
                        "port": self.port,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
            finally:
                self._connected = False
                self.writer = None
                self.reader = None

    @property
    def is_connected(self) -> bool:
        """Check if connection is active."""
        return self._connected

    def __repr__(self) -> str:
        """String representation."""
        status = "connected" if self._connected else "disconnected"
        return f"TCPConnection({self.host}:{self.port}, {status})"
