# Packet Captures

**Status**: ✅ Complete
**Total Packets**: 24,960 analyzed across 8 capture files

---

## Capture Summary

| Flow                         | Packets | Status      |
| ---------------------------- | ------- | ----------- |
| Handshake (0x23→0x28)        | 572     | ✅ Complete |
| Toggle (0x73→0x7B→0x83→0x88) | 788     | ✅ Complete |
| Status (0x83→0x88)           | 2,680   | ✅ Complete |
| Heartbeat (0xD3→0xD8)        | 21,441  | ✅ Complete |
| Device Info (0x43→0x48)      | 7+      | ✅ Complete |

**Total analyzed**: 24,960 packets from 9 devices

---

## Validated Findings

### Endpoint Derivation (5 bytes)

**Position**: bytes[5:10] in all packet types
**Pattern**: Consistent 5-byte identifier
**No derivation needed**: Same field in handshake and data packets

**Extraction**:

```python
endpoint = packet[5:10]  # 5 bytes (bytes 5-9)
msg_id = packet[10:13]   # 3 bytes (bytes 10-12)
# No overlap confirmed
```

### ACK Structure Validation

| ACK Type | Sample Size | msg_id Present? | Position | Matching Strategy |
| -------- | ----------- | --------------- | -------- | ----------------- |
| 0x28     | 25          | NO              | N/A      | FIFO queue        |
| 0x7B     | 9           | YES             | byte 10  | Parallel (msg_id) |
| 0x88     | 97          | NO              | N/A      | FIFO queue        |
| 0xD8     | 4,415       | NO              | N/A      | FIFO queue        |

**Result**: Hybrid ACK matching required (see validation-report.md).

---

## Example Packets

### 0x23 Handshake (DEV→CLOUD)

```text
23 00 00 00 1a 45 88 0f 3a 00 00 10 31 65...
│  │     │  │  └─endpoint (5 bytes)
│  │     │  └─length: 26 bytes
│  │     └─multiplier: 0
│  └─padding
└─type: 0x23
```

### 0x73 Data Packet (CLOUD→DEV)

```text
73 00 00 00 1e 45 88 0f 3a 00 09 00 00 7e 0d 01...
│  │     │  │  └─endpoint└─msg_id─┘
│  │     │  └─length: 30 bytes
│  │     └─multiplier: 0
│  └─padding
└─type: 0x73
```

**Byte positions validated**:

- endpoint: bytes[5:10]
- msg_id: bytes[10:13]
- 0x7e marker: byte 13

### 0x7B Data ACK (DEV→CLOUD)

```text
7b 00 00 00 07 45 88 0f 3a 00 09 00
│  │     │  │  └─endpoint└─msg_id[10:13]
│  │     │  └─length: 7 bytes
│  └─padding
└─type: 0x7B
```

**msg_id position**: bytes[10:13] - 3 bytes (validated 9/9 captures)

### 0xD8 Heartbeat ACK (CLOUD→DEV)

```text
d8 00 00 00 00
│  │     │  └─length: 0 bytes
│  └─padding
└─type: 0xD8
```

**Minimal packet**: 5 bytes, no msg_id field

---

## Capture Files

**Location**: `/workspaces/hass-addons/python-rebuild-tcp-comm/captures/`

**Files**:

- `capture_20251107_003432.txt` (3,313 packets)
- `capture_20251107_004629.txt` (1,135 packets)
- `capture_20251107_011532.txt` (3,328 packets)
- `capture_20251107_094857.txt` (924 packets)
- `capture_20251107_152132.txt` (7,312 packets)
- `capture_20251107_160329.txt` (1,254 packets)
- `capture_20251107_232328.txt` (3,313 packets)
- `capture_20251108_005059.txt` (4,381 packets)

**Total**: 24,960 packets (11MB across 8 files)

---

## Analysis Tools

**Parser**: `mitm/parse-capture.py`

**Usage**:

```bash
# Extract ACK pairs
python mitm/parse-capture.py --type ack-pairs capture_*.txt

# Filter by packet type
python mitm/parse-capture.py --filter 0x7B capture_*.txt

# Statistics
python mitm/parse-capture.py --stats capture_*.txt
```

---

## Key Validation Results

✅ **Endpoint structure**: 5 bytes at bytes[5:10], no derivation needed
✅ **msg_id position**: bytes[10:13] (clean boundary, no overlap)
✅ **Hybrid ACK matching**: 0x7B has msg_id, others don't
✅ **Checksum algorithm**: 100% validated
✅ **Protocol stability**: 0 malformed packets in 24,960 analyzed

**Reference**: See `validation-report.md` for detailed analysis and `phase-1-handoff.md` for quick reference.
