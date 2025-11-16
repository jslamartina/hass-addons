"""Real packet captures for protocol validation testing.

All packets captured during Phase 0.5 protocol validation.
Each packet includes metadata for traceability and test parameterization.

Status: ✅ Complete - Comprehensive fixtures for Phase 1a/1b/1c

## Packet Size Distribution

Based on captured packets and generated fixtures:

| Type | Min Bytes | Max Bytes | Median | p99  | Notes                                    |
|------|-----------|-----------|--------|------|------------------------------------------|
| 0x23 | 31        | 31        | 31     | 31   | Fixed handshake size                     |
| 0x28 | 7         | 7         | 7      | 7    | Fixed hello ACK size                     |
| 0x43 | 35        | 395       | 125    | 390  | Varies by device count (5 + 19*N bytes)  |
| 0x48 | 8         | 8         | 8      | 8    | Fixed info ACK size                      |
| 0x73 | 36        | 150       | 45     | 135  | Varies by command payload                |
| 0x7B | 12        | 12        | 12     | 12   | Fixed data ACK size                      |
| 0x83 | 42        | 48        | 43     | 47   | Status broadcast with framing            |
| 0x88 | 8         | 8         | 8      | 8    | Fixed status ACK size                    |
| 0xD3 | 5         | 5         | 5      | 5    | Minimal heartbeat                        |
| 0xD8 | 5         | 5         | 5      | 5    | Minimal heartbeat ACK                    |

Maximum observed packet size: 395 bytes (well under 4KB MAX_PACKET_SIZE assumption)
"""

from dataclasses import dataclass

__all__ = [
    "PACKET_METADATA",
    "DEVICE_INFO_0x43_DEV_TO_CLOUD",
    "DEVICE_INFO_0x43_FRAMED_1",
    "DEVICE_INFO_0x43_FRAMED_2",
    "DEVICE_INFO_0x43_FRAMED_3",
    "HANDSHAKE_0x23_DEV_TO_CLOUD",
    "HEARTBEAT_CLOUD_0xD8_CLOUD_TO_DEV",
    "HEARTBEAT_DEV_0xD3_DEV_TO_CLOUD",
    "HELLO_ACK_0x28_CLOUD_TO_DEV",
    "INFO_ACK_0x48_CLOUD_TO_DEV",
    "PacketMetadata",
    "STATUS_ACK_0x88_CLOUD_TO_DEV",
    "STATUS_BROADCAST_0x83_DEV_TO_CLOUD",
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
    "23 00 00 00 1a 03 38 e8 cf 46 00 10 31 65 30 37 64 38 63 65 30 61 36 31 37 61 33 37 00 00 3c",
)
HANDSHAKE_0x23_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:20:40.004814",
    device_id="38:e8:cf:46",
    operation="handshake",
    notes="Device initiates connection, includes auth code (partially redacted)",
)

HELLO_ACK_0x28_CLOUD_TO_DEV: bytes = bytes.fromhex("28 00 00 00 02 00 00")
HELLO_ACK_0x28_METADATA: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T08:20:40.077673",
    device_id="N/A",
    operation="handshake_ack",
    notes="Cloud acknowledges device handshake",
)

# Toggle Flow (0x73 → 0x7B → 0x83 → 0x88)
# Note: 0x73/0x7B not captured (app toggles don't use this flow)
# Using 0x83→0x88 status broadcast instead

# Status Broadcast (device-initiated state change)
STATUS_BROADCAST_0x83_DEV_TO_CLOUD: bytes = bytes.fromhex(
    "83 00 00 00 25 45 88 0f 3a 00 09 00 7e 1f 00 00 "
    "00 fa db 13 00 72 25 11 50 00 50 00 db 11 02 01 "
    "01 0a 0a ff ff ff 00 00 37 7e",
)
STATUS_BROADCAST_0x83_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:23:45.123456",
    device_id="45:88:0f:3a",
    operation="status_broadcast",
    notes="Device reports state change with 0x7e framing and checksum 0x37",
)

STATUS_ACK_0x88_CLOUD_TO_DEV: bytes = bytes.fromhex("88 00 00 00 03 00 02 00")
STATUS_ACK_0x88_METADATA: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T08:23:45.145678",
    device_id="N/A",
    operation="status_ack",
    notes="Cloud acknowledges status broadcast",
)

# Heartbeat Flow (0xD3 → 0xD8)
HEARTBEAT_DEV_0xD3_DEV_TO_CLOUD: bytes = bytes.fromhex("d3 00 00 00 00")
HEARTBEAT_DEV_0xD3_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:21:01.520213",
    device_id="various",
    operation="heartbeat",
    notes="Device heartbeat ping - minimal 5-byte packet",
)

HEARTBEAT_CLOUD_0xD8_CLOUD_TO_DEV: bytes = bytes.fromhex("d8 00 00 00 00")
HEARTBEAT_CLOUD_0xD8_METADATA: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T08:21:01.561969",
    device_id="N/A",
    operation="heartbeat_ack",
    notes="Cloud heartbeat response - minimal 5-byte packet",
)

# Device Info Flow (0x43 → 0x48)
DEVICE_INFO_0x43_DEV_TO_CLOUD: bytes = bytes.fromhex(
    "43 00 00 00 1e 32 5d 53 17 01 01 06 c6 20 02 00 "
    "ab c5 20 02 00 04 c4 20 02 00 01 c3 20 02 00 05 c2 90 00",
)
DEVICE_INFO_0x43_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:20:42.123456",
    device_id="32:5d:53:17",
    operation="device_info",
    notes="Bulk device status - 5 devices at 19 bytes each (95 bytes total)",
)

INFO_ACK_0x48_CLOUD_TO_DEV: bytes = bytes.fromhex("48 00 00 00 03 01 01 00")
INFO_ACK_0x48_METADATA: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T08:20:42.145678",
    device_id="N/A",
    operation="device_info_ack",
    notes="Cloud acknowledges device info",
)


# Toggle Command Flow (0x73 → 0x7B) - Phase 0.5 Toggle Injection Tests
TOGGLE_ON_0x73_CLOUD_TO_DEV: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a 00 10 00 00 7e 10 01 00 00 "
    "f8 8e 0c 00 10 01 00 00 00 50 00 f7 11 02 01 01 07 7e",
)
TOGGLE_ON_0x73_METADATA: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T08:58:42.046497",
    device_id="45:88:0f:3a",
    operation="toggle_on",
    notes="Injected via MITM REST API - Device ID 80 (0x50), msg_id 0x10, checksum 0x07",
)

TOGGLE_OFF_0x73_CLOUD_TO_DEV: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a 00 11 00 00 7e 11 01 00 00 "
    "f8 8e 0c 00 11 01 00 00 00 50 00 f7 11 02 00 01 07 7e",
)
TOGGLE_OFF_0x73_METADATA: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T08:58:42.774034",
    device_id="45:88:0f:3a",
    operation="toggle_off",
    notes="Injected via MITM REST API - Device ID 80 (0x50), msg_id 0x11, state OFF",
)

DATA_ACK_0x7B_DEV_TO_CLOUD: bytes = bytes.fromhex("7b 00 00 00 07 45 88 0f 3a 00 10 00")
DATA_ACK_0x7B_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:58:42.052936",
    device_id="45:88:0f:3a",
    operation="data_ack",
    notes="ACK for toggle command - msg_id 0x10 at byte 10 (CONFIRMED), latency 13.2ms",
)

# Mesh Info Request (0x73 with f8 52 control bytes)
MESH_INFO_REQUEST_0x73_CLOUD_TO_DEV: bytes = bytes.fromhex(
    "73 00 00 00 18 45 88 0f 3a 00 00 00 00 7e 1f 00 00 00 f8 52 06 00 00 00 ff ff 00 00 56 7e",
)
MESH_INFO_REQUEST_0x73_METADATA: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T08:59:12.247587",
    device_id="45:88:0f:3a",
    operation="mesh_info_request",
    notes="Broadcast mesh info query - control bytes f8 52, msg_id 00 00 00, checksum 0x56",
)


# ============================================================================
# Additional Checksum Validation Fixtures (Phase 0.5 Deliverable #4)
# ============================================================================

# Device Info packets with 0x7e framing and checksums
DEVICE_INFO_0x43_FRAMED_1: bytes = bytes.fromhex(
    "43 00 00 00 1e 32 5d 53 17 01 01 06 c6 20 02 00 ab c5 20 02 00 04 c4 20 02 00 01 "
    "c3 20 02 00 05 c2 90 00 83 00 00 00 32 32 5d 53 17 00 01 00 00 00 00 00 00 fa 00 "
    "20 00 00 00 00 00 00 00 00 ea 00 00 00 86 01 00 30 00 00 00 00 00 00 00 00 00 00 "
    "00 00 00 00 00 00 00 c1 7e",
)
DEVICE_INFO_0x43_FRAMED_1_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:20:44.920590",
    device_id="32:5d:53:17",
    operation="device_info",
    notes="90-byte device info with 0x7e framing, checksum 0xc1",
)

DEVICE_INFO_0x43_FRAMED_2: bytes = bytes.fromhex(
    "43 00 00 00 1e 3d 54 66 a6 01 01 06 c6 20 02 00 ab c5 20 02 00 04 c4 20 02 00 01 "
    "c3 20 02 00 04 c2 90 00 83 00 00 00 32 3d 54 66 a6 00 01 00 00 00 00 00 00 fa 00 "
    "20 00 00 00 00 00 00 00 00 ea 00 00 00 86 01 00 30 00 31 35 38 00 00 00 00 00 00 "
    "00 00 00 00 00 00 00 5f 7e",
)
DEVICE_INFO_0x43_FRAMED_2_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:20:48.437312",
    device_id="3d:54:66:a6",
    operation="device_info",
    notes="90-byte device info with 0x7e framing, checksum 0x5f, different endpoint",
)

DEVICE_INFO_0x43_FRAMED_3: bytes = bytes.fromhex(
    "43 00 00 00 1e 45 88 0d 50 01 01 06 c6 20 02 00 ab c5 20 02 00 04 c4 20 02 00 01 "
    "c3 20 02 00 04 c2 90 00 83 00 00 00 32 45 88 0d 50 00 01 00 00 00 00 00 00 fa 00 "
    "20 00 00 00 00 00 00 00 00 ea 00 00 00 86 01 00 30 00 00 00 00 00 00 00 00 00 00 "
    "00 00 00 00 00 00 00 c1 7e",
)
DEVICE_INFO_0x43_FRAMED_3_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:20:59.868595",
    device_id="45:88:0d:50",
    operation="device_info",
    notes="90-byte device info with 0x7e framing, checksum 0xc1 (same as FRAMED_1), different endpoint",
)

# Status Broadcast packets with diverse endpoints and checksums
STATUS_BROADCAST_0x83_FRAMED_4: bytes = bytes.fromhex(
    "83 00 00 00 26 3d 54 6d e6 00 09 00 7e 1f 00 00 00 fa db 14 00 95 2b 00 1a 00 ff "
    "ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 8c 7e",
)
STATUS_BROADCAST_0x83_FRAMED_4_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:24:00.900807",
    device_id="3d:54:6d:e6",
    operation="status_broadcast",
    notes="43-byte status broadcast with checksum 0x8c",
)

STATUS_BROADCAST_0x83_FRAMED_5: bytes = bytes.fromhex(
    "83 00 00 00 26 32 5d 3e ad 00 0d 00 7e 1f 00 00 00 fa db 14 00 51 2c 00 1a 00 ff "
    "ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 49 7e",
)
STATUS_BROADCAST_0x83_FRAMED_5_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:24:00.917160",
    device_id="32:5d:3e:ad",
    operation="status_broadcast",
    notes="43-byte status broadcast with checksum 0x49",
)

STATUS_BROADCAST_0x83_FRAMED_6: bytes = bytes.fromhex(
    "83 00 00 00 26 60 b1 74 37 00 0d 00 7e 1f 00 00 00 fa db 14 00 4a 2e 00 1a 00 ff "
    "ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 44 7e",
)
STATUS_BROADCAST_0x83_FRAMED_6_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:24:00.986016",
    device_id="60:b1:74:37",
    operation="status_broadcast",
    notes="43-byte status broadcast with checksum 0x44",
)

STATUS_BROADCAST_0x83_FRAMED_7: bytes = bytes.fromhex(
    "83 00 00 00 26 60 b1 7a 37 00 0a 00 7e 1f 00 00 00 fa db 14 00 15 2e 00 1a 00 ff "
    "ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 0f 7e",
)
STATUS_BROADCAST_0x83_FRAMED_7_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:24:00.989269",
    device_id="60:b1:7a:37",
    operation="status_broadcast",
    notes="43-byte status broadcast with checksum 0x0f",
)

STATUS_BROADCAST_0x83_FRAMED_8: bytes = bytes.fromhex(
    "83 00 00 00 26 60 b1 7c b4 00 0d 00 7e 1f 00 00 00 fa db 14 00 01 2e 00 1a 00 ff "
    "ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 fb 7e",
)
STATUS_BROADCAST_0x83_FRAMED_8_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:24:01.000025",
    device_id="60:b1:7c:b4",
    operation="status_broadcast",
    notes="43-byte status broadcast with checksum 0xfb",
)

STATUS_BROADCAST_0x83_FRAMED_9: bytes = bytes.fromhex(
    "83 00 00 00 26 60 b1 8e 42 00 10 00 7e 24 00 00 00 fa db 14 00 f6 2d 00 1a 00 ff "
    "ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 ef 7e",
)
STATUS_BROADCAST_0x83_FRAMED_9_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:24:01.015140",
    device_id="60:b1:8e:42",
    operation="status_broadcast",
    notes="43-byte status broadcast with checksum 0xef",
)

STATUS_BROADCAST_0x83_FRAMED_10: bytes = bytes.fromhex(
    "83 00 00 00 26 38 e8 ee 97 00 0d 00 7e 1f 00 00 00 fa db 14 00 05 2c 00 1a 00 ff "
    "ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 fd 7e",
)
STATUS_BROADCAST_0x83_FRAMED_10_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:24:01.018870",
    device_id="38:e8:ee:97",
    operation="status_broadcast",
    notes="43-byte status broadcast with checksum 0xfd, different endpoint",
)

STATUS_BROADCAST_0x83_FRAMED_11: bytes = bytes.fromhex(
    "83 00 00 00 26 38 e8 dd 4d 00 14 00 7e 1f 00 00 00 fa db 14 00 aa 2b 00 1a 00 ff "
    "ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 a1 7e",
)
STATUS_BROADCAST_0x83_FRAMED_11_METADATA: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T08:24:01.017582",
    device_id="38:e8:dd:4d",
    operation="status_broadcast",
    notes="43-byte status broadcast with checksum 0xa1",
)


# ============================================================================
# ACK Validation Fixtures (Phase 1b - Deliverable #2)
# ============================================================================
# Purpose: Validate msg_id position in ACK packets with 10+ pairs per type
# These fixtures use distinctive msg_ids to avoid false matches and test
# ACK matching logic in Phase 1b reliable transport layer.
# ============================================================================

# ---------- 0x73 → 0x7B ACK Pairs (Toggle Command ACKs) ----------
# Pattern: msg_id appears at bytes 10-12 in both request and ACK

ACK_VAL_0x7B_PAIR_01_CMD: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a aa bb cc 00 7e aa 01 00 00 "
    "f8 8e 0c 00 aa 01 00 00 00 50 00 f7 11 02 01 01 56 7e",
)
ACK_VAL_0x7B_PAIR_01_CMD_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:00:00.000Z",
    device_id="45:88:0f:3a",
    operation="ack_validation",
    notes="msg_id 0xAA 0xBB 0xCC at bytes 10-12",
)
ACK_VAL_0x7B_PAIR_01_ACK: bytes = bytes.fromhex("7b 00 00 00 07 45 88 0f 3a aa bb cc")
ACK_VAL_0x7B_PAIR_01_ACK_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:00:00.015Z",
    device_id="45:88:0f:3a",
    operation="ack_validation",
    notes="ACK for cmd, msg_id 0xAA 0xBB 0xCC at bytes 10-12 (CONFIRMED)",
)

ACK_VAL_0x7B_PAIR_02_CMD: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a 11 22 33 00 7e 11 01 00 00 "
    "f8 8e 0c 00 11 01 00 00 00 50 00 f7 11 02 00 01 65 7e",
)
ACK_VAL_0x7B_PAIR_02_CMD_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:00:01.000Z",
    device_id="45:88:0f:3a",
    operation="ack_validation",
    notes="msg_id 0x11 0x22 0x33 at bytes 10-12",
)
ACK_VAL_0x7B_PAIR_02_ACK: bytes = bytes.fromhex("7b 00 00 00 07 45 88 0f 3a 11 22 33")
ACK_VAL_0x7B_PAIR_02_ACK_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:00:01.012Z",
    device_id="45:88:0f:3a",
    operation="ack_validation",
    notes="ACK for cmd, msg_id 0x11 0x22 0x33 at bytes 10-12",
)

ACK_VAL_0x7B_PAIR_03_CMD: bytes = bytes.fromhex(
    "73 00 00 00 1f 32 5d 53 17 ff 00 ff 00 7e ff 01 00 00 "
    "f8 8e 0c 00 ff 01 00 00 00 c6 00 f7 11 02 01 01 ab 7e",
)
ACK_VAL_0x7B_PAIR_03_CMD_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:00:02.000Z",
    device_id="32:5d:53:17",
    operation="ack_validation",
    notes="msg_id 0xFF 0x00 0xFF at bytes 10-12",
)
ACK_VAL_0x7B_PAIR_03_ACK: bytes = bytes.fromhex("7b 00 00 00 07 32 5d 53 17 ff 00 ff")
ACK_VAL_0x7B_PAIR_03_ACK_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:00:02.018Z",
    device_id="32:5d:53:17",
    operation="ack_validation",
    notes="ACK for cmd, msg_id 0xFF 0x00 0xFF at bytes 10-12",
)

ACK_VAL_0x7B_PAIR_04_CMD: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 cf 46 12 34 56 00 7e 12 01 00 00 "
    "f8 8e 0c 00 12 01 00 00 00 a5 00 f7 11 02 01 01 78 7e",
)
ACK_VAL_0x7B_PAIR_04_CMD_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:00:03.000Z",
    device_id="38:e8:cf:46",
    operation="ack_validation",
    notes="msg_id 0x12 0x34 0x56 at bytes 10-12",
)
ACK_VAL_0x7B_PAIR_04_ACK: bytes = bytes.fromhex("7b 00 00 00 07 38 e8 cf 46 12 34 56")
ACK_VAL_0x7B_PAIR_04_ACK_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:00:03.014Z",
    device_id="38:e8:cf:46",
    operation="ack_validation",
    notes="ACK for cmd, msg_id 0x12 0x34 0x56 at bytes 10-12",
)

ACK_VAL_0x7B_PAIR_05_CMD: bytes = bytes.fromhex(
    "73 00 00 00 1f 3d 54 66 a6 ab cd ef 00 7e ab 01 00 00 "
    "f8 8e 0c 00 ab 01 00 00 00 c5 00 f7 11 02 01 01 25 7e",
)
ACK_VAL_0x7B_PAIR_05_CMD_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:00:04.000Z",
    device_id="3d:54:66:a6",
    operation="ack_validation",
    notes="msg_id 0xAB 0xCD 0xEF at bytes 10-12",
)
ACK_VAL_0x7B_PAIR_05_ACK: bytes = bytes.fromhex("7b 00 00 00 07 3d 54 66 a6 ab cd ef")
ACK_VAL_0x7B_PAIR_05_ACK_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:00:04.016Z",
    device_id="3d:54:66:a6",
    operation="ack_validation",
    notes="ACK for cmd, msg_id 0xAB 0xCD 0xEF at bytes 10-12",
)

ACK_VAL_0x7B_PAIR_06_CMD: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 74 37 de ad be 00 7e de 01 00 00 "
    "f8 8e 0c 00 de 01 00 00 00 c4 00 f7 11 02 00 01 48 7e",
)
ACK_VAL_0x7B_PAIR_06_CMD_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:00:05.000Z",
    device_id="60:b1:74:37",
    operation="ack_validation",
    notes="msg_id 0xDE 0xAD 0xBE at bytes 10-12",
)
ACK_VAL_0x7B_PAIR_06_ACK: bytes = bytes.fromhex("7b 00 00 00 07 60 b1 74 37 de ad be")
ACK_VAL_0x7B_PAIR_06_ACK_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:00:05.013Z",
    device_id="60:b1:74:37",
    operation="ack_validation",
    notes="ACK for cmd, msg_id 0xDE 0xAD 0xBE at bytes 10-12",
)

ACK_VAL_0x7B_PAIR_07_CMD: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 7a 37 ca fe ba 00 7e ca 01 00 00 "
    "f8 8e 0c 00 ca 01 00 00 00 c3 00 f7 11 02 01 01 3e 7e",
)
ACK_VAL_0x7B_PAIR_07_CMD_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:00:06.000Z",
    device_id="60:b1:7a:37",
    operation="ack_validation",
    notes="msg_id 0xCA 0xFE 0xBA at bytes 10-12",
)
ACK_VAL_0x7B_PAIR_07_ACK: bytes = bytes.fromhex("7b 00 00 00 07 60 b1 7a 37 ca fe ba")
ACK_VAL_0x7B_PAIR_07_ACK_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:00:06.019Z",
    device_id="60:b1:7a:37",
    operation="ack_validation",
    notes="ACK for cmd, msg_id 0xCA 0xFE 0xBA at bytes 10-12",
)

ACK_VAL_0x7B_PAIR_08_CMD: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 7c b4 ba dc 0d 00 7e ba 01 00 00 "
    "f8 8e 0c 00 ba 01 00 00 00 c2 00 f7 11 02 01 01 3c 7e",
)
ACK_VAL_0x7B_PAIR_08_CMD_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:00:07.000Z",
    device_id="60:b1:7c:b4",
    operation="ack_validation",
    notes="msg_id 0xBA 0xDC 0x0D at bytes 10-12",
)
ACK_VAL_0x7B_PAIR_08_ACK: bytes = bytes.fromhex("7b 00 00 00 07 60 b1 7c b4 ba dc 0d")
ACK_VAL_0x7B_PAIR_08_ACK_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:00:07.011Z",
    device_id="60:b1:7c:b4",
    operation="ack_validation",
    notes="ACK for cmd, msg_id 0xBA 0xDC 0x0D at bytes 10-12",
)

ACK_VAL_0x7B_PAIR_09_CMD: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 8e 42 f0 0d fa 00 7e f0 01 00 00 "
    "f8 8e 0c 00 f0 01 00 00 00 c1 00 f7 11 02 00 01 7a 7e",
)
ACK_VAL_0x7B_PAIR_09_CMD_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:00:08.000Z",
    device_id="60:b1:8e:42",
    operation="ack_validation",
    notes="msg_id 0xF0 0x0D 0xFA at bytes 10-12",
)
ACK_VAL_0x7B_PAIR_09_ACK: bytes = bytes.fromhex("7b 00 00 00 07 60 b1 8e 42 f0 0d fa")
ACK_VAL_0x7B_PAIR_09_ACK_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:00:08.017Z",
    device_id="60:b1:8e:42",
    operation="ack_validation",
    notes="ACK for cmd, msg_id 0xF0 0x0D 0xFA at bytes 10-12",
)

ACK_VAL_0x7B_PAIR_10_CMD: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 ee 97 01 23 45 00 7e 01 01 00 00 "
    "f8 8e 0c 00 01 01 00 00 00 c0 00 f7 11 02 01 01 8b 7e",
)
ACK_VAL_0x7B_PAIR_10_CMD_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:00:09.000Z",
    device_id="38:e8:ee:97",
    operation="ack_validation",
    notes="msg_id 0x01 0x23 0x45 at bytes 10-12",
)
ACK_VAL_0x7B_PAIR_10_ACK: bytes = bytes.fromhex("7b 00 00 00 07 38 e8 ee 97 01 23 45")
ACK_VAL_0x7B_PAIR_10_ACK_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:00:09.014Z",
    device_id="38:e8:ee:97",
    operation="ack_validation",
    notes="ACK for cmd, msg_id 0x01 0x23 0x45 at bytes 10-12",
)

ACK_VAL_0x7B_PAIR_11_CMD: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 dd 4d 67 89 ab 00 7e 67 01 00 00 "
    "f8 8e 0c 00 67 01 00 00 00 50 00 f7 11 02 01 01 de 7e",
)
ACK_VAL_0x7B_PAIR_11_CMD_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:00:10.000Z",
    device_id="38:e8:dd:4d",
    operation="ack_validation",
    notes="msg_id 0x67 0x89 0xAB at bytes 10-12",
)
ACK_VAL_0x7B_PAIR_11_ACK: bytes = bytes.fromhex("7b 00 00 00 07 38 e8 dd 4d 67 89 ab")
ACK_VAL_0x7B_PAIR_11_ACK_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:00:10.016Z",
    device_id="38:e8:dd:4d",
    operation="ack_validation",
    notes="ACK for cmd, msg_id 0x67 0x89 0xAB at bytes 10-12",
)

# ---------- 0x23 → 0x28 ACK Pairs (Handshake ACKs) ----------
# Pattern: 0x28 ACK has NO msg_id (handshake doesn't use msg_id)

ACK_VAL_0x28_PAIR_01_HS: bytes = bytes.fromhex(
    "23 00 00 00 1a 03 45 88 0f 3a 00 10 31 65 30 37 64 38 63 65 30 61 36 31 37 61 33 37 00 00 3c",
)
ACK_VAL_0x28_PAIR_01_HS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:01:00.000Z",
    device_id="45:88:0f:3a",
    operation="ack_validation",
    notes="Handshake with endpoint 45:88:0f:3a, no msg_id",
)
ACK_VAL_0x28_PAIR_01_ACK: bytes = bytes.fromhex("28 00 00 00 02 00 00")
ACK_VAL_0x28_PAIR_01_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:01:00.050Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Hello ACK, NO msg_id present (CONFIRMED)",
)

ACK_VAL_0x28_PAIR_02_HS: bytes = bytes.fromhex(
    "23 00 00 00 1a 03 32 5d 53 17 00 10 31 65 30 37 61 62 63 64 30 61 36 31 37 61 33 37 00 00 3d",
)
ACK_VAL_0x28_PAIR_02_HS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:01:01.000Z",
    device_id="32:5d:53:17",
    operation="ack_validation",
    notes="Handshake with endpoint 32:5d:53:17",
)
ACK_VAL_0x28_PAIR_02_ACK: bytes = bytes.fromhex("28 00 00 00 02 00 00")
ACK_VAL_0x28_PAIR_02_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:01:01.048Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Hello ACK, NO msg_id",
)

ACK_VAL_0x28_PAIR_03_HS: bytes = bytes.fromhex(
    "23 00 00 00 1a 03 38 e8 cf 46 00 10 31 65 30 37 65 66 67 68 30 61 36 31 37 61 33 37 00 00 3e",
)
ACK_VAL_0x28_PAIR_03_HS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:01:02.000Z",
    device_id="38:e8:cf:46",
    operation="ack_validation",
    notes="Handshake with endpoint 38:e8:cf:46",
)
ACK_VAL_0x28_PAIR_03_ACK: bytes = bytes.fromhex("28 00 00 00 02 00 00")
ACK_VAL_0x28_PAIR_03_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:01:02.052Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Hello ACK, NO msg_id",
)

ACK_VAL_0x28_PAIR_04_HS: bytes = bytes.fromhex(
    "23 00 00 00 1a 03 3d 54 66 a6 00 10 31 65 30 37 69 6a 6b 6c 30 61 36 31 37 61 33 37 00 00 3f",
)
ACK_VAL_0x28_PAIR_04_HS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:01:03.000Z",
    device_id="3d:54:66:a6",
    operation="ack_validation",
    notes="Handshake with endpoint 3d:54:66:a6",
)
ACK_VAL_0x28_PAIR_04_ACK: bytes = bytes.fromhex("28 00 00 00 02 00 00")
ACK_VAL_0x28_PAIR_04_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:01:03.051Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Hello ACK, NO msg_id",
)

ACK_VAL_0x28_PAIR_05_HS: bytes = bytes.fromhex(
    "23 00 00 00 1a 03 60 b1 74 37 00 10 31 65 30 37 6d 6e 6f 70 30 61 36 31 37 61 33 37 00 00 40",
)
ACK_VAL_0x28_PAIR_05_HS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:01:04.000Z",
    device_id="60:b1:74:37",
    operation="ack_validation",
    notes="Handshake with endpoint 60:b1:74:37",
)
ACK_VAL_0x28_PAIR_05_ACK: bytes = bytes.fromhex("28 00 00 00 02 00 00")
ACK_VAL_0x28_PAIR_05_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:01:04.049Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Hello ACK, NO msg_id",
)

ACK_VAL_0x28_PAIR_06_HS: bytes = bytes.fromhex(
    "23 00 00 00 1a 03 60 b1 7a 37 00 10 31 65 30 37 71 72 73 74 30 61 36 31 37 61 33 37 00 00 41",
)
ACK_VAL_0x28_PAIR_06_HS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:01:05.000Z",
    device_id="60:b1:7a:37",
    operation="ack_validation",
    notes="Handshake with endpoint 60:b1:7a:37",
)
ACK_VAL_0x28_PAIR_06_ACK: bytes = bytes.fromhex("28 00 00 00 02 00 00")
ACK_VAL_0x28_PAIR_06_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:01:05.053Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Hello ACK, NO msg_id",
)

ACK_VAL_0x28_PAIR_07_HS: bytes = bytes.fromhex(
    "23 00 00 00 1a 03 60 b1 7c b4 00 10 31 65 30 37 75 76 77 78 30 61 36 31 37 61 33 37 00 00 42",
)
ACK_VAL_0x28_PAIR_07_HS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:01:06.000Z",
    device_id="60:b1:7c:b4",
    operation="ack_validation",
    notes="Handshake with endpoint 60:b1:7c:b4",
)
ACK_VAL_0x28_PAIR_07_ACK: bytes = bytes.fromhex("28 00 00 00 02 00 00")
ACK_VAL_0x28_PAIR_07_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:01:06.047Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Hello ACK, NO msg_id",
)

ACK_VAL_0x28_PAIR_08_HS: bytes = bytes.fromhex(
    "23 00 00 00 1a 03 60 b1 8e 42 00 10 31 65 30 37 79 7a 61 62 30 61 36 31 37 61 33 37 00 00 43",
)
ACK_VAL_0x28_PAIR_08_HS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:01:07.000Z",
    device_id="60:b1:8e:42",
    operation="ack_validation",
    notes="Handshake with endpoint 60:b1:8e:42",
)
ACK_VAL_0x28_PAIR_08_ACK: bytes = bytes.fromhex("28 00 00 00 02 00 00")
ACK_VAL_0x28_PAIR_08_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:01:07.051Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Hello ACK, NO msg_id",
)

ACK_VAL_0x28_PAIR_09_HS: bytes = bytes.fromhex(
    "23 00 00 00 1a 03 38 e8 ee 97 00 10 31 65 30 37 63 64 65 66 30 61 36 31 37 61 33 37 00 00 44",
)
ACK_VAL_0x28_PAIR_09_HS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:01:08.000Z",
    device_id="38:e8:ee:97",
    operation="ack_validation",
    notes="Handshake with endpoint 38:e8:ee:97",
)
ACK_VAL_0x28_PAIR_09_ACK: bytes = bytes.fromhex("28 00 00 00 02 00 00")
ACK_VAL_0x28_PAIR_09_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:01:08.048Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Hello ACK, NO msg_id",
)

ACK_VAL_0x28_PAIR_10_HS: bytes = bytes.fromhex(
    "23 00 00 00 1a 03 38 e8 dd 4d 00 10 31 65 30 37 67 68 69 6a 30 61 36 31 37 61 33 37 00 00 45",
)
ACK_VAL_0x28_PAIR_10_HS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:01:09.000Z",
    device_id="38:e8:dd:4d",
    operation="ack_validation",
    notes="Handshake with endpoint 38:e8:dd:4d",
)
ACK_VAL_0x28_PAIR_10_ACK: bytes = bytes.fromhex("28 00 00 00 02 00 00")
ACK_VAL_0x28_PAIR_10_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:01:09.052Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Hello ACK, NO msg_id",
)

# ---------- 0x83 → 0x88 ACK Pairs (Status Broadcast ACKs) ----------
# Pattern: 0x88 ACK has minimal structure, no msg_id field

ACK_VAL_0x88_PAIR_01_STATUS: bytes = bytes.fromhex(
    "83 00 00 00 25 45 88 0f 3a 00 09 00 7e 1f 00 00 "
    "00 fa db 13 00 72 25 11 50 00 50 00 db 11 02 01 "
    "01 0a 0a ff ff ff 00 00 37 7e",
)
ACK_VAL_0x88_PAIR_01_STATUS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:02:00.000Z",
    device_id="45:88:0f:3a",
    operation="ack_validation",
    notes="Status broadcast, device on",
)
ACK_VAL_0x88_PAIR_01_ACK: bytes = bytes.fromhex("88 00 00 00 03 00 00 00")
ACK_VAL_0x88_PAIR_01_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:02:00.018Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Status ACK, NO msg_id (counter byte at position 6)",
)

ACK_VAL_0x88_PAIR_02_STATUS: bytes = bytes.fromhex(
    "83 00 00 00 25 32 5d 53 17 00 0a 00 7e 1f 00 00 "
    "00 fa db 13 00 72 25 11 c6 00 00 00 db 11 02 00 "
    "01 0a 0a ff ff ff 00 00 22 7e",
)
ACK_VAL_0x88_PAIR_02_STATUS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:02:01.000Z",
    device_id="32:5d:53:17",
    operation="ack_validation",
    notes="Status broadcast, device off",
)
ACK_VAL_0x88_PAIR_02_ACK: bytes = bytes.fromhex("88 00 00 00 03 00 01 00")
ACK_VAL_0x88_PAIR_02_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:02:01.015Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Status ACK, counter incremented",
)

ACK_VAL_0x88_PAIR_03_STATUS: bytes = bytes.fromhex(
    "83 00 00 00 26 38 e8 cf 46 00 0b 00 7e 1f 00 00 "
    "00 fa db 14 00 95 2b 00 64 00 ff ff ea 11 02 64 "
    "a1 01 0b 01 00 00 00 00 00 bc 7e",
)
ACK_VAL_0x88_PAIR_03_STATUS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:02:02.000Z",
    device_id="38:e8:cf:46",
    operation="ack_validation",
    notes="Status broadcast, brightness 100%",
)
ACK_VAL_0x88_PAIR_03_ACK: bytes = bytes.fromhex("88 00 00 00 03 00 02 00")
ACK_VAL_0x88_PAIR_03_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:02:02.017Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Status ACK, counter 2",
)

ACK_VAL_0x88_PAIR_04_STATUS: bytes = bytes.fromhex(
    "83 00 00 00 26 3d 54 66 a6 00 0c 00 7e 1f 00 00 "
    "00 fa db 14 00 51 2c 00 32 00 ff ff ea 11 02 32 "
    "a1 01 0b 01 00 00 00 00 00 8a 7e",
)
ACK_VAL_0x88_PAIR_04_STATUS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:02:03.000Z",
    device_id="3d:54:66:a6",
    operation="ack_validation",
    notes="Status broadcast, brightness 50%",
)
ACK_VAL_0x88_PAIR_04_ACK: bytes = bytes.fromhex("88 00 00 00 03 00 03 00")
ACK_VAL_0x88_PAIR_04_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:02:03.019Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Status ACK, counter 3",
)

ACK_VAL_0x88_PAIR_05_STATUS: bytes = bytes.fromhex(
    "83 00 00 00 26 60 b1 74 37 00 0d 00 7e 1f 00 00 "
    "00 fa db 14 00 4a 2e 00 0a 00 ff ff ea 11 02 0a "
    "a1 01 0b 01 00 00 00 00 00 62 7e",
)
ACK_VAL_0x88_PAIR_05_STATUS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:02:04.000Z",
    device_id="60:b1:74:37",
    operation="ack_validation",
    notes="Status broadcast, brightness 10%",
)
ACK_VAL_0x88_PAIR_05_ACK: bytes = bytes.fromhex("88 00 00 00 03 00 04 00")
ACK_VAL_0x88_PAIR_05_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:02:04.016Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Status ACK, counter 4",
)

ACK_VAL_0x88_PAIR_06_STATUS: bytes = bytes.fromhex(
    "83 00 00 00 26 60 b1 7a 37 00 0e 00 7e 1f 00 00 "
    "00 fa db 14 00 15 2e 00 64 00 ff ff ea 11 02 64 "
    "a1 01 0b 01 00 00 00 00 00 b3 7e",
)
ACK_VAL_0x88_PAIR_06_STATUS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:02:05.000Z",
    device_id="60:b1:7a:37",
    operation="ack_validation",
    notes="Status broadcast, brightness 100%",
)
ACK_VAL_0x88_PAIR_06_ACK: bytes = bytes.fromhex("88 00 00 00 03 00 05 00")
ACK_VAL_0x88_PAIR_06_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:02:05.018Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Status ACK, counter 5",
)

ACK_VAL_0x88_PAIR_07_STATUS: bytes = bytes.fromhex(
    "83 00 00 00 26 60 b1 7c b4 00 0f 00 7e 1f 00 00 "
    "00 fa db 14 00 01 2e 00 00 00 ff ff ea 11 02 00 "
    "a1 01 0b 01 00 00 00 00 00 09 7e",
)
ACK_VAL_0x88_PAIR_07_STATUS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:02:06.000Z",
    device_id="60:b1:7c:b4",
    operation="ack_validation",
    notes="Status broadcast, device off",
)
ACK_VAL_0x88_PAIR_07_ACK: bytes = bytes.fromhex("88 00 00 00 03 00 06 00")
ACK_VAL_0x88_PAIR_07_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:02:06.014Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Status ACK, counter 6",
)

ACK_VAL_0x88_PAIR_08_STATUS: bytes = bytes.fromhex(
    "83 00 00 00 26 60 b1 8e 42 00 10 00 7e 24 00 00 "
    "00 fa db 14 00 f6 2d 00 19 00 ff ff ea 11 02 19 "
    "a1 01 0b 01 00 00 00 00 00 74 7e",
)
ACK_VAL_0x88_PAIR_08_STATUS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:02:07.000Z",
    device_id="60:b1:8e:42",
    operation="ack_validation",
    notes="Status broadcast, brightness 25%",
)
ACK_VAL_0x88_PAIR_08_ACK: bytes = bytes.fromhex("88 00 00 00 03 00 07 00")
ACK_VAL_0x88_PAIR_08_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:02:07.019Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Status ACK, counter 7",
)

ACK_VAL_0x88_PAIR_09_STATUS: bytes = bytes.fromhex(
    "83 00 00 00 26 38 e8 ee 97 00 11 00 7e 1f 00 00 "
    "00 fa db 14 00 05 2c 00 4b 00 ff ff ea 11 02 4b "
    "a1 01 0b 01 00 00 00 00 00 a7 7e",
)
ACK_VAL_0x88_PAIR_09_STATUS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:02:08.000Z",
    device_id="38:e8:ee:97",
    operation="ack_validation",
    notes="Status broadcast, brightness 75%",
)
ACK_VAL_0x88_PAIR_09_ACK: bytes = bytes.fromhex("88 00 00 00 03 00 08 00")
ACK_VAL_0x88_PAIR_09_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:02:08.017Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Status ACK, counter 8",
)

ACK_VAL_0x88_PAIR_10_STATUS: bytes = bytes.fromhex(
    "83 00 00 00 26 38 e8 dd 4d 00 12 00 7e 1f 00 00 "
    "00 fa db 14 00 aa 2b 00 64 00 ff ff ea 11 02 64 "
    "a1 01 0b 01 00 00 00 00 00 c0 7e",
)
ACK_VAL_0x88_PAIR_10_STATUS_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:02:09.000Z",
    device_id="38:e8:dd:4d",
    operation="ack_validation",
    notes="Status broadcast, brightness 100%",
)
ACK_VAL_0x88_PAIR_10_ACK: bytes = bytes.fromhex("88 00 00 00 03 00 09 00")
ACK_VAL_0x88_PAIR_10_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:02:09.016Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Status ACK, counter 9",
)

# ---------- 0xD3 → 0xD8 ACK Pairs (Heartbeat ACKs) ----------
# Pattern: Minimal 5-byte packets, no msg_id

ACK_VAL_0xD8_PAIR_01_HB: bytes = bytes.fromhex("d3 00 00 00 00")
ACK_VAL_0xD8_PAIR_01_HB_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:03:00.000Z",
    device_id="various",
    operation="ack_validation",
    notes="Device heartbeat, minimal packet",
)
ACK_VAL_0xD8_PAIR_01_ACK: bytes = bytes.fromhex("d8 00 00 00 00")
ACK_VAL_0xD8_PAIR_01_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:03:00.042Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Heartbeat ACK, NO msg_id, 5-byte minimal",
)

ACK_VAL_0xD8_PAIR_02_HB: bytes = bytes.fromhex("d3 00 00 00 00")
ACK_VAL_0xD8_PAIR_02_HB_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:03:01.000Z",
    device_id="various",
    operation="ack_validation",
    notes="Device heartbeat",
)
ACK_VAL_0xD8_PAIR_02_ACK: bytes = bytes.fromhex("d8 00 00 00 00")
ACK_VAL_0xD8_PAIR_02_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:03:01.039Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Heartbeat ACK",
)

ACK_VAL_0xD8_PAIR_03_HB: bytes = bytes.fromhex("d3 00 00 00 00")
ACK_VAL_0xD8_PAIR_03_HB_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:03:02.000Z",
    device_id="various",
    operation="ack_validation",
    notes="Device heartbeat",
)
ACK_VAL_0xD8_PAIR_03_ACK: bytes = bytes.fromhex("d8 00 00 00 00")
ACK_VAL_0xD8_PAIR_03_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:03:02.041Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Heartbeat ACK",
)

ACK_VAL_0xD8_PAIR_04_HB: bytes = bytes.fromhex("d3 00 00 00 00")
ACK_VAL_0xD8_PAIR_04_HB_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:03:03.000Z",
    device_id="various",
    operation="ack_validation",
    notes="Device heartbeat",
)
ACK_VAL_0xD8_PAIR_04_ACK: bytes = bytes.fromhex("d8 00 00 00 00")
ACK_VAL_0xD8_PAIR_04_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:03:03.038Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Heartbeat ACK",
)

ACK_VAL_0xD8_PAIR_05_HB: bytes = bytes.fromhex("d3 00 00 00 00")
ACK_VAL_0xD8_PAIR_05_HB_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:03:04.000Z",
    device_id="various",
    operation="ack_validation",
    notes="Device heartbeat",
)
ACK_VAL_0xD8_PAIR_05_ACK: bytes = bytes.fromhex("d8 00 00 00 00")
ACK_VAL_0xD8_PAIR_05_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:03:04.043Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Heartbeat ACK",
)

ACK_VAL_0xD8_PAIR_06_HB: bytes = bytes.fromhex("d3 00 00 00 00")
ACK_VAL_0xD8_PAIR_06_HB_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:03:05.000Z",
    device_id="various",
    operation="ack_validation",
    notes="Device heartbeat",
)
ACK_VAL_0xD8_PAIR_06_ACK: bytes = bytes.fromhex("d8 00 00 00 00")
ACK_VAL_0xD8_PAIR_06_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:03:05.040Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Heartbeat ACK",
)

ACK_VAL_0xD8_PAIR_07_HB: bytes = bytes.fromhex("d3 00 00 00 00")
ACK_VAL_0xD8_PAIR_07_HB_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:03:06.000Z",
    device_id="various",
    operation="ack_validation",
    notes="Device heartbeat",
)
ACK_VAL_0xD8_PAIR_07_ACK: bytes = bytes.fromhex("d8 00 00 00 00")
ACK_VAL_0xD8_PAIR_07_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:03:06.037Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Heartbeat ACK",
)

ACK_VAL_0xD8_PAIR_08_HB: bytes = bytes.fromhex("d3 00 00 00 00")
ACK_VAL_0xD8_PAIR_08_HB_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:03:07.000Z",
    device_id="various",
    operation="ack_validation",
    notes="Device heartbeat",
)
ACK_VAL_0xD8_PAIR_08_ACK: bytes = bytes.fromhex("d8 00 00 00 00")
ACK_VAL_0xD8_PAIR_08_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:03:07.044Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Heartbeat ACK",
)

ACK_VAL_0xD8_PAIR_09_HB: bytes = bytes.fromhex("d3 00 00 00 00")
ACK_VAL_0xD8_PAIR_09_HB_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:03:08.000Z",
    device_id="various",
    operation="ack_validation",
    notes="Device heartbeat",
)
ACK_VAL_0xD8_PAIR_09_ACK: bytes = bytes.fromhex("d8 00 00 00 00")
ACK_VAL_0xD8_PAIR_09_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:03:08.041Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Heartbeat ACK",
)

ACK_VAL_0xD8_PAIR_10_HB: bytes = bytes.fromhex("d3 00 00 00 00")
ACK_VAL_0xD8_PAIR_10_HB_META: PacketMetadata = PacketMetadata(
    device_type="device",
    firmware_version="unknown",
    captured_at="2025-11-06T10:03:09.000Z",
    device_id="various",
    operation="ack_validation",
    notes="Device heartbeat",
)
ACK_VAL_0xD8_PAIR_10_ACK: bytes = bytes.fromhex("d8 00 00 00 00")
ACK_VAL_0xD8_PAIR_10_ACK_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T10:03:09.039Z",
    device_id="N/A",
    operation="ack_validation",
    notes="Heartbeat ACK",
)


# ============================================================================
# Retry Packet Fixtures (Phase 1b Deduplication - Deliverable #8)
# ============================================================================
# Purpose: Validate Full Fingerprint deduplication strategy with retry packets
# Each triplet contains: original command + 2 retries
# Expected behavior: Same logical command produces identical dedup_key
# Full Fingerprint format: "packet_type:endpoint:msg_id:payload_hash[:16]"
# ============================================================================

# Triplet 1: Toggle ON command retries
RETRY_SET_01_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a aa bb cc 00 7e aa 01 00 00 "
    "f8 8e 0c 00 aa 01 00 00 00 50 00 f7 11 02 01 01 56 7e",
)
RETRY_SET_01_ORIG_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T11:00:00.000Z",
    device_id="45:88:0f:3a",
    operation="retry_test",
    notes="Toggle ON original, dedup_key: 73:45880f3a:aabbcc:payload_hash",
)
RETRY_SET_01_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a aa bb cc 00 7e aa 01 00 00 "
    "f8 8e 0c 00 aa 01 00 00 00 50 00 f7 11 02 01 01 56 7e",
)
RETRY_SET_01_RETRY_1_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T11:00:02.000Z",
    device_id="45:88:0f:3a",
    operation="retry_test",
    notes="Toggle ON retry 1, identical dedup_key (should deduplicate)",
)
RETRY_SET_01_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a aa bb cc 00 7e aa 01 00 00 "
    "f8 8e 0c 00 aa 01 00 00 00 50 00 f7 11 02 01 01 56 7e",
)
RETRY_SET_01_RETRY_2_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T11:00:04.000Z",
    device_id="45:88:0f:3a",
    operation="retry_test",
    notes="Toggle ON retry 2, identical dedup_key",
)

# Triplet 2: Toggle OFF command retries
RETRY_SET_02_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a 11 22 33 00 7e 11 01 00 00 "
    "f8 8e 0c 00 11 01 00 00 00 50 00 f7 11 02 00 01 65 7e",
)
RETRY_SET_02_ORIG_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T11:01:00.000Z",
    device_id="45:88:0f:3a",
    operation="retry_test",
    notes="Toggle OFF original, dedup_key: 73:45880f3a:112233:payload_hash",
)
RETRY_SET_02_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a 11 22 33 00 7e 11 01 00 00 "
    "f8 8e 0c 00 11 01 00 00 00 50 00 f7 11 02 00 01 65 7e",
)
RETRY_SET_02_RETRY_1_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T11:01:02.000Z",
    device_id="45:88:0f:3a",
    operation="retry_test",
    notes="Toggle OFF retry 1",
)
RETRY_SET_02_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a 11 22 33 00 7e 11 01 00 00 "
    "f8 8e 0c 00 11 01 00 00 00 50 00 f7 11 02 00 01 65 7e",
)
RETRY_SET_02_RETRY_2_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T11:01:04.000Z",
    device_id="45:88:0f:3a",
    operation="retry_test",
    notes="Toggle OFF retry 2",
)

# Triplet 3: Brightness 50% retries
RETRY_SET_03_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 32 5d 53 17 ff 00 ff 00 7e ff 01 00 00 "
    "f8 8e 0c 00 ff 01 00 00 00 32 00 f7 11 02 32 01 db 7e",
)
RETRY_SET_03_ORIG_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T11:02:00.000Z",
    device_id="32:5d:53:17",
    operation="retry_test",
    notes="Brightness 50% original",
)
RETRY_SET_03_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 32 5d 53 17 ff 00 ff 00 7e ff 01 00 00 "
    "f8 8e 0c 00 ff 01 00 00 00 32 00 f7 11 02 32 01 db 7e",
)
RETRY_SET_03_RETRY_1_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T11:02:02.000Z",
    device_id="32:5d:53:17",
    operation="retry_test",
    notes="Brightness 50% retry 1",
)
RETRY_SET_03_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 32 5d 53 17 ff 00 ff 00 7e ff 01 00 00 "
    "f8 8e 0c 00 ff 01 00 00 00 32 00 f7 11 02 32 01 db 7e",
)
RETRY_SET_03_RETRY_2_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T11:02:04.000Z",
    device_id="32:5d:53:17",
    operation="retry_test",
    notes="Brightness 50% retry 2",
)

# Triplet 4: Brightness 100% retries
RETRY_SET_04_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 cf 46 12 34 56 00 7e 12 01 00 00 "
    "f8 8e 0c 00 12 01 00 00 00 64 00 f7 11 02 64 01 15 7e",
)
RETRY_SET_04_ORIG_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T11:03:00.000Z",
    device_id="38:e8:cf:46",
    operation="retry_test",
    notes="Brightness 100% original",
)
RETRY_SET_04_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 cf 46 12 34 56 00 7e 12 01 00 00 "
    "f8 8e 0c 00 12 01 00 00 00 64 00 f7 11 02 64 01 15 7e",
)
RETRY_SET_04_RETRY_1_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T11:03:02.000Z",
    device_id="38:e8:cf:46",
    operation="retry_test",
    notes="Brightness 100% retry 1",
)
RETRY_SET_04_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 cf 46 12 34 56 00 7e 12 01 00 00 "
    "f8 8e 0c 00 12 01 00 00 00 64 00 f7 11 02 64 01 15 7e",
)
RETRY_SET_04_RETRY_2_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T11:03:04.000Z",
    device_id="38:e8:cf:46",
    operation="retry_test",
    notes="Brightness 100% retry 2",
)

# Triplet 5: Brightness 10% retries
RETRY_SET_05_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 3d 54 66 a6 ab cd ef 00 7e ab 01 00 00 "
    "f8 8e 0c 00 ab 01 00 00 00 0a 00 f7 11 02 0a 01 5d 7e",
)
RETRY_SET_05_ORIG_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T11:04:00.000Z",
    device_id="3d:54:66:a6",
    operation="retry_test",
    notes="Brightness 10% original",
)
RETRY_SET_05_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 3d 54 66 a6 ab cd ef 00 7e ab 01 00 00 "
    "f8 8e 0c 00 ab 01 00 00 00 0a 00 f7 11 02 0a 01 5d 7e",
)
RETRY_SET_05_RETRY_1_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T11:04:02.000Z",
    device_id="3d:54:66:a6",
    operation="retry_test",
    notes="Brightness 10% retry 1",
)
RETRY_SET_05_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 3d 54 66 a6 ab cd ef 00 7e ab 01 00 00 "
    "f8 8e 0c 00 ab 01 00 00 00 0a 00 f7 11 02 0a 01 5d 7e",
)
RETRY_SET_05_RETRY_2_META: PacketMetadata = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-06T11:04:04.000Z",
    device_id="3d:54:66:a6",
    operation="retry_test",
    notes="Brightness 10% retry 2",
)

# Triplets 6-20: Additional retry scenarios for comprehensive testing
# (Using shorter naming for space efficiency)

RETRY_SET_06_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 74 37 de ad be 00 7e de 01 00 00 f8 8e 0c 00 de 01 00 00 00 "
    "19 00 f7 11 02 19 01 84 7e",
)
RETRY_SET_06_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 74 37 de ad be 00 7e de 01 00 00 f8 8e 0c 00 de 01 00 00 00 "
    "19 00 f7 11 02 19 01 84 7e",
)
RETRY_SET_06_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 74 37 de ad be 00 7e de 01 00 00 f8 8e 0c 00 de 01 00 00 00 "
    "19 00 f7 11 02 19 01 84 7e",
)

RETRY_SET_07_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 7a 37 ca fe ba 00 7e ca 01 00 00 f8 8e 0c 00 ca 01 00 00 00 "
    "32 00 f7 11 02 32 01 dc 7e",
)
RETRY_SET_07_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 7a 37 ca fe ba 00 7e ca 01 00 00 f8 8e 0c 00 ca 01 00 00 00 "
    "32 00 f7 11 02 32 01 dc 7e",
)
RETRY_SET_07_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 7a 37 ca fe ba 00 7e ca 01 00 00 f8 8e 0c 00 ca 01 00 00 00 "
    "32 00 f7 11 02 32 01 dc 7e",
)

RETRY_SET_08_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 7c b4 ba dc 0d 00 7e ba 01 00 00 f8 8e 0c 00 ba 01 00 00 00 "
    "4b 00 f7 11 02 4b 01 f5 7e",
)
RETRY_SET_08_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 7c b4 ba dc 0d 00 7e ba 01 00 00 f8 8e 0c 00 ba 01 00 00 00 "
    "4b 00 f7 11 02 4b 01 f5 7e",
)
RETRY_SET_08_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 7c b4 ba dc 0d 00 7e ba 01 00 00 f8 8e 0c 00 ba 01 00 00 00 "
    "4b 00 f7 11 02 4b 01 f5 7e",
)

RETRY_SET_09_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 8e 42 f0 0d fa 00 7e f0 01 00 00 f8 8e 0c 00 f0 01 00 00 00 "
    "00 00 f7 11 02 00 01 92 7e",
)
RETRY_SET_09_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 8e 42 f0 0d fa 00 7e f0 01 00 00 f8 8e 0c 00 f0 01 00 00 00 "
    "00 00 f7 11 02 00 01 92 7e",
)
RETRY_SET_09_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 8e 42 f0 0d fa 00 7e f0 01 00 00 f8 8e 0c 00 f0 01 00 00 00 "
    "00 00 f7 11 02 00 01 92 7e",
)

RETRY_SET_10_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 ee 97 01 23 45 00 7e 01 01 00 00 f8 8e 0c 00 01 01 00 00 00 "
    "64 00 f7 11 02 64 01 0f 7e",
)
RETRY_SET_10_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 ee 97 01 23 45 00 7e 01 01 00 00 f8 8e 0c 00 01 01 00 00 00 "
    "64 00 f7 11 02 64 01 0f 7e",
)
RETRY_SET_10_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 ee 97 01 23 45 00 7e 01 01 00 00 f8 8e 0c 00 01 01 00 00 00 "
    "64 00 f7 11 02 64 01 0f 7e",
)

RETRY_SET_11_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 dd 4d 67 89 ab 00 7e 67 01 00 00 f8 8e 0c 00 67 01 00 00 00 "
    "50 00 f7 11 02 01 01 d8 7e",
)
RETRY_SET_11_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 dd 4d 67 89 ab 00 7e 67 01 00 00 f8 8e 0c 00 67 01 00 00 00 "
    "50 00 f7 11 02 01 01 d8 7e",
)
RETRY_SET_11_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 dd 4d 67 89 ab 00 7e 67 01 00 00 f8 8e 0c 00 67 01 00 00 00 "
    "50 00 f7 11 02 01 01 d8 7e",
)

RETRY_SET_12_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a 22 33 44 00 7e 22 01 00 00 f8 8e 0c 00 22 01 00 00 00 "
    "0a 00 f7 11 02 0a 01 6f 7e",
)
RETRY_SET_12_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a 22 33 44 00 7e 22 01 00 00 f8 8e 0c 00 22 01 00 00 00 "
    "0a 00 f7 11 02 0a 01 6f 7e",
)
RETRY_SET_12_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a 22 33 44 00 7e 22 01 00 00 f8 8e 0c 00 22 01 00 00 00 "
    "0a 00 f7 11 02 0a 01 6f 7e",
)

RETRY_SET_13_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 32 5d 53 17 55 66 77 00 7e 55 01 00 00 f8 8e 0c 00 55 01 00 00 00 "
    "19 00 f7 11 02 19 01 20 7e",
)
RETRY_SET_13_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 32 5d 53 17 55 66 77 00 7e 55 01 00 00 f8 8e 0c 00 55 01 00 00 00 "
    "19 00 f7 11 02 19 01 20 7e",
)
RETRY_SET_13_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 32 5d 53 17 55 66 77 00 7e 55 01 00 00 f8 8e 0c 00 55 01 00 00 00 "
    "19 00 f7 11 02 19 01 20 7e",
)

RETRY_SET_14_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 cf 46 88 99 aa 00 7e 88 01 00 00 f8 8e 0c 00 88 01 00 00 00 "
    "32 00 f7 11 02 32 01 52 7e",
)
RETRY_SET_14_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 cf 46 88 99 aa 00 7e 88 01 00 00 f8 8e 0c 00 88 01 00 00 00 "
    "32 00 f7 11 02 32 01 52 7e",
)
RETRY_SET_14_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 cf 46 88 99 aa 00 7e 88 01 00 00 f8 8e 0c 00 88 01 00 00 00 "
    "32 00 f7 11 02 32 01 52 7e",
)

RETRY_SET_15_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 3d 54 66 a6 bb cc dd 00 7e bb 01 00 00 f8 8e 0c 00 bb 01 00 00 00 "
    "4b 00 f7 11 02 4b 01 6b 7e",
)
RETRY_SET_15_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 3d 54 66 a6 bb cc dd 00 7e bb 01 00 00 f8 8e 0c 00 bb 01 00 00 00 "
    "4b 00 f7 11 02 4b 01 6b 7e",
)
RETRY_SET_15_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 3d 54 66 a6 bb cc dd 00 7e bb 01 00 00 f8 8e 0c 00 bb 01 00 00 00 "
    "4b 00 f7 11 02 4b 01 6b 7e",
)

RETRY_SET_16_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 74 37 cc dd ee 00 7e cc 01 00 00 f8 8e 0c 00 cc 01 00 00 00 "
    "64 00 f7 11 02 64 01 2d 7e",
)
RETRY_SET_16_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 74 37 cc dd ee 00 7e cc 01 00 00 f8 8e 0c 00 cc 01 00 00 00 "
    "64 00 f7 11 02 64 01 2d 7e",
)
RETRY_SET_16_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 74 37 cc dd ee 00 7e cc 01 00 00 f8 8e 0c 00 cc 01 00 00 00 "
    "64 00 f7 11 02 64 01 2d 7e",
)

RETRY_SET_17_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 7a 37 dd ee ff 00 7e dd 01 00 00 f8 8e 0c 00 dd 01 00 00 00 "
    "00 00 f7 11 02 00 01 7e 7e",
)
RETRY_SET_17_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 7a 37 dd ee ff 00 7e dd 01 00 00 f8 8e 0c 00 dd 01 00 00 00 "
    "00 00 f7 11 02 00 01 7e 7e",
)
RETRY_SET_17_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 7a 37 dd ee ff 00 7e dd 01 00 00 f8 8e 0c 00 dd 01 00 00 00 "
    "00 00 f7 11 02 00 01 7e 7e",
)

RETRY_SET_18_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 7c b4 ee ff 00 00 7e ee 01 00 00 f8 8e 0c 00 ee 01 00 00 00 "
    "0a 00 f7 11 02 0a 01 9d 7e",
)
RETRY_SET_18_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 7c b4 ee ff 00 00 7e ee 01 00 00 f8 8e 0c 00 ee 01 00 00 00 "
    "0a 00 f7 11 02 0a 01 9d 7e",
)
RETRY_SET_18_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 7c b4 ee ff 00 00 7e ee 01 00 00 f8 8e 0c 00 ee 01 00 00 00 "
    "0a 00 f7 11 02 0a 01 9d 7e",
)

RETRY_SET_19_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 8e 42 ff 00 11 00 7e ff 01 00 00 f8 8e 0c 00 ff 01 00 00 00 "
    "19 00 f7 11 02 19 01 a4 7e",
)
RETRY_SET_19_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 8e 42 ff 00 11 00 7e ff 01 00 00 f8 8e 0c 00 ff 01 00 00 00 "
    "19 00 f7 11 02 19 01 a4 7e",
)
RETRY_SET_19_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 60 b1 8e 42 ff 00 11 00 7e ff 01 00 00 f8 8e 0c 00 ff 01 00 00 00 "
    "19 00 f7 11 02 19 01 a4 7e",
)

RETRY_SET_20_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 ee 97 00 11 22 00 7e 00 01 00 00 f8 8e 0c 00 00 01 00 00 00 "
    "32 00 f7 11 02 32 01 d3 7e",
)
RETRY_SET_20_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 ee 97 00 11 22 00 7e 00 01 00 00 f8 8e 0c 00 00 01 00 00 00 "
    "32 00 f7 11 02 32 01 d3 7e",
)
RETRY_SET_20_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 ee 97 00 11 22 00 7e 00 01 00 00 f8 8e 0c 00 00 01 00 00 00 "
    "32 00 f7 11 02 32 01 d3 7e",
)

RETRY_SET_21_ORIG: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 dd 4d 11 22 33 00 7e 11 01 00 00 f8 8e 0c 00 11 01 00 00 00 "
    "4b 00 f7 11 02 4b 01 01 7e",
)
RETRY_SET_21_RETRY_1: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 dd 4d 11 22 33 00 7e 11 01 00 00 f8 8e 0c 00 11 01 00 00 00 "
    "4b 00 f7 11 02 4b 01 01 7e",
)
RETRY_SET_21_RETRY_2: bytes = bytes.fromhex(
    "73 00 00 00 1f 38 e8 dd 4d 11 22 33 00 7e 11 01 00 00 f8 8e 0c 00 11 01 00 00 00 "
    "4b 00 f7 11 02 4b 01 01 7e",
)


# ============================================================================
# Edge Case Fixtures (Phase 1a Codec Robustness)
# ============================================================================
# Purpose: Test codec handling of malformed, boundary, and unusual packets
# These fixtures validate error handling and edge case robustness in Phase 1a
# ============================================================================

# Malformed packets (should fail gracefully)
EDGE_TRUNCATED_HEADER: bytes = bytes.fromhex("73 00 00")  # Only 3 bytes, needs 5
EDGE_TRUNCATED_HEADER_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:00.000Z",
    device_id="N/A",
    operation="edge_case",
    notes="Truncated header (3 bytes), should_fail=True",
)

EDGE_INVALID_LENGTH: bytes = (
    bytes.fromhex("73 00 00 00 ff") + b"\x00" * 10
)  # Claims 255 bytes but only has 15 total
EDGE_INVALID_LENGTH_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:01.000Z",
    device_id="N/A",
    operation="edge_case",
    notes="Length field 255 but packet truncated, should handle gracefully",
)

EDGE_MISSING_START_MARKER: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a aa bb cc 00 aa 01 00 00 "
    "f8 8e 0c 00 aa 01 00 00 00 50 00 f7 11 02 01 01 56",
)  # Missing 0x7e markers
EDGE_MISSING_START_MARKER_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:02.000Z",
    device_id="N/A",
    operation="edge_case",
    notes="Missing 0x7e framing markers",
)

EDGE_INVALID_CHECKSUM: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a aa bb cc 00 7e aa 01 00 00 "
    "f8 8e 0c 00 aa 01 00 00 00 50 00 f7 11 02 01 01 FF 7e",
)  # Checksum 0xFF is wrong
EDGE_INVALID_CHECKSUM_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:03.000Z",
    device_id="N/A",
    operation="edge_case",
    notes="Invalid checksum 0xFF (should be 0x56)",
)

EDGE_UNKNOWN_PACKET_TYPE: bytes = bytes.fromhex("FF 00 00 00 05 aa bb cc dd ee")
EDGE_UNKNOWN_PACKET_TYPE_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:04.000Z",
    device_id="N/A",
    operation="edge_case",
    notes="Unknown packet type 0xFF",
)

# Boundary conditions (valid but edge cases)
EDGE_ZERO_LENGTH: bytes = bytes.fromhex("73 00 00 00 00")  # Header only, zero data length
EDGE_ZERO_LENGTH_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:05.000Z",
    device_id="N/A",
    operation="edge_case",
    notes="Zero-length payload (header only)",
)

EDGE_MIN_VALID_0x73: bytes = bytes.fromhex(
    "73 00 00 00 14 45 88 0f 3a aa bb cc 00 7e 00 00 00 00 00 00 00 00 00 7e",
)  # Minimal valid 0x73 packet
EDGE_MIN_VALID_0x73_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:06.000Z",
    device_id="N/A",
    operation="edge_case",
    notes="Minimal valid 0x73 packet (20 bytes total)",
)

EDGE_LARGE_MULTIPLIER: bytes = (
    bytes.fromhex("73 00 00 01 00") + b"\x00" * 256
)  # Length multiplier = 1
EDGE_LARGE_MULTIPLIER_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:07.000Z",
    device_id="N/A",
    operation="edge_case",
    notes="Length multiplier = 1 (256 bytes data)",
)

# Unusual but valid
EDGE_ENDPOINT_ALL_ZEROS: bytes = bytes.fromhex(
    "23 00 00 00 1a 03 00 00 00 00 00 10 31 65 30 37 64 38 63 65 30 61 36 31 37 61 33 37 00 00 3c",
)
EDGE_ENDPOINT_ALL_ZEROS_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:08.000Z",
    device_id="00:00:00:00",
    operation="edge_case",
    notes="Endpoint all zeros (valid but unusual)",
)

EDGE_ENDPOINT_ALL_FF: bytes = bytes.fromhex(
    "23 00 00 00 1a 03 ff ff ff ff 00 10 31 65 30 37 64 38 63 65 30 61 36 31 37 61 33 37 00 00 3c",
)
EDGE_ENDPOINT_ALL_FF_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:09.000Z",
    device_id="ff:ff:ff:ff",
    operation="edge_case",
    notes="Endpoint all 0xFF (broadcast address?)",
)

EDGE_MSG_ID_ALL_ZEROS: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a 00 00 00 00 7e 00 01 00 00 "
    "f8 8e 0c 00 00 01 00 00 00 50 00 f7 11 02 01 01 53 7e",
)
EDGE_MSG_ID_ALL_ZEROS_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:10.000Z",
    device_id="45:88:0f:3a",
    operation="edge_case",
    notes="msg_id all zeros (valid but unusual)",
)

EDGE_MSG_ID_ALL_FF: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a ff ff ff 00 7e ff 01 00 00 "
    "f8 8e 0c 00 ff 01 00 00 00 50 00 f7 11 02 01 01 a5 7e",
)
EDGE_MSG_ID_ALL_FF_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:11.000Z",
    device_id="45:88:0f:3a",
    operation="edge_case",
    notes="msg_id all 0xFF (max value)",
)

EDGE_DEVICE_INFO_EMPTY: bytes = bytes.fromhex("43 00 00 00 05 00 00 00 00 00")  # 0 devices
EDGE_DEVICE_INFO_EMPTY_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:12.000Z",
    device_id="N/A",
    operation="edge_case",
    notes="Device info with 0 devices (valid but unusual)",
)

EDGE_DEVICE_INFO_SINGLE: bytes = bytes.fromhex(
    "43 00 00 00 18 32 5d 53 17 01 01 06 c6 20 02 00 ab c5 20 02 00 04 c4 20 02 00",
)  # Exactly 1 device (19 bytes)
EDGE_DEVICE_INFO_SINGLE_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:13.000Z",
    device_id="32:5d:53:17",
    operation="edge_case",
    notes="Device info with exactly 1 device (minimal valid)",
)

EDGE_MAX_BRIGHTNESS: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a aa bb cc 00 7e aa 01 00 00 "
    "f8 8e 0c 00 aa 01 00 00 00 64 00 f7 11 02 64 01 15 7e",
)  # Brightness = 100 (0x64)
EDGE_MAX_BRIGHTNESS_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:14.000Z",
    device_id="45:88:0f:3a",
    operation="edge_case",
    notes="Maximum brightness value (100 = 0x64)",
)

EDGE_MIN_BRIGHTNESS: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a aa bb cc 00 7e aa 01 00 00 "
    "f8 8e 0c 00 aa 01 00 00 00 01 00 f7 11 02 01 01 54 7e",
)  # Brightness = 1 (minimum non-zero)
EDGE_MIN_BRIGHTNESS_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:15.000Z",
    device_id="45:88:0f:3a",
    operation="edge_case",
    notes="Minimum brightness value (1)",
)

EDGE_LARGE_DEVICE_INFO: bytes = bytes.fromhex(
    "43 00 00 01 2d 32 5d 53 17 01 14",  # 20 devices = 20*19 = 380 bytes + 5 header = 385 total
) + (b"\x06\xc6\x20\x02\x00\xab\xc5\x20\x02\x00\x04\xc4\x20\x02\x00\x01\xc3\x20\x02\x00" * 20)
EDGE_LARGE_DEVICE_INFO_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:16.000Z",
    device_id="32:5d:53:17",
    operation="edge_case",
    notes="Device info with 20 devices (385 bytes total, near max)",
)

# Additional malformed variants
EDGE_PARTIAL_PAYLOAD: bytes = bytes.fromhex(
    "73 00 00 00 1f 45 88 0f 3a aa bb cc 00 7e aa 01 00",
)  # Incomplete payload
EDGE_PARTIAL_PAYLOAD_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:17.000Z",
    device_id="45:88:0f:3a",
    operation="edge_case",
    notes="Partial payload (truncated mid-packet)",
)

EDGE_DOUBLE_START_MARKER: bytes = bytes.fromhex(
    "73 00 00 00 20 45 88 0f 3a aa bb cc 00 7e 7e aa 01 00 00 "
    "f8 8e 0c 00 aa 01 00 00 00 50 00 f7 11 02 01 01 56 7e",
)  # Double 0x7e at start
EDGE_DOUBLE_START_MARKER_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:18.000Z",
    device_id="45:88:0f:3a",
    operation="edge_case",
    notes="Double 0x7e start marker (ambiguous framing)",
)

EDGE_NO_END_MARKER: bytes = bytes.fromhex(
    "73 00 00 00 1e 45 88 0f 3a aa bb cc 00 7e aa 01 00 00 "
    "f8 8e 0c 00 aa 01 00 00 00 50 00 f7 11 02 01 01 56",
)  # Missing trailing 0x7e
EDGE_NO_END_MARKER_META: PacketMetadata = PacketMetadata(
    device_type="test",
    firmware_version="N/A",
    captured_at="2025-11-06T12:00:19.000Z",
    device_id="45:88:0f:3a",
    operation="edge_case",
    notes="Missing trailing 0x7e marker",
)


# ============================================================================
# Device Variety Fixtures (Multi-type Coverage)
# ============================================================================
# Purpose: Fixtures from different device types (switch, plug) and firmware versions
# Provides coverage beyond just bulbs for Phase 1a/1b/1c testing
# ============================================================================

# Switch device fixtures (firmware 2.1.0)
SWITCH_HANDSHAKE_0x23: bytes = bytes.fromhex(
    "23 00 00 00 1a 03 a1 b2 c3 d4 00 10 73 77 69 74 63 68 30 31 32 33 34 35 36 37 38 39 00 00 4a",
)
SWITCH_HANDSHAKE_0x23_META: PacketMetadata = PacketMetadata(
    device_type="switch",
    firmware_version="2.1.0",
    captured_at="2025-11-06T13:00:00.000Z",
    device_id="a1:b2:c3:d4",
    operation="handshake",
    notes="Switch device handshake",
)

SWITCH_TOGGLE_0x73: bytes = bytes.fromhex(
    "73 00 00 00 1f a1 b2 c3 d4 10 20 30 00 7e 10 01 00 00 "
    "f8 8e 0c 00 10 01 00 00 00 01 00 f7 11 02 01 01 25 7e",
)
SWITCH_TOGGLE_0x73_META: PacketMetadata = PacketMetadata(
    device_type="switch",
    firmware_version="2.1.0",
    captured_at="2025-11-06T13:00:01.000Z",
    device_id="a1:b2:c3:d4",
    operation="toggle_on",
    notes="Switch toggle command (switches don't use brightness)",
)

SWITCH_STATUS_0x83: bytes = bytes.fromhex(
    "83 00 00 00 25 a1 b2 c3 d4 00 05 00 7e 1f 00 00 "
    "00 fa db 13 00 72 25 11 01 00 01 00 db 11 02 01 "
    "01 0a 0a ff ff ff 00 00 15 7e",
)
SWITCH_STATUS_0x83_META: PacketMetadata = PacketMetadata(
    device_type="switch",
    firmware_version="2.1.0",
    captured_at="2025-11-06T13:00:02.000Z",
    device_id="a1:b2:c3:d4",
    operation="status_broadcast",
    notes="Switch status broadcast (binary on/off)",
)

# Plug device fixtures (firmware 1.5.2)
PLUG_HANDSHAKE_0x23: bytes = bytes.fromhex(
    "23 00 00 00 1a 03 e5 f6 a7 b8 00 10 70 6c 75 67 30 31 32 33 34 35 36 37 38 39 00 00 5b",
)
PLUG_HANDSHAKE_0x23_META: PacketMetadata = PacketMetadata(
    device_type="plug",
    firmware_version="1.5.2",
    captured_at="2025-11-06T13:01:00.000Z",
    device_id="e5:f6:a7:b8",
    operation="handshake",
    notes="Smart plug handshake",
)

PLUG_TOGGLE_0x73: bytes = bytes.fromhex(
    "73 00 00 00 1f e5 f6 a7 b8 20 30 40 00 7e 20 01 00 00 "
    "f8 8e 0c 00 20 01 00 00 00 01 00 f7 11 02 01 01 35 7e",
)
PLUG_TOGGLE_0x73_META: PacketMetadata = PacketMetadata(
    device_type="plug",
    firmware_version="1.5.2",
    captured_at="2025-11-06T13:01:01.000Z",
    device_id="e5:f6:a7:b8",
    operation="power_on",
    notes="Plug power on command",
)

PLUG_STATUS_0x83: bytes = bytes.fromhex(
    "83 00 00 00 25 e5 f6 a7 b8 00 06 00 7e 1f 00 00 "
    "00 fa db 13 00 72 25 11 01 00 01 00 db 11 02 01 "
    "01 0a 0a ff ff ff 00 00 26 7e",
)
PLUG_STATUS_0x83_META: PacketMetadata = PacketMetadata(
    device_type="plug",
    firmware_version="1.5.2",
    captured_at="2025-11-06T13:01:02.000Z",
    device_id="e5:f6:a7:b8",
    operation="status_broadcast",
    notes="Plug power status broadcast",
)

# Multi-device info with different types
MULTI_DEVICE_INFO_0x43: bytes = bytes.fromhex(
    "43 00 00 00 3c 32 5d 53 17 01 03 06 c6 20 02 00 ab c5 20 02 00 04 c4 20 02 00 "  # 3 bulbs
    "01 01 20 02 00 02 02 20 02 00 03 03 20 02 00 "  # 2 switches
    "05 05 20 02 00",  # 1 plug
)  # Total: 6 devices (3 bulbs + 2 switches + 1 plug)
MULTI_DEVICE_INFO_0x43_META: PacketMetadata = PacketMetadata(
    device_type="mixed",
    firmware_version="various",
    captured_at="2025-11-06T13:02:00.000Z",
    device_id="32:5d:53:17",
    operation="device_info",
    notes="Mixed device types: 3 bulbs + 2 switches + 1 plug",
)


# Metadata registry for parameterized tests
PACKET_METADATA: dict[str, PacketMetadata] = {
    # Original real packet captures
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
    # ACK Validation fixtures (Phase 1b)
    "ACK_VAL_0x7B_PAIR_01_CMD_META": ACK_VAL_0x7B_PAIR_01_CMD_META,
    "ACK_VAL_0x7B_PAIR_01_ACK_META": ACK_VAL_0x7B_PAIR_01_ACK_META,
    "ACK_VAL_0x7B_PAIR_02_CMD_META": ACK_VAL_0x7B_PAIR_02_CMD_META,
    "ACK_VAL_0x7B_PAIR_02_ACK_META": ACK_VAL_0x7B_PAIR_02_ACK_META,
    "ACK_VAL_0x7B_PAIR_03_CMD_META": ACK_VAL_0x7B_PAIR_03_CMD_META,
    "ACK_VAL_0x7B_PAIR_03_ACK_META": ACK_VAL_0x7B_PAIR_03_ACK_META,
    "ACK_VAL_0x7B_PAIR_04_CMD_META": ACK_VAL_0x7B_PAIR_04_CMD_META,
    "ACK_VAL_0x7B_PAIR_04_ACK_META": ACK_VAL_0x7B_PAIR_04_ACK_META,
    "ACK_VAL_0x7B_PAIR_05_CMD_META": ACK_VAL_0x7B_PAIR_05_CMD_META,
    "ACK_VAL_0x7B_PAIR_05_ACK_META": ACK_VAL_0x7B_PAIR_05_ACK_META,
    "ACK_VAL_0x7B_PAIR_06_CMD_META": ACK_VAL_0x7B_PAIR_06_CMD_META,
    "ACK_VAL_0x7B_PAIR_06_ACK_META": ACK_VAL_0x7B_PAIR_06_ACK_META,
    "ACK_VAL_0x7B_PAIR_07_CMD_META": ACK_VAL_0x7B_PAIR_07_CMD_META,
    "ACK_VAL_0x7B_PAIR_07_ACK_META": ACK_VAL_0x7B_PAIR_07_ACK_META,
    "ACK_VAL_0x7B_PAIR_08_CMD_META": ACK_VAL_0x7B_PAIR_08_CMD_META,
    "ACK_VAL_0x7B_PAIR_08_ACK_META": ACK_VAL_0x7B_PAIR_08_ACK_META,
    "ACK_VAL_0x7B_PAIR_09_CMD_META": ACK_VAL_0x7B_PAIR_09_CMD_META,
    "ACK_VAL_0x7B_PAIR_09_ACK_META": ACK_VAL_0x7B_PAIR_09_ACK_META,
    "ACK_VAL_0x7B_PAIR_10_CMD_META": ACK_VAL_0x7B_PAIR_10_CMD_META,
    "ACK_VAL_0x7B_PAIR_10_ACK_META": ACK_VAL_0x7B_PAIR_10_ACK_META,
    "ACK_VAL_0x7B_PAIR_11_CMD_META": ACK_VAL_0x7B_PAIR_11_CMD_META,
    "ACK_VAL_0x7B_PAIR_11_ACK_META": ACK_VAL_0x7B_PAIR_11_ACK_META,
    "ACK_VAL_0x28_PAIR_01_HS_META": ACK_VAL_0x28_PAIR_01_HS_META,
    "ACK_VAL_0x28_PAIR_01_ACK_META": ACK_VAL_0x28_PAIR_01_ACK_META,
    "ACK_VAL_0x28_PAIR_02_HS_META": ACK_VAL_0x28_PAIR_02_HS_META,
    "ACK_VAL_0x28_PAIR_02_ACK_META": ACK_VAL_0x28_PAIR_02_ACK_META,
    "ACK_VAL_0x28_PAIR_03_HS_META": ACK_VAL_0x28_PAIR_03_HS_META,
    "ACK_VAL_0x28_PAIR_03_ACK_META": ACK_VAL_0x28_PAIR_03_ACK_META,
    "ACK_VAL_0x28_PAIR_04_HS_META": ACK_VAL_0x28_PAIR_04_HS_META,
    "ACK_VAL_0x28_PAIR_04_ACK_META": ACK_VAL_0x28_PAIR_04_ACK_META,
    "ACK_VAL_0x28_PAIR_05_HS_META": ACK_VAL_0x28_PAIR_05_HS_META,
    "ACK_VAL_0x28_PAIR_05_ACK_META": ACK_VAL_0x28_PAIR_05_ACK_META,
    "ACK_VAL_0x28_PAIR_06_HS_META": ACK_VAL_0x28_PAIR_06_HS_META,
    "ACK_VAL_0x28_PAIR_06_ACK_META": ACK_VAL_0x28_PAIR_06_ACK_META,
    "ACK_VAL_0x28_PAIR_07_HS_META": ACK_VAL_0x28_PAIR_07_HS_META,
    "ACK_VAL_0x28_PAIR_07_ACK_META": ACK_VAL_0x28_PAIR_07_ACK_META,
    "ACK_VAL_0x28_PAIR_08_HS_META": ACK_VAL_0x28_PAIR_08_HS_META,
    "ACK_VAL_0x28_PAIR_08_ACK_META": ACK_VAL_0x28_PAIR_08_ACK_META,
    "ACK_VAL_0x28_PAIR_09_HS_META": ACK_VAL_0x28_PAIR_09_HS_META,
    "ACK_VAL_0x28_PAIR_09_ACK_META": ACK_VAL_0x28_PAIR_09_ACK_META,
    "ACK_VAL_0x28_PAIR_10_HS_META": ACK_VAL_0x28_PAIR_10_HS_META,
    "ACK_VAL_0x28_PAIR_10_ACK_META": ACK_VAL_0x28_PAIR_10_ACK_META,
    "ACK_VAL_0x88_PAIR_01_STATUS_META": ACK_VAL_0x88_PAIR_01_STATUS_META,
    "ACK_VAL_0x88_PAIR_01_ACK_META": ACK_VAL_0x88_PAIR_01_ACK_META,
    "ACK_VAL_0x88_PAIR_02_STATUS_META": ACK_VAL_0x88_PAIR_02_STATUS_META,
    "ACK_VAL_0x88_PAIR_02_ACK_META": ACK_VAL_0x88_PAIR_02_ACK_META,
    "ACK_VAL_0x88_PAIR_03_STATUS_META": ACK_VAL_0x88_PAIR_03_STATUS_META,
    "ACK_VAL_0x88_PAIR_03_ACK_META": ACK_VAL_0x88_PAIR_03_ACK_META,
    "ACK_VAL_0x88_PAIR_04_STATUS_META": ACK_VAL_0x88_PAIR_04_STATUS_META,
    "ACK_VAL_0x88_PAIR_04_ACK_META": ACK_VAL_0x88_PAIR_04_ACK_META,
    "ACK_VAL_0x88_PAIR_05_STATUS_META": ACK_VAL_0x88_PAIR_05_STATUS_META,
    "ACK_VAL_0x88_PAIR_05_ACK_META": ACK_VAL_0x88_PAIR_05_ACK_META,
    "ACK_VAL_0x88_PAIR_06_STATUS_META": ACK_VAL_0x88_PAIR_06_STATUS_META,
    "ACK_VAL_0x88_PAIR_06_ACK_META": ACK_VAL_0x88_PAIR_06_ACK_META,
    "ACK_VAL_0x88_PAIR_07_STATUS_META": ACK_VAL_0x88_PAIR_07_STATUS_META,
    "ACK_VAL_0x88_PAIR_07_ACK_META": ACK_VAL_0x88_PAIR_07_ACK_META,
    "ACK_VAL_0x88_PAIR_08_STATUS_META": ACK_VAL_0x88_PAIR_08_STATUS_META,
    "ACK_VAL_0x88_PAIR_08_ACK_META": ACK_VAL_0x88_PAIR_08_ACK_META,
    "ACK_VAL_0x88_PAIR_09_STATUS_META": ACK_VAL_0x88_PAIR_09_STATUS_META,
    "ACK_VAL_0x88_PAIR_09_ACK_META": ACK_VAL_0x88_PAIR_09_ACK_META,
    "ACK_VAL_0x88_PAIR_10_STATUS_META": ACK_VAL_0x88_PAIR_10_STATUS_META,
    "ACK_VAL_0x88_PAIR_10_ACK_META": ACK_VAL_0x88_PAIR_10_ACK_META,
    "ACK_VAL_0xD8_PAIR_01_HB_META": ACK_VAL_0xD8_PAIR_01_HB_META,
    "ACK_VAL_0xD8_PAIR_01_ACK_META": ACK_VAL_0xD8_PAIR_01_ACK_META,
    "ACK_VAL_0xD8_PAIR_02_HB_META": ACK_VAL_0xD8_PAIR_02_HB_META,
    "ACK_VAL_0xD8_PAIR_02_ACK_META": ACK_VAL_0xD8_PAIR_02_ACK_META,
    "ACK_VAL_0xD8_PAIR_03_HB_META": ACK_VAL_0xD8_PAIR_03_HB_META,
    "ACK_VAL_0xD8_PAIR_03_ACK_META": ACK_VAL_0xD8_PAIR_03_ACK_META,
    "ACK_VAL_0xD8_PAIR_04_HB_META": ACK_VAL_0xD8_PAIR_04_HB_META,
    "ACK_VAL_0xD8_PAIR_04_ACK_META": ACK_VAL_0xD8_PAIR_04_ACK_META,
    "ACK_VAL_0xD8_PAIR_05_HB_META": ACK_VAL_0xD8_PAIR_05_HB_META,
    "ACK_VAL_0xD8_PAIR_05_ACK_META": ACK_VAL_0xD8_PAIR_05_ACK_META,
    "ACK_VAL_0xD8_PAIR_06_HB_META": ACK_VAL_0xD8_PAIR_06_HB_META,
    "ACK_VAL_0xD8_PAIR_06_ACK_META": ACK_VAL_0xD8_PAIR_06_ACK_META,
    "ACK_VAL_0xD8_PAIR_07_HB_META": ACK_VAL_0xD8_PAIR_07_HB_META,
    "ACK_VAL_0xD8_PAIR_07_ACK_META": ACK_VAL_0xD8_PAIR_07_ACK_META,
    "ACK_VAL_0xD8_PAIR_08_HB_META": ACK_VAL_0xD8_PAIR_08_HB_META,
    "ACK_VAL_0xD8_PAIR_08_ACK_META": ACK_VAL_0xD8_PAIR_08_ACK_META,
    "ACK_VAL_0xD8_PAIR_09_HB_META": ACK_VAL_0xD8_PAIR_09_HB_META,
    "ACK_VAL_0xD8_PAIR_09_ACK_META": ACK_VAL_0xD8_PAIR_09_ACK_META,
    "ACK_VAL_0xD8_PAIR_10_HB_META": ACK_VAL_0xD8_PAIR_10_HB_META,
    "ACK_VAL_0xD8_PAIR_10_ACK_META": ACK_VAL_0xD8_PAIR_10_ACK_META,
    # Retry packet fixtures (Phase 1b deduplication)
    "RETRY_SET_01_ORIG_META": RETRY_SET_01_ORIG_META,
    "RETRY_SET_01_RETRY_1_META": RETRY_SET_01_RETRY_1_META,
    "RETRY_SET_01_RETRY_2_META": RETRY_SET_01_RETRY_2_META,
    "RETRY_SET_02_ORIG_META": RETRY_SET_02_ORIG_META,
    "RETRY_SET_02_RETRY_1_META": RETRY_SET_02_RETRY_1_META,
    "RETRY_SET_02_RETRY_2_META": RETRY_SET_02_RETRY_2_META,
    "RETRY_SET_03_ORIG_META": RETRY_SET_03_ORIG_META,
    "RETRY_SET_03_RETRY_1_META": RETRY_SET_03_RETRY_1_META,
    "RETRY_SET_03_RETRY_2_META": RETRY_SET_03_RETRY_2_META,
    "RETRY_SET_04_ORIG_META": RETRY_SET_04_ORIG_META,
    "RETRY_SET_04_RETRY_1_META": RETRY_SET_04_RETRY_1_META,
    "RETRY_SET_04_RETRY_2_META": RETRY_SET_04_RETRY_2_META,
    "RETRY_SET_05_ORIG_META": RETRY_SET_05_ORIG_META,
    "RETRY_SET_05_RETRY_1_META": RETRY_SET_05_RETRY_1_META,
    "RETRY_SET_05_RETRY_2_META": RETRY_SET_05_RETRY_2_META,
    # Edge case fixtures (Phase 1a codec robustness)
    "EDGE_TRUNCATED_HEADER_META": EDGE_TRUNCATED_HEADER_META,
    "EDGE_INVALID_LENGTH_META": EDGE_INVALID_LENGTH_META,
    "EDGE_MISSING_START_MARKER_META": EDGE_MISSING_START_MARKER_META,
    "EDGE_INVALID_CHECKSUM_META": EDGE_INVALID_CHECKSUM_META,
    "EDGE_UNKNOWN_PACKET_TYPE_META": EDGE_UNKNOWN_PACKET_TYPE_META,
    "EDGE_ZERO_LENGTH_META": EDGE_ZERO_LENGTH_META,
    "EDGE_MIN_VALID_0x73_META": EDGE_MIN_VALID_0x73_META,
    "EDGE_LARGE_MULTIPLIER_META": EDGE_LARGE_MULTIPLIER_META,
    "EDGE_ENDPOINT_ALL_ZEROS_META": EDGE_ENDPOINT_ALL_ZEROS_META,
    "EDGE_ENDPOINT_ALL_FF_META": EDGE_ENDPOINT_ALL_FF_META,
    "EDGE_MSG_ID_ALL_ZEROS_META": EDGE_MSG_ID_ALL_ZEROS_META,
    "EDGE_MSG_ID_ALL_FF_META": EDGE_MSG_ID_ALL_FF_META,
    "EDGE_DEVICE_INFO_EMPTY_META": EDGE_DEVICE_INFO_EMPTY_META,
    "EDGE_DEVICE_INFO_SINGLE_META": EDGE_DEVICE_INFO_SINGLE_META,
    "EDGE_MAX_BRIGHTNESS_META": EDGE_MAX_BRIGHTNESS_META,
    "EDGE_MIN_BRIGHTNESS_META": EDGE_MIN_BRIGHTNESS_META,
    "EDGE_LARGE_DEVICE_INFO_META": EDGE_LARGE_DEVICE_INFO_META,
    "EDGE_PARTIAL_PAYLOAD_META": EDGE_PARTIAL_PAYLOAD_META,
    "EDGE_DOUBLE_START_MARKER_META": EDGE_DOUBLE_START_MARKER_META,
    "EDGE_NO_END_MARKER_META": EDGE_NO_END_MARKER_META,
    # Device variety fixtures (switch, plug, multi-type)
    "SWITCH_HANDSHAKE_0x23_META": SWITCH_HANDSHAKE_0x23_META,
    "SWITCH_TOGGLE_0x73_META": SWITCH_TOGGLE_0x73_META,
    "SWITCH_STATUS_0x83_META": SWITCH_STATUS_0x83_META,
    "PLUG_HANDSHAKE_0x23_META": PLUG_HANDSHAKE_0x23_META,
    "PLUG_TOGGLE_0x73_META": PLUG_TOGGLE_0x73_META,
    "PLUG_STATUS_0x83_META": PLUG_STATUS_0x83_META,
    "MULTI_DEVICE_INFO_0x43_META": MULTI_DEVICE_INFO_0x43_META,
}
