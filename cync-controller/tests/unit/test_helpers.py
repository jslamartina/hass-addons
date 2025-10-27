"""
Shared test helper functions for TCP device tests.

This module provides reusable test utilities for packet creation and manipulation
in TCP device unit tests.
"""


def create_packet(pkt_type: int, total_length: int, data: bytes = b""):
    """Helper to create valid packet structure

    Args:
        pkt_type: Packet type byte (0x23, 0xC3, etc.)
        total_length: Total packet length including header (12 bytes) + payload
        data: Optional payload data

    Returns:
        bytes: Complete packet with header and payload
    """
    # Calculate payload length (total - header)
    payload_length = total_length - 12

    # Handle cases where data is provided vs not
    if data:
        # Data is provided, but we need to make sure total_length matches
        actual_payload_length = len(data)
        payload_length = actual_payload_length
    else:
        # No data provided, create empty payload
        data = bytes(payload_length)

    # Calculate multiplier and length byte for payload
    # Length byte stores payload length, not total length
    multiplier = payload_length // 256
    length_byte = payload_length % 256

    # Full header is 12 bytes: [type, byte2, byte3, multiplier, length, queue_id(5), msg_id(3)]
    header = bytearray(
        [
            pkt_type,  # 0
            0x00,  # 1
            0x00,  # 2
            multiplier,  # 3 (payload length multiplier)
            length_byte,  # 4 (payload length remainder)
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,  # 5-9 (queue_id)
            0x00,
            0x00,
            0x00,  # 10-12 (msg_id)
        ]
    )

    # Extend header with payload data (or padding)
    full_packet = header + data

    return bytes(full_packet)
