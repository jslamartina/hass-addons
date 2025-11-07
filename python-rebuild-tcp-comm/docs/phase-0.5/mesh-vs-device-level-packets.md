# Mesh-Level vs Device-Level Packet Types

**Date:** 2025-11-07
**Source:** Phase 0.5 Deliverable #8 - Empirical Analysis
**Capture File:** `capture_20251107_014534.txt` (22 Wi-Fi bridges, 25+ total devices)

---

## ⚠️ CRITICAL: Command Endpoint Targeting (Updated 2025-11-07)

### Commands MUST target bridge endpoints, NOT mesh coordinator endpoint

### Endpoint Usage Rules

#### For SENDING commands (CLOUD→DEV)

- ✅ Target: **Bridge endpoints** (e.g., `38:e8:cf:46`, `45:88:0f:3a`)
- ❌ Do NOT target: Mesh coordinator endpoint (e.g., `1b:dc:da:3e`)

### For RECEIVING status (DEV→CLOUD)

- Bridges report status using **mesh coordinator endpoint** in 0x73/0x7B packets
- Each bridge has unique **own endpoint** in 0x83 packets

### Test Results

| Target Endpoint            | Command      | Response       | Result      |
| -------------------------- | ------------ | -------------- | ----------- |
| Bridge (`38:e8:cf:46`)     | POWER_TOGGLE | Compound (36B) | ✅ Works    |
| Mesh Coord (`1b:dc:da:3e`) | POWER_TOGGLE | Pure ACK (12B) | ❌ Rejected |

**Reason:** Mesh coordinator endpoint is for **status reporting only**, not command execution.

### Implementation

```python
## Get bridge endpoint from 0x23 handshake (bytes 6-9)
bridge_endpoint = handshake_packet[6:10]

## Send command to bridge endpoint, NOT mesh coordinator
command_packet = build_command(
    endpoint=bridge_endpoint,  # Use bridge endpoint
    device_id=target_device_id,
    command_type=POWER_TOGGLE
)
```

---

## Executive Summary

Cync protocol packets fall into two behavioral categories:

1. **MESH-LEVEL** - Multiple Wi-Fi bridges send identical payloads for the same mesh event
2. **DEVICE-LEVEL** - One Wi-Fi bridge per endpoint (1:1 mapping)

**Critical for Deduplication**: Mesh-level packets REQUIRE payload hash deduplication to avoid processing the same logical event multiple times.

---

## Packet Type Classification

### ✅ MESH-LEVEL PACKETS (Multi-Bridge Behavior)

These packets show **N bridges → 1 endpoint** (multiple TCP connections report same endpoint).

#### **0x73 - Compound Status Packets** ⚠️ HIGHEST DEDUP IMPACT

**Direction:** DEV→CLOUD (status reporting)

**⚠️ Note:** 0x73 packets are bi-directional but serve different purposes:

- **CLOUD→DEV**: Commands sent TO devices (target bridge endpoints)
- **DEV→CLOUD**: Status reported FROM devices (use mesh coordinator endpoint)

### Observed Behavior (DEV→CLOUD status)

- **18 Wi-Fi bridges** sending to **1 endpoint** (`1b:dc:da:3e`)
- All 18 bridges sent **identical payloads** (71 packets with same payload hash)
- Each bridge had **different msg_id** (15 unique msg_ids observed)

### Deduplication Impact

- **WITHOUT payload hash dedup**: Process same event 18 times (1,700% overhead!)
- **WITH payload hash dedup**: 98.6% dedup rate (70 out of 71 packets filtered)

### Use Case

- Mesh status updates (e.g., "Light 5 in mesh is ON")
- Bridge-originated status broadcasts
- Contains 0x73 status (24 bytes) + 0x7B ACK (12 bytes) in 36-byte compound packet

### Endpoint Meaning (DEV→CLOUD)

- Represents **mesh coordinator's ID** (not bridge's own ID)
- All bridges in mesh report this shared endpoint
- **DO NOT use this endpoint for sending commands** (see warning above)

---

#### **0x7B - ACK Packets** (Standalone)

#### Observed Behavior

- **8 TCP connections** to **1 endpoint** (`1b:dc:da:3e`)
- Multi-bridge pattern detected

### Use Case

- Acknowledgment packets for commands
- Can be sent standalone or embedded in 0x73 compound packets

### Endpoint Meaning

- Same as 0x73 - mesh coordinator ID

---

#### **0x23 - Auth Packets**

#### Observed Behavior

- **24 endpoints** from **26 connections**
- **2 endpoints** had multiple connections (max 2 connections per endpoint)

### Use Case

- Device authentication to cloud
- Sets the endpoint for the session

### Endpoint Meaning

- Device's own identifier during auth phase
- Some multi-connection behavior suggests mesh coordination

---

#### **0x43 - Multi-Device Status Broadcasts**

#### Observed Behavior

- **24 endpoints** from **25 connections**
- **1 endpoint** had multiple connections (max 2 connections per endpoint)

### Use Case

- Bulk status updates (can contain multiple devices in one packet)
- Each status entry is 19 bytes (device ID, state, brightness, temp, RGB, etc.)

### Endpoint Meaning

- Bridge's own ID or mesh coordinator ID

**Reference:** See `packet_structure.md` for 0x43 status structure details.

---

### ✅ DEVICE-LEVEL PACKETS (Single-Bridge Behavior)

These packets show **1:1 bridge-to-endpoint mapping** (no multi-bridge duplication).

#### **0x83 - Bridge Health/Status Packets** ✓ NO DEDUP NEEDED

#### Observed Behavior

- **22 TCP connections** to **22 unique endpoints**
- **ZERO endpoints** with multiple connections
- **Perfect 1:1 mapping**

### Deduplication Impact

- **NO deduplication needed** (each packet is from a unique bridge)

### Use Case

- Bridge firmware version
- Bridge self-status updates
- Device joining mesh events

### Endpoint Meaning

- Bridge's **own identifier** (not mesh coordinator)
- Each bridge reports its own ID in 0x83 packets

**Reference:** See `packet_structure.md` for 0x83 details.

---

#### **0xD3 - Ping Packets** ✓ NO DEDUP NEEDED

#### Observed Behavior

- **1 connection** to **1 endpoint**
- Device-level behavior (1:1 mapping)

### Use Case

- Keepalive ping from device to server

**Response:** Server sends 0xD8 with no data: `d8 00 00 00 00`

---

## Summary Table

| Packet Type | Level        | Max Bridges per Endpoint | Dedup Required? | Primary Use                   |
| ----------- | ------------ | ------------------------ | --------------- | ----------------------------- |
| **0x73**    | MESH         | **18** ⚠️                | **✅ CRITICAL** | Compound status (mesh events) |
| **0x7B**    | MESH         | 8                        | ✅ Yes          | ACK packets (standalone)      |
| **0x23**    | MESH (minor) | 2                        | ⚠️ Optional     | Authentication                |
| **0x43**    | MESH (minor) | 2                        | ⚠️ Optional     | Multi-device status           |
| **0x83**    | DEVICE       | 1                        | ❌ No           | Bridge health/status          |
| **0xD3**    | DEVICE       | 1                        | ❌ No           | Ping/keepalive                |

---

## Topology Implications

### Network Structure

In the user's network (25 Wi-Fi bridges, 29 Bluetooth-only devices):

```python

┌────────────────────────────────────────────────────┐
│ Large Mesh Network (Endpoint: 1b:dc:da:3e)        │
├────────────────────────────────────────────────────┤
│                                                     │
│  18 Wi-Fi Bridges ──┬── All report: 1b:dc:da:3e   │
│                     └── Each has independent:      │
│                          • TCP connection          │
│                          • msg_id counter          │
│                                                     │
│  + N Bluetooth-only devices (no TCP)               │
│                                                     │
└────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────┐
│ Small Mesh Networks (Various endpoints)           │
├────────────────────────────────────────────────────┤
│                                                     │
│  2 Wi-Fi Bridges ──┬── Report same endpoint       │
│                    └── 0x23 and 0x43 packets       │
│                                                     │
└────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────┐
│ Standalone Bridges (22 unique endpoints)          │
├────────────────────────────────────────────────────┤
│                                                     │
│  22 Wi-Fi Bridges ──┬── Each reports own ID       │
│                     └── 0x83 packets               │
│                                                     │
└────────────────────────────────────────────────────┘

```

---

## Key Findings for Phase 1b Implementation

### 1. Payload Hash Deduplication is ESSENTIAL

#### Without it

- Single mesh event (e.g., "Light 5 ON") triggers 18 identical packets
- Each processed separately → 1,700% CPU overhead
- 18 redundant Home Assistant state updates

### With it

- First packet: Process ✅
- Next 17 packets: Deduplicate (same payload hash) ✅
- 94% reduction in redundant processing

### 2. msg_id is UNSUITABLE for Deduplication

#### Why

- Each Wi-Fi bridge has **independent msg_id counter**
- 18 bridges send identical payload with **different msg_ids**
- msg_id-based dedup would process all 18 (FAIL)

### Correct Use

- msg_id is a **sequential counter** (+1 per transaction per bridge)
- Used for **ACK matching** (0x7B ack msg_id matches 0x73 command msg_id)
- Used for **transaction tracking** within a single bridge's stream

### 3. Endpoint Meaning is Context-Dependent

| Packet Type | Endpoint Represents                |
| ----------- | ---------------------------------- |
| 0x73, 0x7B  | Mesh coordinator ID (shared)       |
| 0x83        | Bridge's own ID (unique)           |
| 0x23, 0x43  | Context-dependent (mixed behavior) |

---

## Recommended Deduplication Strategy

```python
def get_dedup_key(packet: bytes) -> str:
    """
    Generate deduplication key for Cync protocol packets.

    Strategy:
    - MESH packets (0x73): Use payload hash (multi-bridge safe)
    - DEVICE packets (0x83): Use msg_id (no multi-bridge issue)
    """
    packet_type = packet[0]

    if packet_type == 0x73:
        # MESH-LEVEL: Multiple bridges send identical payloads
        # Must use payload hash to deduplicate across bridges
        payload = extract_payload(packet)
        payload_hash = hashlib.sha256(payload).hexdigest()[:16]
        return f"73:{payload_hash}"

    elif packet_type == 0x83:
        # DEVICE-LEVEL: 1:1 bridge-to-endpoint mapping
        # msg_id is stable within single bridge's stream
        endpoint = packet[5:9].hex(":")
        msg_id = packet[9:12].hex(":")
        return f"83:{endpoint}:{msg_id}"

    else:
        # Default: payload hash (safest for unknown packet types)
        payload = extract_payload(packet)
        payload_hash = hashlib.sha256(payload).hexdigest()[:16]
        return f"{packet_type:02x}:{payload_hash}"
```

---

## References

- **Phase 0.5 Deliverable #8**: `docs/phase-0.5/deduplication-strategy.md`
- **Topology Analysis**: `working-files/202511070013_retry_field_verification/202511070230_TOPOLOGY_EXPLAINED.md`
- **Capture Data**: `captures/capture_20251107_014534.txt`
- **Packet Structure**: `docs/protocol/packet_structure.md`

---

## Testing Evidence

### Proof of Multi-Bridge Duplication (0x73 Packets)

**Test Date:** 2025-11-07
**Capture File:** `capture_20251107_014534.txt`

```yaml
Endpoint: 1b:dc:da:3e
Total 0x73 packets: 72
Unique TCP connections: 18
Unique payloads: 2

Payload: 7e 0d 01 00 00 f9 8e 01 00 00 8f 7e...
  Occurrences: 71
  Unique connections: 18  ← 18 DIFFERENT BRIDGES!
  Unique msg_ids: 15      ← 15 DIFFERENT COUNTERS!

✅ DEFINITIVE PROOF: 18 bridges sent IDENTICAL payload with DIFFERENT msg_ids
```

**Conclusion:** Payload Hash deduplication is not theoretical - it's a measured requirement for handling real-world Cync mesh networks.

---

**Status:** ✅ Validated and Ready for Phase 1b Implementation
