"""Cync protocol package - packet encoding, decoding, and framing.

This package implements the Cync device protocol codec based on validated
packet captures from Phase 0.5. It provides packet type definitions,
encoding/decoding functions, and TCP stream framing.

Public API:
- Packet type constants (PACKET_TYPE_*)
- Packet dataclasses (CyncPacket, CyncDataPacket)
- Protocol encoder/decoder (CyncProtocol)
"""

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

__all__ = [
    # Protocol encoder/decoder
    "CyncProtocol",
    # Packet type constants
    "PACKET_TYPE_HANDSHAKE",
    "PACKET_TYPE_HELLO_ACK",
    "PACKET_TYPE_DEVICE_INFO",
    "PACKET_TYPE_INFO_ACK",
    "PACKET_TYPE_DATA_CHANNEL",
    "PACKET_TYPE_DATA_ACK",
    "PACKET_TYPE_STATUS_BROADCAST",
    "PACKET_TYPE_STATUS_ACK",
    "PACKET_TYPE_HEARTBEAT_DEVICE",
    "PACKET_TYPE_HEARTBEAT_CLOUD",
    # Dataclasses
    "CyncPacket",
    "CyncDataPacket",
]
