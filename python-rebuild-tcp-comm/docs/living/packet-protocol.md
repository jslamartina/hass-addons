# Cync Protocol Reference

## Universal Header (5 bytes)

| Byte | Field       | Description                                                |
| ---- | ----------- | ---------------------------------------------------------- |
| 0    | packet_type | 0x23, 0x28, 0x43, 0x48, 0x73, 0x7B, 0x83, 0x88, 0xD3, 0xD8 |
| 1-2  | padding     | Always 0x00 0x00                                           |
| 3-4  | data_length | (byte[3] \* 256) + byte[4]                                 |

Total packet size = 5 + data_length

## Packet Types

| Type | Name             | Direction     | Framed | Size (bytes) |
| ---- | ---------------- | ------------- | ------ | ------------ |
| 0x23 | HANDSHAKE        | DEV→CLOUD     | No     | 31           |
| 0x28 | HELLO_ACK        | CLOUD→DEV     | No     | 7            |
| 0x43 | DEVICE_INFO      | DEV→CLOUD     | No     | 12-145       |
| 0x48 | INFO_ACK         | CLOUD→DEV     | No     | 8-16         |
| 0x73 | DATA_CHANNEL     | Bidirectional | Yes    | Variable     |
| 0x7B | DATA_ACK         | DEV→CLOUD     | No     | 12 or 36     |
| 0x83 | STATUS_BROADCAST | DEV→CLOUD     | Yes    | 42-73        |
| 0x88 | STATUS_ACK       | CLOUD→DEV     | No     | 8-16         |
| 0xD3 | HEARTBEAT_DEV    | DEV→CLOUD     | No     | 5            |
| 0xD8 | HEARTBEAT_CLOUD  | CLOUD→DEV     | No     | 5            |

**Framed packets:** 0x73, 0x83 (have 0x7e markers and checksums)

## Field Positions

### Endpoint (5 bytes)

Device address extracted as bytes[5:10] in all packet types.

**Byte Position**: bytes[5:10] (5 bytes total)

- Handshake (0x23): bytes[5:10] (validated in HANDSHAKE_0x23_DEV_TO_CLOUD)
- Data packets (0x73, 0x83): bytes[5:10] (validated in STATUS_BROADCAST_0x83)

**Extraction**:

```python
endpoint = packet[5:10]  # All packet types - position is IDENTICAL
```

**Note**: Position is IDENTICAL across all packet types

### Message ID (2 bytes)

Position in 0x73/0x83 packets: bytes[10:11] (2 bytes)

```python
msg_id = data_packet[10:11]  # 2 bytes
```

**Note**: Corrected from earlier 3-byte assumption. See `src/protocol/cync_protocol.py` extract_endpoint_and_msg_id() for implementation.

### Device ID (2 bytes)

Encoding: Little-endian, range 10-255

```python
device_id_bytes = device_id.to_bytes(2, byteorder="little")
```

## Framing Structure

Framed packets (0x73, 0x83):

```python

[header][endpoint][msg_id][padding][0x7e][data...][checksum][0x7e]
0-4     5-9       10-11   12       13     14...    N-1       N

```

**Important**: 0x73 packets include padding byte at position 12, but 0x83 STATUS_BROADCAST packets do NOT:

- **0x73 DATA_CHANNEL**: `[endpoint][msg_id][padding=0x00][0x7e][data...]`
- **0x83 STATUS_BROADCAST**: `[endpoint][msg_id][0x7e][data...]` (no padding)

See `src/protocol/cync_protocol.py` encode_status_broadcast() vs encode_data_packet() for implementation details.

## Checksum Algorithm

Applies to: 0x73, 0x83 only

```python
def calculate_checksum(packet: bytes) -> int:
    start = packet.find(0x7e)
    end = packet.rfind(0x7e)
    data_to_sum = packet[start + 6 : end - 1]
    return sum(data_to_sum) % 256
```

Checksum position: byte before final 0x7e marker

## Command Types

| Command      | Bytes    | Valid For                      | Response       |
| ------------ | -------- | ------------------------------ | -------------- |
| POWER_TOGGLE | f8 d0 0d | Bulbs, lights, switches, plugs | 36 bytes       |
| SET_MODE     | f8 8e 0c | Switches only                  | 12 or 36 bytes |

## Response Types

### Pure ACK (12 bytes)

- 0x7B DATA_ACK only
- Meaning: Command invalid OR device not found

### Compound (36 bytes)

- Bytes 0-23: 0x73 DATA_CHANNEL (status update)
- Bytes 24-35: 0x7B DATA_ACK
- Meaning: Command valid AND device exists

```python
def handle_response(response: bytes) -> tuple[bool, dict]:
    if len(response) == 12:
        return (False, {"type": "pure_ack"})
    elif len(response) == 36:
        return (True, {"status": response[0:24], "ack": response[24:36]})
    else:
        return (False, {"type": "unknown"})
```

## ACK Matching

| ACK Type             | msg_id Present | Position      | Strategy     |
| -------------------- | -------------- | ------------- | ------------ |
| 0x28 HELLO_ACK       | No             | N/A           | FIFO queue   |
| 0x7B DATA_ACK        | Yes            | Bytes [10:11] | msg_id match |
| 0x88 STATUS_ACK      | No             | N/A           | FIFO queue   |
| 0xD8 HEARTBEAT_CLOUD | No             | N/A           | FIFO queue   |

```python
def extract_ack_msg_id(ack_packet: bytes) -> bytes:
    return ack_packet[10:11]  # 0x7B only - 2 bytes
```

## Implementation

### CyncProtocol Class

Location: `src/protocol/cync_protocol.py`

**Decoders:** All packet types (0x23, 0x43, 0x73, 0x7B, 0x83, 0xD3, etc.)
**Encoders:** 0x23 (handshake), 0x73 (data), 0x83 (status broadcast), 0xD3 (heartbeat)

### PacketFramer

Location: `src/protocol/packet_framer.py`

Handles TCP stream fragmentation:

- Buffers incomplete packets
- Extracts complete packets from stream
- Per-connection state isolation
- MAX_PACKET_SIZE: 4096 bytes

### Custom Exceptions

Location: `src/protocol/exceptions.py`

```python
CyncProtocolError          # Base exception
├── PacketDecodeError      # Malformed packets, invalid checksums
└── PacketFramingError     # Buffer overflow, oversized packets
```

All exceptions include:

- `reason: str` - Machine-readable error code
- `data_preview: bytes` - First 16 bytes of problematic data

### CodecValidatorPlugin

Location: `mitm/validation/codec_validator.py`

MITM proxy plugin for live traffic validation:

- Uses CyncProtocol + PacketFramer
- Validates packets during capture
- Per-connection framer isolation
- Logs validation errors with context

**Usage:**

```bash
./scripts/start-mitm-local.sh --enable-codec-validation
```
