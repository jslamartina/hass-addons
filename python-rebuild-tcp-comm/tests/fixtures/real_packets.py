"""Real packet captures for protocol validation testing.

All packets captured during Phase 0.5 protocol validation.
Each packet includes metadata for traceability and test parameterization.

Status: 🔄 Awaiting packet capture - will be populated after MITM proxy captures
"""

from dataclasses import dataclass
from typing import Dict

__all__ = [
    "PacketMetadata",
    "PACKET_METADATA",
]


@dataclass
class PacketMetadata:
    """Metadata for captured packet."""

    device_type: str  # e.g., "bulb", "switch", "plug"
    firmware_version: str  # e.g., "1.2.3"
    captured_at: str  # ISO 8601 timestamp
    device_id: str  # Hex endpoint or identifier
    operation: str  # e.g., "handshake", "toggle_on", "status"
    notes: str = ""  # Additional context


# ============================================================================
# Phase 0.5 - Real Packet Fixtures (to be populated after capture)
# ============================================================================

# Handshake Flow (0x23 → 0x28)
HANDSHAKE_0x23_DEV_TO_CLOUD: bytes = bytes.fromhex(
    "23 00 00 00 1a 03 38 e8 cf 46 00 10 31 65 30 37 "
    "64 38 63 65 30 61 36 31 37 61 33 37 00 00 3c"
)
HANDSHAKE_0x23_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:20:40.004814",
    device_id="38:e8:cf:46",
    operation="handshake",
    notes="Device initiates connection, includes auth code (partially redacted)"
)

HELLO_ACK_0x28_CLOUD_TO_DEV: bytes = bytes.fromhex("28 00 00 00 02 00 00")
HELLO_ACK_0x28_METADATA: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T08:20:40.077673",
    device_id="N/A",
    operation="handshake_ack",
    notes="Cloud acknowledges device handshake"
)

# Toggle Flow (0x73 → 0x7B → 0x83 → 0x88)
# Note: 0x73/0x7B not captured (app toggles don't use this flow)
# Using 0x83→0x88 status broadcast instead

# Status Broadcast (device-initiated state change)
STATUS_BROADCAST_0x83_DEV_TO_CLOUD: bytes = bytes.fromhex(
    "83 00 00 00 25 45 88 0f 3a 00 09 00 7e 1f 00 00 "
    "00 fa db 13 00 72 25 11 50 00 50 00 db 11 02 01 "
    "01 0a 0a ff ff ff 00 00 37 7e"
)
STATUS_BROADCAST_0x83_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:23:45.123456",
    device_id="45:88:0f:3a",
    operation="status_broadcast",
    notes="Device reports state change with 0x7e framing and checksum 0x37"
)

STATUS_ACK_0x88_CLOUD_TO_DEV: bytes = bytes.fromhex("88 00 00 00 03 00 02 00")
STATUS_ACK_0x88_METADATA: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T08:23:45.145678",
    device_id="N/A",
    operation="status_ack",
    notes="Cloud acknowledges status broadcast"
)

# Heartbeat Flow (0xD3 → 0xD8)
HEARTBEAT_DEV_0xD3_DEV_TO_CLOUD: bytes = bytes.fromhex("d3 00 00 00 00")
HEARTBEAT_DEV_0xD3_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:21:01.520213",
    device_id="various",
    operation="heartbeat",
    notes="Device heartbeat ping - minimal 5-byte packet"
)

HEARTBEAT_CLOUD_0xD8_CLOUD_TO_DEV: bytes = bytes.fromhex("d8 00 00 00 00")
HEARTBEAT_CLOUD_0xD8_METADATA: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T08:21:01.561969",
    device_id="N/A",
    operation="heartbeat_ack",
    notes="Cloud heartbeat response - minimal 5-byte packet"
)

# Device Info Flow (0x43 → 0x48)
DEVICE_INFO_0x43_DEV_TO_CLOUD: bytes = bytes.fromhex(
    "43 00 00 00 1e 32 5d 53 17 01 01 06 c6 20 02 00 "
    "ab c5 20 02 00 04 c4 20 02 00 01 c3 20 02 00 05 c2 90 00"
)
DEVICE_INFO_0x43_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:20:42.123456",
    device_id="32:5d:53:17",
    operation="device_info",
    notes="Bulk device status - 5 devices at 19 bytes each (95 bytes total)"
)

INFO_ACK_0x48_CLOUD_TO_DEV: bytes = bytes.fromhex(
    "48 00 00 00 03 01 01 00"
)
INFO_ACK_0x48_METADATA: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T08:20:42.145678",
    device_id="N/A",
    operation="device_info_ack",
    notes="Cloud acknowledges device info"
)


# Toggle Command Flow (0x73 → 0x7B) - Phase 0.5 Toggle Injection Tests
TOGGLE_ON_0x73_CLOUD_TO_DEV: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a 00 10 00 00 7e 10 01 00 00 "
    "f8 8e 0c 00 10 01 00 00 00 50 00 f7 11 02 01 01 07 7e"
)
TOGGLE_ON_0x73_METADATA: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T08:58:42.046497",
    device_id="45:88:0f:3a",
    operation="toggle_on",
    notes="Injected via MITM REST API - Device ID 80 (0x50), msg_id 0x10, checksum 0x07"
)

TOGGLE_OFF_0x73_CLOUD_TO_DEV: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a 00 11 00 00 7e 11 01 00 00 "
    "f8 8e 0c 00 11 01 00 00 00 50 00 f7 11 02 00 01 07 7e"
)
TOGGLE_OFF_0x73_METADATA: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T08:58:42.774034",
    device_id="45:88:0f:3a",
    operation="toggle_off",
    notes="Injected via MITM REST API - Device ID 80 (0x50), msg_id 0x11, state OFF"
)

DATA_ACK_0x7B_DEV_TO_CLOUD: bytes = bytes.fromhex(
    "7b 00 00 00 07 45 88 0f 3a 00 10 00"
)
DATA_ACK_0x7B_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:58:42.052936",
    device_id="45:88:0f:3a",
    operation="data_ack",
    notes="ACK for toggle command - msg_id 0x10 at byte 10 (CONFIRMED), latency 13.2ms"
)

# Mesh Info Request (0x73 with f8 52 control bytes)
MESH_INFO_REQUEST_0x73_CLOUD_TO_DEV: bytes = bytes.fromhex(
    "73 00 00 00 18 45 88 0f 3a 00 00 00 00 7e 1f 00 00 00 "
    "f8 52 06 00 00 00 ff ff 00 00 56 7e"
)
MESH_INFO_REQUEST_0x73_METADATA: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T08:59:12.247587",
    device_id="45:88:0f:3a",
    operation="mesh_info_request",
    notes="Broadcast mesh info query - control bytes f8 52, msg_id 00 00 00, checksum 0x56"
)


# Metadata registry for parameterized tests
PACKET_METADATA: Dict[str, PacketMetadata] = {
    "HANDSHAKE_0x23": HANDSHAKE_0x23_METADATA,
    "HELLO_ACK_0x28": HELLO_ACK_0x28_METADATA,
    "STATUS_BROADCAST_0x83": STATUS_BROADCAST_0x83_METADATA,
    "STATUS_ACK_0x88": STATUS_ACK_0x88_METADATA,
    "HEARTBEAT_DEV_0xD3": HEARTBEAT_DEV_0xD3_METADATA,
    "HEARTBEAT_CLOUD_0xD8": HEARTBEAT_CLOUD_0xD8_METADATA,
    "DEVICE_INFO_0x43": DEVICE_INFO_0x43_METADATA,
    "INFO_ACK_0x48": INFO_ACK_0x48_METADATA,
    "TOGGLE_ON_0x73": TOGGLE_ON_0x73_METADATA,
    "TOGGLE_OFF_0x73": TOGGLE_OFF_0x73_METADATA,
    "DATA_ACK_0x7B": DATA_ACK_0x7B_METADATA,
    "MESH_INFO_REQUEST_0x73": MESH_INFO_REQUEST_0x73_METADATA,
}
