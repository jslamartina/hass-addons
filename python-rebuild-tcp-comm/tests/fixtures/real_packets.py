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
    "HANDSHAKE_0x23_DEV_TO_CLOUD",
    "HELLO_ACK_0x28_CLOUD_TO_DEV",
    "STATUS_BROADCAST_0x83_DEV_TO_CLOUD",
    "STATUS_ACK_0x88_CLOUD_TO_DEV",
    "HEARTBEAT_DEV_0xD3_DEV_TO_CLOUD",
    "HEARTBEAT_CLOUD_0xD8_CLOUD_TO_DEV",
    "DEVICE_INFO_0x43_DEV_TO_CLOUD",
    "INFO_ACK_0x48_CLOUD_TO_DEV",
    "DEVICE_INFO_0x43_FRAMED_1",
    "DEVICE_INFO_0x43_FRAMED_2",
    "DEVICE_INFO_0x43_FRAMED_3",
    "STATUS_BROADCAST_0x83_FRAMED_4",
    "STATUS_BROADCAST_0x83_FRAMED_5",
    "STATUS_BROADCAST_0x83_FRAMED_6",
    "STATUS_BROADCAST_0x83_FRAMED_7",
    "STATUS_BROADCAST_0x83_FRAMED_8",
    "STATUS_BROADCAST_0x83_FRAMED_9",
    "STATUS_BROADCAST_0x83_FRAMED_10",
    "STATUS_BROADCAST_0x83_FRAMED_11",
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


# ============================================================================
# Additional Checksum Validation Fixtures (Phase 0.5 Deliverable #4)
# ============================================================================

# Device Info packets with 0x7e framing and checksums
DEVICE_INFO_0x43_FRAMED_1: bytes = bytes.fromhex(
    "43 00 00 00 1e 32 5d 53 17 01 01 06 c6 20 02 00 ab c5 20 02 00 04 c4 20 02 00 01 c3 20 02 00 05 c2 90 00 "
    "83 00 00 00 32 32 5d 53 17 00 01 00 00 00 00 00 00 fa 00 20 00 00 00 00 00 00 00 00 ea 00 00 00 86 01 00 "
    "30 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 c1 7e"
)
DEVICE_INFO_0x43_FRAMED_1_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:20:44.920590",
    device_id="32:5d:53:17",
    operation="device_info",
    notes="90-byte device info with 0x7e framing, checksum 0xc1"
)

DEVICE_INFO_0x43_FRAMED_2: bytes = bytes.fromhex(
    "43 00 00 00 1e 3d 54 66 a6 01 01 06 c6 20 02 00 ab c5 20 02 00 04 c4 20 02 00 01 c3 20 02 00 04 c2 90 00 "
    "83 00 00 00 32 3d 54 66 a6 00 01 00 00 00 00 00 00 fa 00 20 00 00 00 00 00 00 00 00 ea 00 00 00 86 01 00 "
    "30 00 31 35 38 00 00 00 00 00 00 00 00 00 00 00 00 00 5f 7e"
)
DEVICE_INFO_0x43_FRAMED_2_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:20:48.437312",
    device_id="3d:54:66:a6",
    operation="device_info",
    notes="90-byte device info with 0x7e framing, checksum 0x5f, different endpoint"
)

DEVICE_INFO_0x43_FRAMED_3: bytes = bytes.fromhex(
    "43 00 00 00 1e 45 88 0d 50 01 01 06 c6 20 02 00 ab c5 20 02 00 04 c4 20 02 00 01 c3 20 02 00 04 c2 90 00 "
    "83 00 00 00 32 45 88 0d 50 00 01 00 00 00 00 00 00 fa 00 20 00 00 00 00 00 00 00 00 ea 00 00 00 86 01 00 "
    "30 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 c1 7e"
)
DEVICE_INFO_0x43_FRAMED_3_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:20:59.868595",
    device_id="45:88:0d:50",
    operation="device_info",
    notes="90-byte device info with 0x7e framing, checksum 0xc1 (same as FRAMED_1), different endpoint"
)

# Status Broadcast packets with diverse endpoints and checksums
STATUS_BROADCAST_0x83_FRAMED_4: bytes = bytes.fromhex(
    "83 00 00 00 26 3d 54 6d e6 00 09 00 7e 1f 00 00 00 fa db 14 00 95 2b 00 1a 00 ff ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 8c 7e"
)
STATUS_BROADCAST_0x83_FRAMED_4_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:24:00.900807",
    device_id="3d:54:6d:e6",
    operation="status_broadcast",
    notes="43-byte status broadcast with checksum 0x8c"
)

STATUS_BROADCAST_0x83_FRAMED_5: bytes = bytes.fromhex(
    "83 00 00 00 26 32 5d 3e ad 00 0d 00 7e 1f 00 00 00 fa db 14 00 51 2c 00 1a 00 ff ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 49 7e"
)
STATUS_BROADCAST_0x83_FRAMED_5_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:24:00.917160",
    device_id="32:5d:3e:ad",
    operation="status_broadcast",
    notes="43-byte status broadcast with checksum 0x49"
)

STATUS_BROADCAST_0x83_FRAMED_6: bytes = bytes.fromhex(
    "83 00 00 00 26 60 b1 74 37 00 0d 00 7e 1f 00 00 00 fa db 14 00 4a 2e 00 1a 00 ff ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 44 7e"
)
STATUS_BROADCAST_0x83_FRAMED_6_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:24:00.986016",
    device_id="60:b1:74:37",
    operation="status_broadcast",
    notes="43-byte status broadcast with checksum 0x44"
)

STATUS_BROADCAST_0x83_FRAMED_7: bytes = bytes.fromhex(
    "83 00 00 00 26 60 b1 7a 37 00 0a 00 7e 1f 00 00 00 fa db 14 00 15 2e 00 1a 00 ff ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 0f 7e"
)
STATUS_BROADCAST_0x83_FRAMED_7_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:24:00.989269",
    device_id="60:b1:7a:37",
    operation="status_broadcast",
    notes="43-byte status broadcast with checksum 0x0f"
)

STATUS_BROADCAST_0x83_FRAMED_8: bytes = bytes.fromhex(
    "83 00 00 00 26 60 b1 7c b4 00 0d 00 7e 1f 00 00 00 fa db 14 00 01 2e 00 1a 00 ff ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 fb 7e"
)
STATUS_BROADCAST_0x83_FRAMED_8_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:24:01.000025",
    device_id="60:b1:7c:b4",
    operation="status_broadcast",
    notes="43-byte status broadcast with checksum 0xfb"
)

STATUS_BROADCAST_0x83_FRAMED_9: bytes = bytes.fromhex(
    "83 00 00 00 26 60 b1 8e 42 00 10 00 7e 24 00 00 00 fa db 14 00 f6 2d 00 1a 00 ff ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 ef 7e"
)
STATUS_BROADCAST_0x83_FRAMED_9_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:24:01.015140",
    device_id="60:b1:8e:42",
    operation="status_broadcast",
    notes="43-byte status broadcast with checksum 0xef"
)

STATUS_BROADCAST_0x83_FRAMED_10: bytes = bytes.fromhex(
    "83 00 00 00 26 38 e8 ee 97 00 0d 00 7e 1f 00 00 00 fa db 14 00 05 2c 00 1a 00 ff ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 fd 7e"
)
STATUS_BROADCAST_0x83_FRAMED_10_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:24:01.018870",
    device_id="38:e8:ee:97",
    operation="status_broadcast",
    notes="43-byte status broadcast with checksum 0xfd, different endpoint"
)

STATUS_BROADCAST_0x83_FRAMED_11: bytes = bytes.fromhex(
    "83 00 00 00 26 38 e8 dd 4d 00 14 00 7e 1f 00 00 00 fa db 14 00 aa 2b 00 1a 00 ff ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 a1 7e"
)
STATUS_BROADCAST_0x83_FRAMED_11_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:24:01.017582",
    device_id="38:e8:dd:4d",
    operation="status_broadcast",
    notes="43-byte status broadcast with checksum 0xa1"
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
    # Checksum validation fixtures
    "DEVICE_INFO_0x43_FRAMED_1": DEVICE_INFO_0x43_FRAMED_1_METADATA,
    "DEVICE_INFO_0x43_FRAMED_2": DEVICE_INFO_0x43_FRAMED_2_METADATA,
    "DEVICE_INFO_0x43_FRAMED_3": DEVICE_INFO_0x43_FRAMED_3_METADATA,
    "STATUS_BROADCAST_0x83_FRAMED_4": STATUS_BROADCAST_0x83_FRAMED_4_METADATA,
    "STATUS_BROADCAST_0x83_FRAMED_5": STATUS_BROADCAST_0x83_FRAMED_5_METADATA,
    "STATUS_BROADCAST_0x83_FRAMED_6": STATUS_BROADCAST_0x83_FRAMED_6_METADATA,
    "STATUS_BROADCAST_0x83_FRAMED_7": STATUS_BROADCAST_0x83_FRAMED_7_METADATA,
    "STATUS_BROADCAST_0x83_FRAMED_8": STATUS_BROADCAST_0x83_FRAMED_8_METADATA,
    "STATUS_BROADCAST_0x83_FRAMED_9": STATUS_BROADCAST_0x83_FRAMED_9_METADATA,
    "STATUS_BROADCAST_0x83_FRAMED_10": STATUS_BROADCAST_0x83_FRAMED_10_METADATA,
    "STATUS_BROADCAST_0x83_FRAMED_11": STATUS_BROADCAST_0x83_FRAMED_11_METADATA,
}
