# Cync Protocol Structure - Validated

**Phase**: 0.5 | **Date**: 2025-11-07 | **Status**: ✅ Validated against 24,960 packets

---

## Packet Header (5 bytes)

```text
[type][0x00][0x00][len_mult][base_len]
```

**Length calculation**: `data_length = (byte[3] × 256) + byte[4]`
**Total packet**: `5 + data_length` (header NOT included in data_length)

---

## Packet Types

| Type | Name             | Direction | Framed | Size   |
| ---- | ---------------- | --------- | ------ | ------ |
| 0x23 | HANDSHAKE        | DEV→CLOUD | No     | 31     |
| 0x28 | HELLO_ACK        | CLOUD→DEV | No     | 7      |
| 0x43 | DEVICE_INFO      | DEV→CLOUD | No     | 12-145 |
| 0x48 | INFO_ACK         | CLOUD→DEV | No     | 8-16   |
| 0x73 | DATA_CHANNEL     | Both      | Yes    | 20-150 |
| 0x7B | DATA_ACK         | Both      | No     | 12     |
| 0x83 | STATUS_BROADCAST | DEV→CLOUD | Yes    | 42-73  |
| 0x88 | STATUS_ACK       | CLOUD→DEV | No     | 8-16   |
| 0xD3 | HEARTBEAT_DEV    | DEV→CLOUD | No     | 5      |
| 0xD8 | HEARTBEAT_CLOUD  | CLOUD→DEV | No     | 5      |

**Framed**: Packets with 0x7e markers and checksum (0x73, 0x83 only)

---

## Field Extraction

### Byte Positions (Validated)

| Field    | Position     | Size    | Packet Types |
| -------- | ------------ | ------- | ------------ |
| endpoint | bytes[5:10]  | 5 bytes | All          |
| msg_id   | bytes[10:12] | 2 bytes | 0x73, 0x83   |

**No overlap**: Clean byte boundaries confirmed. Byte 12 is padding (0x00), byte 13 is 0x7e marker.

### Extraction Code

```python
# All packet types
packet_type = packet[0]
data_length = (packet[3] * 256) + packet[4]
endpoint = packet[5:10]  # 5 bytes

# Data packets (0x73, 0x83)
msg_id = packet[10:12]   # 2 bytes (byte 12 is 0x00 padding, byte 13 is 0x7e marker)
```

---

## Framing and Checksums

### Framed Packets (0x73, 0x83)

**Structure**:

```text
[header(5)][endpoint(5)][msg_id(2)][padding(1)][0x7e][skip 6][data...][checksum][0x7e]
```

Note: Byte 12 is always 0x00 (padding), byte 13 is the 0x7e start marker.

**Checksum Algorithm**:

```python
def calculate_checksum_between_markers(packet: bytes) -> int:
    start = packet.find(0x7E)
    end = packet.rfind(0x7E)
    return sum(packet[start+6:end-1]) % 256
```

**Validation**: 100% match rate (13/13 packets)

### Unframed Packets

No 0x7e markers, no checksum: 0x23, 0x28, 0x43, 0x48, 0x88, 0xD3, 0xD8

---

## ACK Structure

### msg_id Presence by ACK Type

| ACK Type | msg_id? | Position | Matching Strategy |
| -------- | ------- | -------- | ----------------- |
| 0x28     | NO      | N/A      | FIFO queue        |
| 0x7B     | YES     | byte 10  | Parallel (msg_id) |
| 0x88     | NO      | N/A      | FIFO queue        |
| 0xD8     | NO      | N/A      | FIFO queue        |

**Architecture**: Hybrid ACK matching required.

---

## Implementation Constants

```python
# Buffer sizes
MAX_PACKET_SIZE = 4096  # Validated safe (max observed: 145 bytes)

# Routing
ROUTING_BYTE = 0x00  # Constant 5th byte of endpoint

# Framing markers
FRAME_MARKER = 0x7E

# Packet types
HANDSHAKE = 0x23
HELLO_ACK = 0x28
DEVICE_INFO = 0x43
INFO_ACK = 0x48
DATA_CHANNEL = 0x73
DATA_ACK = 0x7B
STATUS_BROADCAST = 0x83
STATUS_ACK = 0x88
HEARTBEAT_DEV = 0xD3
HEARTBEAT_CLOUD = 0xD8
```

---

## Timing Recommendations

| Operation | Timeout | Basis                     |
| --------- | ------- | ------------------------- |
| ACK wait  | 128ms   | p99 (51ms) × 2.5          |
| Handshake | 320ms   | ACK timeout × 2.5         |
| Heartbeat | 10s     | max(ACK timeout × 3, 10s) |

**Reference**: See `ack-latency-measurements.md` for detailed measurements.

---

## Edge Cases

- **0x7e in payload**: Use structural position (beyond byte 10)
- **Unframed packets**: Check packet type before checksum validation
- **Variable length**: Use header length field, validate < MAX_PACKET_SIZE
- **Missing fields**: Raise `PacketDecodeError` for malformed packets

---

## Phase 1 Implementation Guide

### Phase 1a (Codec)

- Copy checksum algorithm (validated)
- Use byte positions: endpoint[5:10], msg_id[10:12]
- Validate packet length < 4096 bytes
- Test with fixtures from `tests/fixtures/real_packets.py`

### Phase 1b (Transport)

- Hybrid ACK matching (0x7B parallel, others FIFO)
- Timeout: 128ms default (monitor in Phase 1d)
- Full Fingerprint dedup (all 4 fields)

---

**Reference**: See `phase-1-handoff.md` for quick reference and `validation-report.md` for detailed findings.
