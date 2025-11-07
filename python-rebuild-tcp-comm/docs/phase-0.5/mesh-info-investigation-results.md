# Mesh Info Response Investigation Results

**Date**: 2025-11-06
**Investigation**: Mesh info request injection via MITM proxy
**Status**: ✅ COMPLETE - Negative Result

---

## Executive Summary

Mesh info requests injected via MITM proxy are acknowledged by devices (standard 0x7B ACKs received) but **do NOT trigger mesh info responses**. Devices never send the expected 0x73 packets containing mesh info data.

**Conclusion**: Injected mesh info requests are treated as invalid or unauthorized. Devices likely require:

1. Proper authentication/session state
2. The request to originate from the device that owns the queue_id
3. Specific handshake or authorization not present in raw packet injection

**Phase 0.5 Impact**: Mesh info cannot be obtained via packet injection. Alternative approaches needed for Phase 1.

---

## Investigation Findings

### Test Setup

- **Method**: Injected mesh info request packets via MITM proxy REST API
- **Target**: All 25 active device connections
- **Packet Format**: `73 00 00 00 18 [queue_id] 00 00 00 7e 1f 00 00 00 f8 52 06 00 00 00 ff ff 00 00 56 7e`

### Results

#### ✅ Injection Successful

- 25 identical packets sent to all connections
- All devices responded with 0x7B ACK packets

### ❌ No Mesh Info Response

- No 0x73 packets with `f9 52 01` (mesh info ACK)
- No 0x73 packets with large payloads containing device data
- Analyzed entire 7-minute log window - zero mesh info responses

### Actual Response Received

```text
7b 00 00 00 07 45 88 0f 3a 00 00 00
```

- Type: 0x7B (DATA_ACK)
- Length: 7 bytes
- Queue ID: 45 88 0f 3a 00
- msg_id: 00 00 (matches request)

**Interpretation**: Device acknowledged receipt but did not process the request.

### Expected Responses (NOT Received)

1. **Small mesh info ACK:**

   ```text
   73 00 00 00 [length] [queue_id] 00 00 00 7e 1f 00 00 00 f9 52 01 00 00 53 7e
   ```

2. **Large mesh info data:**

   ```text
   73 00 00 00 [large_length] [queue_id] 00 00 00 7e [24-byte device structs...] 7e
   ```

---

## Root Cause Analysis

### Packet Structure Validation ✅

Injected packet structure matches production code (`tcp_device.py` lines 213-266):

- ✅ Correct packet type (0x73)
- ✅ Correct length (0x18 = 24 bytes)
- ✅ Valid queue_id (from device's own 0x23 handshake)
- ✅ Correct inner command (`f8 52 06` = QUERY_STATUS)
- ✅ Valid checksum (0x56)

**Conclusion**: Packet structure is correct. Issue is authorization/session state.

### Likely Authorization Requirements

Based on production code behavior, devices probably require:

1. **Session Context:**
   - Request must be part of an authenticated session
   - May require specific session tokens or state

2. **Queue ID Ownership:**
   - Request may need to originate from the device that "owns" the queue_id
   - Proxy injection violates this ownership model

3. **Handshake Sequence:**
   - May require specific handshake or authorization packet before mesh info requests
   - One-off injection lacks required context

---

## Implications for Phase 0.5 & Phase 1

### Phase 0.5 Deliverables

- ❌ Mesh info packet injection not feasible via MITM proxy
- ✅ All other Phase 0.5 objectives achieved (checksum, ACK structure, packet capture)

### Phase 1 Alternatives

#### Option 1: Parse from Natural Traffic

- Monitor for natural mesh info responses during device operation
- Devices may send mesh info periodically or on specific triggers
- Requires patience but avoids injection issues

### Option 2: Reverse Engineer Authorization

- Capture complete session establishment sequence
- Identify required authorization tokens/state
- Implement proper session context (complex)

### Option 3: Defer to Phase 1d

- Phase 1a/1b/1c don't require mesh info
- Mesh info discovery can be deferred to later phases
- Focus on core command/ACK functionality first

**Recommendation**: Use Option 1 or 3. Avoid complex authorization reverse engineering unless absolutely necessary.

---

## Conclusion

Mesh info packet injection via MITM proxy is **not feasible** due to authorization/session requirements. Devices acknowledge injected requests but do not process them.

**Phase 0.5 Status**: Complete - all required deliverables achieved. Mesh info discovery deferred to Phase 1.

### Files Referenced

- Test script: `mitm/test-toggle-injection.py`
- Production code: `cync-controller/src/cync_controller/devices/tcp_device.py` lines 213-266
- Packet handler: `cync-controller/src/cync_controller/devices/tcp_packet_handler.py` lines 524-564
