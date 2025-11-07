# Device Backpressure Behavior Testing

**Status**: Analysis from Existing Captures + Manual Testing Required
**Date**: 2025-11-07
**Phase**: 0.5 Deliverable #9

## Executive Summary

Analyzed 8 captures totaling 24,960 packets to infer device behavior. Devices handle high throughput (peak 161 packets/sec) and buffer aggressively (52,597 rapid sequences <100ms apart). Multiple reconnections observed (572 handshakes, avg 71/capture) indicating devices recover from connection issues. **Manual backpressure testing required** to measure specific timeout thresholds and recv_queue requirements.

**Test Execution Guide**: See `working-files/202511071820_backpressure_tests/test_execution_guide.md`

## Test Setup

**Analysis Source**: 8 existing capture files (11MB total)

- Capture period: 2025-11-07 00:34-15:21
- Total packets analyzed: 24,960
- Devices captured: ~9 Cync devices (various types)
- Connection events: 572 handshakes

**Test Environment** (for manual tests):

- MITM Proxy Version: Enhanced with backpressure modes (`--backpressure-mode`)
- DNS Redirection: `cm.gelighting.com → 127.0.0.1`
- Upstream: `35.196.85.236:23779`
- TLS: Enabled

**Test Methodology** (manual execution required):

- Scenario 1: Slow Consumer (1 msg/sec read rate)
- Scenario 2: TCP Buffer Fill (stop after 10 packets)
- Scenario 3: ACK Delay (2s and 5s delays)

## Scenario 1: Slow Consumer

**Status**: ⏳ Manual Testing Required

### Inferred Behavior from Existing Captures

**Observed Patterns**:

- Peak throughput: 161 packets/second (devices can send aggressively)
- Rapid packet bursts: 52,597 sequences with <100ms intervals
- Devices buffer and send in bursts rather than steady stream

**Inference**: Devices likely have internal send buffers and will queue packets if network is slow. Need manual testing to confirm behavior when buffer fills.

### Manual Test Required

**Execute**: Follow `working-files/202511071820_backpressure_tests/test_execution_guide.md`

**Measure**:

- Device continues sending vs stops vs disconnects
- Timeout threshold if disconnection occurs
- TCP Recv-Q size growth

### Key Findings

- ⏳ Requires manual test execution with live devices
- Devices show aggressive buffering behavior
- Peak send rate: 161 packets/sec

## Scenario 2: TCP Buffer Fill

**Status**: ⏳ Manual Testing Required

### Inferred Behavior from Existing Captures

**Reconnection Patterns**:

- Total handshakes across captures: 572
- Avg reconnections per capture: 71.5
- Reconnection intervals: Min 0s, Max 42s, Mean 2.6s

**Inference**: Devices reconnect frequently, suggesting they detect connection issues and recover automatically. Short intervals (2.6s mean) indicate quick timeout thresholds.

### Manual Test Required

**Execute**: Follow `working-files/202511071820_backpressure_tests/test_execution_guide.md`

**Measure**:

- Time to disconnect after buffer fills
- Reconnection behavior and timing
- TCP Recv-Q size at disconnection

### Key Findings

- ⏳ Requires manual test execution
- Devices reconnect frequently (auto-recovery)
- Quick reconnection intervals (avg 2.6s)

## Scenario 3: ACK Delay

**Status**: ⏳ Manual Testing Required

### Inferred Behavior from Existing Captures

**ACK Latency Baselines** (from normal operation):

- 0x7B (DATA_ACK): p50=863ms, p95=505s (includes outliers from long sessions)
- 0x7B (normal): ~40-50ms typical, ~100-200ms p95
- 0x88 (STATUS_ACK): p50=44ms, p95=254ms
- 0xD8 (HEARTBEAT_ACK): p50=43.5ms, p95=50.9ms

**Inference**: Normal ACK latencies are 40-250ms. High p95/p99 values in some ACKs (seconds range) suggest devices tolerate long delays but may eventually timeout/reconnect.

### Manual Test Required

**Execute**: Follow `working-files/202511071820_backpressure_tests/test_execution_guide.md`

#### Run A: 2 Second Delay

- Measure toggle success rate
- Observe physical vs HA state update timing
- Count any timeouts or retries

### Run B: 5 Second Delay

- Compare behavior to 2s delay
- Identify timeout threshold
- Document retry patterns

### Timeout Thresholds

- ⏳ Requires manual measurement
- Expected threshold: 2-10 seconds (based on reconnection intervals)
- Heartbeat timeout likely higher (10+ seconds based on p95=18.8s in long sessions)

### Key Findings

- ⏳ Requires manual test execution
- Normal ACK latency: 40-250ms
- Devices tolerate delays (seconds range observed in captures)

## Phase 1c Recommendations

### recv_queue Size Recommendation

**Recommended Size**: **100 packets** (preliminary, refine with manual tests)

**Justification**:
Based on observed behavior, devices handle high throughput (161 pkt/sec peak) and reconnect quickly (2.6s avg). Queue must absorb bursts during brief processing delays.

**Calculation** (preliminary):

- Device peak send rate: 161 packets/sec
- Expected reconnection threshold: ~2-3 seconds
- Required capacity: 161 × 3 = 483 packets (worst case)
- **But**: Devices reconnect quickly, don't wait indefinitely
- Practical recommendation: 100 packets (0.6s buffer at peak rate)
- **Refine with manual tests**: Measure actual timeout threshold

### recv_queue Policy Recommendation

**Recommended Policy**: **BLOCK** (preliminary, refine with manual tests)

**Justification**:
Devices show aggressive buffering and quick reconnection. Blocking recv_queue matches device behavior: preserve all messages, let devices handle disconnection if processing too slow.

**Rationale**:

- Devices buffer internally (52,597 burst sequences observed)
- Quick reconnect intervals (2.6s mean) suggest timeout-based recovery
- **BLOCK** policy: preserve all packets, device disconnects if we're too slow
- Alternative (if manual tests show packet loss): **DROP_OLDEST**

**Manual test will determine**: Does device retry lost packets after reconnect?

### Edge Case Handling

**Timeout Handling**:

- Normal ACK latency: 40-250ms
- Expected device timeout: 2-10 seconds (based on reconnection intervals)
- Phase 1c should process within: <250ms to stay within normal range
- If processing slower: device may reconnect (acceptable, auto-recovery works)

**Buffer Overflow**:

- If recv_queue full with BLOCK: backpressure propagates to device
- Device will either slow down or disconnect/reconnect
- Log warning if queue approaches capacity (>80% full)

**Reconnection**:

- Devices reconnect automatically (avg 2.6s interval)
- Phase 1c should: accept new connections gracefully
- Maintain dedup cache across reconnections (5min TTL covers reconnect window)

## Additional Findings

### Device Behavior Patterns

- **Aggressive Buffering**: 52,597 rapid packet sequences (<100ms intervals) indicate devices buffer heavily
- **Auto-Recovery**: 572 handshakes across 8 captures show devices reconnect automatically
- **High Throughput**: Peak 161 packets/sec demonstrates devices can handle burst traffic
- **Multiple Devices**: Simultaneous handshakes (10 within 12 seconds) show multi-device mesh coordination

### Performance Characteristics

- **Packet burst rate**: Up to 161 packets/second
- **Typical reconnection**: 2.6 seconds average
- **Connection stability**: Variable (some captures show frequent reconnects, others stable)
- **ACK latency baseline**: 40-250ms normal, seconds-range outliers during long sessions

### Anomalies

- High handshake count (avg 71/capture) suggests either:
  - Many devices connecting/reconnecting
  - Connection instability during capture sessions
  - Normal mesh behavior (multiple bridges per mesh)
- Manual testing needed to distinguish normal vs abnormal patterns

## Capture File References

**Analysis Source**:

- All 8 captures: `mitm/captures/*.txt`
- Primary analysis: `capture_20251107_003419.txt` (2.2MB, 20,106 packets)
- ACK latency data: See `docs/phase-0.5/ack-latency-measurements.md`

**Manual Test Captures** (when executed):

- Scenario 1: `mitm/captures/backpressure_slow_consumer_*.txt`
- Scenario 2: `mitm/captures/backpressure_buffer_fill_*.txt`
- Scenario 3 (2s): `mitm/captures/backpressure_ack_delay_2s_*.txt`
- Scenario 3 (5s): `mitm/captures/backpressure_ack_delay_5s_*.txt`

## Test Completion

- [x] Existing capture analysis complete
- [x] Device behavior patterns documented
- [x] Preliminary Phase 1c recommendations provided
- [ ] Scenario 1 manual test (slow consumer) - **Requires execution**
- [ ] Scenario 2 manual test (buffer fill) - **Requires execution**
- [ ] Scenario 3 manual test (ACK delay) - **Requires execution**
- [x] Test execution guide created
- [x] Preliminary recommendations made (pending refinement from manual tests)

## Implementation Notes for Phase 1c

**Critical Constraints**:

- Devices reconnect quickly (2.6s avg) - don't over-engineer recovery
- Peak throughput is 161 pkt/sec - queue must handle bursts
- Normal ACK latency is 40-250ms - process quickly to avoid backpressure
- Devices buffer aggressively - they handle their own flow control

**Configuration Values** (preliminary, refine with manual tests):

```python
RECV_QUEUE_SIZE = 100  # Handles 0.6s burst at peak rate
RECV_QUEUE_POLICY = "BLOCK"  # Let devices handle backpressure via disconnect/reconnect
ACK_TIMEOUT = 2.0  # 2 seconds (based on normal latencies + margin)
HEARTBEAT_TIMEOUT = 10.0  # 10 seconds (devices reconnect quickly anyway)
```

**Manual Test Refinement**:

- Execute tests per `working-files/202511071820_backpressure_tests/test_execution_guide.md`
- Measure actual device timeout thresholds
- Adjust RECV_QUEUE_SIZE based on observed buffer requirements
- Confirm BLOCK vs DROP_OLDEST policy based on device retry behavior

## Acceptance Criteria

- [x] Device backpressure behavior **inferred** from existing captures
- [x] Preliminary recv_queue size recommendation provided (100 packets)
- [x] Preliminary recv_queue policy recommendation provided (BLOCK)
- [x] Timeout values inferred from capture data (2-10s range)
- [x] Edge case handling guidance provided
- [ ] **Manual testing required** to refine recommendations and measure actual thresholds

**Status**: **Tier 3 deliverable partially complete**. Preliminary recommendations sufficient for Phase 1c planning. Manual tests recommended before production deployment.
