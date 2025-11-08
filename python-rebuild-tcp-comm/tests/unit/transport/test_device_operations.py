"""Unit tests for DeviceOperations class.

Tests for mesh info and device info request/response handling with:
- Primary device enforcement
- Packet/ACK analysis
- 24-byte device struct parsing
- Error handling and metrics

Test data uses fixtures from Phase 0.5 packet captures where available.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from src.transport.device_info import (
    DeviceInfo,
    DeviceStructParseError,
    MeshInfoRequestError,
)
from src.transport.device_operations import DeviceOperations


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
    protocol = Mock()
    return protocol


@pytest.fixture
def device_ops(mock_transport, mock_protocol):
    """Create DeviceOperations instance with mocks."""
    return DeviceOperations(mock_transport, mock_protocol)


@pytest.mark.asyncio
async def test_ask_for_mesh_info_success(device_ops, mock_transport):
    """Test successful mesh info request with 0x83 responses."""
    # Setup
    device_ops.set_primary(True)
    mock_transport.send_reliable.return_value = MockSendResult(success=True)

    # Mock 0x83 status broadcast response
    response_packet = MockCyncPacket(
        packet_type=0x83,
        payload=bytes(24),  # 24-byte device struct
    )
    tracked_packet = MockTrackedPacket(response_packet)

    # Return packet once, then timeout
    mock_transport.recv_reliable.side_effect = [tracked_packet, asyncio.TimeoutError()]

    # Execute
    responses = await device_ops.ask_for_mesh_info(parse=False)

    # Assert
    assert len(responses) == 1
    assert responses[0].packet_type == 0x83
    mock_transport.send_reliable.assert_called_once()
    assert mock_transport.recv_reliable.call_count == 2


@pytest.mark.asyncio
async def test_ask_for_mesh_info_parse(device_ops, mock_transport):
    """Test mesh info request with parsing enabled."""
    # Setup
    device_ops.set_primary(True)
    mock_transport.send_reliable.return_value = MockSendResult(success=True)

    # Mock 0x83 packet with 24-byte device struct
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
            0x00,  # state (on=True, brightness=255)
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
    mock_transport.recv_reliable.side_effect = [tracked_packet, asyncio.TimeoutError()]

    # Execute
    responses = await device_ops.ask_for_mesh_info(parse=True)

    # Assert
    assert len(responses) == 1
    assert isinstance(responses[0], DeviceInfo)
    assert responses[0].device_id == bytes([0x39, 0x87, 0xC8, 0x57])
    assert responses[0].device_type == 0x01
    assert responses[0].state["on"] is True


@pytest.mark.asyncio
async def test_ask_for_mesh_info_primary_only(device_ops):
    """Test that non-primary device cannot request mesh info."""
    # Setup - NOT setting is_primary to True
    device_ops.set_primary(False)

    # Execute & Assert
    with pytest.raises(MeshInfoRequestError) as exc_info:
        await device_ops.ask_for_mesh_info()

    assert exc_info.value.reason == "not_primary"


@pytest.mark.asyncio
async def test_ask_for_mesh_info_send_failed(device_ops, mock_transport):
    """Test mesh info request with send failure."""
    # Setup
    device_ops.set_primary(True)
    mock_transport.send_reliable.return_value = MockSendResult(
        success=False, reason="connection_lost"
    )

    # Execute & Assert
    with pytest.raises(MeshInfoRequestError) as exc_info:
        await device_ops.ask_for_mesh_info()

    assert exc_info.value.reason == "connection_lost"


@pytest.mark.asyncio
async def test_request_device_info(device_ops, mock_transport):
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
    assert device_info.device_type == 0x02
    assert device_info.state["on"] is True


@pytest.mark.asyncio
async def test_request_device_info_timeout(device_ops, mock_transport):
    """Test device info request timeout."""
    # Setup
    device_id = bytes([0x39, 0x87, 0xC8, 0x57])
    mock_transport.send_reliable.return_value = MockSendResult(success=True)
    mock_transport.recv_reliable.side_effect = asyncio.TimeoutError()

    # Execute
    device_info = await device_ops.request_device_info(device_id, timeout=1.0)

    # Assert
    assert device_info is None


def test_device_struct_parsing(device_ops):
    """Test parsing of 24-byte device struct."""
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
            0x00,  # state (on=True, brightness=255)
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
    device_info = device_ops._parse_device_struct(
        device_struct, correlation_id="12345678-1234-1234-1234-123456789abc"
    )

    # Assert
    assert device_info.device_id == bytes([0x39, 0x87, 0xC8, 0x57])
    assert device_info.device_type == 0x01
    assert device_info.state["on"] is True
    assert device_info.state["brightness"] == 255
    assert len(device_info.raw_bytes) == 24


def test_device_struct_parsing_invalid_length(device_ops):
    """Test device struct parsing with invalid length."""
    # Setup - struct with wrong length
    invalid_struct = bytes([0x01, 0x02, 0x03])  # Only 3 bytes

    # Execute & Assert
    with pytest.raises(DeviceStructParseError) as exc_info:
        device_ops._parse_device_struct(
            invalid_struct, correlation_id="12345678-1234-1234-1234-123456789abc"
        )

    assert "Invalid device struct length" in str(exc_info.value)


def test_set_primary(device_ops):
    """Test setting primary device status."""
    # Initial state
    assert device_ops.is_primary is False

    # Set to primary
    device_ops.set_primary(True)
    assert device_ops.is_primary is True

    # Unset primary
    device_ops.set_primary(False)
    assert device_ops.is_primary is False


def test_device_cache(device_ops):
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
    device_info = device_ops._parse_device_struct(
        device_struct, correlation_id="12345678-1234-1234-1234-123456789abc"
    )

    # Assert - device should be cached
    device_id_hex = device_info.device_id.hex()
    assert device_id_hex in device_ops.device_cache
    assert device_ops.device_cache[device_id_hex] == device_info


@pytest.mark.asyncio
async def test_parse_0x83_packet_multiple_devices(device_ops):
    """Test parsing 0x83 packet with multiple device structs."""
    # Setup - two 24-byte device structs concatenated
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
    devices = device_ops._parse_0x83_packet(
        packet, correlation_id="12345678-1234-1234-1234-123456789abc"
    )

    # Assert
    assert len(devices) == 2
    assert devices[0].device_id == bytes([0x39, 0x87, 0xC8, 0x57])
    assert devices[1].device_id == bytes([0x60, 0xB1, 0x12, 0x34])
