"""
Checksum utilities for Cync MITM/debugging packets.

The Cync 0x73 packets contain an inner structure delimited by 0x7E markers.
Empirically, the checksum equals the sum of inner structure bytes starting
6 bytes after the starting 0x7E up to (but excluding) the checksum byte and
the trailing 0x7E, modulo 256.

This module centralizes that logic to avoid duplicated implementations.
"""

from __future__ import annotations

from typing import Final


DEFAULT_OFFSET_AFTER_START: Final[int] = 6


def calculate_checksum_between_markers(
    packet: bytes, *, offset_after_start: int = DEFAULT_OFFSET_AFTER_START
) -> int:
    """
    Compute checksum for a packet with 0x7E-delimited inner structure.

    Algorithm (verified against captured packets):
    - Find the first 0x7E and the last 0x7E
    - Sum bytes from (start_index + offset_after_start) up to the byte
      just before the checksum (i.e., excluding the last two bytes: checksum and 0x7E)
    - Return sum modulo 256

    Args:
        packet: Complete packet bytes
        offset_after_start: Number of bytes to skip after the first 0x7E

    Returns:
        The checksum (0-255)
    """
    start = packet.index(0x7E)
    end = len(packet) - 1  # index of trailing 0x7E

    if end <= start + offset_after_start:
        raise ValueError("Packet too short to compute checksum with given offset")

    # Exclude checksum byte at position end-1 and trailing 0x7E at position end
    data_to_sum = packet[start + offset_after_start : end - 1]
    return sum(data_to_sum) % 256


def insert_checksum_in_place(
    packet: bytearray,
    checksum_index: int,
    *,
    offset_after_start: int = DEFAULT_OFFSET_AFTER_START,
) -> None:
    """
    Compute and insert checksum into a mutable packet at the given index.

    Args:
        packet: Mutable packet buffer
        checksum_index: Index where checksum byte should be written
        offset_after_start: Offset after 0x7E start marker used in calculation
    """
    checksum = calculate_checksum_between_markers(
        bytes(packet), offset_after_start=offset_after_start
    )
    packet[checksum_index] = checksum
