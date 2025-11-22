"""Fixtures for integration tests."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, cast

import pytest

from .performance import PerformanceTracker

logger = logging.getLogger(__name__)


class ResponseMode(Enum):
    """Response mode for mock TCP server."""

    SUCCESS = "success"  # Immediate ACK response
    DELAY = "delay"  # Delayed response (simulates slow network)
    DISCONNECT = "disconnect"  # Accept connection then close immediately
    TIMEOUT = "timeout"  # Never respond (simulates timeout)
    REJECT = "reject"  # Refuse connection


@dataclass
class ReceivedPacket:
    """Represents a packet received by the mock server."""

    magic: bytes
    version: int
    length: int
    payload: dict[str, Any]
    raw_bytes: bytes


class MockTCPServer:
    """Mock TCP server for integration testing."""

    def __init__(
        self,
        response_mode: ResponseMode = ResponseMode.SUCCESS,
        response_delay: float = 0.0,
        host: str = "127.0.0.1",
        port: int = 0,
    ):
        """Initialize mock TCP server.

        Args:
            response_mode: How the server should respond
            response_delay: Delay before responding (for DELAY mode)
            host: Host to bind to
            port: Port to bind to (0 = OS assigns)

        """
        self.response_mode = response_mode
        self.response_delay = response_delay
        self.host = host
        self.port = port
        self.server: asyncio.Server | None = None
        self.received_packets: list[ReceivedPacket] = []
        self.connection_count = 0
        self._should_accept_connection = True

    async def start(self) -> None:
        """Start the mock TCP server."""
        self.server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port,
        )
        # Get the actual port assigned
        if self.port == 0:
            self.port = self.server.sockets[0].getsockname()[1]
        logger.info("Mock TCP server started on %s:%d", self.host, self.port)

    async def stop(self) -> None:
        """Stop the mock TCP server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Mock TCP server stopped")

    def set_response_mode(self, mode: ResponseMode) -> None:
        """Change response mode dynamically."""
        self.response_mode = mode

    def reject_next_connection(self) -> None:
        """Reject the next connection attempt."""
        self._should_accept_connection = False

    async def _handle_connection_rejection(self, writer: asyncio.StreamWriter) -> bool:
        """Handle connection rejection/disconnect modes. Returns True if connection handled."""
        if self.response_mode == ResponseMode.REJECT or not self._should_accept_connection:
            logger.info("Rejecting connection (mode: %s)", self.response_mode)
            writer.close()
            await writer.wait_closed()
            self._should_accept_connection = True  # Reset for next connection
            return True

        if self.response_mode == ResponseMode.DISCONNECT:
            logger.info("Accepting then disconnecting")
            writer.close()
            await writer.wait_closed()
            return True

        return False

    async def _read_packet_header(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> tuple[bytes, int, int] | None:
        """Read and parse packet header. Returns (magic, version, payload_length) or None."""
        header_length = 7  # magic (2) + version (1) + length (4)
        header = await asyncio.wait_for(reader.read(header_length), timeout=2.0)
        if len(header) < header_length:
            logger.error("Incomplete header received: %d bytes", len(header))
            writer.close()
            await writer.wait_closed()
            return None

        magic = header[0:2]
        version = header[2]
        payload_length = int.from_bytes(header[3:7], "big")

        logger.info(
            "Received header: magic=%s, version=0x%02x, length=%d",
            magic.hex(),
            version,
            payload_length,
        )
        return (magic, version, payload_length)

    async def _read_packet_payload(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        payload_length: int,
    ) -> tuple[bytes, dict[str, Any]] | None:
        """Read and parse packet payload. Returns (payload_bytes, payload_dict) or None."""
        payload_bytes = await asyncio.wait_for(
            reader.read(payload_length),
            timeout=2.0,
        )
        if len(payload_bytes) < payload_length:
            logger.error(
                "Incomplete payload: expected %d, got %d",
                payload_length,
                len(payload_bytes),
            )
            writer.close()
            await writer.wait_closed()
            return None

        try:
            payload_dict = json.loads(payload_bytes.decode("utf-8"))
            logger.info("Parsed payload: %s", payload_dict)
        except json.JSONDecodeError:
            logger.exception("Failed to parse JSON payload")
            writer.close()
            await writer.wait_closed()
            return None

        return (payload_bytes, payload_dict)

    async def _send_response(self, writer: asyncio.StreamWriter) -> None:
        """Send response based on response mode."""
        if self.response_mode == ResponseMode.SUCCESS:
            response = b"ACK"
            writer.write(response)
            await writer.drain()
            logger.info("Sent ACK response")
        elif self.response_mode == ResponseMode.DELAY:
            logger.info("Delaying response by %.2fs", self.response_delay)
            await asyncio.sleep(self.response_delay)
            response = b"ACK"
            writer.write(response)
            await writer.drain()
            logger.info("Sent delayed ACK response")
        elif self.response_mode == ResponseMode.TIMEOUT:
            logger.info("Timeout mode - not responding")
            await asyncio.sleep(5.0)  # Long enough to trigger client timeout

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle incoming client connection."""
        self.connection_count += 1
        addr = writer.get_extra_info("peername")
        logger.info("Connection #%d from %s", self.connection_count, addr)

        # Handle rejection/disconnect modes
        if await self._handle_connection_rejection(writer):
            return

        try:
            # Read packet header
            header_result = await self._read_packet_header(reader, writer)
            if header_result is None:
                return
            magic, version, payload_length = header_result

            # Read packet payload
            payload_result = await self._read_packet_payload(reader, writer, payload_length)
            if payload_result is None:
                return
            payload_bytes, payload_dict = payload_result

            # Store received packet
            header = magic + bytes([version]) + payload_length.to_bytes(4, "big")
            packet = ReceivedPacket(
                magic=magic,
                version=version,
                length=payload_length,
                payload=payload_dict,
                raw_bytes=header + payload_bytes,
            )
            self.received_packets.append(packet)

            # Send response based on mode
            await self._send_response(writer)

        except TimeoutError:
            logger.warning("Timeout reading from client")
        except Exception:
            logger.exception("Error handling client")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                logger.warning("Error closing writer: %s", e)


@pytest.fixture
async def mock_tcp_server() -> AsyncGenerator[MockTCPServer]:
    """Fixture providing a mock TCP server."""
    server = MockTCPServer()
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
async def mock_tcp_server_with_delay() -> AsyncGenerator[MockTCPServer]:
    """Fixture providing a mock TCP server with delayed responses."""
    server = MockTCPServer(response_mode=ResponseMode.DELAY, response_delay=2.0)
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
async def mock_tcp_server_timeout() -> AsyncGenerator[MockTCPServer]:
    """Fixture providing a mock TCP server that never responds."""
    server = MockTCPServer(response_mode=ResponseMode.TIMEOUT)
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
def unique_device_id(request: pytest.FixtureRequest) -> str:
    """Generate unique device ID for each test to avoid metric collisions.

    Uses the test node ID to ensure uniqueness.
    """
    # Use test name as device ID to ensure uniqueness
    test_name: str = cast(str, getattr(request.node, "name", ""))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    # Sanitize for use as device_id
    device_id: str = test_name.replace("[", "_").replace("]", "_").replace("-", "_")
    return f"TEST_{device_id}"


@pytest.fixture
def unique_metrics_port() -> int:
    """Get a unique port for metrics server.

    In practice, since we're running tests sequentially and the metrics
    server is global, we'll use a fixed port. The metrics server is
    idempotent and will reuse the existing server.
    """
    return 19400  # High port to avoid conflicts


@pytest.fixture(scope="session")
def performance_tracker() -> PerformanceTracker:
    """Session-scoped performance tracker for collecting latency metrics."""
    return PerformanceTracker()


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: Any) -> None:  # noqa: ARG001
    """Hook to display performance report at end of test session."""
    # Get the performance tracker from the session
    tracker = getattr(config, "_performance_tracker", None)

    if tracker is None or not tracker.samples:
        return

    # Display text report
    terminalreporter.write_line(tracker.format_text_report())

    # Save JSON artifact
    report_path = Path("test-reports/performance-report.json")
    tracker.save_report(report_path)
    terminalreporter.write_line(
        f"Performance report saved to: {report_path}",
        bold=True,
    )


@pytest.fixture(scope="session", autouse=True)
def _init_performance_tracker(  # pyright: ignore[reportUnusedFunction]
    request: pytest.FixtureRequest,
    performance_tracker: PerformanceTracker,
) -> PerformanceTracker:
    """Initialize performance tracker in pytest config."""
    request.config._performance_tracker = performance_tracker  # pyright: ignore[reportAttributeAccessIssue]
    return performance_tracker
