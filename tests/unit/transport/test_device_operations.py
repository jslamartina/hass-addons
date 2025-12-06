"""Unit tests for DeviceOperations class.

Tests for mesh info and device info request/response handling with:
- Primary device enforcement
- Packet/ACK analysis
- DEVICE_TYPE_LENGTH-byte device struct parsing
- Error handling and metrics

Test data uses fixtures from Phase 0.5 packet captures where available.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, Mock

import pytest

from cync_controller.protocol import PACKET_TYPE_STATUS_BROADCAST
from cync_controller.transport.device_info import (
    DEVICE_TYPE_BULB,
    DeviceInfo,
    DeviceInfoRequestError,
    DeviceStructParseError,
    MeshInfoRequestError,
)
from cync_controller.transport.device_operations import DeviceOperations
from tests.helpers.expectations import expect_async_exception

EXPECTED_DEVICE_COUNT = 2

# Test constants
MAX_BRIGHTNESS = 255
DEVICE_TYPE_LENGTH = 24
EXPECTED_RECV_CALL_COUNT = 2  # One for timeout, one for actual packet


class DeviceOperationsTestHarness(DeviceOperations):
    """Expose protected helpers for unit tests."""

    async def parse_device_struct_for_test(self, device_struct: bytes, *, correlation_id: str) -> DeviceInfo:
        return await self._parse_device_struct(device_struct, correlation_id=correlation_id)

    async def parse_0x83_packet_for_test(self, packet: MockCyncPacket, *, correlation_id: str) -> list[DeviceInfo]:
        return await self._parse_0x83_packet(packet, correlation_id=correlation_id)

    async def add_to_cache_for_test(self, device_id_hex: str, device_info: DeviceInfo) -> None:
        await self._add_to_cache(device_id_hex, device_info)


class MockCyncPacket:
    """Mock CyncPacket for testing."""

    def __init__(self, packet_type: int, payload: bytes):
        self.packet_type = packet_type
        self.payload = payload


class MockTrackedPacket:
    """Mock TrackedPacket for testing."""

    def __init__(self, packet: MockCyncPacket):
        self.packet = packet


class MockSendResult:
    """Mock SendResult for testing."""

    def __init__(self, success: bool, reason: str = ""):
        self.success = success
        self.reason = reason


@pytest.fixture
def mock_transport():
    """Create mock ReliableTransport."""
    transport = Mock()
    transport.send_reliable = AsyncMock()
    transport.recv_reliable = AsyncMock()
    return transport


@pytest.fixture
def mock_protocol():
    """Create mock CyncProtocol."""
    return Mock()


@pytest.fixture
def device_ops(mock_transport: Mock, mock_protocol: Mock) -> DeviceOperationsTestHarness:
    """Create DeviceOperations instance with mocks."""
    return DeviceOperationsTestHarness(mock_transport, mock_protocol)


@pytest.mark.asyncio
async def test_ask_for_mesh_info_success(device_ops: DeviceOperationsTestHarness, mock_transport: Mock) -> None:
    """Test successful mesh info request with 0x83 responses."""
    # Setup
    device_ops.set_primary(True)
    mock_transport.send_reliable.return_value = MockSendResult(success=True)

    # Mock 0x83 status broadcast response
    response_packet = MockCyncPacket(
        packet_type=0x83,
        payload=bytes(DEVICE_TYPE_LENGTH),  # DEVICE_TYPE_LENGTH-byte device struct
    )
    tracked_packet = MockTrackedPacket(response_packet)

    # Return packet once, then timeout
    mock_transport.recv_reliable.side_effect = [tracked_packet, TimeoutError()]

    # Execute
    responses = await device_ops.ask_for_mesh_info(parse=False)

    # Assert
    assert len(responses) == 1
    assert responses[0].packet_type == PACKET_TYPE_STATUS_BROADCAST
    mock_transport.send_reliable.assert_called_once()
    assert mock_transport.recv_reliable.call_count == EXPECTED_RECV_CALL_COUNT


@pytest.mark.asyncio
async def test_ask_for_mesh_info_parse(device_ops: DeviceOperationsTestHarness, mock_transport: Mock) -> None:
    """Test mesh info request with parsing enabled."""
    # Setup
    device_ops.set_primary(True)
    mock_transport.send_reliable.return_value = MockSendResult(success=True)

    # Mock 0x83 packet with DEVICE_TYPE_LENGTH-byte device struct
    device_struct = bytes(
        [
            0x39,
            0x87,
            0xC8,
            0x57,  # device_id
            0x01,
            0x00,
            0x00,
            0x00,  # capabilities (type=0x01)
            0x01,
            0xFF,
            0x00,
            0x00,  # state (on=True, brightness=MAX_BRIGHTNESS)
            0x00,
            0x00,
            0x00,
            0x00,  # padding
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    response_packet = MockCyncPacket(packet_type=0x83, payload=device_struct)
    tracked_packet = MockTrackedPacket(response_packet)

    # Return packet once, then timeout
    mock_transport.recv_reliable.side_effect = [tracked_packet, TimeoutError()]

    # Execute
    responses = await device_ops.ask_for_mesh_info(parse=True)

    # Assert
    assert len(responses) == 1
    assert isinstance(responses[0], DeviceInfo)
    assert responses[0].device_id == bytes([0x39, 0x87, 0xC8, 0x57])
    assert responses[0].device_type == 0x01
    assert responses[0].state["on"] is True


@pytest.mark.asyncio
async def test_ask_for_mesh_info_primary_only(device_ops: DeviceOperationsTestHarness) -> None:
    """Test that non-primary device cannot request mesh info."""
    # Setup - NOT setting is_primary to True
    device_ops.set_primary(False)

    # Execute & Assert
    err = await expect_async_exception(device_ops.ask_for_mesh_info, MeshInfoRequestError)
    assert err.reason == "not_primary"


@pytest.mark.asyncio
async def test_ask_for_mesh_info_send_failed(device_ops: DeviceOperationsTestHarness, mock_transport: Mock) -> None:
    """Test mesh info request with send failure."""
    # Setup
    device_ops.set_primary(True)
    mock_transport.send_reliable.return_value = MockSendResult(success=False, reason="connection_lost")

    # Execute & Assert
    err = await expect_async_exception(device_ops.ask_for_mesh_info, MeshInfoRequestError)
    assert err.reason == "connection_lost"


@pytest.mark.asyncio
async def test_request_device_info(device_ops: DeviceOperationsTestHarness, mock_transport: Mock) -> None:
    """Test individual device info request (0x43)."""
    # Setup
    device_id = bytes([0x39, 0x87, 0xC8, 0x57])
    mock_transport.send_reliable.return_value = MockSendResult(success=True)

    # Mock 0x43 device info response
    device_struct = bytes(
        [
            0x39,
            0x87,
            0xC8,
            0x57,  # device_id
            0x02,
            0x00,
            0x00,
            0x00,  # capabilities (type=0x02 - bulb)
            0x01,
            0x80,
            0x00,
            0x00,  # state (on=True, brightness=128)
            0x00,
            0x00,
            0x00,
            0x00,  # padding
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    response_packet = MockCyncPacket(packet_type=0x43, payload=device_struct)
    tracked_packet = MockTrackedPacket(response_packet)

    mock_transport.recv_reliable.return_value = tracked_packet

    # Execute
    device_info = await device_ops.request_device_info(device_id)

    # Assert
    assert device_info is not None
    assert device_info.device_id == device_id
    assert device_info.device_type == DEVICE_TYPE_BULB
    assert device_info.state["on"] is True


@pytest.mark.asyncio
async def test_request_device_info_timeout(device_ops: DeviceOperationsTestHarness, mock_transport: Mock) -> None:
    """Test device info request timeout."""
    # Setup
    device_id = bytes([0x39, 0x87, 0xC8, 0x57])
    mock_transport.send_reliable.return_value = MockSendResult(success=True)
    mock_transport.recv_reliable.side_effect = TimeoutError()

    # Execute
    device_info = await device_ops.request_device_info(device_id, timeout=1.0)

    # Assert
    assert device_info is None


@pytest.mark.asyncio
async def test_device_struct_parsing(device_ops: DeviceOperationsTestHarness) -> None:
    """Test parsing of DEVICE_TYPE_LENGTH-byte device struct."""
    # Setup - device struct from Phase 0.5 captures
    device_struct = bytes(
        [
            0x39,
            0x87,
            0xC8,
            0x57,  # device_id
            0x01,
            0x00,
            0x00,
            0x00,  # capabilities (type=0x01 - bridge)
            0x01,
            0xFF,
            0x00,
            0x00,  # state (on=True, brightness=MAX_BRIGHTNESS)
            0x00,
            0x00,
            0x00,
            0x00,  # additional fields
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )

    # Execute
    device_info = await device_ops.parse_device_struct_for_test(
        device_struct, correlation_id="12345678-1234-1234-1234-123456789abc"
    )

    # Assert
    assert device_info.device_id == bytes([0x39, 0x87, 0xC8, 0x57])
    assert device_info.device_type == 0x01
    assert device_info.state["on"] is True
    assert device_info.state["brightness"] == MAX_BRIGHTNESS
    assert len(device_info.raw_bytes) == DEVICE_TYPE_LENGTH


@pytest.mark.asyncio
async def test_device_struct_parsing_invalid_length(
    device_ops: DeviceOperationsTestHarness,
) -> None:
    """Test device struct parsing with invalid length."""
    # Setup - struct with wrong length
    invalid_struct = bytes([0x01, 0x02, 0x03])  # Only 3 bytes

    # Execute & Assert
    err = await expect_async_exception(
        device_ops.parse_device_struct_for_test,
        DeviceStructParseError,
        invalid_struct,
        correlation_id="12345678-1234-1234-1234-123456789abc",
    )
    assert "Invalid device struct length" in str(err)


def test_set_primary(device_ops: DeviceOperationsTestHarness) -> None:
    """Test setting primary device status."""
    # Initial state
    assert device_ops.is_primary is False
    # Set to primary
    device_ops.set_primary(True)
    assert device_ops.is_primary is True
    # Unset primary
    device_ops.set_primary(False)
    assert device_ops.is_primary is False


@pytest.mark.asyncio
async def test_device_cache(device_ops: DeviceOperationsTestHarness) -> None:
    """Test device caching after parsing."""
    # Setup
    device_struct = bytes(
        [
            0x39,
            0x87,
            0xC8,
            0x57,  # device_id
            0x01,
            0x00,
            0x00,
            0x00,  # capabilities
            0x01,
            0xFF,
            0x00,
            0x00,  # state
            0x00,
            0x00,
            0x00,
            0x00,  # padding
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )

    # Execute
    device_info = await device_ops.parse_device_struct_for_test(
        device_struct, correlation_id="12345678-1234-1234-1234-123456789abc"
    )

    # Assert - device should be cached
    device_id_hex = device_info.device_id.hex()
    assert device_id_hex in device_ops.device_cache
    assert device_ops.device_cache[device_id_hex] == device_info


@pytest.mark.asyncio
async def test_parse_0x83_packet_multiple_devices(device_ops: DeviceOperationsTestHarness) -> None:
    """Test parsing 0x83 packet with multiple device structs."""
    # Setup - two DEVICE_TYPE_LENGTH-byte device structs concatenated
    device1 = bytes(
        [
            0x39,
            0x87,
            0xC8,
            0x57,  # device_id
            0x01,
            0x00,
            0x00,
            0x00,  # capabilities
            0x01,
            0xFF,
            0x00,
            0x00,  # state
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    device2 = bytes(
        [
            0x60,
            0xB1,
            0x12,
            0x34,  # device_id
            0x02,
            0x00,
            0x00,
            0x00,  # capabilities
            0x01,
            0x80,
            0x00,
            0x00,  # state
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )
    payload = device1 + device2

    packet = MockCyncPacket(packet_type=0x83, payload=payload)

    # Execute
    devices = await device_ops.parse_0x83_packet_for_test(packet, correlation_id="12345678-1234-1234-1234-123456789abc")

    # Assert
    assert len(devices) == EXPECTED_DEVICE_COUNT
    assert devices[0].device_id == bytes([0x39, 0x87, 0xC8, 0x57])
    assert devices[1].device_id == bytes([0x60, 0xB1, 0x12, 0x34])


class TestDeviceOperationsErrorPaths:
    """Tests for error handling in DeviceOperations."""

    @pytest.mark.asyncio
    async def test_request_device_info_invalid_device_id_length(self, device_ops: DeviceOperationsTestHarness) -> None:
        """Test that invalid device_id length raises ValueError."""
        # Setup - device_id with wrong length
        invalid_device_id = bytes([0x39, 0x87, 0xC8])  # Only 3 bytes, should be 4

        # Execute & Assert
        with pytest.raises(ValueError, match="must be 4 bytes"):
            await device_ops.request_device_info(invalid_device_id)

    @pytest.mark.asyncio
    async def test_ask_for_mesh_info_exception_logs_and_raises(
        self, device_ops: DeviceOperationsTestHarness, mock_transport: Mock
    ) -> None:
        """Test that exceptions in ask_for_mesh_info are logged and re-raised."""
        # Setup
        device_ops.set_primary(True)
        mock_transport.send_reliable.side_effect = ConnectionError("Connection lost")

        # Execute & Assert
        err = await expect_async_exception(device_ops.ask_for_mesh_info, MeshInfoRequestError)
        assert err.reason == "send_failed"

    @pytest.mark.asyncio
    async def test_ask_for_mesh_info_unexpected_exception_wrapped(
        self, device_ops: DeviceOperationsTestHarness, mock_transport: Mock
    ) -> None:
        """Test that unexpected exceptions are wrapped in MeshInfoRequestError
        with exception chaining.
        """
        # Setup
        device_ops.set_primary(True)
        # Mock transport to raise unexpected exception
        # (not ConnectionError, TimeoutError, or OSError)
        mock_transport.send_reliable.side_effect = ValueError("Unexpected error")

        # Execute & Assert
        err = await expect_async_exception(device_ops.ask_for_mesh_info, MeshInfoRequestError)

        # Verify exception is wrapped
        assert err.reason == "unexpected_error"
        assert "Unexpected error during mesh info request" in str(err)
        assert "correlation_id" in str(err)

        # Verify exception chain preserved (__cause__ should be the original ValueError)
        assert err.__cause__ is not None
        assert isinstance(err.__cause__, ValueError)
        assert "Unexpected error" in str(err.__cause__)

    @pytest.mark.asyncio
    async def test_request_device_info_send_exception(
        self, device_ops: DeviceOperationsTestHarness, mock_transport: Mock
    ) -> None:
        """Test that send exceptions are caught and re-raised as DeviceInfoRequestError."""
        # Setup
        device_id = bytes([0x39, 0x87, 0xC8, 0x57])
        mock_transport.send_reliable.side_effect = TimeoutError("Send timeout")

        # Execute & Assert
        err = await expect_async_exception(device_ops.request_device_info, DeviceInfoRequestError, device_id)
        assert err.reason == "send_failed"

    @pytest.mark.asyncio
    async def test_request_device_info_empty_device_id(self, device_ops: DeviceOperationsTestHarness) -> None:
        """Test that empty device_id raises ValueError."""
        # Setup - empty device_id
        empty_device_id = b""

        # Execute & Assert
        with pytest.raises(ValueError, match="cannot be empty"):
            await device_ops.request_device_info(empty_device_id)

    @pytest.mark.asyncio
    async def test_request_device_info_invalid_timeout_negative(self, device_ops: DeviceOperationsTestHarness) -> None:
        """Test that negative timeout raises ValueError."""
        # Setup
        device_id = bytes([0x39, 0x87, 0xC8, 0x57])
        negative_timeout = -1.0

        # Execute & Assert
        with pytest.raises(ValueError, match="must be positive"):
            await device_ops.request_device_info(device_id, timeout=negative_timeout)

    @pytest.mark.asyncio
    async def test_request_device_info_invalid_timeout_zero(self, device_ops: DeviceOperationsTestHarness) -> None:
        """Test that zero timeout raises ValueError."""
        # Setup
        device_id = bytes([0x39, 0x87, 0xC8, 0x57])
        zero_timeout = 0.0

        # Execute & Assert
        with pytest.raises(ValueError, match="must be positive"):
            await device_ops.request_device_info(device_id, timeout=zero_timeout)

    @pytest.mark.asyncio
    async def test_request_device_info_send_failure_not_success(
        self, device_ops: DeviceOperationsTestHarness, mock_transport: Mock
    ) -> None:
        """Test DeviceInfoRequestError when send_reliable returns success=False."""
        # Setup
        device_id = bytes([0x39, 0x87, 0xC8, 0x57])
        mock_transport.send_reliable.return_value = MockSendResult(success=False, reason="connection_lost")

        # Execute & Assert
        err = await expect_async_exception(device_ops.request_device_info, DeviceInfoRequestError, device_id)
        assert err.reason == "connection_lost"

    @pytest.mark.asyncio
    async def test_request_device_info_oserror_exception(
        self, device_ops: DeviceOperationsTestHarness, mock_transport: Mock
    ) -> None:
        """Test that OSError exceptions are caught and re-raised as DeviceInfoRequestError."""
        # Setup
        device_id = bytes([0x39, 0x87, 0xC8, 0x57])
        mock_transport.send_reliable.side_effect = OSError("Network unreachable")

        # Execute & Assert
        err = await expect_async_exception(device_ops.request_device_info, DeviceInfoRequestError, device_id)
        assert err.reason == "send_failed"

    @pytest.mark.asyncio
    async def test_request_device_info_invalid_struct_parse_error(
        self, device_ops: DeviceOperationsTestHarness, mock_transport: Mock
    ) -> None:
        """Test DeviceStructParseError when receiving 0x43 packet with invalid struct."""
        # Setup
        device_id = bytes([0x39, 0x87, 0xC8, 0x57])
        mock_transport.send_reliable.return_value = MockSendResult(success=True)

        # Mock 0x43 packet with invalid struct (too short)
        invalid_struct = bytes([0x01, 0x02, 0x03])  # Only 3 bytes, should be 24
        response_packet = MockCyncPacket(packet_type=0x43, payload=invalid_struct)
        tracked_packet = MockTrackedPacket(response_packet)

        mock_transport.recv_reliable.return_value = tracked_packet

        # Execute & Assert
        err = await expect_async_exception(device_ops.request_device_info, DeviceStructParseError, device_id)
        assert "Invalid device struct length" in str(err)

    @pytest.mark.asyncio
    async def test_request_device_info_wrong_packet_type_timeout(
        self, device_ops: DeviceOperationsTestHarness, mock_transport: Mock
    ) -> None:
        """Test timeout when receiving wrong packet types (not 0x43)."""
        # Setup
        device_id = bytes([0x39, 0x87, 0xC8, 0x57])
        mock_transport.send_reliable.return_value = MockSendResult(success=True)

        # Mock wrong packet type (0x83 instead of 0x43)
        wrong_packet = MockCyncPacket(packet_type=0x83, payload=bytes(DEVICE_TYPE_LENGTH))
        tracked_packet = MockTrackedPacket(wrong_packet)

        # Return wrong packet, then timeout
        mock_transport.recv_reliable.side_effect = [tracked_packet, TimeoutError()]

        # Execute - should timeout because we never receive 0x43
        device_info = await device_ops.request_device_info(device_id, timeout=0.1)

        # Assert - should return None due to timeout
        assert device_info is None
        min_call_count = 2  # At least wrong packet + timeout
        assert mock_transport.recv_reliable.call_count >= min_call_count

    @pytest.mark.asyncio
    async def test_request_device_info_connection_error_exception(
        self, device_ops: DeviceOperationsTestHarness, mock_transport: Mock
    ) -> None:
        """Test that ConnectionError exceptions are caught and re-raised as
        DeviceInfoRequestError.
        """
        # Setup
        device_id = bytes([0x39, 0x87, 0xC8, 0x57])
        mock_transport.send_reliable.side_effect = ConnectionError("Connection refused")

        # Execute & Assert
        err = await expect_async_exception(device_ops.request_device_info, DeviceInfoRequestError, device_id)
        assert err.reason == "send_failed"


class TestDeviceOperationsCache:
    """Tests for device cache management."""

    @pytest.mark.asyncio
    async def test_cache_eviction_lru(self, device_ops: DeviceOperationsTestHarness) -> None:
        """Test that cache evicts oldest entries when over limit."""
        # Temporarily reduce cache size for testing
        original_max = device_ops.MAX_CACHE_SIZE
        device_ops.MAX_CACHE_SIZE = 3  # pyright: ignore[reportAttributeAccessIssue]  # Small cache for testing

        try:
            # Create 4 device structs (one more than cache limit)
            device_ids: list[str] = []
            for i in range(4):
                device_id = bytes([0x39, 0x87, 0xC8, i])
                device_struct = device_id + bytes([0] * 20)  # 24 bytes total
                correlation_id = str(uuid.uuid4())
                await device_ops.parse_device_struct_for_test(device_struct, correlation_id=correlation_id)
                device_ids.append(device_id.hex())

            # First 3 should be in cache
            expected_cache_size = 3
            assert len(device_ops.device_cache) == expected_cache_size
            # First device should be evicted (oldest)
            assert device_ids[0] not in device_ops.device_cache
            # Last 3 devices should be in cache
            assert device_ids[1] in device_ops.device_cache
            assert device_ids[2] in device_ops.device_cache
            assert device_ids[3] in device_ops.device_cache
        finally:
            # Restore original cache size
            device_ops.MAX_CACHE_SIZE = original_max

    @pytest.mark.asyncio
    async def test_cache_lru_update_on_access(self, device_ops: DeviceOperationsTestHarness) -> None:
        """Test that accessing cached device moves it to end (most recent)."""
        # Temporarily reduce cache size for testing
        original_max = device_ops.MAX_CACHE_SIZE
        device_ops.MAX_CACHE_SIZE = 2  # pyright: ignore[reportAttributeAccessIssue]

        try:
            # Add 2 devices
            device_id1 = bytes([0x39, 0x87, 0xC8, 0x01])
            device_id2 = bytes([0x39, 0x87, 0xC8, 0x02])
            device_struct1 = device_id1 + bytes([0] * 20)
            device_struct2 = device_id2 + bytes([0] * 20)

            await device_ops.parse_device_struct_for_test(device_struct1, correlation_id=str(uuid.uuid4()))
            await device_ops.parse_device_struct_for_test(device_struct2, correlation_id=str(uuid.uuid4()))

            # Both should be in cache
            expected_cache_size = 2
            assert len(device_ops.device_cache) == expected_cache_size

            # Access first device through _add_to_cache (should move to end via move_to_end)
            device_info1 = device_ops.device_cache[device_id1.hex()]
            await device_ops.add_to_cache_for_test(device_id1.hex(), device_info1)

            # Add third device - should evict device2 (oldest), not device1
            device_id3 = bytes([0x39, 0x87, 0xC8, 0x03])
            device_struct3 = device_id3 + bytes([0] * 20)
            await device_ops.parse_device_struct_for_test(device_struct3, correlation_id=str(uuid.uuid4()))

            assert device_id1.hex() in device_ops.device_cache  # Should still be there
            assert device_id2.hex() not in device_ops.device_cache  # Should be evicted
            assert device_id3.hex() in device_ops.device_cache  # Should be there
        finally:
            device_ops.MAX_CACHE_SIZE = original_max
