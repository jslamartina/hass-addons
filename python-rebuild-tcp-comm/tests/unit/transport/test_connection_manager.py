"""Unit tests for connection manager."""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from protocol.cync_protocol import CyncProtocol
from protocol.exceptions import CyncProtocolError, PacketDecodeError
from protocol.packet_framer import PacketFramer
from protocol.packet_types import (
    PACKET_TYPE_DATA_CHANNEL,
    PACKET_TYPE_HEARTBEAT_CLOUD,
    PACKET_TYPE_HELLO_ACK,
    CyncPacket,
)
from tests.helpers.expectations import expect_async_exception
from transport.connection_manager import ConnectionManager, ConnectionState
from transport.exceptions import CyncConnectionError
from transport.retry_policy import TimeoutConfig
from transport.socket_abstraction import TCPConnection

# Test constants
MAX_EXPECTED_LOCK_HOLD_TIME_SECONDS = 0.1  # Should be very fast (< 100ms)


class ConnectionManagerTestHarness(ConnectionManager):
    """Expose protected helpers for testing."""

    @property
    def data_packet_queue(self) -> asyncio.Queue[CyncPacket]:
        return self._data_packet_queue

    def create_packet_router_task(self) -> asyncio.Task[None]:
        return asyncio.create_task(self._packet_router())

    async def process_packets_for_test(self, packets: list[bytes]) -> None:
        await self._process_packets(packets)


class TestConnectionState:
    """Tests for ConnectionState enum."""

    def test_connection_state_values(self):
        """Test ConnectionState enum values."""
        assert ConnectionState.DISCONNECTED.value == "disconnected"
        assert ConnectionState.CONNECTING.value == "connecting"
        assert ConnectionState.CONNECTED.value == "connected"
        assert ConnectionState.RECONNECTING.value == "reconnecting"


class TestConnectionManagerInit:
    """Tests for ConnectionManager initialization."""

    def test_init_defaults(self):
        """Test ConnectionManager initialization with defaults."""
        conn = MagicMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)

        mgr = ConnectionManagerTestHarness(conn, protocol)

        assert mgr.conn == conn
        assert mgr.protocol == protocol
        assert mgr.state == ConnectionState.DISCONNECTED
        assert mgr.ack_handler is None
        assert isinstance(mgr.framer, PacketFramer)
        assert isinstance(mgr.data_packet_queue, asyncio.Queue)
        assert len(mgr.pending_requests) == 0

    def test_init_with_timeout_config(self):
        """Test ConnectionManager initialization with custom TimeoutConfig."""
        conn = MagicMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)
        timeout_config = TimeoutConfig(measured_p99_ms=100.0)

        mgr = ConnectionManagerTestHarness(conn, protocol, timeout_config=timeout_config)

        assert mgr.timeout_config == timeout_config

    def test_init_with_ack_handler(self):
        """Test ConnectionManager initialization with ACK handler."""
        conn = MagicMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)
        ack_handler = AsyncMock()

        mgr = ConnectionManagerTestHarness(conn, protocol, ack_handler=ack_handler)

        assert mgr.ack_handler == ack_handler


class TestConnectionManagerConnect:
    """Tests for ConnectionManager.connect()."""

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful handshake."""
        conn = AsyncMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)
        endpoint = b"\x01\x02\x03\x04\x05"
        auth_code = b"\x10" * 16

        # Mock handshake encoding
        handshake_packet = bytes([0x23, 0x00, 0x00, 0x00, 0x1A]) + b"handshake_data"
        protocol.encode_handshake.return_value = handshake_packet

        # Mock successful send
        conn.send.return_value = True

        # Mock successful ACK response
        ack_response = bytes([PACKET_TYPE_HELLO_ACK]) + b"ack_data"
        conn.recv.return_value = ack_response

        mgr = ConnectionManagerTestHarness(conn, protocol)

        result = await mgr.connect(endpoint, auth_code)

        assert result is True
        assert mgr.state == ConnectionState.CONNECTED
        assert mgr.endpoint == endpoint
        assert mgr.auth_code == auth_code
        assert mgr.packet_router_task is not None
        protocol.encode_handshake.assert_called_once_with(endpoint, auth_code)
        conn.send.assert_called_once_with(handshake_packet)

        # Clean up packet router task
        if mgr.packet_router_task and not mgr.packet_router_task.done():
            mgr.packet_router_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await mgr.packet_router_task
        mgr.packet_router_task = None

    @pytest.mark.asyncio
    async def test_connect_handshake_timeout(self):
        """Test handshake timeout."""
        conn = AsyncMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)
        endpoint = b"\x01\x02\x03\x04\x05"
        auth_code = b"\x10" * 16

        handshake_packet = bytes([0x23, 0x00, 0x00, 0x00, 0x1A]) + b"handshake_data"
        protocol.encode_handshake.return_value = handshake_packet

        conn.send.return_value = True
        conn.recv.side_effect = TimeoutError()

        mgr = ConnectionManagerTestHarness(conn, protocol)

        result = await mgr.connect(endpoint, auth_code)

        assert result is False
        assert mgr.state == ConnectionState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_connect_invalid_ack(self):
        """Test handshake with invalid ACK response."""
        conn = AsyncMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)
        endpoint = b"\x01\x02\x03\x04\x05"
        auth_code = b"\x10" * 16

        handshake_packet = bytes([0x23, 0x00, 0x00, 0x00, 0x1A]) + b"handshake_data"
        protocol.encode_handshake.return_value = handshake_packet

        conn.send.return_value = True
        # Invalid ACK (wrong packet type)
        conn.recv.return_value = bytes([0x7B]) + b"wrong_ack"

        mgr = ConnectionManagerTestHarness(conn, protocol)

        result = await mgr.connect(endpoint, auth_code)

        assert result is False
        assert mgr.state == ConnectionState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_connect_send_failure(self):
        """Test handshake with send failure."""
        conn = AsyncMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)
        endpoint = b"\x01\x02\x03\x04\x05"
        auth_code = b"\x10" * 16

        handshake_packet = bytes([0x23, 0x00, 0x00, 0x00, 0x1A]) + b"handshake_data"
        protocol.encode_handshake.return_value = handshake_packet

        conn.send.return_value = False  # Send failure

        mgr = ConnectionManagerTestHarness(conn, protocol)

        result = await mgr.connect(endpoint, auth_code)

        assert result is False
        assert mgr.state == ConnectionState.DISCONNECTED


class TestConnectionManagerPacketRouter:
    """Tests for ConnectionManager._packet_router()."""

    @pytest.mark.asyncio
    async def test_packet_router_data_packet_routing(self):
        """Test packet router routes data packets to queue."""
        conn = AsyncMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)

        # Mock decoded packet
        # Valid packet format: type=0x73, reserved=0x00 0x00,
        # length=0x00 0x04 (4 bytes), payload='test' (4 bytes)
        packet_bytes = b"\x73\x00\x00\x00\x04test"
        data_packet = CyncPacket(
            packet_type=PACKET_TYPE_DATA_CHANNEL,
            length=4,
            payload=b"test",
            raw=packet_bytes,
        )
        protocol.decode_packet.return_value = data_packet

        # Mock TCP read returning complete packet bytes, then StopAsyncIteration to stop loop
        conn.recv.side_effect = [
            packet_bytes,
            StopAsyncIteration(),
        ]  # StopAsyncIteration signals connection closed

        mgr = ConnectionManagerTestHarness(conn, protocol)
        mgr.state = ConnectionState.CONNECTED

        # Start packet router task
        router_task = mgr.create_packet_router_task()

        # Wait for packet to be processed (router will break on StopAsyncIteration)
        with contextlib.suppress(StopAsyncIteration):
            await router_task

        # Check that packet was queued
        assert not mgr.data_packet_queue.empty()
        queued_packet = mgr.data_packet_queue.get_nowait()
        assert queued_packet == data_packet

    @pytest.mark.asyncio
    async def test_packet_router_heartbeat_ack(self):
        """Test packet router handles heartbeat ACK."""
        conn = AsyncMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)

        # Mock heartbeat ACK packet
        heartbeat_ack = CyncPacket(
            packet_type=PACKET_TYPE_HEARTBEAT_CLOUD,
            length=5,
            payload=b"",
            raw=b"\xd8\x00\x00\x00\x00",
        )
        protocol.decode_packet.return_value = heartbeat_ack

        packet_bytes = b"\xd8\x00\x00\x00\x00"
        conn.recv.side_effect = [
            packet_bytes,
            StopAsyncIteration(),
        ]  # StopAsyncIteration signals connection closed

        mgr = ConnectionManagerTestHarness(conn, protocol)
        mgr.state = ConnectionState.CONNECTED
        mgr.endpoint = b"\x01\x02\x03\x04\x05"

        router_task = mgr.create_packet_router_task()

        await asyncio.sleep(0.1)

        router_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await router_task

        # Heartbeat ACK should not be queued (handled directly)
        assert mgr.data_packet_queue.empty()

    @pytest.mark.asyncio
    async def test_packet_router_ack_handler_callback(self):
        """Test packet router calls ACK handler callback."""
        conn = AsyncMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)
        ack_handler = AsyncMock()

        # Mock ACK packet
        ack_packet = CyncPacket(
            packet_type=PACKET_TYPE_HELLO_ACK,
            length=7,
            payload=b"",
            raw=b"\x28\x00\x00\x00\x02ack",
        )
        protocol.decode_packet.return_value = ack_packet

        packet_bytes = b"\x28\x00\x00\x00\x02ack"
        conn.recv.side_effect = [
            packet_bytes,
            StopAsyncIteration(),
        ]  # StopAsyncIteration signals connection closed

        mgr = ConnectionManagerTestHarness(conn, protocol, ack_handler=ack_handler)
        mgr.state = ConnectionState.CONNECTED

        router_task = mgr.create_packet_router_task()

        await asyncio.sleep(0.1)

        router_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await router_task

        # ACK handler should have been called
        ack_handler.assert_called_once_with(ack_packet)

    @pytest.mark.asyncio
    async def test_packet_router_packet_framer_integration(self):
        """Test packet router uses PacketFramer for partial packets."""
        conn = AsyncMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)

        # Simulate partial packet (header only)
        # Valid packet: type=0x73, reserved=0x00 0x00,
        # length=0x00 0x09 (9 bytes), payload='test_data' (9 bytes)
        partial_header = b"\x73\x00\x00\x00\x09"
        # Then complete packet
        complete_packet_bytes = partial_header + b"test_data"

        # First read: partial
        # Second read: complete
        # Third read: StopAsyncIteration to stop loop
        conn.recv.side_effect = [partial_header, complete_packet_bytes[5:], StopAsyncIteration()]

        data_packet = CyncPacket(
            packet_type=PACKET_TYPE_DATA_CHANNEL,
            length=9,
            payload=b"test_data",
            raw=complete_packet_bytes,
        )
        protocol.decode_packet.return_value = data_packet

        mgr = ConnectionManagerTestHarness(conn, protocol)
        mgr.state = ConnectionState.CONNECTED

        router_task = mgr.create_packet_router_task()

        # Wait for packet router to process packets and break on StopAsyncIteration
        with contextlib.suppress(StopAsyncIteration):
            await router_task

        # PacketFramer should have buffered partial packet and extracted complete one
        assert not mgr.data_packet_queue.empty()


class TestConnectionManagerReconnect:
    """Tests for ConnectionManager.reconnect()."""

    @pytest.mark.asyncio
    async def test_reconnect_success(self):
        """Test successful reconnection."""
        conn = AsyncMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)
        endpoint = b"\x01\x02\x03\x04\x05"
        auth_code = b"\x10" * 16

        handshake_packet = bytes([0x23, 0x00, 0x00, 0x00, 0x1A]) + b"handshake_data"
        protocol.encode_handshake.return_value = handshake_packet

        conn.send.return_value = True
        ack_response = bytes([PACKET_TYPE_HELLO_ACK]) + b"ack_data"
        conn.recv.return_value = ack_response

        mgr = ConnectionManagerTestHarness(conn, protocol)
        mgr.endpoint = endpoint
        mgr.auth_code = auth_code
        mgr.state = ConnectionState.CONNECTED

        # Mock disconnect
        mgr.disconnect = AsyncMock()

        result = await mgr.reconnect("test_reason")

        assert result is True
        mgr.disconnect.assert_called_once()

        # Clean up packet router task that was started by connect() during reconnect()
        if mgr.packet_router_task and not mgr.packet_router_task.done():
            mgr.packet_router_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await mgr.packet_router_task
        mgr.packet_router_task = None

    @pytest.mark.asyncio
    async def test_reconnect_no_credentials(self):
        """Test reconnection fails without credentials."""
        conn = AsyncMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)

        mgr = ConnectionManagerTestHarness(conn, protocol)
        mgr.endpoint = b""
        mgr.auth_code = b""

        err = await expect_async_exception(mgr.reconnect, CyncConnectionError, "test_reason")
        assert "no credentials stored" in str(err)


class TestConnectionManagerDisconnect:
    """Tests for ConnectionManager.disconnect()."""

    @pytest.mark.asyncio
    async def test_disconnect_cleanup_order(self):
        """Test disconnect cleans up tasks in correct order."""
        conn = AsyncMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)

        mgr = ConnectionManagerTestHarness(conn, protocol)
        mgr.state = ConnectionState.CONNECTED
        mgr.endpoint = b"\x01\x02\x03\x04\x05"

        # Create mock tasks (short sleep - just enough to test cancellation)
        packet_router_task: asyncio.Task[None] = asyncio.create_task(asyncio.sleep(0.1))
        reconnect_task_raw: asyncio.Task[None] = asyncio.create_task(asyncio.sleep(0.1))
        reconnect_task: asyncio.Task[bool | None] = reconnect_task_raw  # type: ignore[assignment]
        mgr.packet_router_task = packet_router_task
        mgr.reconnect_task = reconnect_task

        await mgr.disconnect()

        assert mgr.state == ConnectionState.DISCONNECTED
        assert mgr.packet_router_task is None
        assert mgr.reconnect_task is None
        assert packet_router_task.cancelled()
        assert reconnect_task.cancelled()
        conn.close.assert_called_once()

        # Wait briefly to ensure cancellation completes (prevents unretrieved task warnings)
        await asyncio.sleep(0.01)


class TestConnectionManagerWithStateCheck:
    """Tests for ConnectionManager.with_state_check()."""

    @pytest.mark.asyncio
    async def test_with_state_check_success(self):
        """Test with_state_check with CONNECTED state."""
        conn = MagicMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)

        mgr = ConnectionManagerTestHarness(conn, protocol)
        mgr.state = ConnectionState.CONNECTED

        action = AsyncMock(return_value="result")

        result = await mgr.with_state_check("test_operation", action)

        assert result == "result"
        action.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_state_check_not_connected(self):
        """Test with_state_check raises error when not CONNECTED."""
        conn = MagicMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)

        mgr = ConnectionManagerTestHarness(conn, protocol)
        mgr.state = ConnectionState.DISCONNECTED

        action = AsyncMock()

        err = await expect_async_exception(mgr.with_state_check, CyncConnectionError, "test_operation", action)
        assert "CONNECTED state" in str(err)
        action.assert_not_called()

    @pytest.mark.asyncio
    async def test_with_state_check_lock_hold_time(self):
        """Test with_state_check records lock hold time."""
        conn = MagicMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)

        mgr = ConnectionManagerTestHarness(conn, protocol)
        mgr.state = ConnectionState.CONNECTED

        action = AsyncMock(return_value="result")

        with patch("metrics.registry.record_state_lock_hold") as mock_record:
            await mgr.with_state_check("test_operation", action)

            # Should record lock hold time
            mock_record.assert_called_once()
            hold_time = mock_record.call_args[0][0]
            assert hold_time >= 0
            assert hold_time < MAX_EXPECTED_LOCK_HOLD_TIME_SECONDS


class TestConnectionManagerFIFOQueue:
    """Tests for FIFO queue matching."""

    @pytest.mark.asyncio
    async def test_fifo_queue_handshake_matching(self):
        """Test FIFO queue matches handshake ACK."""
        conn = AsyncMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)
        endpoint = b"\x01\x02\x03\x04\x05"
        auth_code = b"\x10" * 16

        handshake_packet = bytes([0x23, 0x00, 0x00, 0x00, 0x1A]) + b"handshake_data"
        protocol.encode_handshake.return_value = handshake_packet

        conn.send.return_value = True
        ack_response = bytes([PACKET_TYPE_HELLO_ACK]) + b"ack_data"
        conn.recv.return_value = ack_response

        mgr = ConnectionManagerTestHarness(conn, protocol)

        result = await mgr.connect(endpoint, auth_code)

        assert result is True
        # Pending request should have been matched and removed
        assert len(mgr.pending_requests) == 0

        # Clean up packet router task
        if mgr.packet_router_task and not mgr.packet_router_task.done():
            mgr.packet_router_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await mgr.packet_router_task
        mgr.packet_router_task = None


class TestConnectionManagerIsConnected:
    """Tests for ConnectionManager.is_connected()."""

    def test_is_connected_true(self):
        """Test is_connected returns True when CONNECTED."""
        conn = MagicMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)

        mgr = ConnectionManagerTestHarness(conn, protocol)
        mgr.state = ConnectionState.CONNECTED

        assert mgr.is_connected() is True

    def test_is_connected_false(self):
        """Test is_connected returns False when not CONNECTED."""
        conn = MagicMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)

        mgr = ConnectionManagerTestHarness(conn, protocol)
        mgr.state = ConnectionState.DISCONNECTED

        assert mgr.is_connected() is False


class TestConnectionManagerExceptionHandling:
    """Tests for exception handling in ConnectionManager."""

    @pytest.mark.asyncio
    async def test_connect_handshake_exception_propagates(self):
        """Test that exceptions during handshake are logged and retried."""
        conn = AsyncMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)
        endpoint = b"\x01\x02\x03\x04\x05"
        auth_code = b"\x10" * 16

        handshake_packet = bytes([0x23, 0x00, 0x00, 0x00, 0x1A]) + b"handshake_data"
        protocol.encode_handshake.return_value = handshake_packet

        # First attempt raises exception, second succeeds
        conn.send.side_effect = [OSError("Network error"), True]
        ack_response = bytes([PACKET_TYPE_HELLO_ACK]) + b"ack_data"
        conn.recv.return_value = ack_response

        mgr = ConnectionManager(conn, protocol)

        result = await mgr.connect(endpoint, auth_code)

        # Should succeed on retry
        assert result is True
        max_retries = 3
        assert conn.send.call_count <= max_retries  # First attempt + retries

        # Clean up packet router task
        if mgr.packet_router_task and not mgr.packet_router_task.done():
            mgr.packet_router_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await mgr.packet_router_task
        mgr.packet_router_task = None

    @pytest.mark.asyncio
    async def test_ack_handler_exception_protocol_error_raises(self):
        """Test that protocol errors in ACK handler are re-raised."""
        conn = AsyncMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)

        ack_handler = AsyncMock(side_effect=CyncProtocolError("Protocol error"))

        # Mock ACK packet
        ack_packet = CyncPacket(
            packet_type=PACKET_TYPE_HELLO_ACK,
            length=7,
            payload=b"",
            raw=b"\x28\x00\x00\x00\x02ack",
        )
        protocol.decode_packet.return_value = ack_packet

        packet_bytes = b"\x28\x00\x00\x00\x02ack"
        conn.recv.side_effect = [packet_bytes, StopAsyncIteration()]

        mgr = ConnectionManagerTestHarness(conn, protocol, ack_handler=ack_handler)
        mgr.state = ConnectionState.CONNECTED

        router_task = mgr.create_packet_router_task()

        # Should raise the protocol error
        with pytest.raises(CyncProtocolError):
            await router_task

    @pytest.mark.asyncio
    async def test_ack_handler_exception_unexpected_swallowed(self):
        """Test that unexpected exceptions in ACK handler are logged but not re-raised."""
        conn = AsyncMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)

        ack_handler = AsyncMock(side_effect=ValueError("Unexpected error"))

        # Mock ACK packet
        ack_packet = CyncPacket(
            packet_type=PACKET_TYPE_HELLO_ACK,
            length=7,
            payload=b"",
            raw=b"\x28\x00\x00\x00\x02ack",
        )
        protocol.decode_packet.return_value = ack_packet

        packet_bytes = b"\x28\x00\x00\x00\x02ack"
        conn.recv.side_effect = [packet_bytes, StopAsyncIteration()]

        mgr = ConnectionManagerTestHarness(conn, protocol, ack_handler=ack_handler)
        mgr.state = ConnectionState.CONNECTED

        router_task = mgr.create_packet_router_task()

        # Should not raise - unexpected errors are swallowed
        with contextlib.suppress(StopAsyncIteration):
            await router_task

        # Handler should have been called
        ack_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_packet_decode_error_continues_processing(self):
        """Test that packet decode errors are logged and processing continues."""
        conn = AsyncMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)

        # Test _process_packets directly with decode errors
        bad_packet_bytes = b"bad_packet_data"
        good_packet_bytes = b"\x73\x00\x00\x00\x04test"
        good_packet = CyncPacket(
            packet_type=PACKET_TYPE_DATA_CHANNEL,
            length=4,
            payload=b"test",
            raw=good_packet_bytes,
        )

        # First packet fails to decode, second succeeds
        protocol.decode_packet.side_effect = [
            PacketDecodeError("invalid_checksum", bad_packet_bytes),
            good_packet,
        ]

        mgr = ConnectionManagerTestHarness(conn, protocol)
        mgr.state = ConnectionState.CONNECTED

        # Process packets directly
        await mgr.process_packets_for_test([bad_packet_bytes, good_packet_bytes])

        # Should have processed the second packet despite first decode error
        assert not mgr.data_packet_queue.empty()
        queued_packet = mgr.data_packet_queue.get_nowait()
        assert queued_packet == good_packet

    @pytest.mark.asyncio
    async def test_packet_router_exception_triggers_reconnect(self):
        """Test that exceptions in packet router trigger reconnection."""
        conn = AsyncMock(spec=TCPConnection)
        protocol = MagicMock(spec=CyncProtocol)

        # Simulate exception during packet processing
        conn.recv.side_effect = RuntimeError("Unexpected error")

        mgr = ConnectionManagerTestHarness(conn, protocol)
        mgr.state = ConnectionState.CONNECTED
        mgr.endpoint = b"\x01\x02\x03\x04\x05"
        mgr.auth_code = b"\x10" * 16  # Set credentials so reconnect can work

        router_task = mgr.create_packet_router_task()

        # Should raise the exception (which triggers reconnect)
        with pytest.raises(RuntimeError):
            await router_task

        # Reconnect should have been triggered
        assert mgr.reconnect_task is not None

        # Clean up reconnect task (wait briefly to let it start)
        await asyncio.sleep(0.01)
        if mgr.reconnect_task and not mgr.reconnect_task.done():
            mgr.reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, CyncConnectionError):
                await mgr.reconnect_task
        mgr.reconnect_task = None
