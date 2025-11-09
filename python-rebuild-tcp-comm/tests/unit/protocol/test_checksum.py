"""Unit tests for checksum algorithm.

Tests validate checksum calculation against Phase 0.5 real packet captures.
"""

import pytest

from src.protocol.checksum import (
    calculate_checksum_between_markers,
    insert_checksum_in_place,
)
from tests.fixtures.real_packets import (
    STATUS_BROADCAST_0x83_DEV_TO_CLOUD,
    STATUS_BROADCAST_0x83_FRAMED_10,
    STATUS_BROADCAST_0x83_FRAMED_11,
    STATUS_BROADCAST_0x83_FRAMED_4,
    STATUS_BROADCAST_0x83_FRAMED_5,
    STATUS_BROADCAST_0x83_FRAMED_6,
    STATUS_BROADCAST_0x83_FRAMED_7,
    STATUS_BROADCAST_0x83_FRAMED_8,
    STATUS_BROADCAST_0x83_FRAMED_9,
    TOGGLE_OFF_0x73_CLOUD_TO_DEV,
    TOGGLE_ON_0x73_CLOUD_TO_DEV,
)


@pytest.mark.unit
def test_checksum_status_broadcast() -> None:
    """Test checksum calculation against real status broadcast packet."""
    packet = STATUS_BROADCAST_0x83_DEV_TO_CLOUD
    expected_checksum = 0x37  # From packet capture
    calculated = calculate_checksum_between_markers(packet)
    assert calculated == expected_checksum


@pytest.mark.unit
@pytest.mark.parametrize(
    "packet,expected_checksum",
    [
        (STATUS_BROADCAST_0x83_FRAMED_4, 0x8C),
        (STATUS_BROADCAST_0x83_FRAMED_5, 0x49),
        (STATUS_BROADCAST_0x83_FRAMED_6, 0x44),
        (STATUS_BROADCAST_0x83_FRAMED_7, 0x0F),
        (STATUS_BROADCAST_0x83_FRAMED_8, 0xFB),
        (STATUS_BROADCAST_0x83_FRAMED_9, 0xEF),
        (STATUS_BROADCAST_0x83_FRAMED_10, 0xFD),
        (STATUS_BROADCAST_0x83_FRAMED_11, 0xA1),
    ],
)
def test_checksum_validation_fixtures(packet: bytes, expected_checksum: int) -> None:
    """Test checksum against Phase 0.5 validation fixtures."""
    calculated = calculate_checksum_between_markers(packet)
    assert calculated == expected_checksum


@pytest.mark.unit
@pytest.mark.parametrize(
    "packet,expected_checksum",
    [
        (TOGGLE_ON_0x73_CLOUD_TO_DEV, 0x07),
        (TOGGLE_OFF_0x73_CLOUD_TO_DEV, 0x07),
    ],
)
def test_checksum_toggle_fixtures(packet: bytes, expected_checksum: int) -> None:
    """Test checksum against Phase 0.5 toggle command fixtures."""
    calculated = calculate_checksum_between_markers(packet)
    assert calculated == expected_checksum


@pytest.mark.unit
def test_checksum_too_short_packet() -> None:
    """Test error handling for packet too short to compute checksum."""
    short_packet = b"\x7e\x00\x00\x7e"  # Only 4 bytes
    with pytest.raises(ValueError, match="too short"):
        calculate_checksum_between_markers(short_packet)


@pytest.mark.unit
def test_checksum_edge_case_empty_slice() -> None:
    """Test boundary condition: packet that would produce empty data_to_sum slice.

    This is a regression test for an off-by-one error in the boundary check.
    Packet structure: 0x7e + 6 bytes + 0x7e (8 bytes total)
    With offset_after_start=6, the slice would be packet[6:6] (empty).
    The corrected boundary check should reject this as too short.
    """
    # 8 bytes: start=0, end=7, offset=6 → would slice [6:6] (empty)
    edge_case_packet = b"\x7e\x00\x00\x00\x00\x00\x00\x7e"
    with pytest.raises(ValueError, match="too short"):
        calculate_checksum_between_markers(edge_case_packet)


@pytest.mark.unit
def test_checksum_no_start_marker() -> None:
    """Test error handling when packet lacks 0x7e start marker."""
    packet_no_marker = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08"
    with pytest.raises(ValueError, match="subsection not found"):
        calculate_checksum_between_markers(packet_no_marker)


@pytest.mark.unit
def test_insert_checksum_in_place() -> None:
    """Test in-place checksum insertion."""
    packet = bytearray(STATUS_BROADCAST_0x83_DEV_TO_CLOUD)
    # Corrupt checksum
    packet[-2] = 0xFF
    # Recalculate and insert
    insert_checksum_in_place(packet, len(packet) - 2)
    assert packet[-2] == 0x37  # Should restore correct checksum


@pytest.mark.unit
def test_insert_checksum_toggle_on() -> None:
    """Test in-place checksum insertion for toggle command."""
    packet = bytearray(TOGGLE_ON_0x73_CLOUD_TO_DEV)
    original_checksum = packet[-2]
    # Corrupt checksum
    packet[-2] = 0x00
    # Recalculate and insert
    insert_checksum_in_place(packet, len(packet) - 2)
    assert packet[-2] == original_checksum


@pytest.mark.unit
def test_checksum_immutability() -> None:
    """Test that calculate_checksum_between_markers doesn't modify input."""
    packet = STATUS_BROADCAST_0x83_DEV_TO_CLOUD
    packet_copy = bytes(packet)
    calculate_checksum_between_markers(packet)
    assert packet == packet_copy  # Ensure no mutation


@pytest.mark.unit
def test_insert_checksum_preserves_other_bytes() -> None:
    """Test that insert_checksum_in_place only modifies checksum byte."""
    packet = bytearray(STATUS_BROADCAST_0x83_DEV_TO_CLOUD)
    original_bytes = bytes(packet)

    # Corrupt checksum
    packet[-2] = 0xFF

    # Recalculate and insert
    insert_checksum_in_place(packet, len(packet) - 2)

    # Verify only checksum byte changed
    for i in range(len(packet)):
        if i == len(packet) - 2:
            assert packet[i] == 0x37  # Checksum restored
        else:
            assert packet[i] == original_bytes[i]  # All other bytes unchanged
