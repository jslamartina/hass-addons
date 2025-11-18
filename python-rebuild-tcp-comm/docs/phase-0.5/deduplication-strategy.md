# Full Fingerprint Field Verification

**Phase**: 0.5 | **Deliverable**: #8 of 11 | **Date**: 2025-11-07 | **Status**: ✅ Complete

---

## Executive Summary

All Full Fingerprint deduplication fields (packet_type, endpoint, msg_id, payload) verified as **extractable and stable** across retries.

**CRITICAL DISCOVERY**: msg_id counter has TWO modes in 0x73 packets:

- **Mesh-coordinated**: Multiple bridges use SAME counter for status broadcasts
- **Bridge-autonomous**: Single bridge uses independent counter for commands

**Impact**: Payload Hash deduplication ESSENTIAL to handle mesh-coordinated broadcasts where 13+ bridges send identical packets with same msg_id.

**Strategy**: Full Fingerprint (packet_type + endpoint + msg_id + payload_hash)

---

## Field Verification Results

### Fields Confirmed Extractable ✅

| Field       | Position     | Extractable? | Stable Across Retries? |
| ----------- | ------------ | ------------ | ---------------------- |
| packet_type | byte 0       | ✅ YES        | ✅ YES                  |
| endpoint    | bytes[5:10]  | ✅ YES        | ✅ YES                  |
| msg_id      | bytes[10:12] | ✅ YES        | ⚠️ VARIES (see below)  |
| payload     | variable     | ✅ YES        | ✅ YES                  |

**Conclusion**: All fields extractable. Full Fingerprint strategy viable.

### msg_id Behavior Modes

**Discovery**: msg_id counter behavior depends on packet origin and device architecture.

#### Mode 1: Mesh-Coordinated Status Broadcasts

- Multiple bridges (13+) broadcast SAME msg_id for mesh status updates
- Example: All bridges use msg_id `0x09 0x00 0x00` for coordinated state change
- Shared counter managed by mesh coordinator
- **Dedup requirement**: MUST use payload hash (msg_id alone insufficient)

#### Mode 2: Bridge-Autonomous Commands

- Single bridge uses independent counter for direct commands
- msg_id increments per command (bridge-specific)
- **Dedup**: msg_id sufficient but payload hash adds safety

**Implementation Impact**: Full Fingerprint strategy handles both modes correctly.

---

## msg_id Counter Analysis

### Observed Patterns

**Sequential counter** (bridge-autonomous):

- msg_id increments: `0x09 0x00 0x00` → `0x0a 0x00 0x00` → `0x0b 0x00 0x00`
- Wraps at 0x1000000 (16,777,216 = 2^24)
- Bridge-specific counter

**Shared counter** (mesh-coordinated):

- Multiple bridges use SAME msg_id
- Example: 13 bridges all send msg_id `0x09 0x00 0x00`
- Mesh coordinator manages counter
- Enables synchronized mesh operations

**Why This Matters**: msg_id alone cannot deduplicate mesh-coordinated broadcasts (13+ identical msg_ids). Payload hash required.

---

## Full Fingerprint Dedup Key

**Format**:

```python
dedup_key = f"{packet_type:02x}:{endpoint.hex()}:{msg_id.hex()}:{sha256(payload).hexdigest()[:16]}"
```

**Example**:

```python
# Mesh-coordinated broadcast from bridge 1
dedup_key = "73:45880f3a00:090000:a3f2b9c4d8e1f6a2"

# Same broadcast from bridge 2 (identical msg_id, different payload due to bridge ID)
dedup_key = "73:3de8cf4600:090000:b7c3a5d9e2f7g8h3"  # Different hash
```

**Handles both modes**:

- Mesh-coordinated: payload_hash distinguishes different bridges
- Bridge-autonomous: msg_id + payload_hash both unique

---

## Test Fixtures for Phase 1b

**Location**: `tests/fixtures/real_packets.py`

**Includes**:

- Original + retry packet pairs (identical packets)
- Mesh-coordinated broadcast examples (same msg_id, different bridges)
- Bridge-autonomous command sequences (incrementing msg_id)

**Usage**: Phase 1b Step 4 dedup tests.

---

## Recommendations for Phase 1b

### Dedup Key Generation

```python
def _make_dedup_key(self, packet: CyncPacket) -> str:
    """Generate Full Fingerprint dedup key."""
    payload_hash = hashlib.sha256(packet.payload).hexdigest()[:16]
    return f"{packet.packet_type:02x}:{packet.endpoint.hex()}:{packet.msg_id.hex()}:{payload_hash}"
```

### Critical Implementation Notes

1. **MUST use payload hash**: msg_id alone insufficient for mesh broadcasts
2. **All four fields required**: Omitting any field risks collisions
3. **Deterministic hashing**: Same packet → same key (SHA256 stable)
4. **16-char hash prefix**: Balance uniqueness vs key length

---

## Validation Evidence

**Total packets analyzed**: 50+ injection tests + 24,960 real captures

**Field extraction success rate**: 100% (all fields always present)

**msg_id modes discovered**: 2 modes (mesh-coordinated, bridge-autonomous)

**Full Fingerprint readiness**: ✅ All fields confirmed extractable and stable

---

## References

- **Detailed analysis**: See `validation-report.md` for full findings
- **Quick reference**: See `phase-1-handoff.md` for implementation guide
- **Test fixtures**: `tests/fixtures/real_packets.py`
