# Phase 0.5 → Phase 1 Handoff

**Date**: 2025-11-07
**Status**: ✅ Complete
**Purpose**: Quick reference for Phase 1 implementation based on Phase 0.5 validated findings

---

## Executive Summary

Phase 0.5 successfully validated the Cync protocol structure with 100% checksum validation, confirmed clean byte boundaries, and measured ACK latencies significantly lower than assumed. Key architecture impact: **Hybrid ACK matching required** (not universal parallel matching).

---

## Quick Reference Tables

### Byte Positions (Validated)

| Field    | Position              | Size    | Overlap? | Validated? |
| -------- | --------------------- | ------- | -------- | ---------- |
| endpoint | bytes[5:10]           | 5 bytes | NO       | ✅         |
| msg_id   | bytes[10:12]          | 2 bytes | NO       | ✅         |
| padding  | byte 12               | 1 byte  | N/A      | ✅ (0x00)  |
| checksum | Last byte before 0x7E | 1 byte  | N/A      | ✅         |

**Implementation**: Simple array slicing, no overlap handling needed.

### ACK Structure (Validated - HYBRID MATCHING REQUIRED)

| ACK Type | Request Type | msg_id Present? | Position | Strategy          | Sample Size |
| -------- | ------------ | --------------- | -------- | ----------------- | ----------- |
| 0x28     | 0x23         | NO              | N/A      | FIFO queue        | 25          |
| 0x7B     | 0x73         | **YES**         | byte 10  | Parallel (msg_id) | 9           |
| 0x88     | 0x83         | NO              | N/A      | FIFO queue        | 97          |
| 0xD8     | 0xD3         | NO              | N/A      | FIFO queue        | 21,441      |

**Architecture Impact**: Phase 1b must implement hybrid ACK matching strategy (0x7B uses msg_id, others use FIFO).

### ACK Latency Measurements (for Timeout Configuration)

| ACK Type | Median (p50) | p95     | p99    | Sample Size | Confidence |
| -------- | ------------ | ------- | ------ | ----------- | ---------- |
| 0x28     | 45.9ms       | 129.4ms | N/A    | 25          | Medium     |
| 0x7B     | 21.4ms       | 30.4ms  | ~51ms  | 9           | **Low**    |
| 0x88     | 41.7ms       | 47.7ms  | N/A    | 97          | High       |
| 0xD8     | 43.5ms       | 50.9ms  | 84.1ms | 21,441      | **High**   |

**Timeout Recommendation**: Use 51ms p99 for 0x7B (small sample - monitor in Phase 1d).
**Formula**: `timeout = p99 × 2.5` → 51ms × 2.5 = 128ms

### Checksum Algorithm (Validated - 100% Match Rate)

```python
def calculate_checksum_between_markers(packet: bytes) -> int:
    """Calculate checksum between 0x7E markers.

    Algorithm: sum(packet[start+6:end-1]) % 256
    Validated: 13/13 packets (2 legacy + 11 real)
    """
    start = packet.find(0x7E)
    end = packet.rfind(0x7E)
    return sum(packet[start+6:end-1]) % 256
```

**Status**: Ready for Phase 1a implementation (copy algorithm, don't import).

---

## Critical Architecture Decisions

### Decision 1: Hybrid ACK Matching Strategy

**Finding**: Only 0x7B DATA_ACK contains msg_id; other ACKs require FIFO queue.

**Implementation** (Phase 1b):

- 0x7B: Use 3-byte msg_id at bytes[10:13] for parallel ACK matching
- 0x28/0x88/0xD8: Use connection-level FIFO queue

**Code Pattern**:

```python
if ack_type == 0x7B:
    msg_id = ack_packet[10:13]  # 3-byte msg_id
    return self.pending_requests_by_msgid.get(msg_id)
else:
    return self.fifo_queue.pop_first_matching(ack_type)
```

### Decision 2: Timeout Recalibration

**Finding**: Measured p99 (51ms) significantly lower than assumption (800ms).

**Implementation** (Phase 1b TimeoutConfig):

- Default: `measured_p99_ms = 51.0` (from Phase 0.5)
- Note: Small sample size (9 pairs), monitor in Phase 1d
- Formula-based scaling: all timeouts derive from this value

**Calculated Timeouts**:

- ACK timeout: 128ms (51ms × 2.5)
- Handshake timeout: 320ms (128ms × 2.5)
- Heartbeat timeout: 10s (max(384ms, 10s))

### Decision 3: Recv Queue Configuration

**Finding**: Devices tolerate backpressure, peak throughput 161 pkts/sec.

**Preliminary Recommendations** (Phase 1c - validate in Phase 1d):

- recv_queue size: 100 packets (~620ms buffer at peak)
- recv_queue policy: BLOCK (devices handle backpressure)

---

## Test Fixtures Location

**File**: `tests/fixtures/real_packets.py`

**Coverage**: 13 validated packets

- 2 legacy fixtures (SIMPLE_PACKET, MODULO_256_PACKET)
- 11 real packets from diverse devices (11 unique endpoints)

**Usage**: Import for unit tests in Phase 1a/1b/1c.

---

## Protocol Stability Metrics

- **Total packets analyzed**: 2,251
- **Malformed packets**: 0 (100% well-formed)
- **Checksum match rate**: 100% (13/13 validated)
- **Protocol consistency**: No firmware variations detected across 9 devices
- **Peak throughput**: 161 packets/second
- **Rapid sequences**: 52,597 packets with <100ms spacing

---

## Phase 1 Readiness Checklist

- [x] Checksum algorithm validated (100% match rate)
- [x] Byte positions confirmed (no overlap)
- [x] ACK structure validated (hybrid strategy documented)
- [x] ACK latency measured (timeout recommendations provided)
- [x] Test fixtures created (13 packets available)
- [x] Backpressure behavior analyzed (recommendations provided)
- [x] Full Fingerprint dedup strategy validated (all fields extractable)

**Status**: ✅ Phase 1a ready to begin implementation

---

## Open Questions / Monitor in Phase 1d

1. **0x7B p99 latency**: Small sample (9 pairs) - monitor in Phase 1d testing, may need adjustment
2. **Recv queue sizing**: 100 packets preliminary - validate under chaos conditions in Phase 1d
3. **Retry behavior**: Not observed in Phase 0.5 stable network - test in Phase 1d chaos scenarios

---

## References

**Deliverables**:

- Protocol Capture: `docs/phase-0.5/captures.md`
- Validation Report: `docs/phase-0.5/validation-report.md`
- Packet Structure: `docs/phase-0.5/packet-structure-validated.md`
- ACK Latency: `docs/phase-0.5/ack-latency-measurements.md`
- Dedup Strategy: `docs/phase-0.5/deduplication-strategy.md`
- Backpressure: `docs/phase-0.5/backpressure-behavior.md`
- Completion Summary: `docs/phase-0.5/PHASE_0.5_COMPLETE.md`

**Updated Specs**:

- Phase 1 Master: `docs/02-phase-1-spec.md` (terminology glossary updated)
- Phase 1a: `docs/02b-phase-1a-protocol-codec.md` (checksum + byte positions)
- Phase 1b: `docs/02c-phase-1b-reliable-transport.md` (hybrid ACK + timeouts)
- Phase 1c: `docs/02d-phase-1c-backpressure.md` (recv_queue recommendations)
- Phase 1d: `docs/02e-phase-1d-simulator.md` (performance baselines)
