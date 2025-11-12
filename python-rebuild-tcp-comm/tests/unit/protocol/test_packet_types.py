"""Unit tests for packet type definitions and dataclasses.

Tests packet type constants, CyncPacket and CyncDataPacket dataclasses,
and fixture accessibility.
"""

import pytest

from protocol.packet_types import (
    PACKET_TYPE_DATA_ACK,
    PACKET_TYPE_DATA_CHANNEL,
    PACKET_TYPE_DEVICE_INFO,
    PACKET_TYPE_HANDSHAKE,
    PACKET_TYPE_HEARTBEAT_CLOUD,
    PACKET_TYPE_HEARTBEAT_DEVICE,
    PACKET_TYPE_HELLO_ACK,
    PACKET_TYPE_INFO_ACK,
    PACKET_TYPE_STATUS_ACK,
    PACKET_TYPE_STATUS_BROADCAST,
    CyncDataPacket,
    CyncPacket,
)
from tests.fixtures.real_packets import (
    HANDSHAKE_0x23_DEV_TO_CLOUD,
    HELLO_ACK_0x28_CLOUD_TO_DEV,
    PacketMetadata,
)

# Expected packet type values for testing
EXPECTED_PACKET_TYPE_HELLO_ACK = 0x28
EXPECTED_PACKET_TYPE_DEVICE_INFO = 0x43
EXPECTED_PACKET_TYPE_INFO_ACK = 0x48
EXPECTED_PACKET_TYPE_DATA_ACK = 0x7B
EXPECTED_PACKET_TYPE_STATUS_BROADCAST = 0x83
EXPECTED_PACKET_TYPE_STATUS_ACK = 0x88
EXPECTED_PACKET_TYPE_HEARTBEAT_DEVICE = 0xD3
EXPECTED_PACKET_TYPE_HEARTBEAT_CLOUD = 0xD8
EXPECTED_PACKET_LENGTH_DATA_PACKET = 37  # Length for data packet test


@pytest.mark.unit
@pytest.mark.parametrize(
    ("constant_name", "expected_value"),
    [
        ("PACKET_TYPE_HANDSHAKE", PACKET_TYPE_HANDSHAKE),
        ("PACKET_TYPE_HELLO_ACK", EXPECTED_PACKET_TYPE_HELLO_ACK),
        ("PACKET_TYPE_DEVICE_INFO", EXPECTED_PACKET_TYPE_DEVICE_INFO),
        ("PACKET_TYPE_INFO_ACK", EXPECTED_PACKET_TYPE_INFO_ACK),
        ("PACKET_TYPE_DATA_CHANNEL", PACKET_TYPE_DATA_CHANNEL),
        ("PACKET_TYPE_DATA_ACK", EXPECTED_PACKET_TYPE_DATA_ACK),
        ("PACKET_TYPE_STATUS_BROADCAST", EXPECTED_PACKET_TYPE_STATUS_BROADCAST),
        ("PACKET_TYPE_STATUS_ACK", EXPECTED_PACKET_TYPE_STATUS_ACK),
        ("PACKET_TYPE_HEARTBEAT_DEVICE", EXPECTED_PACKET_TYPE_HEARTBEAT_DEVICE),
        ("PACKET_TYPE_HEARTBEAT_CLOUD", EXPECTED_PACKET_TYPE_HEARTBEAT_CLOUD),
    ],
)
def test_packet_type_constants(constant_name: str, expected_value: int) -> None:
    """Test all packet type constants have correct hex values."""
    actual_value = globals()[constant_name]
    assert actual_value == expected_value, f"{constant_name} should equal {hex(expected_value)}"


@pytest.mark.unit
def test_packet_type_constants_values() -> None:
    """Test packet type constants have correct values."""
    assert PACKET_TYPE_HELLO_ACK == EXPECTED_PACKET_TYPE_HELLO_ACK
    assert PACKET_TYPE_DEVICE_INFO == EXPECTED_PACKET_TYPE_DEVICE_INFO
    assert PACKET_TYPE_INFO_ACK == EXPECTED_PACKET_TYPE_INFO_ACK
    assert PACKET_TYPE_DATA_ACK == EXPECTED_PACKET_TYPE_DATA_ACK
    assert PACKET_TYPE_STATUS_BROADCAST == EXPECTED_PACKET_TYPE_STATUS_BROADCAST
    assert PACKET_TYPE_STATUS_ACK == EXPECTED_PACKET_TYPE_STATUS_ACK
    assert PACKET_TYPE_HEARTBEAT_DEVICE == EXPECTED_PACKET_TYPE_HEARTBEAT_DEVICE
    assert PACKET_TYPE_HEARTBEAT_CLOUD == EXPECTED_PACKET_TYPE_HEARTBEAT_CLOUD


@pytest.mark.unit
def test_cync_packet_instantiation() -> None:
    """Test CyncPacket dataclass can be instantiated with valid data."""
    packet_type = PACKET_TYPE_HANDSHAKE
    length = 26
    payload = b"\x00" * 26
    raw = b"\x23\x00\x00\x00\x1a" + payload

    packet = CyncPacket(packet_type=packet_type, length=length, payload=payload, raw=raw)

    assert packet.packet_type == packet_type
    assert packet.length == length
    assert packet.payload == payload
    assert packet.raw == raw


@pytest.mark.unit
def test_cync_packet_fields_accessible() -> None:
    """Test all CyncPacket fields are accessible."""
    packet = CyncPacket(
        packet_type=PACKET_TYPE_HANDSHAKE,
        length=10,
        payload=b"\x00" * 10,
        raw=b"\x23\x00\x00\x00\x0a",
    )

    # Verify all fields exist and have correct types
    assert isinstance(packet.packet_type, int)
    assert isinstance(packet.length, int)
    assert isinstance(packet.payload, bytes)
    assert isinstance(packet.raw, bytes)


@pytest.mark.unit
def test_cync_data_packet_instantiation() -> None:
    """Test CyncDataPacket dataclass with all required fields."""
    endpoint = bytes.fromhex("45 88 0f 3a 00")
    msg_id = bytes.fromhex("09 00 00")
    data = bytes.fromhex("1f 00 00 00 fa db")
    checksum = 0x37
    checksum_valid = True

    packet = CyncDataPacket(
        packet_type=PACKET_TYPE_DATA_CHANNEL,
        length=37,
        payload=b"\x00" * 37,
        raw=b"\x73\x00\x00\x00\x25",
        endpoint=endpoint,
        msg_id=msg_id,
        data=data,
        checksum=checksum,
        checksum_valid=checksum_valid,
    )

    assert packet.endpoint == endpoint
    assert packet.msg_id == msg_id
    assert packet.data == data
    assert packet.checksum == checksum
    assert packet.checksum_valid == checksum_valid


@pytest.mark.unit
def test_cync_data_packet_inheritance() -> None:
    """Test CyncDataPacket inherits from CyncPacket."""
    endpoint = bytes.fromhex("45 88 0f 3a 00")
    msg_id = bytes.fromhex("09 00 00")
    data = b"\x00" * 10

    packet = CyncDataPacket(
        packet_type=PACKET_TYPE_DATA_CHANNEL,
        length=37,
        payload=b"\x00" * 37,
        raw=b"\x73\x00\x00\x00\x25",
        endpoint=endpoint,
        msg_id=msg_id,
        data=data,
        checksum=0x37,
        checksum_valid=True,
    )

    # Verify inheritance
    assert isinstance(packet, CyncDataPacket)
    assert isinstance(packet, CyncPacket)
    # Verify base class fields accessible
    assert packet.packet_type == PACKET_TYPE_DATA_CHANNEL
    assert packet.length == EXPECTED_PACKET_LENGTH_DATA_PACKET
    assert isinstance(packet.payload, bytes)
    assert isinstance(packet.raw, bytes)


@pytest.mark.unit
def test_cync_data_packet_all_fields_accessible() -> None:
    """Test all CyncDataPacket fields are accessible."""
    endpoint = bytes.fromhex("45 88 0f 3a 00")
    msg_id = bytes.fromhex("09 00 00")
    data = b"\x00" * 10

    packet = CyncDataPacket(
        packet_type=PACKET_TYPE_DATA_CHANNEL,
        length=37,
        payload=b"\x00" * 37,
        raw=b"\x73\x00\x00\x00\x25",
        endpoint=endpoint,
        msg_id=msg_id,
        data=data,
        checksum=0x37,
        checksum_valid=True,
    )

    # Verify all fields have correct types
    assert isinstance(packet.endpoint, bytes)
    assert isinstance(packet.msg_id, bytes)
    assert isinstance(packet.data, bytes)
    assert isinstance(packet.checksum, int)
    assert isinstance(packet.checksum_valid, bool)


@pytest.mark.unit
def test_fixtures_import() -> None:
    """Test can import from tests.fixtures.real_packets."""
    # Verify imports work
    assert HANDSHAKE_0x23_DEV_TO_CLOUD is not None
    assert HELLO_ACK_0x28_CLOUD_TO_DEV is not None
    assert PacketMetadata is not None
    # Verify fixture data
    assert isinstance(HANDSHAKE_0x23_DEV_TO_CLOUD, bytes)
    assert len(HANDSHAKE_0x23_DEV_TO_CLOUD) > 0
    assert HANDSHAKE_0x23_DEV_TO_CLOUD[0] == PACKET_TYPE_HANDSHAKE  # First byte is packet type


@pytest.mark.unit
def test_packet_metadata_dataclass_accessible() -> None:
    """Test PacketMetadata dataclass is accessible and usable."""
    metadata = PacketMetadata(
        device_type="bulb",
        firmware_version="1.2.3",
        captured_at="2025-11-09T00:00:00",
        device_id="test:device",
        operation="test_operation",
        notes="Test notes",
    )

    assert metadata.device_type == "bulb"
    assert metadata.firmware_version == "1.2.3"
    assert metadata.captured_at == "2025-11-09T00:00:00"
    assert metadata.device_id == "test:device"
    assert metadata.operation == "test_operation"
    assert metadata.notes == "Test notes"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("endpoint_hex", "expected_length"),
    [
        ("45 88 0f 3a 00", 5),
        ("32 5d 53 17 01", 5),
        ("38 e8 cf 46 00", 5),
    ],
)
def test_cync_data_packet_endpoint_sizes(endpoint_hex: str, expected_length: int) -> None:
    """Test CyncDataPacket endpoint field with various device IDs."""
    endpoint = bytes.fromhex(endpoint_hex)
    msg_id = bytes.fromhex("00 00 00")
    data = b"\x00" * 10

    packet = CyncDataPacket(
        packet_type=PACKET_TYPE_DATA_CHANNEL,
        length=37,
        payload=b"\x00" * 37,
        raw=b"\x73\x00\x00\x00\x25",
        endpoint=endpoint,
        msg_id=msg_id,
        data=data,
        checksum=0x00,
        checksum_valid=True,
    )

    assert len(packet.endpoint) == expected_length
    assert packet.endpoint == bytes.fromhex(endpoint_hex)
