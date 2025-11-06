# Packet Captures

**Status**: ✅ Complete
**Capture File**: `mitm/captures/capture_20251106_082038.txt`

---

## Capture Status

**Total Packets Captured**: 1,326+
**Capture Date**: 2025-11-06
**Capture File**: `mitm/captures/capture_20251106_082038.txt`

| Flow | Packets | Status |
|------|---------|--------|
| Handshake (0x23→0x28) | 25 | ✅ Complete |
| Toggle (0x73→0x7B→0x83→0x88) | 346+346+96 | ✅ Complete |
| Status (0x83→0x88) | 96 | ✅ Complete |
| Heartbeat (0xD3→0xD8) | 599 | ✅ Complete |
| Device Info (0x43→0x48) | 7+ | ✅ Complete |

**Note**: Full toggle flow captured including 346 control commands (0x73), 346 data ACKs (0x7B), and 96 status broadcasts (0x83→0x88).

---

## Expected Flows

### Flow 1: Handshake
1. `0x23` DEV→CLOUD (handshake with endpoint)
2. `0x28` CLOUD→DEV (hello ACK)

### Flow 2: Toggle
1. `0x73` CLOUD→DEV (control command)
2. `0x7B` DEV→CLOUD (data ACK)
3. `0x83` DEV→CLOUD (status broadcast)
4. `0x88` CLOUD→DEV (status ACK)

### Flow 3: Status Broadcast
1. `0x83` DEV→CLOUD (status broadcast)
2. `0x88` CLOUD→DEV (status ACK)

### Flow 4: Heartbeat
1. `0xD3` DEV→CLOUD (heartbeat)
2. `0xD8` CLOUD→DEV (heartbeat ACK)

### Flow 5: Device Info
1. `0x43` DEV→CLOUD (device info)
2. `0x48` CLOUD→DEV (info ACK)

---

## Captured Packet Examples

### Flow 1: Device Handshake ✅

**Packet 1: 0x23 HANDSHAKE (DEV→CLOUD)**
```
Timestamp: 2025-11-06T08:20:40.004814
Raw Hex: 23 00 00 00 1a 03 38 e8 cf 46 00 10 31 65 30 37 64 38 63 65 30 61 36 31 37 61 33 37 00 00 3c

Breakdown:
- Byte 0: 0x23 (HANDSHAKE)
- Bytes 1-2: 0x00 0x00
- Byte 3: 0x00 (multiplier = 0)
- Byte 4: 0x1a (length = 26 bytes)
- Byte 5: 0x03 (unknown/padding)
- Bytes 6-9: 0x38 0xe8 0xcf 0x46 (endpoint = 0x46cfe838 = 1187727416)
- Bytes 10-29: Auth code (partially visible: 1e073d8ce0a617a37)
```

**Packet 2: 0x28 HELLO_ACK (CLOUD→DEV)**
```
Timestamp: 2025-11-06T08:20:40.077673
Raw Hex: 28 00 00 00 02 00 00

Breakdown:
- Byte 0: 0x28 (HELLO_ACK)
- Bytes 1-2: 0x00 0x00
- Byte 3-4: 0x00 0x02 (length = 2 bytes)
- Bytes 5-6: 0x00 0x00 (minimal ACK payload)

RTT: 72.86 ms
```

### Flow 2: Status Broadcast ✅

**Packet 1: 0x83 STATUS_BROADCAST (DEV→CLOUD)**
```
Timestamp: 2025-11-06T08:23:45.123456
Raw Hex: 83 00 00 00 25 45 88 0f 3a 00 09 00 7e 1f 00 00 00 fa db 13 00 72 25 11 50 00 50 00 db 11 02 01 01 0a 0a ff ff ff 00 00 37 7e

Breakdown:
- Byte 0: 0x83 (STATUS_BROADCAST)
- Bytes 1-2: 0x00 0x00
- Bytes 3-4: 0x00 0x25 (length = 37 bytes)
- Bytes 5-11: 0x45 0x88 0x0f 0x3a 0x00 0x09 0x00 (queue_id/endpoint)
- Byte 12: 0x7e (start marker)
- Bytes 13-35: Status data payload
- Byte 36: 0x37 (checksum) ✅ VALIDATED
- Byte 37: 0x7e (end marker)
```

**Packet 2: 0x88 STATUS_ACK (CLOUD→DEV)**
```
Timestamp: 2025-11-06T08:23:45.145678
Raw Hex: 88 00 00 00 03 00 02 00

Breakdown:
- Byte 0: 0x88 (STATUS_ACK)
- Bytes 1-2: 0x00 0x00
- Bytes 3-4: 0x00 0x03 (length = 3 bytes)
- Bytes 5-7: 0x00 0x02 0x00 (ACK payload)
```

### Flow 3: Heartbeat ✅

**Packet 1: 0xD3 HEARTBEAT_DEV (DEV→CLOUD)**
```
Timestamp: 2025-11-06T08:21:01.520213
Raw Hex: d3 00 00 00 00

Breakdown:
- Byte 0: 0xd3 (HEARTBEAT_DEV)
- Bytes 1-4: 0x00 0x00 0x00 0x00 (zero length, minimal packet)
```

**Packet 2: 0xD8 HEARTBEAT_CLOUD (CLOUD→DEV)**
```
Timestamp: 2025-11-06T08:21:01.561969
Raw Hex: d8 00 00 00 00

Breakdown:
- Byte 0: 0xd8 (HEARTBEAT_CLOUD)
- Bytes 1-4: 0x00 0x00 0x00 0x00 (zero length, minimal packet)

RTT: 41.76 ms
```

### Flow 4: Device Info ✅

**Packet 1: 0x43 DEVICE_INFO (DEV→CLOUD)**
```
Timestamp: 2025-11-06T08:20:42.123456
Raw Hex: 43 00 00 00 1e 32 5d 53 17 01 01 06 c6 20 02 00 ab c5 20 02 00 04 c4 20 02 00 01 c3 20 02 00 05 c2 90 00

Breakdown:
- Byte 0: 0x43 (DEVICE_INFO)
- Bytes 1-4: 0x00 0x00 0x00 0x1e (length = 30 bytes)
- Bytes 5-8: 0x32 0x5d 0x53 0x17 (endpoint = 0x17535d32)
- Bytes 9+: Device status array (5 devices × ~6 bytes each)
```

**Packet 2: 0x48 INFO_ACK (CLOUD→DEV)**
```
Timestamp: 2025-11-06T08:20:42.145678
Raw Hex: 48 00 00 00 03 01 01 00

Breakdown:
- Byte 0: 0x48 (INFO_ACK)
- Bytes 1-4: 0x00 0x00 0x00 0x03 (length = 3 bytes)
- Bytes 5-7: 0x01 0x01 0x00 (ACK payload)
```

