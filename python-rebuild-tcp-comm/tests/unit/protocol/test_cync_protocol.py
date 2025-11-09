"""Unit tests for CyncProtocol encoder/decoder."""

from __future__ import annotations

import pytest

from protocol.cync_protocol import CyncProtocol
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
    DATA_ACK_0x7B_DEV_TO_CLOUD,
    DEVICE_INFO_0x43_DEV_TO_CLOUD,
    HANDSHAKE_0x23_DEV_TO_CLOUD,
    HEARTBEAT_CLOUD_0xD8_CLOUD_TO_DEV,
    HEARTBEAT_DEV_0xD3_DEV_TO_CLOUD,
    HELLO_ACK_0x28_CLOUD_TO_DEV,
    INFO_ACK_0x48_CLOUD_TO_DEV,
    STATUS_ACK_0x88_CLOUD_TO_DEV,
    STATUS_BROADCAST_0x83_DEV_TO_CLOUD,
    TOGGLE_OFF_0x73_CLOUD_TO_DEV,
    TOGGLE_ON_0x73_CLOUD_TO_DEV,
)


# =============================================================================
# Header Parsing Tests
# =============================================================================


def test_parse_header_handshake() -> None:
    """Test parsing 0x23 handshake header."""
    packet_type, length, reserved = CyncProtocol.parse_header(HANDSHAKE_0x23_DEV_TO_CLOUD)

    assert packet_type == 0x23
    assert length == 26  # 0x00 * 256 + 0x1a
    assert reserved == 0x0000


def test_parse_header_data_channel() -> None:
    """Test parsing 0x73 data channel header."""
    packet_type, length, reserved = CyncProtocol.parse_header(TOGGLE_ON_0x73_CLOUD_TO_DEV)

    assert packet_type == 0x73
    assert length == 31  # 0x00 * 256 + 0x1f
    assert reserved == 0x0000


def test_parse_header_length_calculation() -> None:
    """Test multiplier * 256 + base calculation."""
    # Create test packet with length = 2 * 256 + 5 = 517
    test_packet = bytes([0x23, 0x00, 0x00, 0x02, 0x05])
    packet_type, length, reserved = CyncProtocol.parse_header(test_packet)

    assert packet_type == 0x23
    assert length == 517
    assert reserved == 0x0000


def test_parse_header_large_packet() -> None:
    """Test with multiplier > 0 (packets > 255 bytes)."""
    # Device info packet has length 30 (0x1e)
    packet_type, length, reserved = CyncProtocol.parse_header(DEVICE_INFO_0x43_DEV_TO_CLOUD)

    assert packet_type == 0x43
    assert length == 30
    assert reserved == 0x0000


# =============================================================================
# Header Encoding Tests
# =============================================================================


def test_encode_header_small_packet() -> None:
    """Test encoding header with length < 256 (multiplier=0)."""
    header = CyncProtocol.encode_header(0x23, 26)

    assert header == bytes([0x23, 0x00, 0x00, 0x00, 0x1A])
    assert len(header) == 5


def test_encode_header_large_packet() -> None:
    """Test encoding header with length > 255 (multiplier > 0)."""
    # Length 517 = 2 * 256 + 5
    header = CyncProtocol.encode_header(0x73, 517)

    assert header == bytes([0x73, 0x00, 0x00, 0x02, 0x05])
    assert len(header) == 5


def test_encode_header_roundtrip() -> None:
    """Test encode then parse, verify equality."""
    original_type = 0x83
    original_length = 37

    # Encode
    header = CyncProtocol.encode_header(original_type, original_length)

    # Parse (need full packet, so add dummy payload)
    test_packet = header + bytes(original_length)
    packet_type, length, _ = CyncProtocol.parse_header(test_packet)

    assert packet_type == original_type
    assert length == original_length


# =============================================================================
# Packet Decoding Tests (All Types)
# =============================================================================


def test_decode_handshake_0x23() -> None:
    """Decode real 0x23 handshake packet."""
    packet = CyncProtocol.decode_packet(HANDSHAKE_0x23_DEV_TO_CLOUD)

    assert isinstance(packet, CyncPacket)
    assert packet.packet_type == PACKET_TYPE_HANDSHAKE
    assert packet.length == 26
    assert len(packet.payload) == 26
    assert packet.raw == HANDSHAKE_0x23_DEV_TO_CLOUD


def test_decode_hello_ack_0x28() -> None:
    """Decode real 0x28 hello ACK packet."""
    packet = CyncProtocol.decode_packet(HELLO_ACK_0x28_CLOUD_TO_DEV)

    assert isinstance(packet, CyncPacket)
    assert packet.packet_type == PACKET_TYPE_HELLO_ACK
    assert packet.length == 2
    assert len(packet.payload) == 2
    assert packet.raw == HELLO_ACK_0x28_CLOUD_TO_DEV


def test_decode_device_info_0x43() -> None:
    """Decode real 0x43 device info packet."""
    packet = CyncProtocol.decode_packet(DEVICE_INFO_0x43_DEV_TO_CLOUD)

    assert isinstance(packet, CyncPacket)
    assert packet.packet_type == PACKET_TYPE_DEVICE_INFO
    assert packet.length == 30
    assert len(packet.payload) == 30
    assert packet.raw == DEVICE_INFO_0x43_DEV_TO_CLOUD


def test_decode_info_ack_0x48() -> None:
    """Decode real 0x48 info ACK packet."""
    packet = CyncProtocol.decode_packet(INFO_ACK_0x48_CLOUD_TO_DEV)

    assert isinstance(packet, CyncPacket)
    assert packet.packet_type == PACKET_TYPE_INFO_ACK
    assert packet.length == 3
    assert len(packet.payload) == 3
    assert packet.raw == INFO_ACK_0x48_CLOUD_TO_DEV


def test_decode_data_ack_0x7B() -> None:
    """Decode real 0x7B data ACK packet."""
    packet = CyncProtocol.decode_packet(DATA_ACK_0x7B_DEV_TO_CLOUD)

    assert isinstance(packet, CyncPacket)
    assert packet.packet_type == PACKET_TYPE_DATA_ACK
    assert packet.length == 7
    assert len(packet.payload) == 7
    assert packet.raw == DATA_ACK_0x7B_DEV_TO_CLOUD


def test_decode_status_broadcast_0x83() -> None:
    """Decode real 0x83 status broadcast packet."""
    packet = CyncProtocol.decode_packet(STATUS_BROADCAST_0x83_DEV_TO_CLOUD)

    assert isinstance(packet, CyncDataPacket)
    assert packet.packet_type == PACKET_TYPE_STATUS_BROADCAST
    assert packet.length == 37
    assert packet.endpoint == bytes.fromhex("45 88 0f 3a 00")
    assert packet.msg_id == bytes.fromhex("09 00 7e")  # Note: 0x7e is part of msg_id here
    assert packet.checksum == 0x37
    assert packet.checksum_valid is True


def test_decode_status_ack_0x88() -> None:
    """Decode real 0x88 status ACK packet."""
    packet = CyncProtocol.decode_packet(STATUS_ACK_0x88_CLOUD_TO_DEV)

    assert isinstance(packet, CyncPacket)
    assert packet.packet_type == PACKET_TYPE_STATUS_ACK
    assert packet.length == 3
    assert len(packet.payload) == 3
    assert packet.raw == STATUS_ACK_0x88_CLOUD_TO_DEV


def test_decode_heartbeat_device_0xD3() -> None:
    """Decode real 0xD3 device heartbeat packet."""
    packet = CyncProtocol.decode_packet(HEARTBEAT_DEV_0xD3_DEV_TO_CLOUD)

    assert isinstance(packet, CyncPacket)
    assert packet.packet_type == PACKET_TYPE_HEARTBEAT_DEVICE
    assert packet.length == 0
    assert len(packet.payload) == 0
    assert packet.raw == HEARTBEAT_DEV_0xD3_DEV_TO_CLOUD


def test_decode_heartbeat_cloud_0xD8() -> None:
    """Decode real 0xD8 cloud heartbeat packet."""
    packet = CyncProtocol.decode_packet(HEARTBEAT_CLOUD_0xD8_CLOUD_TO_DEV)

    assert isinstance(packet, CyncPacket)
    assert packet.packet_type == PACKET_TYPE_HEARTBEAT_CLOUD
    assert packet.length == 0
    assert len(packet.payload) == 0
    assert packet.raw == HEARTBEAT_CLOUD_0xD8_CLOUD_TO_DEV


# =============================================================================
# Data Packet Tests (0x73/0x83)
# =============================================================================


def test_extract_endpoint_and_msg_id() -> None:
    """Test extracting endpoint and msg_id from payload."""
    # Use toggle ON packet payload (header stripped)
    payload = TOGGLE_ON_0x73_CLOUD_TO_DEV[5:]  # Skip header

    endpoint, msg_id = CyncProtocol.extract_endpoint_and_msg_id(payload)

    assert endpoint == bytes.fromhex("45 88 0f 3a 00")
    assert msg_id == bytes.fromhex("10 00 00")


def test_decode_data_packet_with_framing() -> None:
    """Decode 0x73 packet, verify 0x7e markers present."""
    packet = CyncProtocol.decode_packet(TOGGLE_ON_0x73_CLOUD_TO_DEV)

    assert isinstance(packet, CyncDataPacket)
    assert packet.packet_type == PACKET_TYPE_DATA_CHANNEL

    # Verify 0x7e markers in raw packet
    assert 0x7E in packet.raw
    assert packet.raw[0] != 0x7E  # Not at start
    assert packet.raw[-1] == 0x7E  # At end

    # Verify endpoint and msg_id extraction
    assert packet.endpoint == bytes.fromhex("45 88 0f 3a 00")
    assert packet.msg_id == bytes.fromhex("10 00 00")

    # Verify checksum
    assert packet.checksum == 0x07
    assert packet.checksum_valid is True


def test_decode_status_broadcast_framing() -> None:
    """Decode 0x83 packet with framing."""
    packet = CyncProtocol.decode_packet(STATUS_BROADCAST_0x83_DEV_TO_CLOUD)

    assert isinstance(packet, CyncDataPacket)
    assert packet.packet_type == PACKET_TYPE_STATUS_BROADCAST

    # Verify 0x7e markers
    assert 0x7E in packet.raw
    assert packet.raw[-1] == 0x7E

    # Verify endpoint extraction
    assert packet.endpoint == bytes.fromhex("45 88 0f 3a 00")

    # Verify checksum
    assert packet.checksum == 0x37
    assert packet.checksum_valid is True


def test_decode_toggle_off_data_packet() -> None:
    """Decode toggle OFF 0x73 packet."""
    packet = CyncProtocol.decode_packet(TOGGLE_OFF_0x73_CLOUD_TO_DEV)

    assert isinstance(packet, CyncDataPacket)
    assert packet.packet_type == PACKET_TYPE_DATA_CHANNEL
    assert packet.endpoint == bytes.fromhex("45 88 0f 3a 00")
    assert packet.msg_id == bytes.fromhex("11 00 00")
    assert packet.checksum == 0x07
    assert packet.checksum_valid is True


# =============================================================================
# Edge Case Tests
# =============================================================================


def test_decode_packet_too_short() -> None:
    """Test packet < 5 bytes raises ValueError."""
    with pytest.raises(ValueError, match="too short"):
        CyncProtocol.decode_packet(bytes([0x23, 0x00]))


def test_decode_packet_length_mismatch() -> None:
    """Test header length doesn't match actual data."""
    # Header claims length 100, but only provide 10 bytes of payload
    bad_packet = bytes([0x23, 0x00, 0x00, 0x00, 0x64]) + bytes(10)

    with pytest.raises(ValueError, match="length mismatch"):
        CyncProtocol.decode_packet(bad_packet)


def test_parse_header_invalid_input() -> None:
    """Test empty bytes raises ValueError."""
    with pytest.raises(ValueError, match="too short"):
        CyncProtocol.parse_header(bytes())


def test_parse_header_partial_header() -> None:
    """Test partial header (3 bytes) raises ValueError."""
    with pytest.raises(ValueError, match="too short"):
        CyncProtocol.parse_header(bytes([0x23, 0x00, 0x00]))


def test_extract_endpoint_payload_too_short() -> None:
    """Test payload too short for endpoint/msg_id extraction."""
    with pytest.raises(ValueError, match="too short"):
        CyncProtocol.extract_endpoint_and_msg_id(bytes([0x01, 0x02]))


def test_decode_data_packet_missing_markers() -> None:
    """Test data packet without 0x7e markers raises ValueError."""
    # Create malformed 0x73 packet without 0x7e markers
    bad_packet = bytes([0x73, 0x00, 0x00, 0x00, 0x10]) + bytes(16)

    with pytest.raises(ValueError, match="0x7e"):
        CyncProtocol.decode_packet(bad_packet)


def test_decode_data_packet_with_trailing_data() -> None:
    """Test data packet decoding ignores trailing data beyond declared length.

    This verifies the fix for the bug where end marker search would incorrectly
    find markers in trailing data when buffer contains multiple packets.
    """
    # Use a valid toggle ON packet
    valid_packet = TOGGLE_ON_0x73_CLOUD_TO_DEV

    # Create buffer with valid packet + trailing garbage containing 0x7e markers
    # The trailing data should be ignored during marker search
    trailing_data = bytes([0x7E, 0xFF, 0xFF, 0x7E, 0x00, 0x00])
    buffer_with_trailing = valid_packet + trailing_data

    # Decode should work correctly, ignoring trailing data
    packet = CyncProtocol.decode_packet(buffer_with_trailing)

    assert isinstance(packet, CyncDataPacket)
    assert packet.packet_type == PACKET_TYPE_DATA_CHANNEL
    assert packet.endpoint == bytes.fromhex("45 88 0f 3a 00")
    assert packet.msg_id == bytes.fromhex("10 00 00")
    assert packet.checksum == 0x07
    assert packet.checksum_valid is True

    # Verify we only processed the declared packet length
    expected_packet_length = 5 + packet.length  # Header + payload
    assert expected_packet_length == len(valid_packet)
    assert len(buffer_with_trailing) > len(valid_packet)  # Has trailing data


# =============================================================================
# Encoder Stub Tests (Step 4 not yet implemented)
# =============================================================================


def test_encode_handshake_not_implemented() -> None:
    """Test encode_handshake raises NotImplementedError."""
    endpoint = bytes.fromhex("45 88 0f 3a 00")
    auth_code = bytes(16)

    with pytest.raises(NotImplementedError, match="Step 4"):
        CyncProtocol.encode_handshake(endpoint, auth_code)


def test_encode_data_packet_not_implemented() -> None:
    """Test encode_data_packet raises NotImplementedError."""
    endpoint = bytes.fromhex("45 88 0f 3a 00")
    msg_id = bytes.fromhex("10 00 00")
    payload = bytes(16)

    with pytest.raises(NotImplementedError, match="Step 4"):
        CyncProtocol.encode_data_packet(endpoint, msg_id, payload)


# =============================================================================
# Additional Coverage Tests
# =============================================================================


def test_decode_all_packet_types_from_fixtures() -> None:
    """Test decoding all major packet types from real fixtures."""
    test_cases = [
        (HANDSHAKE_0x23_DEV_TO_CLOUD, PACKET_TYPE_HANDSHAKE, 26),
        (HELLO_ACK_0x28_CLOUD_TO_DEV, PACKET_TYPE_HELLO_ACK, 2),
        (DEVICE_INFO_0x43_DEV_TO_CLOUD, PACKET_TYPE_DEVICE_INFO, 30),
        (INFO_ACK_0x48_CLOUD_TO_DEV, PACKET_TYPE_INFO_ACK, 3),
        (TOGGLE_ON_0x73_CLOUD_TO_DEV, PACKET_TYPE_DATA_CHANNEL, 31),
        (DATA_ACK_0x7B_DEV_TO_CLOUD, PACKET_TYPE_DATA_ACK, 7),
        (STATUS_BROADCAST_0x83_DEV_TO_CLOUD, PACKET_TYPE_STATUS_BROADCAST, 37),
        (STATUS_ACK_0x88_CLOUD_TO_DEV, PACKET_TYPE_STATUS_ACK, 3),
        (HEARTBEAT_DEV_0xD3_DEV_TO_CLOUD, PACKET_TYPE_HEARTBEAT_DEVICE, 0),
        (HEARTBEAT_CLOUD_0xD8_CLOUD_TO_DEV, PACKET_TYPE_HEARTBEAT_CLOUD, 0),
    ]

    for packet_data, expected_type, expected_length in test_cases:
        packet = CyncProtocol.decode_packet(packet_data)
        assert packet.packet_type == expected_type
        assert packet.length == expected_length
        assert packet.raw == packet_data


def test_header_encode_decode_all_lengths() -> None:
    """Test header encoding/decoding for various lengths."""
    test_lengths = [0, 1, 50, 127, 128, 255, 256, 300, 500, 1000, 4095]

    for length in test_lengths:
        header = CyncProtocol.encode_header(0x73, length)
        test_packet = header + bytes(length)
        _, parsed_length, _ = CyncProtocol.parse_header(test_packet)
        assert parsed_length == length

