"""Cync protocol packet type definitions and dataclass structures.

This module defines all packet type constants and dataclass structures for the
Cync device protocol. Packet types are based on Phase 0.5 protocol validation.

Packet Type Overview:
- 0x23/0x28: Handshake flow (device → cloud, cloud → device)
- 0x43/0x48: Device info flow (device → cloud, cloud → device)
- 0x73/0x7B: Data channel flow (cloud → device, device → cloud)
- 0x83/0x88: Status broadcast flow (device → cloud, cloud → device)
- 0xD3/0xD8: Heartbeat flow (device → cloud, cloud → device)
"""

from dataclasses import dataclass

# Packet Type Constants
# Handshake Flow
PACKET_TYPE_HANDSHAKE = 0x23  # Device → Cloud: Initial handshake with auth code
PACKET_TYPE_HELLO_ACK = 0x28  # Cloud → Device: Handshake acknowledgment

# Device Info Flow
PACKET_TYPE_DEVICE_INFO = 0x43  # Device → Cloud: Device information broadcast
PACKET_TYPE_INFO_ACK = 0x48  # Cloud → Device: Device info acknowledgment

# Data Channel Flow
PACKET_TYPE_DATA_CHANNEL = 0x73  # Cloud → Device: Command data packet (framed)
PACKET_TYPE_DATA_ACK = 0x7B  # Device → Cloud: Data command acknowledgment

# Status Broadcast Flow
PACKET_TYPE_STATUS_BROADCAST = 0x83  # Device → Cloud: Status update (framed)
PACKET_TYPE_STATUS_ACK = 0x88  # Cloud → Device: Status acknowledgment

# Heartbeat Flow
PACKET_TYPE_HEARTBEAT_DEVICE = 0xD3  # Device → Cloud: Heartbeat ping
PACKET_TYPE_HEARTBEAT_CLOUD = 0xD8  # Cloud → Device: Heartbeat response


@dataclass
class CyncPacket:
    """Base packet structure for all Cync protocol packets.

    All Cync packets share a common header structure:
    - Byte 0: Packet type (one of the PACKET_TYPE_* constants)
    - Bytes 1-2: Reserved (usually 0x00 0x00)
    - Bytes 3-4: Length field (multiplier * 256 + base)
    - Bytes 5+: Payload (varies by packet type)

    Attributes:
        packet_type: Packet type byte (0x23, 0x73, etc.)
        length: Payload length in bytes (from header bytes 3-4)
        payload: Raw payload bytes (header stripped)
        raw: Complete packet bytes including header

    """

    packet_type: int
    length: int
    payload: bytes
    raw: bytes


@dataclass
class CyncDataPacket(CyncPacket):
    """Data channel packet (0x73) with 0x7e framing and checksum.

    Data packets include additional fields for routing and validation:
    - endpoint: 5-byte device endpoint identifier (bytes[5:10])
    - msg_id: 2-byte wire protocol message ID (bytes[10:12])
    - data: Inner payload between 0x7e frame markers
    - checksum: Calculated checksum byte (sum % 256 between markers)
    - checksum_valid: Whether checksum validation passed

    Note: Byte 12 is padding (0x00), byte 13 is the 0x7e start marker.

    The data field is framed with 0x7e markers:
        0x7e [data bytes] [checksum] 0x7e

    Used for:
    - 0x73 (PACKET_TYPE_DATA_CHANNEL): Cloud → Device commands
    - 0x83 (PACKET_TYPE_STATUS_BROADCAST): Device → Cloud status updates
    """

    endpoint: bytes  # 5 bytes (bytes[5:10])
    msg_id: bytes  # 2 bytes - wire protocol message ID (bytes[10:12])
    data: bytes  # Inner payload (between 0x7e markers)
    checksum: int
    checksum_valid: bool
