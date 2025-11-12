"""Unit tests for CyncProtocol encoder/decoder."""

from __future__ import annotations

import pytest

from protocol.cync_protocol import CyncProtocol
from protocol.exceptions import PacketDecodeError
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

# Constants for test assertions
PACKET_LENGTH_26 = 26
PACKET_LENGTH_30 = 30
PACKET_LENGTH_31 = 31
PACKET_LENGTH_517 = 517  # Test value: 2 * 256 + 5
PACKET_LENGTH_HELLO_ACK = 2
PACKET_LENGTH_INFO_ACK = 3
PACKET_LENGTH_DATA_ACK = 7
PACKET_LENGTH_STATUS_BROADCAST = 37
PACKET_LENGTH_EMPTY = 0
PACKET_HEADER_LENGTH = 5
PACKET_MIN_LENGTH = 7

# Checksum constants
EXPECTED_CHECKSUM_STATUS_BROADCAST = 0x37
EXPECTED_CHECKSUM_TOGGLE_ON = 0x07

# Frame marker constant
FRAME_MARKER_0x7E = 0x7E

# Reserved field constant
RESERVED_FIELD_VALUE = 0x0000

# Header byte constants
HEADER_BYTE_HANDSHAKE_TYPE = 0x23
HEADER_BYTE_RESERVED_0 = 0x00
HEADER_BYTE_LENGTH_26_LOW = 0x1A
HEADER_BYTE_DATA_CHANNEL_TYPE = 0x73
HEADER_BYTE_MULTIPLIER_2 = 0x02
HEADER_BYTE_BASE_5 = 0x05

# Handshake packet structure constants
HANDSHAKE_PREFIX_BYTE = 0x03
HANDSHAKE_AUTH_CODE_LENGTH_INDICATOR = 0x10

# Packet type constants for round-trip tests
EXPECTED_PACKET_TYPE_HEARTBEAT_DEVICE = 0xD3

# Status broadcast packet structure constants
STATUS_BROADCAST_START_MARKER_POSITION = 12  # After header(5) + endpoint(5) + msg_id(2), no padding
EXPECTED_MARKER_COUNT = 2  # Start and end markers

# Payload size constants
PAYLOAD_SIZE_MODULO_256 = 256

# =============================================================================
# Header Parsing Tests
# =============================================================================


def test_parse_header_handshake() -> None:
    """Test parsing 0x23 handshake header."""
    packet_type, length, reserved = CyncProtocol.parse_header(HANDSHAKE_0x23_DEV_TO_CLOUD)

    assert packet_type == PACKET_TYPE_HANDSHAKE
    assert length == PACKET_LENGTH_26  # 0x00 * 256 + 0x1a
    assert reserved == RESERVED_FIELD_VALUE


def test_parse_header_data_channel() -> None:
    """Test parsing 0x73 data channel header."""
    packet_type, length, reserved = CyncProtocol.parse_header(TOGGLE_ON_0x73_CLOUD_TO_DEV)

    assert packet_type == PACKET_TYPE_DATA_CHANNEL
    assert length == PACKET_LENGTH_31  # 0x00 * 256 + 0x1f
    assert reserved == RESERVED_FIELD_VALUE


def test_parse_header_length_calculation() -> None:
    """Test multiplier * 256 + base calculation."""
    # Create test packet with length = 2 * 256 + 5 = 517
    test_packet = bytes([0x23, 0x00, 0x00, 0x02, 0x05])
    packet_type, length, reserved = CyncProtocol.parse_header(test_packet)

    assert packet_type == PACKET_TYPE_HANDSHAKE
    assert length == PACKET_LENGTH_517
    assert reserved == RESERVED_FIELD_VALUE


def test_parse_header_large_packet() -> None:
    """Test with multiplier > 0 (packets > 255 bytes)."""
    # Device info packet has length 30 (0x1e)
    packet_type, length, reserved = CyncProtocol.parse_header(DEVICE_INFO_0x43_DEV_TO_CLOUD)

    assert packet_type == PACKET_TYPE_DEVICE_INFO
    assert length == PACKET_LENGTH_30
    assert reserved == RESERVED_FIELD_VALUE


# =============================================================================
# Header Encoding Tests
# =============================================================================


def test_encode_header_small_packet() -> None:
    """Test encoding header with length < 256 (multiplier=0)."""
    header = CyncProtocol.encode_header(PACKET_TYPE_HANDSHAKE, PACKET_LENGTH_26)

    assert header == bytes(
        [
            HEADER_BYTE_HANDSHAKE_TYPE,
            HEADER_BYTE_RESERVED_0,
            HEADER_BYTE_RESERVED_0,
            HEADER_BYTE_RESERVED_0,
            HEADER_BYTE_LENGTH_26_LOW,
        ]
    )
    assert len(header) == PACKET_HEADER_LENGTH


def test_encode_header_large_packet() -> None:
    """Test encoding header with length > 255 (multiplier > 0)."""
    # Length 517 = 2 * 256 + 5
    header = CyncProtocol.encode_header(PACKET_TYPE_DATA_CHANNEL, PACKET_LENGTH_517)

    assert header == bytes(
        [
            HEADER_BYTE_DATA_CHANNEL_TYPE,
            HEADER_BYTE_RESERVED_0,
            HEADER_BYTE_RESERVED_0,
            HEADER_BYTE_MULTIPLIER_2,
            HEADER_BYTE_BASE_5,
        ]
    )
    assert len(header) == PACKET_HEADER_LENGTH


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


def test_decode_handshake_packet_type_0x23() -> None:
    """Decode real 0x23 handshake packet."""
    packet = CyncProtocol.decode_packet(HANDSHAKE_0x23_DEV_TO_CLOUD)

    assert isinstance(packet, CyncPacket)
    assert packet.packet_type == PACKET_TYPE_HANDSHAKE
    assert packet.length == PACKET_LENGTH_26
    assert len(packet.payload) == PACKET_LENGTH_26
    assert packet.raw == HANDSHAKE_0x23_DEV_TO_CLOUD


def test_decode_hello_ack_packet_type_0x28() -> None:
    """Decode real 0x28 hello ACK packet."""
    packet = CyncProtocol.decode_packet(HELLO_ACK_0x28_CLOUD_TO_DEV)

    assert isinstance(packet, CyncPacket)
    assert packet.packet_type == PACKET_TYPE_HELLO_ACK
    assert packet.length == PACKET_LENGTH_HELLO_ACK
    assert len(packet.payload) == PACKET_LENGTH_HELLO_ACK
    assert packet.raw == HELLO_ACK_0x28_CLOUD_TO_DEV


def test_decode_device_info_packet_type_0x43() -> None:
    """Decode real 0x43 device info packet."""
    packet = CyncProtocol.decode_packet(DEVICE_INFO_0x43_DEV_TO_CLOUD)

    assert isinstance(packet, CyncPacket)
    assert packet.packet_type == PACKET_TYPE_DEVICE_INFO
    assert packet.length == PACKET_LENGTH_30
    assert len(packet.payload) == PACKET_LENGTH_30
    assert packet.raw == DEVICE_INFO_0x43_DEV_TO_CLOUD


def test_decode_info_ack_packet_type_0x48() -> None:
    """Decode real 0x48 info ACK packet."""
    packet = CyncProtocol.decode_packet(INFO_ACK_0x48_CLOUD_TO_DEV)

    assert isinstance(packet, CyncPacket)
    assert packet.packet_type == PACKET_TYPE_INFO_ACK
    assert packet.length == PACKET_LENGTH_INFO_ACK
    assert len(packet.payload) == PACKET_LENGTH_INFO_ACK
    assert packet.raw == INFO_ACK_0x48_CLOUD_TO_DEV


def test_decode_data_ack_packet_type_0x7b() -> None:
    """Decode real 0x7B data ACK packet."""
    packet = CyncProtocol.decode_packet(DATA_ACK_0x7B_DEV_TO_CLOUD)

    assert isinstance(packet, CyncPacket)
    assert packet.packet_type == PACKET_TYPE_DATA_ACK
    assert packet.length == PACKET_LENGTH_DATA_ACK
    assert len(packet.payload) == PACKET_LENGTH_DATA_ACK
    assert packet.raw == DATA_ACK_0x7B_DEV_TO_CLOUD


def test_decode_status_broadcast_packet_type_0x83() -> None:
    """Decode real 0x83 status broadcast packet."""
    packet = CyncProtocol.decode_packet(STATUS_BROADCAST_0x83_DEV_TO_CLOUD)

    assert isinstance(packet, CyncDataPacket)
    assert packet.packet_type == PACKET_TYPE_STATUS_BROADCAST
    assert packet.length == PACKET_LENGTH_STATUS_BROADCAST
    assert packet.endpoint == bytes.fromhex("45 88 0f 3a 00")
    assert packet.msg_id == bytes.fromhex("09 00")  # 2 bytes - byte 12 is padding, not msg_id
    assert packet.checksum == EXPECTED_CHECKSUM_STATUS_BROADCAST
    assert packet.checksum_valid is True


def test_decode_status_ack_packet_type_0x88() -> None:
    """Decode real 0x88 status ACK packet."""
    packet = CyncProtocol.decode_packet(STATUS_ACK_0x88_CLOUD_TO_DEV)

    assert isinstance(packet, CyncPacket)
    assert packet.packet_type == PACKET_TYPE_STATUS_ACK
    assert packet.length == PACKET_LENGTH_INFO_ACK
    assert len(packet.payload) == PACKET_LENGTH_INFO_ACK
    assert packet.raw == STATUS_ACK_0x88_CLOUD_TO_DEV


def test_decode_heartbeat_device_packet_type_0xd3() -> None:
    """Decode real 0xD3 device heartbeat packet."""
    packet = CyncProtocol.decode_packet(HEARTBEAT_DEV_0xD3_DEV_TO_CLOUD)

    assert isinstance(packet, CyncPacket)
    assert packet.packet_type == PACKET_TYPE_HEARTBEAT_DEVICE
    assert packet.length == PACKET_LENGTH_EMPTY
    assert len(packet.payload) == PACKET_LENGTH_EMPTY
    assert packet.raw == HEARTBEAT_DEV_0xD3_DEV_TO_CLOUD


def test_decode_heartbeat_cloud_packet_type_0xd8() -> None:
    """Decode real 0xD8 cloud heartbeat packet."""
    packet = CyncProtocol.decode_packet(HEARTBEAT_CLOUD_0xD8_CLOUD_TO_DEV)

    assert isinstance(packet, CyncPacket)
    assert packet.packet_type == PACKET_TYPE_HEARTBEAT_CLOUD
    assert packet.length == PACKET_LENGTH_EMPTY
    assert len(packet.payload) == PACKET_LENGTH_EMPTY
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
    assert msg_id == bytes.fromhex("10 00")


def test_decode_data_packet_with_framing() -> None:
    """Decode 0x73 packet, verify 0x7e markers present."""
    packet = CyncProtocol.decode_packet(TOGGLE_ON_0x73_CLOUD_TO_DEV)

    assert isinstance(packet, CyncDataPacket)
    assert packet.packet_type == PACKET_TYPE_DATA_CHANNEL

    # Verify 0x7e markers in raw packet
    assert FRAME_MARKER_0x7E in packet.raw
    assert packet.raw[0] != FRAME_MARKER_0x7E  # Not at start
    assert packet.raw[-1] == FRAME_MARKER_0x7E  # At end

    # Verify endpoint and msg_id extraction
    assert packet.endpoint == bytes.fromhex("45 88 0f 3a 00")
    assert packet.msg_id == bytes.fromhex("10 00")

    # Verify checksum
    assert packet.checksum == EXPECTED_CHECKSUM_TOGGLE_ON
    assert packet.checksum_valid is True


def test_decode_status_broadcast_framing() -> None:
    """Decode 0x83 packet with framing."""
    packet = CyncProtocol.decode_packet(STATUS_BROADCAST_0x83_DEV_TO_CLOUD)

    assert isinstance(packet, CyncDataPacket)
    assert packet.packet_type == PACKET_TYPE_STATUS_BROADCAST

    # Verify 0x7e markers
    assert FRAME_MARKER_0x7E in packet.raw
    assert packet.raw[-1] == FRAME_MARKER_0x7E

    # Verify endpoint extraction
    assert packet.endpoint == bytes.fromhex("45 88 0f 3a 00")

    # Verify checksum
    assert packet.checksum == EXPECTED_CHECKSUM_STATUS_BROADCAST
    assert packet.checksum_valid is True


def test_decode_toggle_off_data_packet() -> None:
    """Decode toggle OFF 0x73 packet."""
    packet = CyncProtocol.decode_packet(TOGGLE_OFF_0x73_CLOUD_TO_DEV)

    assert isinstance(packet, CyncDataPacket)
    assert packet.packet_type == PACKET_TYPE_DATA_CHANNEL
    assert packet.endpoint == bytes.fromhex("45 88 0f 3a 00")
    assert packet.msg_id == bytes.fromhex("11 00")
    assert packet.checksum == EXPECTED_CHECKSUM_TOGGLE_ON
    assert packet.checksum_valid is True


# =============================================================================
# Edge Case Tests
# =============================================================================


def test_decode_packet_too_short() -> None:
    """Test packet < 5 bytes raises PacketDecodeError."""
    with pytest.raises(PacketDecodeError, match="too_short"):
        CyncProtocol.decode_packet(bytes([0x23, 0x00]))


def test_decode_packet_length_mismatch() -> None:
    """Test header length doesn't match actual data."""
    # Header claims length 100, but only provide 10 bytes of payload
    bad_packet = bytes([0x23, 0x00, 0x00, 0x00, 0x64]) + bytes(10)

    with pytest.raises(PacketDecodeError, match="invalid_length"):
        CyncProtocol.decode_packet(bad_packet)


def test_parse_header_invalid_input() -> None:
    """Test empty bytes raises PacketDecodeError."""
    with pytest.raises(PacketDecodeError, match="too_short"):
        CyncProtocol.parse_header(b"")


def test_parse_header_partial_header() -> None:
    """Test partial header (3 bytes) raises PacketDecodeError."""
    with pytest.raises(PacketDecodeError, match="too_short"):
        CyncProtocol.parse_header(bytes([0x23, 0x00, 0x00]))


def test_extract_endpoint_payload_too_short() -> None:
    """Test payload too short for endpoint/msg_id extraction."""
    with pytest.raises(PacketDecodeError, match="too_short"):
        CyncProtocol.extract_endpoint_and_msg_id(bytes([0x01, 0x02]))


def test_decode_data_packet_missing_markers() -> None:
    """Test data packet without 0x7e markers raises PacketDecodeError."""
    # Create malformed 0x73 packet without 0x7e markers
    bad_packet = bytes([0x73, 0x00, 0x00, 0x00, 0x10]) + bytes(16)

    with pytest.raises(PacketDecodeError, match="missing_0x7e_markers"):
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
    assert packet.msg_id == bytes.fromhex("10 00")
    assert packet.checksum == EXPECTED_CHECKSUM_TOGGLE_ON
    assert packet.checksum_valid is True

    # Verify we only processed the declared packet length
    expected_packet_length = 5 + packet.length  # Header + payload
    assert expected_packet_length == len(valid_packet)
    assert len(buffer_with_trailing) > len(valid_packet)  # Has trailing data


# =============================================================================
# Handshake Encoder Tests
# =============================================================================


def test_encode_handshake_basic() -> None:
    """Test basic handshake encoding with valid inputs."""
    endpoint = bytes.fromhex("38 e8 cf 46 00")
    auth_code = bytes.fromhex("31 65 30 37 64 38 63 65 30 61 36 31 37 61 33 37")

    packet = CyncProtocol.encode_handshake(endpoint, auth_code)

    # Verify packet type
    assert packet[0] == HEADER_BYTE_HANDSHAKE_TYPE

    # Verify length (26 bytes payload)
    assert packet[3] == HEADER_BYTE_RESERVED_0  # Multiplier
    assert packet[4] == HEADER_BYTE_LENGTH_26_LOW  # Base (26)

    # Verify structure
    assert packet[5] == HANDSHAKE_PREFIX_BYTE  # Prefix
    assert packet[6:11] == endpoint  # Endpoint at bytes 6-10
    assert packet[11] == HANDSHAKE_AUTH_CODE_LENGTH_INDICATOR  # Auth code length indicator
    assert packet[12:28] == auth_code  # Auth code at bytes 12-27


def test_encode_handshake_invalid_endpoint() -> None:
    """Test ValueError for wrong endpoint size."""
    auth_code = bytes(16)

    # Too short
    with pytest.raises(ValueError, match="Endpoint must be 5 bytes"):
        CyncProtocol.encode_handshake(bytes(3), auth_code)

    # Too long
    with pytest.raises(ValueError, match="Endpoint must be 5 bytes"):
        CyncProtocol.encode_handshake(bytes(7), auth_code)


def test_encode_handshake_invalid_auth_code() -> None:
    """Test ValueError for wrong auth code size."""
    endpoint = bytes(5)

    # Too short
    with pytest.raises(ValueError, match="Auth code must be 16 bytes"):
        CyncProtocol.encode_handshake(endpoint, bytes(10))

    # Too long
    with pytest.raises(ValueError, match="Auth code must be 16 bytes"):
        CyncProtocol.encode_handshake(endpoint, bytes(20))


def test_encode_handshake_roundtrip() -> None:
    """Test encode → decode → verify fields match."""
    endpoint = bytes.fromhex("38 e8 cf 46 00")
    auth_code = bytes.fromhex("31 65 30 37 64 38 63 65 30 61 36 31 37 61 33 37")

    # Encode
    encoded = CyncProtocol.encode_handshake(endpoint, auth_code)

    # Decode
    decoded = CyncProtocol.decode_packet(encoded)

    # Verify round-trip
    assert decoded.packet_type == PACKET_TYPE_HANDSHAKE
    assert decoded.length == PACKET_LENGTH_26
    assert decoded.raw == encoded
    # Verify endpoint embedded correctly
    assert encoded[6:11] == endpoint
    assert encoded[12:28] == auth_code


def test_encode_handshake_matches_fixture() -> None:
    """Compare encoded output with HANDSHAKE_0x23_DEV_TO_CLOUD fixture."""
    # Extract endpoint and auth_code from fixture
    fixture = HANDSHAKE_0x23_DEV_TO_CLOUD
    endpoint = fixture[6:11]  # Bytes 6-10
    auth_code = fixture[12:28]  # Bytes 12-27 (after 0x10 length indicator)

    # Encode with same parameters
    encoded = CyncProtocol.encode_handshake(endpoint, auth_code)

    # Should match fixture exactly
    assert encoded == fixture


# =============================================================================
# Data Packet Encoder Tests
# =============================================================================


def test_encode_data_packet_basic() -> None:
    """Test basic data packet encoding with valid inputs."""
    endpoint = bytes.fromhex("45 88 0f 3a 00")
    msg_id = bytes.fromhex("10 00")
    inner_payload = bytes.fromhex("10 01 00 00 f8 8e 0c 00 10 01 00 00 00 50 00 f7 11 02 01 01")

    packet = CyncProtocol.encode_data_packet(endpoint, msg_id, inner_payload)

    # Verify packet type
    assert packet[0] == HEADER_BYTE_DATA_CHANNEL_TYPE

    # Verify endpoint and msg_id in packet
    assert packet[5:10] == endpoint
    assert packet[10:12] == msg_id  # 2 bytes
    assert packet[12] == HEADER_BYTE_RESERVED_0  # Padding byte

    # Verify 0x7e markers present
    assert FRAME_MARKER_0x7E in packet
    assert packet[-1] == FRAME_MARKER_0x7E  # End marker


def test_encode_data_packet_invalid_endpoint() -> None:
    """Test ValueError for wrong endpoint size."""
    msg_id = bytes(3)
    payload = bytes(10)

    # Too short
    with pytest.raises(ValueError, match="Endpoint must be 5 bytes"):
        CyncProtocol.encode_data_packet(bytes(3), msg_id, payload)

    # Too long
    with pytest.raises(ValueError, match="Endpoint must be 5 bytes"):
        CyncProtocol.encode_data_packet(bytes(7), msg_id, payload)


def test_encode_data_packet_invalid_msg_id() -> None:
    """Test ValueError for wrong msg_id size."""
    endpoint = bytes(5)
    payload = bytes(10)

    # Too short
    with pytest.raises(ValueError, match="msg_id must be 2 bytes"):
        CyncProtocol.encode_data_packet(endpoint, bytes(1), payload)

    # Too long
    with pytest.raises(ValueError, match="msg_id must be 2 bytes"):
        CyncProtocol.encode_data_packet(endpoint, bytes(3), payload)


def test_encode_data_packet_with_framing() -> None:
    """Verify 0x7e markers present at correct positions."""
    endpoint = bytes.fromhex("45 88 0f 3a 00")
    msg_id = bytes.fromhex("10 00")
    inner_payload = bytes(20)

    packet = CyncProtocol.encode_data_packet(endpoint, msg_id, inner_payload)

    # Find 0x7e markers
    first_7e = packet.index(0x7E)
    last_7e = len(packet) - 1 - packet[::-1].index(0x7E)

    # Verify markers found
    assert packet[first_7e] == FRAME_MARKER_0x7E
    assert packet[last_7e] == FRAME_MARKER_0x7E
    assert first_7e < last_7e

    # Verify data between markers
    data_between = packet[first_7e + 1 : last_7e - 1]  # Exclude checksum
    assert data_between == inner_payload


def test_encode_data_packet_checksum_valid() -> None:
    """Encode → decode → verify checksum valid."""
    endpoint = bytes.fromhex("45 88 0f 3a 00")
    msg_id = bytes.fromhex("10 00")
    inner_payload = bytes.fromhex("10 01 00 00 f8 8e 0c 00 10 01 00 00 00 50 00 f7 11 02 01 01")

    # Encode
    encoded = CyncProtocol.encode_data_packet(endpoint, msg_id, inner_payload)

    # Decode
    decoded = CyncProtocol.decode_packet(encoded)

    # Verify checksum valid
    assert isinstance(decoded, CyncDataPacket)
    assert decoded.checksum_valid is True


def test_encode_data_packet_roundtrip() -> None:
    """Encode → decode → verify all fields match."""
    endpoint = bytes.fromhex("45 88 0f 3a 00")
    msg_id = bytes.fromhex("11 00")
    inner_payload = bytes.fromhex("11 01 00 00 f8 8e 0c 00 11 01 00 00 00 50 00 f7 11 02 00 01")

    # Encode
    encoded = CyncProtocol.encode_data_packet(endpoint, msg_id, inner_payload)

    # Decode
    decoded = CyncProtocol.decode_packet(encoded)

    # Verify all fields preserved
    assert isinstance(decoded, CyncDataPacket)
    assert decoded.packet_type == PACKET_TYPE_DATA_CHANNEL
    assert decoded.endpoint == endpoint
    assert decoded.msg_id == msg_id
    assert decoded.data == inner_payload
    assert decoded.checksum_valid is True


def test_encode_data_packet_matches_fixture() -> None:
    """Compare encoded packet with TOGGLE_ON_0x73_CLOUD_TO_DEV fixture."""
    # Extract parameters from fixture
    fixture = TOGGLE_ON_0x73_CLOUD_TO_DEV
    endpoint = fixture[5:10]  # Bytes 5-9
    msg_id = fixture[10:12]  # Bytes 10-11 (2 bytes, NOT 3)

    # Extract inner payload (between 0x7e markers)
    first_7e = fixture.index(0x7E)
    last_7e = len(fixture) - 1 - fixture[::-1].index(0x7E)
    inner_payload = fixture[first_7e + 1 : last_7e - 1]  # Exclude checksum

    # Encode with same parameters
    encoded = CyncProtocol.encode_data_packet(endpoint, msg_id, inner_payload)

    # Should match fixture exactly
    assert encoded == fixture


# =============================================================================
# Encoder Tests: Heartbeat (0xD3)
# =============================================================================


def test_encode_heartbeat_basic() -> None:
    """Test basic heartbeat packet encoding."""
    packet = CyncProtocol.encode_heartbeat()

    # Verify structure
    assert len(packet) == PACKET_HEADER_LENGTH
    assert packet[0] == PACKET_TYPE_HEARTBEAT_DEVICE  # Packet type
    assert packet[1:] == bytes([0x00, 0x00, 0x00, 0x00])  # Reserved + length


def test_encode_heartbeat_matches_fixture() -> None:
    """Compare encoded heartbeat with HEARTBEAT_DEV_0xD3_DEV_TO_CLOUD fixture."""
    encoded = CyncProtocol.encode_heartbeat()

    # Should match fixture exactly
    assert encoded == HEARTBEAT_DEV_0xD3_DEV_TO_CLOUD


def test_encode_heartbeat_roundtrip() -> None:
    """Encode → decode → verify heartbeat packet."""
    # Encode
    encoded = CyncProtocol.encode_heartbeat()

    # Decode
    decoded = CyncProtocol.decode_packet(encoded)

    # Verify
    assert decoded.packet_type == PACKET_TYPE_HEARTBEAT_DEVICE
    assert decoded.length == PACKET_LENGTH_EMPTY
    assert len(decoded.payload) == 0


# =============================================================================
# Encoder Tests: Status Broadcast (0x83)
# =============================================================================


def test_encode_status_broadcast_basic() -> None:
    """Test basic status broadcast packet encoding with valid inputs."""
    endpoint = bytes.fromhex("45 88 0f 3a 00")
    msg_id = bytes.fromhex("09 00")
    inner_payload = bytes.fromhex(
        "1f 00 00 00 fa db 13 00 72 25 11 50 00 50 00 db 11 02 01 01 0a 0a ff ff ff 00 00"
    )

    packet = CyncProtocol.encode_status_broadcast(endpoint, msg_id, inner_payload)

    # Verify structure
    assert packet[0] == PACKET_TYPE_STATUS_BROADCAST  # Packet type
    assert packet[5:10] == endpoint
    assert packet[10:12] == msg_id
    assert (
        packet[STATUS_BROADCAST_START_MARKER_POSITION] == FRAME_MARKER_0x7E
    )  # Start marker (no padding for 0x83)


def test_encode_status_broadcast_with_framing() -> None:
    """Verify 0x7e markers present at correct positions."""
    endpoint = bytes.fromhex("45 88 0f 3a 00")
    msg_id = bytes.fromhex("09 00")
    inner_payload = bytes(20)

    packet = CyncProtocol.encode_status_broadcast(endpoint, msg_id, inner_payload)

    # Find 0x7e markers
    marker_positions = [i for i, b in enumerate(packet) if b == FRAME_MARKER_0x7E]

    # Should have exactly 2 markers
    assert len(marker_positions) == EXPECTED_MARKER_COUNT
    start_marker = marker_positions[0]
    end_marker = marker_positions[1]

    # Verify markers are in expected range
    assert (
        start_marker == STATUS_BROADCAST_START_MARKER_POSITION
    )  # After header(5) + endpoint(5) + msg_id(2), no padding for 0x83
    assert end_marker == len(packet) - 1  # Last byte


def test_encode_status_broadcast_input_validation() -> None:
    """Test endpoint and msg_id size validation."""
    payload = bytes(20)

    # Valid endpoint and msg_id
    valid_endpoint = bytes(5)
    valid_msg_id = bytes(2)

    # Test endpoint validation
    with pytest.raises(ValueError, match="Endpoint must be 5 bytes"):
        CyncProtocol.encode_status_broadcast(bytes(4), valid_msg_id, payload)

    with pytest.raises(ValueError, match="Endpoint must be 5 bytes"):
        CyncProtocol.encode_status_broadcast(bytes(6), valid_msg_id, payload)

    # Test msg_id validation
    with pytest.raises(ValueError, match="msg_id must be 2 bytes"):
        CyncProtocol.encode_status_broadcast(valid_endpoint, bytes(1), payload)

    with pytest.raises(ValueError, match="msg_id must be 2 bytes"):
        CyncProtocol.encode_status_broadcast(valid_endpoint, bytes(3), payload)


def test_encode_status_broadcast_checksum_valid() -> None:
    """Encode → decode → verify checksum valid."""
    endpoint = bytes.fromhex("45 88 0f 3a 00")
    msg_id = bytes.fromhex("09 00")
    inner_payload = bytes.fromhex(
        "1f 00 00 00 fa db 13 00 72 25 11 50 00 50 00 db 11 02 01 01 0a 0a ff ff ff 00 00"
    )

    # Encode
    encoded = CyncProtocol.encode_status_broadcast(endpoint, msg_id, inner_payload)

    # Decode
    decoded = CyncProtocol.decode_packet(encoded)

    # Verify checksum valid
    assert isinstance(decoded, CyncDataPacket)
    assert decoded.checksum_valid is True


def test_encode_status_broadcast_roundtrip() -> None:
    """Encode → decode → verify all fields match."""
    endpoint = bytes.fromhex("45 88 0f 3a 00")
    msg_id = bytes.fromhex("09 00")
    inner_payload = bytes.fromhex(
        "1f 00 00 00 fa db 13 00 72 25 11 50 00 50 00 db 11 02 01 01 0a 0a ff ff ff 00 00"
    )

    # Encode
    encoded = CyncProtocol.encode_status_broadcast(endpoint, msg_id, inner_payload)

    # Decode
    decoded = CyncProtocol.decode_packet(encoded)

    # Verify all fields preserved
    assert isinstance(decoded, CyncDataPacket)
    assert decoded.packet_type == PACKET_TYPE_STATUS_BROADCAST
    assert decoded.endpoint == endpoint
    assert decoded.msg_id == msg_id
    assert decoded.data == inner_payload
    assert decoded.checksum_valid is True


def test_encode_status_broadcast_matches_fixture() -> None:
    """Compare encoded packet with STATUS_BROADCAST_0x83_DEV_TO_CLOUD fixture."""
    # Extract parameters from fixture
    fixture = STATUS_BROADCAST_0x83_DEV_TO_CLOUD
    endpoint = fixture[5:10]  # Bytes 5-9
    msg_id = fixture[10:12]  # Bytes 10-11 (2 bytes)

    # Extract inner payload (between 0x7e markers)
    first_7e = fixture.index(0x7E)
    last_7e = len(fixture) - 1 - fixture[::-1].index(0x7E)
    inner_payload = fixture[first_7e + 1 : last_7e - 1]  # Exclude checksum

    # Encode with same parameters
    encoded = CyncProtocol.encode_status_broadcast(endpoint, msg_id, inner_payload)

    # Should match fixture exactly
    assert encoded == fixture


# =============================================================================
# Round-Trip Tests: All Packet Types
# =============================================================================


def test_roundtrip_all_packet_types() -> None:
    """Test encode/decode for all major packet types (0x23, 0x73, 0x83, 0xD3)."""
    # Test 0x23 Handshake
    endpoint_hs = bytes.fromhex("45 88 0f 3a 00")
    auth_code = bytes.fromhex("31 65 30 37 64 38 63 65 30 61 36 31 37 61 33 37")
    encoded_hs = CyncProtocol.encode_handshake(endpoint_hs, auth_code)
    decoded_hs = CyncProtocol.decode_packet(encoded_hs)
    assert decoded_hs.packet_type == PACKET_TYPE_HANDSHAKE

    # Test 0x73 Data Channel
    endpoint_dc = bytes.fromhex("45 88 0f 3a 00")
    msg_id_dc = bytes.fromhex("10 00")
    inner_payload_dc = bytes.fromhex("10 01 00 00 f8 8e 0c 00 10 01 00 00 00 50 00 f7 11 02 01 01")
    encoded_dc = CyncProtocol.encode_data_packet(endpoint_dc, msg_id_dc, inner_payload_dc)
    decoded_dc = CyncProtocol.decode_packet(encoded_dc)
    assert decoded_dc.packet_type == PACKET_TYPE_DATA_CHANNEL
    assert isinstance(decoded_dc, CyncDataPacket)
    assert decoded_dc.checksum_valid is True

    # Test 0x83 Status Broadcast
    endpoint_sb = bytes.fromhex("45 88 0f 3a 00")
    msg_id_sb = bytes.fromhex("09 00")
    inner_payload_sb = bytes.fromhex(
        "1f 00 00 00 fa db 13 00 72 25 11 50 00 50 00 db 11 02 01 01 0a 0a ff ff ff 00 00"
    )
    encoded_sb = CyncProtocol.encode_status_broadcast(endpoint_sb, msg_id_sb, inner_payload_sb)
    decoded_sb = CyncProtocol.decode_packet(encoded_sb)
    assert decoded_sb.packet_type == PACKET_TYPE_STATUS_BROADCAST
    assert isinstance(decoded_sb, CyncDataPacket)
    assert decoded_sb.checksum_valid is True

    # Test 0xD3 Heartbeat
    encoded_hb = CyncProtocol.encode_heartbeat()
    decoded_hb = CyncProtocol.decode_packet(encoded_hb)
    assert decoded_hb.packet_type == PACKET_TYPE_HEARTBEAT_DEVICE
    assert decoded_hb.length == 0


# =============================================================================
# Round-Trip Tests (Comprehensive)
# =============================================================================


def test_roundtrip_all_handshake_params() -> None:
    """Test various endpoint/auth_code combinations for handshake."""
    test_cases = [
        (
            bytes.fromhex("38 e8 cf 46 00"),
            bytes.fromhex("31 65 30 37 64 38 63 65 30 61 36 31 37 61 33 37"),
        ),
        (
            bytes.fromhex("45 88 0f 3a 00"),
            bytes.fromhex("00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff"),
        ),
        (
            bytes.fromhex("32 5d 53 17 01"),
            bytes.fromhex("ff ee dd cc bb aa 99 88 77 66 55 44 33 22 11 00"),
        ),
    ]

    for endpoint, auth_code in test_cases:
        # Encode
        encoded = CyncProtocol.encode_handshake(endpoint, auth_code)

        # Decode
        decoded = CyncProtocol.decode_packet(encoded)

        # Verify round-trip preserves data
        assert decoded.packet_type == PACKET_TYPE_HANDSHAKE
        assert decoded.length == PACKET_LENGTH_26
        assert encoded[6:11] == endpoint
        assert encoded[12:28] == auth_code  # After 0x10 length indicator


def test_roundtrip_data_packet_various_payloads() -> None:
    """Test different payload sizes and content for data packets."""
    endpoint = bytes.fromhex("45 88 0f 3a 00")
    msg_id = bytes.fromhex("10 00")

    # Test various payload sizes (minimum 10 bytes due to checksum offset requirements)
    # Real Cync packets use 20+ byte payloads for toggle commands
    payload_sizes = [10, 20, 50, 100]

    for size in payload_sizes:
        # Create payload with pattern
        inner_payload = (
            bytes(range(size % PAYLOAD_SIZE_MODULO_256))
            if size < PAYLOAD_SIZE_MODULO_256
            else bytes(size)
        )

        # Encode
        encoded = CyncProtocol.encode_data_packet(endpoint, msg_id, inner_payload)

        # Decode
        decoded = CyncProtocol.decode_packet(encoded)

        # Verify round-trip
        assert isinstance(decoded, CyncDataPacket)
        assert decoded.endpoint == endpoint
        assert decoded.msg_id == msg_id
        assert decoded.data == inner_payload
        assert decoded.checksum_valid is True


def test_encode_decode_preserves_data() -> None:
    """Verify no data loss in encode → decode cycle."""
    # Test handshake
    endpoint_hs = bytes.fromhex("38 e8 cf 46 00")
    auth_code = bytes.fromhex("31 65 30 37 64 38 63 65 30 61 36 31 37 61 33 37")
    encoded_hs = CyncProtocol.encode_handshake(endpoint_hs, auth_code)
    decoded_hs = CyncProtocol.decode_packet(encoded_hs)
    assert decoded_hs.packet_type == PACKET_TYPE_HANDSHAKE
    assert decoded_hs.raw == encoded_hs

    # Test data packet
    endpoint_dp = bytes.fromhex("45 88 0f 3a 00")
    msg_id_dp = bytes.fromhex("10 00")
    inner_payload_dp = bytes.fromhex("10 01 00 00 f8 8e 0c 00 10 01 00 00 00 50 00 f7 11 02 01 01")
    encoded_dp = CyncProtocol.encode_data_packet(endpoint_dp, msg_id_dp, inner_payload_dp)
    decoded_dp = CyncProtocol.decode_packet(encoded_dp)
    assert decoded_dp.packet_type == PACKET_TYPE_DATA_CHANNEL
    endpoint_dp = bytes.fromhex("45 88 0f 3a 00")
    msg_id = bytes.fromhex("11 00")
    inner_payload = bytes.fromhex("11 01 00 00 f8 8e 0c 00 11 01 00 00 00 50 00 f7 11 02 00 01")
    encoded_dp = CyncProtocol.encode_data_packet(endpoint_dp, msg_id, inner_payload)
    decoded_dp = CyncProtocol.decode_packet(encoded_dp)
    assert isinstance(decoded_dp, CyncDataPacket)
    assert decoded_dp.endpoint == endpoint_dp
    assert decoded_dp.msg_id == msg_id
    assert decoded_dp.data == inner_payload
    assert decoded_dp.checksum_valid is True


def test_roundtrip_toggle_off_packet() -> None:
    """Test round-trip with toggle OFF packet parameters."""
    # Use toggle OFF fixture parameters
    endpoint = bytes.fromhex("45 88 0f 3a 00")
    msg_id = bytes.fromhex("11 00")
    inner_payload = bytes.fromhex("11 01 00 00 f8 8e 0c 00 11 01 00 00 00 50 00 f7 11 02 00 01")

    # Encode
    encoded = CyncProtocol.encode_data_packet(endpoint, msg_id, inner_payload)

    # Decode
    decoded = CyncProtocol.decode_packet(encoded)

    # Verify
    assert isinstance(decoded, CyncDataPacket)
    assert decoded.packet_type == PACKET_TYPE_DATA_CHANNEL
    assert decoded.endpoint == endpoint
    assert decoded.msg_id == msg_id
    assert decoded.data == inner_payload
    assert decoded.checksum_valid is True


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
