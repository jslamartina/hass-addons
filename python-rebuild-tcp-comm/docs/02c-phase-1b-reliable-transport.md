# Phase 1b: Reliable Transport Layer

**Status**: Specified
**Dependencies**: Phase 1a (protocol codec) complete + Phase 0.5 ACK validation complete
**Execution**: Sequential solo implementation

---

## Overview

Phase 1b implements native Cync protocol ACK/response handling with reliability primitives on top of the Phase 1a protocol codec. This includes handling the native Cync ACK packet types (0x28, 0x7B, 0x88, 0xD8), connection management, automatic retries with exponential backoff, and idempotency via LRU-based deduplication.

**See Also**: `02-phase-1-spec.md` for detailed architecture.

---

## Goals

1. Implement native Cync protocol ACK/response handling (0x28, 0x7B, 0x88, 0xD8)
2. Add connection management with handshake (0x23 → 0x28) and reconnection
3. Implement keepalive/heartbeat handling (0xD3 → 0xD8)
4. Add automatic retries with configurable exponential backoff
5. Implement LRU-based deduplication cache for idempotency
6. Track pending messages awaiting ACKs with proper matching
7. Enhance metrics for reliability (ACK rates, retransmits, duplicates, connection state)

---

## Deliverables

### Code
- [ ] `src/transport/reliable_layer.py` - ReliableTransport class (~250-300 lines)
- [ ] `src/transport/connection_manager.py` - Connection state machine (~150-200 lines)
- [ ] `src/transport/deduplication.py` - LRU dedup cache (~100-120 lines)
- [ ] `src/transport/retry_policy.py` - Exponential backoff (~60-80 lines)
- [ ] 25+ unit tests covering all retry/dedup/connection scenarios

### Features
- [ ] Native Cync ACK packet handling (0x28, 0x7B, 0x88, 0xD8)
- [ ] Connection state machine (disconnected, connecting, connected, reconnecting)
- [ ] Handshake flow (0x23 → 0x28)
- [ ] Keepalive/heartbeat (0xD3 → 0xD8)
- [ ] `send_reliable()` - Send with native Cync ACK wait
- [ ] `recv_reliable()` - Receive with auto-ACK and dedup
- [ ] Pending message tracking with ACK matching (msg_id → correlation_id reverse-lookup)
- [ ] Configurable retry policy (max attempts, backoff, jitter)
- [ ] LRU cache (1000 entries, 5min TTL)
- [ ] Automatic reconnection with exponential backoff

### Metrics (New)
```python
# ACK/Response metrics
tcp_comm_ack_received_total{device_id, ack_type, outcome}  # Counter (ack_type: 0x28, 0x7B, 0x88, 0xD8)
tcp_comm_ack_timeout_total{device_id}           # Counter
tcp_comm_idempotent_drop_total{device_id}       # Duplicates dropped
tcp_comm_retry_attempts_total{device_id, attempt_number}
tcp_comm_message_abandoned_total{device_id, reason}

# Connection metrics
tcp_comm_connection_state{device_id, state}     # Gauge (state: disconnected, connecting, connected, reconnecting)
tcp_comm_handshake_total{device_id, outcome}    # Counter
tcp_comm_reconnection_total{device_id, reason}  # Counter
tcp_comm_heartbeat_total{device_id, outcome}    # Counter

# Dedup cache metrics
tcp_comm_dedup_cache_size                       # Gauge
tcp_comm_dedup_cache_hits_total                 # Counter
tcp_comm_dedup_cache_evictions_total           # Counter

# Performance metrics
tcp_comm_state_lock_hold_seconds               # Histogram (track lock hold duration)
```

### Metrics Recording Points

The table below specifies where each metric should be recorded in the codebase.

**⚠️ Line Number Guidance (Technical Review Finding 4.5 - Enhanced)**: Line numbers are **approximate** and WILL drift during implementation/refactoring. Use method names and trigger events as **primary reference**.

**Best Practices**:
- Mark recording locations with comments: `# METRIC: tcp_comm_ack_received_total`
- After implementation: Update table to remove line numbers, keep method names only
- Focus on trigger events (e.g., "after ACK validated") not exact line positions

| Metric | Code Location | Trigger Event | Implementation Guidance |
|--------|---------------|---------------|-------------------------|
| `tcp_comm_ack_received_total` | `ReliableTransport.handle_ack()` (after validation) | After ACK packet validated (checksum valid, type recognized) | Labels: `outcome=matched` if msg_id found in pending_acks, `outcome=orphaned` if no match |
| `tcp_comm_ack_timeout_total` | `ReliableTransport.send_reliable()` (in retry loop, after timeout) | After timeout waiting for ACK | Record immediately after timeout exception caught |
| `tcp_comm_idempotent_drop_total` | `ReliableTransport.recv_reliable()` (after dedup check) | Duplicate detected in dedup cache (cache hit) | Record before raising DuplicatePacketError |
| `tcp_comm_retry_attempts_total` | `ReliableTransport.send_reliable()` (in retry loop) | Each retry attempt | Increment with label `attempt_number={attempt}` |
| `tcp_comm_message_abandoned_total` | `ReliableTransport.send_reliable()` (after max retries) | After max_retries exceeded | Record before returning SendResult(success=False) |
| `tcp_comm_connection_state` | `ConnectionManager.connect()/disconnect()/reconnect()` (in state transition) | On state transition | Set gauge to new state value when updating self.state |
| `tcp_comm_handshake_total` | `ConnectionManager.connect()` (after handshake attempt) | After handshake completes (success or failure) | Record with label `outcome={success/failed}` |
| `tcp_comm_reconnection_total` | `ConnectionManager.reconnect()` (on entry) | On reconnection trigger | Record with label `reason={reason}` before reconnect logic |
| `tcp_comm_heartbeat_total` | `ConnectionManager._packet_router()` (after heartbeat) | After heartbeat exchange (success, timeout, invalid) | Record with label `outcome={success/timeout/invalid}` |
| `tcp_comm_dedup_cache_size` | `LRUCache.add()/cleanup()` (after operation) | After cache add/cleanup operation | Set gauge to `len(self.cache)` |
| `tcp_comm_dedup_cache_hits_total` | `ReliableTransport.recv_reliable()` (on cache hit) | On cache hit (duplicate packet detected) | Record immediately after `dedup_cache.contains()` returns True |
| `tcp_comm_dedup_cache_evictions_total` | `LRUCache.add()` (when evicting) | On LRU eviction (when cache full, oldest removed) | Record when evicting oldest entry from OrderedDict |
| `tcp_comm_state_lock_hold_seconds` | `ConnectionManager.with_state_check()` (after release) | After releasing state lock | Record duration, log warning if > 10ms |

**Implementation Notes**:
- Record metrics **immediately after event completes** (e.g., after validation, after timeout)
- For gauges (connection_state, cache_size): set absolute value
- For counters: increment by 1 (or by attempt_number for retries)
- Include all relevant labels (device_id, outcome, reason, etc.)
- Never record metrics in tight loops; only at decision points
- **Mark recording locations** with comments: `# METRIC: tcp_comm_ack_received_total`
- **Line numbers are approximate** - use method names and trigger events as primary reference

---

## Timeout Configuration Guide

Phase 1b uses multiple timeout values for different operations. This guide documents the rationale for each timeout and provides tuning guidelines based on network characteristics.

### Default Timeout Values

**Architectural Decision**: Balanced timeout hierarchy (Option C from performance target review)

| Operation | Default | Rationale | Used In |
|-----------|---------|-----------|---------|
| **Handshake Timeout** | 5s | Initial connection (2.5× ACK timeout for slower setup) | `ConnectionManager.connect()` |
| **ACK Wait Timeout** | 2s | Data channel timeout (2.5× p99 target of 800ms) | `ReliableTransport.send_reliable()` |
| **Send Timeout** | 2s | Network I/O timeout (matches ACK timeout) | `conn.send()` wrapper |
| **Heartbeat Send Interval** | 60s | How often to send 0xD3 heartbeat packets | `ConnectionManager._packet_router()` |
| **Heartbeat ACK Timeout** | 10s | How long to wait for 0xD8 response; max(3× ACK, 10s) | `ConnectionManager._packet_router()` |
| **Global ACK Cleanup** | 30s | Catch-all for stuck ACKs; 15× ACK timeout for safety | `ReliableTransport._cleanup_expired_acks()` |

**Note**: ACK timeout changed from 5s to 2s based on performance target hierarchy (p99 target = 800ms, timeout = 2.5× p99 = 2000ms).

### Tuning Guidelines

**Heartbeat Timeout Scaling (Formula Clarification - Technical Review Finding 3.4 Enhanced)**:

The heartbeat timeout uses formula: `max(3 × ack_timeout, 10s)` which ensures:
- **Minimum threshold**: Never less than 10s - accounts for network jitter and device processing variance even with low ACK timeouts
- **Scales with ACK timeout**: Increases proportionally if ACK timeout increases
- **Why 10s minimum (rationale)**:
  - Empirical observation: Network jitter and device load can delay heartbeat responses by 5-8s even when individual ACKs complete in < 1s
  - Conservative safety margin for production stability
  - Prevents false-positive reconnections from brief network hiccups
  - Heartbeat tolerance should exceed individual command tolerance (longer time scale)
  - Even on fast local networks (ACK timeout = 1-2s), heartbeats need headroom for:
    - Device processing backlog (if handling multiple commands)
    - Intermittent network congestion (brief packet reordering)
    - WiFi/Ethernet brief disconnections (< 10s recovery)
  - 10s threshold provides 5-10× margin over typical heartbeat response time

**Scaling Examples**:
| ACK Timeout | Formula Calculation | Heartbeat Timeout | Rationale |
|-------------|---------------------|-------------------|-----------|
| 2s (default) | max(3 × 2s, 10s) = max(6s, 10s) | **10s** | Uses minimum (6s < 10s threshold) |
| 3s | max(3 × 3s, 10s) = max(9s, 10s) | **10s** | Uses minimum (9s < 10s threshold) |
| 4s | max(3 × 4s, 10s) = max(12s, 10s) | **12s** | Scales up (12s > 10s threshold) |
| 5s | max(3 × 5s, 10s) = max(15s, 10s) | **15s** | Scales up (15s > 10s threshold) |
| 10s | max(3 × 10s, 10s) = max(30s, 10s) | **30s** | Scales up (30s > 10s threshold) |

**Key Insight**: For default ACK timeout (2s), heartbeat uses 10s minimum. If Phase 0.5 measurements require higher ACK timeout (≥4s), heartbeat automatically scales up to maintain 3× margin.

---

**Based on Network Latency** (from Phase 0.5 measurements):

```
Recommended ACK Timeout = p99_ack_latency × 2.5
```

**Example Calculation**:
- Target p99 ACK latency = 800ms (from performance targets)
- Recommended ACK timeout = 800ms × 2.5 = 2000ms
- Default: 2s

**If Phase 0.5 measures different p99**:
- Phase 0.5 measures p99 ACK latency = 300ms
- Recommended ACK timeout = 300ms × 2.5 = 750ms
- Round up to: 1s (nice round number)

**Dependent Timeouts** (scaled from ACK timeout):
- Handshake: 2.5× ACK timeout (allows for slower initial setup)
- Heartbeat: max(3× ACK timeout, 10s) (tolerates network jitter, min 10s)
- Cleanup: 15× ACK timeout (safety margin for stuck ACKs)

### Adaptive Timeout Configuration (Formula-Based Approach) - MANDATORY

**CRITICAL**: Use of `TimeoutConfig` class is **REQUIRED** for all timeout initialization. Manual hard-coded timeout values are **forbidden**.

**Implementation Goal**: Eliminate need for cascading code changes if Phase 0.5 p99 measurements differ from 800ms assumption.

**TimeoutConfig Class** (implement in Phase 1b Step 1 - REQUIRED):

```python
class TimeoutConfig:
    """Adaptive timeout configuration based on measured ACK latency.

    All timeout values are calculated from measured p99 ACK latency using
    formulas, eliminating need for manual updates if Phase 0.5 findings differ.

    Default assumes p99=800ms. Update measured_p99_ms if Phase 0.5 measures
    different value (no code changes needed, only parameter adjustment).
    """

    def __init__(self, measured_p99_ms: float = 800.0):
        """Initialize timeout configuration.

        Args:
            measured_p99_ms: Measured p99 ACK latency from Phase 0.5 (milliseconds)
                           Default: 800ms (assumed target from performance hierarchy)
        """
        self.measured_p99_ms = measured_p99_ms

        # Calculate all timeouts from measured p99
        self.ack_timeout_seconds = (measured_p99_ms * 2.5) / 1000.0  # 2.5× p99
        self.handshake_timeout_seconds = self.ack_timeout_seconds * 2.5  # 2.5× ACK
        self.heartbeat_timeout_seconds = max(self.ack_timeout_seconds * 3, 10.0)  # max(3× ACK, 10s)
        self.cleanup_timeout_seconds = self.ack_timeout_seconds * 15  # 15× ACK
        self.send_timeout_seconds = self.ack_timeout_seconds  # Match ACK timeout

    def __repr__(self) -> str:
        """String representation showing all calculated timeouts."""
        return (
            f"TimeoutConfig(measured_p99={self.measured_p99_ms}ms, "
            f"ack={self.ack_timeout_seconds:.1f}s, "
            f"handshake={self.handshake_timeout_seconds:.1f}s, "
            f"heartbeat={self.heartbeat_timeout_seconds:.1f}s)"
        )
```

**Usage Example (REQUIRED PATTERN)**:

```python
# ✅ REQUIRED - Use TimeoutConfig for all timeout initialization
timeouts = TimeoutConfig(measured_p99_ms=800.0)  # From Phase 0.5 measurements
transport = ReliableTransport(
    connection=conn,
    protocol=protocol,
    ack_timeout=timeouts.ack_timeout_seconds,  # 2.0s
)
conn_mgr = ConnectionManager(
    connection=conn,
    protocol=protocol,
    handshake_timeout=timeouts.handshake_timeout_seconds,  # 5.0s
    heartbeat_timeout=timeouts.heartbeat_timeout_seconds,  # 10.0s
)

# If Phase 0.5 measures different p99: Only update constructor parameter
# Example: Phase 0.5 measured p99=1200ms instead of 800ms
timeouts_adjusted = TimeoutConfig(measured_p99_ms=1200.0)
# Automatically recalculates: ack=3.0s, handshake=7.5s, heartbeat=10.0s
# No code changes needed, only configuration adjustment

# ❌ FORBIDDEN - Manual hard-coded timeout values
# transport = ReliableTransport(ack_timeout=2.0)  # Rejected by code review
# conn_mgr = ConnectionManager(handshake_timeout=5.0)  # Rejected by code review
```

**Benefits**:
- ✅ **Eliminates cascading changes**: If Phase 0.5 measures p99=1200ms instead of 800ms, change only 1 line
- ✅ **Maintains timeout relationships**: All dependent timeouts scale automatically
- ✅ **Self-documenting**: Formula shows timeout derivation clearly
- ✅ **Easy testing**: Can test with different p99 values without code changes

**Enforcement Scope**:
- **Mandatory in `src/` production code**: Ensures timeout consistency and formula-based scaling
- **Optional in tests**: Tests may use hard-coded values for simplicity (e.g., `ack_timeout=1.0` in unit tests)

**Note**: TimeoutConfig implemented in Phase 1b Step 1. If Phase 0.5 finds different p99, just update the constructor parameter.

**Enforcement Mechanism (Technical Review Finding 4.2 - Added)**:

**Option 1: Custom Linting Rule** (recommended for automated enforcement):
```python
# .ruff_custom_rules/timeout_config_enforcement.py
"""Custom ruff rule to enforce TimeoutConfig usage."""

def check_timeout_hardcoding(node):
    """Flag hardcoded timeout values in ReliableTransport/ConnectionManager constructors.

    Detects patterns like:
    - ReliableTransport(ack_timeout=2.0)  # ❌ Hardcoded
    - ConnectionManager(handshake_timeout=5.0)  # ❌ Hardcoded

    Allows patterns like:
    - ReliableTransport(ack_timeout=timeouts.ack_timeout_seconds)  # ✅ From TimeoutConfig
    """
    # Implementation: AST visitor checking for constructor calls with literal timeout values
    # Scope: src/ directory only (tests excluded)
    pass
```

**Option 2: Code Review Checklist** (manual, simpler to implement):
```markdown
## Phase 1b Code Review Checklist

### TimeoutConfig Enforcement
- [ ] All ReliableTransport instances use `timeouts.ack_timeout_seconds` (NOT hardcoded values)
- [ ] All ConnectionManager instances use `timeouts.handshake_timeout_seconds` and `timeouts.heartbeat_timeout_seconds`
- [ ] TimeoutConfig initialized with Phase 0.5 measured_p99_ms value
- [ ] No hardcoded timeout literals in src/ directory (tests may use literals)

**Search command to verify**:
```bash
# Should return ZERO matches in src/ directory
grep -r "timeout=[0-9]" src/
```
```

**Recommended**: Use Option 2 (code review checklist) for Phase 1b. Add Option 1 (custom linting) in Phase 2 if needed.

### Phase 0.5 Measurement Requirements

**REQUIRED**: Phase 0.5 must measure and document ACK latency distribution for timeout tuning.

**Deliverable #5** (Protocol Validation Report) must include:

| Metric | Measurement | Phase 1b Default | Notes |
|--------|-------------|------------------|-------|
| p50 ACK latency | TBD (Phase 0.5) | Used for typical case analysis | Expected: 50-150ms |
| p95 ACK latency | TBD (Phase 0.5) | Used for reliability testing | Expected: 200-500ms |
| p99 ACK latency | TBD (Phase 0.5) | **Used for timeout tuning** | Expected: 300-800ms |
| Max ACK latency | TBD (Phase 0.5) | Used for worst-case validation | Expected: < 2s |

**Measurement Method**:
1. Capture timestamp when command sent (0x73 packet)
2. Capture timestamp when ACK received (0x7B packet)
3. Calculate latency: ACK_time - Send_time
4. Repeat for 100+ commands to build distribution
5. Calculate percentiles (p50, p95, p99, max)

**Phase 0.5 ACK Latency Measurement**:

Phase 0.5 Tier 2 criteria includes ACK latency measurement for all 4 ACK types. Phase 1d baseline tests will also measure ACK latency to validate timeout assumptions. Default 2s timeout is based on assumed p99 = 800ms; if actual p99 differs significantly, timeout adjustment may be required.

### Environment-Specific Tuning

**Local Network** (device on same LAN):
- ACK timeout: 1-2s (low latency, stable)
- Heartbeat timeout: max(3× ACK, 10s) = 10s

**Cloud Relay** (device connects via internet):
- ACK timeout: 2-5s (moderate latency, variable)
- Heartbeat timeout: max(3× ACK, 10s) = 15s

**Cellular/Satellite** (high latency):
- ACK timeout: 5-10s (very high latency)
- Heartbeat timeout: max(3× ACK, 10s) = 30s

### Configuration Example

```python
# Phase 1b: ReliableTransport initialization
transport = ReliableTransport(
    connection=conn,
    protocol=protocol,
    ack_timeout_seconds=2,  # Tune based on Phase 0.5 p99 × 2.5
)

# Phase 1b: ConnectionManager with environment-specific timeouts
conn_mgr = ConnectionManager(
    connection=conn,
    protocol=protocol,
    handshake_timeout=5,  # 2.5× ACK timeout
    heartbeat_timeout=10,  # max(3× ACK, 10s)
)
```

### Timeout Validation (Phase 1d)

Phase 1d chaos testing will validate timeout choices:

**Test 1: Baseline Performance** (no chaos)
- Verify ACK timeout > p99 actual latency
- Success rate should be > 99.9%

**Test 2: High Latency** (500ms added delay)
- Verify ACK timeout tolerates latency spikes
- Success rate should remain > 99%

**Test 3: Packet Loss** (20% drop rate)
- Verify retry logic with ACK timeout
- Success rate should be > 99% with retries

**If validation fails**: Adjust timeouts based on observed latencies in chaos tests.

### Adaptive Timeout Strategy (Future Enhancement - Phase 2+)

For production deployment, consider adaptive timeouts that adjust based on observed latency:

```python
# Future: Exponentially weighted moving average
class AdaptiveTimeout:
    def __init__(self, initial: float = 5.0, alpha: float = 0.1):
        self.timeout = initial
        self.alpha = alpha  # Smoothing factor

    def update(self, observed_latency: float):
        # EWMA: new = α × observed + (1-α) × old
        self.timeout = self.alpha * observed_latency + (1 - self.alpha) * self.timeout
        # Add safety margin (1.5×)
        self.timeout = self.timeout * 1.5
```

**Note**: Adaptive timeouts deferred to Phase 2 - use fixed values from Phase 0.5 measurements for Phase 1.

---

## Architecture

### Custom Exceptions

Following the **No Nullability** principle, all error cases raise specific exceptions.

**Phase 1b Transport Exceptions** (inherit from `CyncProtocolError` defined in Phase 1a):

```python
from protocol.exceptions import CyncProtocolError  # From Phase 1a

class CyncConnectionError(CyncProtocolError):
    """Connection state error (not connected, handshake failed, etc.)

    Raised when:
    - Attempting to send while disconnected
    - Connection lost during operation
    - Connection manager in invalid state

    Note: Named CyncConnectionError to avoid shadowing Python's built-in ConnectionError.
    """

    def __init__(self, reason: str, state: str = "unknown"):
        self.reason = reason
        self.state = state
        super().__init__(f"Connection error: {reason} (state: {state})")

class HandshakeError(CyncProtocolError):
    """Handshake failed (timeout, invalid response, authentication failed)

    Raised when:
    - 0x23 handshake timeout (no 0x28 ACK received)
    - Invalid handshake response packet
    - Max handshake retries exceeded
    """

    def __init__(self, reason: str, attempts: int = 0):
        self.reason = reason
        self.attempts = attempts
        super().__init__(f"Handshake failed: {reason} after {attempts} attempts")

class PacketReceiveError(CyncProtocolError):
    """Error receiving packet from connection (network failure, timeout, etc.)

    Raised when:
    - TCP connection closed unexpectedly
    - Network read timeout
    - Socket error during receive
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Packet receive failed: {reason}")

class DuplicatePacketError(CyncProtocolError):
    """Packet is a duplicate (caught by deduplication cache)

    This is a normal condition during retry scenarios, not necessarily
    an error. Caller may choose to log and continue.
    """

    def __init__(self, dedup_key: str, correlation_id: str):
        self.dedup_key = dedup_key
        self.correlation_id = correlation_id
        super().__init__(f"Duplicate packet: {dedup_key}")

class ACKTimeoutError(CyncProtocolError):
    """ACK not received within timeout period

    Raised when:
    - Expected ACK not received within ack_timeout_seconds
    - Max retries exceeded waiting for ACK
    """

    def __init__(self, msg_id: bytes, timeout_seconds: float, retries: int):
        self.msg_id = msg_id
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        super().__init__(f"ACK timeout after {timeout_seconds}s ({retries} retries)")
```

**Exception Hierarchy Summary**:
```
CyncProtocolError (Phase 1a - base)
├── PacketDecodeError (Phase 1a)
├── PacketFramingError (Phase 1a)
├── CyncConnectionError (Phase 1b)
├── HandshakeError (Phase 1b)
├── PacketReceiveError (Phase 1b)
├── DuplicatePacketError (Phase 1b)
├── ACKTimeoutError (Phase 1b)
└── QueueFullError (Phase 1c - see Phase 1c spec)
```

**Cross-Reference**: See Phase 1c spec (`02d-phase-1c-backpressure.md`) for complete exception hierarchy across all Phase 1 sub-phases (1a-1c).

#### Exception Handling Patterns

**Pattern 1: Try-Except with Specific Handling**

```python
try:
    packet = protocol.decode_packet(data)
except PacketDecodeError as e:
    logger.error("Decode failed: %s", e.reason)
    metrics.record_decode_error(e.reason)
    # Handle gracefully
except CyncProtocolError as e:
    logger.error("Protocol error: %s", e)
    # Catch-all for other protocol errors
```

**Pattern 2: Connection Retry Logic**

```python
for attempt in range(max_retries):
    try:
        await transport.send_reliable(payload)
        break
    except ACKTimeoutError as e:
        logger.warning("ACK timeout on attempt %d/%d", attempt+1, max_retries)
        if attempt < max_retries - 1:
            await asyncio.sleep(backoff_delay)
        else:
            logger.error("Max retries exceeded")
            raise
```

**Pattern 3: Duplicate Handling**

```python
try:
    packet = await transport.recv_reliable()
    process_packet(packet)
except DuplicatePacketError as e:
    # Normal during retries - log and continue
    logger.debug("Duplicate packet: %s", e.dedup_key)
    metrics.record_duplicate()
    # Don't process, but don't fail either
```

#### Quick Reference: Phase 1b Exceptions

| Exception | When Raised | Typical Action |
|-----------|-------------|----------------|
| `CyncConnectionError` | Connection not established | Reconnect |
| `HandshakeError` | Handshake failed | Retry handshake or fail |
| `PacketReceiveError` | Network receive failure | Reconnect |
| `DuplicatePacketError` | Duplicate packet received | Log and ignore (normal) |
| `ACKTimeoutError` | ACK not received | Retry send |

---

### Identifier Systems Guide (Phase 1b)

Phase 1b introduces three separate identifier systems for different purposes. Understanding when to use each is critical.

#### Quick Decision Tree

**Which identifier should I use?**

**Need to match ACK packet?** → Use `msg_id` (3-byte wire protocol identifier)
**Need to track event in logs?** → Use `correlation_id` (UUID v7 for observability)
**Need to detect duplicates?** → Use `dedup_key` (Full Fingerprint hash)

**Quick Reference Card**:
- **msg_id**: ACK matching over network
- **correlation_id**: Log tracing and metrics
- **dedup_key**: Duplicate detection

#### The Three Identifiers

**msg_id (3-byte wire protocol identifier)**
- **Purpose**: ACK matching over the network
- **Type**: `bytes` (3 bytes)
- **Generation**: Sequential counter (0x000000 → 0xFFFFFF, wraps)
- **Sent over wire**: YES (embedded in packet)
- **Use for deduplication**: NO (use `dedup_key` instead)

**correlation_id (UUID v7 for observability)**
- **Purpose**: Internal event tracking and observability
- **Type**: `str` (UUID v7 format)
- **Generation**: `str(uuid.uuid7())` per send/receive operation
- **Sent over wire**: NO (internal only)
- **Use for deduplication**: NO (use `dedup_key` instead)

**dedup_key (Deterministic hash for duplicate detection)**
- **Purpose**: Identify duplicate packets arriving multiple times
- **Type**: `str` (deterministic hash)
- **Generation**: `f"{packet_type:02x}:{endpoint.hex()}:{msg_id.hex()}:{sha256(payload).hexdigest()[:16]}"`
- **Sent over wire**: NO (internal only)
- **Use for deduplication**: YES (primary purpose)

#### Why Three Systems?

```python
# Scenario: Device retransmits packet X twice (duplicate)

# First Reception
packet_1 = await recv_reliable()
# correlation_id = "01936d45-3c4e-7890-aaaa-111111111111" (UUID v7 - unique)
# dedup_key = "73:3987c857:0a141e:a3f2b9c4d8e1f6a2" (hash - deterministic)
# Cache miss → process packet, add dedup_key to cache

# Second Reception (Duplicate)
packet_2 = await recv_reliable()
# correlation_id = "01936d45-3c4e-7890-bbbb-222222222222" (DIFFERENT UUID!)
# dedup_key = "73:3987c857:0a141e:a3f2b9c4d8e1f6a2" (SAME hash!)
# Cache hit → DuplicatePacketError raised
```

**Benefit**: Can see BOTH reception events in logs (first + duplicate) with unique correlation_ids, while dedup_key correctly identifies them as the same logical packet.

#### Common Mistakes to Avoid

❌ **WRONG: Using correlation_id for deduplication**
```python
# BAD - correlation_id is unique per call, won't detect duplicates!
dedup_key = correlation_id  # UUID v7, never matches duplicates
```

✅ **CORRECT: Use dedup_key for cache, correlation_id for logs**
```python
# Generate both
correlation_id = str(uuid.uuid7())  # For this event
dedup_key = self._make_dedup_key(packet)  # For duplicate detection

# Use appropriately
if await self.dedup_cache.contains(dedup_key):  # Check for duplicate
    logger.warning("Duplicate", correlation_id=correlation_id)  # Log this event
```

❌ **WRONG: Using msg_id for deduplication**
```python
# BAD - msg_id may change on retry (device behavior unknown)
# Also, 3-byte msg_id has collision risk (16M values)
dedup_key = msg_id.hex()
```

✅ **CORRECT: Use Full Fingerprint dedup_key**
```python
# GOOD - Includes msg_id PLUS packet_type, endpoint, payload hash
dedup_key = f"{packet_type:02x}:{endpoint.hex()}:{msg_id.hex()}:{payload_hash}"
```

#### Comparison Table

| Identifier | Purpose | Type | Sent Over Wire | Use for Dedup | Use for Logging |
|------------|---------|------|----------------|---------------|-----------------|
| **msg_id** | ACK matching | `bytes` (3) | YES | ❌ NO | ✅ Yes (secondary) |
| **correlation_id** | Event tracking | `str` (UUID v7) | NO | ❌ NO | ✅ YES (primary) |
| **dedup_key** | Duplicate detection | `str` (hash) | NO | ✅ YES | ⚠️ Metadata only |

#### Implementation Checklist

**When sending**:
- [ ] Generate `msg_id` for wire protocol (3 bytes)
- [ ] Generate `correlation_id` for logging (UUID v7)
- [ ] Track mapping: `msg_id.hex()` → `correlation_id` for ACK matching
- [ ] Log with `correlation_id` and `msg_id`

**When receiving**:
- [ ] Generate `correlation_id` for this reception event (UUID v7)
- [ ] Generate `dedup_key` from packet content (deterministic)
- [ ] Check cache using `dedup_key` (not correlation_id!)
- [ ] Log with `correlation_id` and `dedup_key`

**When matching ACK**:
- [ ] Extract `msg_id` from ACK packet (3 bytes from wire)
- [ ] Reverse-lookup: `msg_id.hex()` → `correlation_id`
- [ ] Find pending message: `pending_acks[correlation_id]`
- [ ] Set ACK event to unblock sender

---

### TrackedPacket Wrapper

Since Phase 1a dataclasses only contain wire protocol fields, Phase 1b adds correlation_id via a wrapper:

```python
@dataclass
class TrackedPacket:
    """Packet with Phase 1b tracking metadata."""
    packet: CyncPacket          # From Phase 1a decode
    correlation_id: str         # UUID v7 for observability
    recv_time: float            # Timestamp for metrics
    dedup_key: str             # Key used for deduplication

@dataclass
class PendingMessage:
    """Tracks message awaiting ACK."""
    msg_id: bytes               # 3-byte wire protocol identifier
    correlation_id: str         # UUID v7 for observability and event tracing
    sent_at: float              # Timestamp for timeout calculation
    ack_event: asyncio.Event    # Set when ACK received
    retry_count: int = 0        # Number of retry attempts
```

### ReliableTransport Class

```python
class ReliableTransport:
    """Reliable message delivery using native Cync protocol ACK/response patterns."""

    def __init__(
        self,
        connection: TCPConnection,
        protocol: CyncProtocol,
        dedup_cache_size: int = 1000,
        dedup_ttl_seconds: int = 300,
        ack_timeout_seconds: int = 30,
    ):
        self.conn = connection
        self.protocol = protocol
        self.conn_mgr = ConnectionManager(connection, protocol)
        self.pending_acks: Dict[str, PendingMessage] = {}  # Key: correlation_id (UUID v7)
        self.msg_id_to_correlation: Dict[str, str] = {}  # Reverse lookup: msg_id.hex() -> correlation_id
        self.dedup_cache = LRUCache(max_size=dedup_cache_size, ttl=dedup_ttl_seconds)
        self.ack_timeout = ack_timeout_seconds

        # Start background cleanup task for expired pending ACKs
        self._ack_cleanup_task: Optional[asyncio.Task] = None
        self._ack_cleanup_task = asyncio.create_task(self._cleanup_expired_acks())

    async def connect(self) -> bool:
        """Perform handshake (0x23 → 0x28) and establish connection."""
        return await self.conn_mgr.connect()

    async def send_reliable(
        self,
        payload: bytes,
        msg_id: Optional[bytes] = None,  # 3 bytes
        timeout: float = 2.0,
        max_retries: int = 3,
    ) -> SendResult:
        """
        Send message and wait for native Cync ACK.

        Holds connection state lock during packet encoding and send to ensure
        atomic operation. Lock is released before waiting for ACK to allow
        reconnection during the wait period.
        """
        # 1. Generate UUID v7 correlation_id for tracking
        correlation_id = str(uuid.uuid7())
        # 2. Generate 3-byte msg_id if not provided (random or sequential)
        msg_id = msg_id or generate_msg_id()

        for attempt in range(max_retries):
            # Acquire lock only for state check + encoding (fast operations)
            async with self.conn_mgr._state_lock:
                if self.conn_mgr.state != ConnectionState.CONNECTED:
                    return SendResult(
                        success=False,
                        correlation_id=correlation_id,
                        reason=f"not_connected: {self.conn_mgr.state.value}"
                    )

                # 3. Store bidirectional mapping for ACK matching
                self.pending_acks[correlation_id] = PendingMessage(msg_id, ...)
                self.msg_id_to_correlation[msg_id.hex()] = correlation_id

                # 4. Encode packet using Phase 1a codec (fast, no network)
                packet = self.protocol.encode_data_packet(queue_id, msg_id, payload)

            # Lock released - perform network I/O outside critical section
            # 5. Send via TCPConnection with separate timeout
            try:
                success = await asyncio.wait_for(
                    self.conn.send(packet),
                    timeout=2.0
                )
            except asyncio.TimeoutError:
                # Cleanup pending message on timeout (with lock - connection may have changed)
                async with self.conn_mgr._state_lock:
                    self.pending_acks.pop(correlation_id, None)  # Use pop() - safe if already deleted
                    self.msg_id_to_correlation.pop(msg_id.hex(), None)
                record_ack_timeout_metric()
                if attempt < max_retries - 1:
                    await asyncio.sleep(self.retry_policy.get_delay(attempt))
                    continue
                else:
                    record_message_abandoned_metric(reason="send_timeout")
                    return SendResult(success=False, correlation_id=correlation_id, reason="send_timeout")

            if not success:
                # Remove from pending since send failed (with lock - prevents race with disconnect)
                async with self.conn_mgr._state_lock:
                    self.pending_acks.pop(correlation_id, None)
                    self.msg_id_to_correlation.pop(msg_id.hex(), None)
                continue  # Retry
            # 6. Wait for ACK (0x7B for 0x73 data, etc.) with timeout
            try:
                ack_received = await asyncio.wait_for(
                    self.pending_acks[correlation_id].ack_event.wait(),
                    timeout=timeout
                )
                if ack_received:
                    return SendResult(success=True, correlation_id=correlation_id)
            except asyncio.TimeoutError:
                # Record metric, retry with exponential backoff
                record_ack_timeout_metric()
                if attempt < max_retries - 1:
                    await asyncio.sleep(self.retry_policy.get_delay(attempt))
                    continue

            # 7. Max retries exceeded
            record_message_abandoned_metric(reason="max_retries")

        # 8. Return failure after all retries exhausted
        return SendResult(success=False, correlation_id=correlation_id, reason="max_retries")

    async def recv_reliable(self) -> TrackedPacket:
        """
        Receive message, send native Cync ACK, deduplicate.

        Returns TrackedPacket with correlation_id and dedup_key for observability.

        Raises:
            DuplicatePacketError: If packet is a duplicate (caught by dedup cache)
            PacketReceiveError: If receive or decode fails
        """
        # 1. Generate correlation_id for this reception (observability)
        correlation_id = str(uuid.uuid7())

        # 2. Receive via TCPConnection
        raw_packet = await self.conn.recv()

        # 3. Decode using Phase 1a codec (may raise PacketDecodeError)
        packet = self.protocol.decode_packet(raw_packet)

        # 4. Generate dedup_key from packet content (deterministic)
        dedup_key = self._make_dedup_key(packet)

        # 5. Check dedup cache
        if await self.dedup_cache.contains(dedup_key):
            # Duplicate detected - send ACK anyway (idempotent), raise exception
            await self._send_ack(packet)
            raise DuplicatePacketError(dedup_key)

        # 6. New packet - cache and process
        await self.dedup_cache.add(dedup_key, {"correlation_id": correlation_id})

        # 7. Send appropriate ACK based on packet type:
        #    - 0x23 → 0x28 (handshake)
        #    - 0x73 → 0x7B (data)
        #    - 0x83 → 0x88 (status)
        #    - 0xD3 → 0xD8 (heartbeat)
        await self._send_ack(packet)

        # 8. Return tracked packet with metadata
        return TrackedPacket(
            packet=packet,
            correlation_id=correlation_id,
            recv_time=time.time(),
            dedup_key=dedup_key
        )

    async def handle_ack(self, ack_packet: CyncPacket):
        """Handle native Cync ACK for pending message."""
        # 1. Extract 3-byte msg_id from ACK packet (position varies by ACK type)
        # 2. Convert to hex string: msg_id.hex()
        # 3. Reverse-lookup correlation_id: msg_id_to_correlation.get(msg_id.hex())
        # 4. Find in pending_acks using correlation_id
        # 5. Set ack_event to unblock sender
        # 6. Record metrics with ack_type
        # 7. Clean up both mappings (pending_acks and msg_id_to_correlation)

    async def _cleanup_expired_acks(self):
        """Background task to cleanup expired pending ACKs.

        Runs periodically with bounded interval (10s to 60s range).
        Removes entries where (now - sent_at) > ack_timeout.

        **Purpose (Technical Review Finding 3.2 - Clarified)**: Safety net for stuck ACKs,
        not primary timeout mechanism. Individual ACKs timeout via asyncio.wait_for() in
        send_reliable(). This cleanup catches edge cases where ACK event never set.

        **Edge Cases**:
        - Short timeout (< 30s): Cleanup interval (10s) may exceed ACK timeout (acceptable)
        - Long timeout (> 180s): Cleanup capped at 60s may delay eviction (acceptable)
        - Purpose is preventing unbounded dict growth, not fast failure detection

        Task lifecycle:
        - Started: In __init__() automatically
        - Stopped: Call stop() method which cancels task
        """
        # Cleanup interval: run 3x per timeout period, but bounded to 10-60s range
        # Example: ack_timeout=5s → interval=max(10, min(60, 5/3))=10s
        # Example: ack_timeout=30s → interval=max(10, min(60, 30/3))=10s
        # Example: ack_timeout=90s → interval=max(10, min(60, 90/3))=30s
        # Example: ack_timeout=300s → interval=max(10, min(60, 300/3))=60s (capped)
        cleanup_interval = max(10, min(60, self.ack_timeout / 3))

        try:
            while True:
                await asyncio.sleep(cleanup_interval)

                now = time.time()
                expired = []

                # Snapshot keys to avoid RuntimeError if dict changes during iteration
                for correlation_id in list(self.pending_acks.keys()):
                    pending_msg = self.pending_acks.get(correlation_id)
                    if pending_msg and (now - pending_msg.sent_at) > self.ack_timeout:
                        expired.append(correlation_id)

                # Remove expired entries
                for correlation_id in expired:
                    pending_msg = self.pending_acks.pop(correlation_id, None)
                    if pending_msg:
                        # Also remove reverse lookup
                        self.msg_id_to_correlation.pop(pending_msg.msg_id.hex(), None)
                        logger.warning(
                            "Expired pending ACK: correlation_id=%s, age=%.1fs",
                            correlation_id, now - pending_msg.sent_at
                        )

                if expired:
                    logger.info("Cleaned up %d expired pending ACKs", len(expired))

        except asyncio.CancelledError:
            logger.debug("ACK cleanup task cancelled")
            raise
        except Exception as e:
            logger.error("ACK cleanup task crashed: %s", e, exc_info=True)
            raise

    async def stop(self):
        """Stop transport and cleanup background tasks."""
        # Cancel ACK cleanup task
        if self._ack_cleanup_task and not self._ack_cleanup_task.done():
            self._ack_cleanup_task.cancel()
            try:
                await self._ack_cleanup_task
            except asyncio.CancelledError:
                pass

        # Disconnect connection manager
        await self.conn_mgr.disconnect()
```

### ACK Packet msg_id Extraction

⚠️ **PENDING PHASE 0.5 VALIDATION**: The positions below are **UNVALIDATED ASSUMPTIONS** based on legacy code patterns that may be incorrect. Actual positions will be confirmed during Phase 0.5 packet capture and documented in the validation report.

| ACK Type | Packet Name | msg_id Present? | Position (TBD from Phase 0.5) | Confidence | Phase 0.5 Status |
|----------|-------------|-----------------|-------------------------------|------------|------------------|
| 0x28 | HELLO_ACK | TBD | TBD | ⏳ Pending | Phase 0.5 Deliverable #2 will validate |
| 0x7B | DATA_ACK | TBD | TBD | ⏳ Pending | Phase 0.5 Deliverable #2 will validate |
| 0x88 | STATUS_ACK | TBD | TBD | ⏳ Pending | Phase 0.5 Deliverable #2 will validate |
| 0xD8 | HEARTBEAT_ACK | TBD | TBD | ⏳ Pending | Phase 0.5 Deliverable #2 will validate |

**Phase 0.5 Deliverable Requirements** (see acceptance criteria):
1. Real captured ACK packets (hex dumps) for all 4 types
2. Annotated breakdown showing actual msg_id positions (if present)
3. Validation of whether msg_id even exists in each ACK type
4. Update this table with confirmed positions before Phase 1b implementation
5. Recommendation for ACK matching strategy based on findings

**Implementation Guidance:**
- Phase 1b spec provides the architecture (ACK matching concept)
- Phase 0.5 provides the data (actual positions from real packets)
- **DO NOT START Phase 1b implementation** until Phase 0.5 validation complete

---

### Fallback Strategy: If msg_id NOT Present in ACK Packets

If Phase 0.5 validation finds that ACK packets do **NOT** contain msg_id, implement connection-level matching:

**Strategy**: FIFO Request-Response Queue
```python
class ReliableTransport:
    def __init__(self):
        # Simple FIFO queue: first sent → first ACK matched
        self.pending_requests: Deque[PendingMessage] = deque()
        # One request in-flight at a time per connection
        self.request_lock = asyncio.Lock()

    async def send_reliable(self, payload: bytes, ...) -> SendResult:
        async with self.request_lock:  # Serialize requests
            # 1. Send packet
            correlation_id = str(uuid.uuid7())
            pending_msg = PendingMessage(correlation_id, ...)
            self.pending_requests.append(pending_msg)

            await self.conn.send(packet)

            # 2. Wait for ACK (any ACK type matches oldest pending)
            await pending_msg.ack_event.wait()

            return SendResult(success=True, correlation_id=correlation_id)

    async def handle_ack(self, ack_packet: CyncPacket):
        # Match ACK to oldest pending request (FIFO)
        if self.pending_requests:
            pending = self.pending_requests.popleft()
            pending.ack_event.set()
```

**Trade-offs**:
- ✅ Simpler implementation (no msg_id extraction logic)
- ✅ Guaranteed correct matching (serialized requests)
- ❌ Lower throughput (one request at a time)
- ❌ Higher latency for bulk operations

**Performance Impact**:
- **Single device**: No impact (same as parallel matching for 1 device)
- **Group operations (10 devices)**: ~10× slower
  - Parallel matching: 10 devices × 200ms (parallel ACK wait) = ~200ms total
  - FIFO serialized: 10 devices × 200ms (serial) = ~2000ms total
- **Acceptable for Phase 1**: Smart home typical usage is 1-10 commands/sec
- **Re-evaluate in Phase 2**: If throughput becomes bottleneck, optimize with parallel matching

### ConnectionManager Class

```python
from enum import Enum

class ConnectionState(Enum):
    """Connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"

class ConnectionManager:
    """
    Manages connection lifecycle, handshake, and reconnection.

    **Architecture Note**: The handshake flow (connect()) uses raw TCPConnection methods
    (send/recv) to avoid a circular dependency with ReliableTransport. Since
    ReliableTransport.send_reliable() requires an established connection, the handshake
    must complete first using direct TCP operations. Handshake has its own retry logic
    separate from message retries.

    **Thread Safety**: Connection state is protected by `_state_lock` (asyncio.Lock) to
    prevent race conditions between retry loops in send_reliable() and reconnection logic.
    All state transitions (CONNECTING, CONNECTED, RECONNECTING, DISCONNECTED) must be
    performed while holding the lock. State checks in send_reliable() also acquire the
    lock to ensure consistent reads.

    **Performance Monitoring (Technical Review Finding 3.1 - Clarified)**: Lock hold time is instrumented and monitored with three-tier thresholds:
    - **Target**: < 1ms (typical state check + encoding operations)
    - **Warning**: > 10ms (logged as warning, investigate potential bottleneck)
    - **Critical**: > 100ms (indicates deadlock risk, escalate immediately)
    - Metric: `tcp_comm_state_lock_hold_seconds` (histogram records all durations)
    """

    def __init__(self, connection: TCPConnection, protocol: CyncProtocol):
        self.conn = connection
        self.protocol = protocol
        self.state = ConnectionState.DISCONNECTED
        self._state_lock = asyncio.Lock()  # Protect state transitions
        self.packet_router_task: Optional[asyncio.Task] = None  # Routes packets + monitors heartbeat
        self.reconnect_task: Optional[asyncio.Task] = None  # Track single reconnection attempt
        self.retry_policy = RetryPolicy(max_retries=5, base_delay=1.0, max_delay=30.0)

        # Credentials for reconnection (set during connect(), never None)
        self.endpoint: bytes = b""
        self.auth_code: bytes = b""

        # Lock hold time monitoring
        self._lock_hold_warnings: int = 0  # Count of >10ms lock holds

    async def connect(self, endpoint: bytes, auth_code: bytes) -> bool:
        """
        Perform handshake using raw TCP (bypass ReliableTransport).

        Uses raw TCPConnection.send() and recv() to avoid circular dependency with
        ReliableTransport. Implements handshake-specific retry logic with exponential backoff.

        Stores endpoint and auth_code for future reconnection attempts.

        Args:
            endpoint: 4-byte endpoint identifier from device authentication
            auth_code: Authentication code for handshake

        Returns:
            True if handshake successful, False otherwise
        """
        # Store credentials for reconnection
        self.endpoint = endpoint
        self.auth_code = auth_code

        async with self._state_lock:
            self.state = ConnectionState.CONNECTING

        for attempt in range(self.retry_policy.max_retries):
            try:
                # 1. Encode 0x23 handshake
                handshake_packet = self.protocol.encode_handshake(endpoint, auth_code)

                # 2. Send via raw TCP
                success = await self.conn.send(handshake_packet)
                if not success:
                    logger.warning("Handshake send failed, attempt %d/%d",
                                   attempt + 1, self.retry_policy.max_retries)
                    continue

                # 3. Wait for 0x28 ACK (timeout: 5s - handshake timeout from table)
                response = await asyncio.wait_for(
                    self.conn.recv(), timeout=5.0
                )

                if response and response[0] == 0x28:
                    async with self._state_lock:
                        self.state = ConnectionState.CONNECTED
                    self.packet_router_task = asyncio.create_task(self._packet_router())
                    record_handshake_metric("success")
                    logger.info("Handshake successful")
                    return True
                else:
                    logger.warning("Invalid handshake response: %s", response[:1].hex() if response else "empty")

            except asyncio.TimeoutError:
                logger.warning("Handshake timeout, attempt %d/%d",
                               attempt + 1, self.retry_policy.max_retries)

            # 4. Retry with exponential backoff
            if attempt < self.retry_policy.max_retries - 1:
                delay = self.retry_policy.get_delay(attempt)
                logger.debug("Retrying handshake after %.2fs", delay)
                await asyncio.sleep(delay)

        async with self._state_lock:
            self.state = ConnectionState.DISCONNECTED
        record_handshake_metric("failed")
        logger.error("Handshake failed after %d attempts", self.retry_policy.max_retries)
        return False

    async def reconnect(self, reason: str = "unknown") -> bool:
        """
        Reconnect with exponential backoff.

        Uses state lock to prevent races with send_reliable() retry loops.
        Uses stored endpoint and auth_code from initial connect() call.

        Raises:
            CyncConnectionError: If credentials not available (connect() never called)
        """
        # Validate credentials exist (set during initial connect())
        if not self.endpoint or not self.auth_code:
            raise CyncConnectionError(
                "Cannot reconnect: no credentials stored (connect() never called)"
            )

        logger.info("Reconnecting: %s", reason)
        record_reconnection_metric(reason)

        async with self._state_lock:
            self.state = ConnectionState.RECONNECTING

        await self.disconnect()  # Clean up old connection and tasks

        # Retry connect with backoff
        for attempt in range(self.retry_policy.max_retries):
            if await self.connect(self.endpoint, self.auth_code):  # Starts new heartbeat task
                return True
            delay = self.retry_policy.get_delay(attempt)
            await asyncio.sleep(delay)

        return False

    async def disconnect(self):
        """
        Clean disconnect with task cleanup.

        Task cleanup order: packet_router first, then reconnect, then connection.
        Uses timeout to prevent hanging on stuck tasks.
        """
        async with self._state_lock:
            self.state = ConnectionState.DISCONNECTED

        # Cleanup order: packet_router → reconnect → connection
        # 1. Cancel and await packet router task (with timeout)
        if self.packet_router_task and not self.packet_router_task.done():
            self.packet_router_task.cancel()
            try:
                await asyncio.wait_for(self.packet_router_task, timeout=5.0)
            except asyncio.CancelledError:
                logger.debug("Packet router task cancelled cleanly")
            except asyncio.TimeoutError:
                logger.warning("Packet router task cleanup timeout (5s)")
            except Exception as e:
                logger.error("Packet router task error during cleanup: %s", e)
            finally:
                self.packet_router_task = None

        # 2. Cancel and await reconnect task (with timeout)
        if self.reconnect_task and not self.reconnect_task.done():
            self.reconnect_task.cancel()
            try:
                await asyncio.wait_for(self.reconnect_task, timeout=5.0)
            except asyncio.CancelledError:
                logger.debug("Reconnect task cancelled cleanly")
            except asyncio.TimeoutError:
                logger.warning("Reconnect task cleanup timeout (5s)")
            except Exception as e:
                logger.error("Reconnect task error during cleanup: %s", e)
            finally:
                self.reconnect_task = None

        # 3. Close connection
        await self.conn.close()
        logger.info("Disconnect complete")

    def _trigger_reconnect(self, reason: str):
        """
        Trigger reconnection if not already in progress.

        Prevents multiple concurrent reconnection attempts. If a reconnection
        is already running, logs and skips the new trigger.
        """
        if self.reconnect_task is None or self.reconnect_task.done():
            logger.info("Triggering reconnection: %s", reason)
            self.reconnect_task = asyncio.create_task(self.reconnect(reason))
        else:
            logger.debug("Reconnection already in progress, skipping: %s", reason)

    async def _packet_router(self):
        """Route incoming packets by type and monitor heartbeat health.

        **Primary Responsibilities**:
        1. Route incoming packets to appropriate handlers/queues by packet type
        2. Monitor connection health via periodic heartbeat (0xD3 → 0xD8)
        3. Trigger reconnection on heartbeat failures or errors

        **Packet Routing**:
        - 0xD8: Heartbeat ACK (monitors connection health, not queued)
        - 0x83, 0x73: Data packets (queued to recv_queue for application processing)
        - Other types: Logged and queued for application

        **Task Lifecycle**:
        - **Start**: Created by connect() on successful handshake
        - **Stop**: Cancelled by disconnect() with proper cleanup
        - **Restart**: reconnect() calls disconnect() then connect() to get fresh task
        - **Crash Handling**: Any exception triggers reconnect()

        **Exception Handling**:
        - asyncio.CancelledError: Clean shutdown (re-raise after logging)
        - Other exceptions: Log error and trigger reconnect

        **Cleanup**: Always sets self.packet_router_task = None in disconnect()
        """
        last_heartbeat_sent = time.time()
        awaiting_heartbeat_ack = False

        try:
            while True:
                # Check connection state with lock (prevents race with reconnect)
                async with self._state_lock:
                    if self.state != ConnectionState.CONNECTED:
                        logger.debug("Packet router exiting: state changed to %s", self.state.value)
                        break

                # 1. Send periodic heartbeat every 60s (heartbeat_send_interval)
                if time.time() - last_heartbeat_sent > 60 and not awaiting_heartbeat_ack:
                    heartbeat_packet = self.protocol.encode_heartbeat()
                    success = await self.conn.send(heartbeat_packet)

                    if not success:
                        logger.warning("Heartbeat send failed")
                        record_heartbeat_metric("send_failed")
                        self._trigger_reconnect("heartbeat_send_failed")
                        break

                    last_heartbeat_sent = time.time()
                    awaiting_heartbeat_ack = True

                # 2. Receive and route packets (timeout allows heartbeat checking)
                try:
                    response = await asyncio.wait_for(
                        self.conn.recv(),
                        timeout=5.0  # Shorter timeout for responsive heartbeat sending
                    )

                    if not response:
                        continue

                    packet_type = response[0]

                    # Route packet by type
                    if packet_type == 0xD8:  # Heartbeat ACK
                        awaiting_heartbeat_ack = False
                        record_heartbeat_metric("success")
                        logger.debug("Heartbeat ACK received")

                    elif packet_type in {0x83, 0x73}:  # Data packets (status/commands)
                        # Queue for application processing (non-blocking)
                        try:
                            await asyncio.wait_for(
                                self.recv_queue.put(response),
                                timeout=1.0
                            )
                            logger.debug("Queued packet type 0x%02x for application", packet_type)
                        except asyncio.TimeoutError:
                            logger.warning("recv_queue full, packet type 0x%02x dropped", packet_type)

                    else:
                        # Unknown/unhandled packet type - queue anyway
                        logger.debug("Received unhandled packet type 0x%02x, queuing", packet_type)
                        try:
                            await asyncio.wait_for(
                                self.recv_queue.put(response),
                                timeout=1.0
                            )
                        except asyncio.TimeoutError:
                            logger.warning("recv_queue full, packet type 0x%02x dropped", packet_type)

                except asyncio.TimeoutError:
                    # No packet received - check if heartbeat ACK overdue
                    # heartbeat_ack_timeout = max(3 × ACK_timeout, 10s) = max(3×2s, 10s) = 10s
                    if awaiting_heartbeat_ack and (time.time() - last_heartbeat_sent > 10):
                        # Recheck connection state before triggering reconnect (prevent race)
                        async with self._state_lock:
                            if self.state == ConnectionState.CONNECTED:
                                logger.warning("Heartbeat ACK timeout (10s)")
                                record_heartbeat_metric("timeout")
                                self._trigger_reconnect("heartbeat_timeout")
                                break
                        # If state changed (reconnect already in progress), continue
                        continue
                    # Otherwise, continue loop (allows heartbeat send check)
                    continue

        except asyncio.CancelledError:
            # Clean cancellation from disconnect() - this is expected
            logger.debug("Packet router cancelled (clean shutdown)")
            raise
        except Exception as e:
            # Unexpected error - trigger reconnect and re-raise
            logger.error("Packet router crashed: %s", e, exc_info=True)
            record_heartbeat_metric("crash")
            self._trigger_reconnect("packet_router_crash")
            raise

    def is_connected(self) -> bool:
        """Check if connection is established."""
        return self.state == ConnectionState.CONNECTED

    async def with_state_check(self, operation: str, action: Callable[[], Awaitable[T]]) -> T:
        """Execute action after state check, with automatic lock pattern enforcement.

        Enforces pattern: acquire lock → check state → release lock → execute action.
        Monitors lock hold time and logs warnings if held too long.

        Args:
            operation: Operation name for logging (e.g., "send", "reconnect")
            action: Async callable to execute after state check

        Returns:
            Result from action

        Raises:
            CyncConnectionError: If connection not in CONNECTED state

        Example:
            # Before (manual pattern - error-prone):
            async with self._state_lock:
                if self.state != ConnectionState.CONNECTED:
                    raise CyncConnectionError("not_connected")
                packet = encode(...)
            # Lock released
            await conn.send(packet)  # Network I/O outside lock

            # After (helper enforces pattern):
            packet = encode(...)
            await self.with_state_check("send",
                lambda: conn.send(packet))
        """
        start = time.time()

        # Acquire lock for state check only (fast operation)
        async with self._state_lock:
            if self.state != ConnectionState.CONNECTED:
                raise CyncConnectionError("not_connected", self.state.value)

            # Record lock hold time
            hold_time = time.time() - start
            if hold_time > 0.01:  # 10ms warning threshold
                self._lock_hold_warnings += 1
                logger.warning(
                    "State lock held for %.1fms (operation: %s, warning #%d)",
                    hold_time * 1000, operation, self._lock_hold_warnings
                )

            # Record metric
            LOCK_HOLD_HISTOGRAM.observe(hold_time)

        # Lock released - execute action outside critical section
        return await action()
```

#### Connection State Lock Rules

The `_state_lock` (asyncio.Lock) protects connection state to prevent race conditions between concurrent operations. Follow these rules:

**When to Acquire the Lock:**

1. **State Transitions** (MUST hold lock):
   - Setting `self.state` to any value (CONNECTING, CONNECTED, RECONNECTING, DISCONNECTED)
   - Example: `async with self._state_lock: self.state = ConnectionState.CONNECTING`

2. **State Checks in Retry Loops** (MUST hold lock):
   - Before attempting to send in `send_reliable()` retry loop
   - Ensures connection isn't being torn down during reconnection
   - Example: `async with self._state_lock: if self.state != ConnectionState.CONNECTED: return SendResult(...)`

**When Lock is NOT Required:**

1. **Simple State Reads** (optional, depends on criticality):
   - `is_connected()` method: Read-only check, acceptable without lock for status queries
   - Heartbeat loop state check: Reads are atomic in Python, lock not strictly required

2. **Operations That Don't Touch State**:
   - Sending/receiving data on established connection
   - Encoding/decoding packets
   - Updating pending_acks or dedup_cache

**Critical Pattern: Retry Loop with Lock Released Before Network I/O**

```python
for attempt in range(max_retries):
    # MUST check state under lock before each retry
    # Hold lock ONLY for state check + encoding (fast operations)
    async with self.conn_mgr._state_lock:
        if self.conn_mgr.state != ConnectionState.CONNECTED:
            return SendResult(success=False, reason="not_connected")

        # Track pending message
        self.pending_acks[correlation_id] = PendingMessage(...)

        # Encode packet (fast, no network)
        packet = self.protocol.encode_data_packet(...)

    # Lock released - perform network I/O outside critical section
    try:
        await asyncio.wait_for(self.conn.send(packet), timeout=2.0)
    except asyncio.TimeoutError:
        # Cleanup pending message
        del self.pending_acks[correlation_id]
        # Handle timeout or retry
```

**Why This Matters:**

Without the lock, this race can occur:
1. Thread A: `send_reliable()` checks `state == CONNECTED` → passes
2. Thread B: `reconnect()` sets `state = RECONNECTING`
3. Thread B: `disconnect()` closes connection
4. Thread A: Attempts to send on closed connection → failure

With the lock, state transitions and checks are serialized, preventing this race.

**Why Lock Release Before Network I/O Matters:**

Without releasing lock before network I/O, deadlock can occur:
1. Thread A: Acquires lock, calls `conn.send()` which blocks on network hang
2. Thread B: Waits for lock indefinitely
3. No progress possible - system stuck

With lock released before network I/O:
1. Thread A: Acquires lock briefly for state check + encoding (fast)
2. Thread A: Releases lock, then performs network I/O with separate timeout
3. Thread B: Can acquire lock for its own operations
4. Network timeout (2s) handles hung connections independently
5. System can recover automatically

**Timeout Selection**:
- 2s for network I/O timeout (matches ACK timeout from performance targets)
- Lock held for minimal time (<1ms for state check + encoding)
- No deadlock possible since network I/O outside critical section

### LRUCache (Deduplication)

```python
class LRUCache:
    """LRU cache for message deduplication."""

    def __init__(self, max_size: int, ttl: int = 300):
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl

    async def contains(self, dedup_key: str) -> bool:
        """Check if message already processed (using Full Fingerprint dedup_key)."""

    async def add(self, dedup_key: str, metadata: dict):
        """Add message to cache (evict oldest if full)."""

    async def cleanup_expired(self) -> int:
        """Remove expired entries."""
```

#### Deduplication Strategy (Full Fingerprint - Selected)

**Status**: Full Fingerprint strategy (Option C) selected as default

**Strategy Selected**:
Full Fingerprint (Option C) provides maximum robustness. See implementation at line 1207 for complete code.

**Phase 0.5 Deliverable #8**: Field verification - confirms required fields (packet_type, endpoint, msg_id, payload) are extractable and stable across retries
**Phase 1b Step 4**: Strategy validation - tests that Full Fingerprint correctly identifies duplicates with automatic retries (this is the actual validation)

**⚠️ DEDUPLICATION STRATEGY: Full Fingerprint (Option C) SELECTED AS DEFAULT**

**Rationale**: Most robust strategy for early perfection of core functionality. Eliminates risk of dedup strategy being inadequate. Handles all protocol variance patterns without requiring Phase 0.5 validation results.

**Selected Strategy**: Option C - Full Fingerprint

**Implementation:**

```python
    def _make_dedup_key(self, packet: CyncPacket) -> str:
        """Generate deduplication key using Full Fingerprint strategy (Option C).

        Strategy: Combines multiple protocol fields for maximum robustness.
        Key format: "{packet_type:02x}:{endpoint.hex()}:{msg_id.hex()}:{payload_hash[:16]}"

        This strategy is collision-resistant and handles all protocol variance patterns
        without depending on Phase 0.5 retry analysis findings.

        Example:
            packet_type=0x73, endpoint=0x3987c857, msg_id=0x0a141e, payload=...
            dedup_key = "73:3987c857:0a141e:a3f2b9c4d8e1f6a2"

        REQUIRED: This method is deterministic - same logical packet MUST
        produce same key, even across multiple receptions.
        """
        import hashlib

        # Extract fields
        packet_type = packet.packet_type
        endpoint = packet.endpoint if hasattr(packet, 'endpoint') else b'\x00\x00\x00\x00'
        msg_id = packet.msg_id if hasattr(packet, 'msg_id') else b'\x00\x00\x00'
        payload = packet.data if hasattr(packet, 'data') else packet.payload

        # Generate payload hash
        payload_hash = hashlib.sha256(payload).hexdigest()[:16]

        # Combine into fingerprint
        return f"{packet_type:02x}:{endpoint.hex()}:{msg_id.hex()}:{payload_hash}"
```

**Observability vs Deduplication:**
- **dedup_key**: Deterministic from packet content (for duplicate detection)
- **correlation_id**: Unique per reception (UUID v7, for log tracing)
- Both tracked in recv_reliable() for comprehensive observability

#### msg_id Collision Risk Analysis

**Architectural Decision**: Sequential msg_id generation selected (Phase 1a Step 5.5)

**Collision Probability**: **0%** (within single connection lifetime)

**Rationale**:
- Sequential counter with wrapping at 16.7M (2^24)
- Typical connection duration: hours to days
- Typical message count: thousands to millions
- Collision only possible after full counter wrap AND reusing same value while previous still pending
- In practice: impossible for smart home usage patterns

**Benefits**:
- ✅ **Zero collision risk** - no collision handling needed in ACK matching
- ✅ **Deterministic behavior** - sequential IDs aid debugging
- ✅ **Simple implementation** - single counter, no complex tracking
- ✅ **Predictable logs** - msg_ids increment in order

**Implementation** (from Phase 1a):
```python
class ReliableTransport:
    def __init__(self):
        self._msg_id_counter: int = 0

    def generate_msg_id(self) -> bytes:
        """Generate sequential 3-byte msg_id."""
        msg_id = (self._msg_id_counter % 0xFFFFFF).to_bytes(3, 'big')
        self._msg_id_counter += 1
        return msg_id
```

**Deduplication Independence**:
- **msg_id**: 3-byte wire protocol identifier for ACK matching
- **dedup_key**: Deterministic hash for collision-free deduplication (based on packet content)
- **correlation_id**: UUID v7 for observability only (NOT used for deduplication)
- Deduplication uses dedup_key (deterministic), NOT msg_id or correlation_id (see section below for details)

**No Collision Analysis Required**: With sequential generation, collision scenarios do not exist. ACK matching using msg_id → correlation_id reverse-lookup is straightforward without collision handling.

---

#### Deduplication vs Observability Identifiers (Clarification)

Phase 1b uses **two separate identifier systems** for different purposes. Understanding this distinction is critical to avoid confusion during implementation.

**System 1: dedup_key (Deterministic, for Duplicate Detection)**

- **Purpose**: Identify duplicate packets arriving multiple times
- **Generation**: Deterministic hash from packet content (endpoint, msg_id, payload)
- **Uniqueness**: Same logical packet → same dedup_key
- **Usage**: LRU cache lookup in `recv_reliable()`
- **Strategy**: Full Fingerprint (Option C) - selected as default for maximum robustness

**System 2: correlation_id (Unique, for Observability)**

- **Purpose**: Track individual reception events for logging and metrics
- **Generation**: UUID v7 generated per `recv_reliable()` call
- **Uniqueness**: Different for every call, even if duplicate packet
- **Usage**: Log tracing, metrics correlation, debugging
- **Strategy**: Always UUID v7 (collision-free)

**Why Two Systems?**

```python
# Scenario: Device sends packet X twice (duplicate)

# First reception:
packet_1 = await recv_reliable()
# - correlation_id = "01936d45-3c4e-7890-aaaa-111111111111" (UUID v7)
# - dedup_key = "sha256(endpoint+msg_id+payload)" = "abc123..."
# - Cache miss → process packet, add to cache

# Second reception (duplicate):
packet_2 = await recv_reliable()
# - correlation_id = "01936d45-3c4e-7890-bbbb-222222222222" (DIFFERENT UUID v7!)
# - dedup_key = "sha256(endpoint+msg_id+payload)" = "abc123..." (SAME!)
# - Cache hit → DuplicatePacketError raised

# Log analysis: Both UUID_A and UUID_B appear in logs
# - UUID_A: "Packet processed successfully"
# - UUID_B: "Duplicate packet dropped (dedup_key=abc123...)"
# This allows full observability of duplicate detection
```

**Common Mistake to Avoid:**

❌ **WRONG**: Using correlation_id as dedup_key
```python
# BAD - correlation_id is unique per call, won't detect duplicates!
dedup_key = correlation_id  # UUID v7, never matches
```

✅ **CORRECT**: Use dedup_key for cache, correlation_id for logs
```python
# Deduplication check
if await self.dedup_cache.contains(dedup_key):  # deterministic key
    logger.warning("Duplicate detected", correlation_id=correlation_id)  # unique ID for this log
    raise DuplicatePacketError(dedup_key)
```

**Implementation Checklist:**

- [ ] `_make_dedup_key(packet)` returns deterministic hash (same packet → same key)
- [ ] `correlation_id` generated fresh per `recv_reliable()` call (UUID v7)
- [ ] LRU cache uses `dedup_key` as lookup key
- [ ] Logs include both `correlation_id` (event ID) and `dedup_key` (content hash)
- [ ] Never use `correlation_id` for deduplication logic
- [ ] Never use `dedup_key` as primary log identifier (not unique per event)

**Table Summary:**

| Identifier | Purpose | Generation | Uniqueness | Used For |
|------------|---------|------------|------------|----------|
| **dedup_key** | Duplicate detection | Deterministic hash of packet content | Same packet → same key | LRU cache lookup |
| **correlation_id** | Event tracking | UUID v7 per reception | Different every call | Logging, metrics, tracing |

---

### RetryPolicy

```python
class RetryPolicy:
    """Exponential backoff retry policy."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 0.25,
        max_delay: float = 5.0,
        jitter: float = 0.1,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """Calculate delay: min(base * 2^attempt, max) + jitter."""
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        return delay + random.uniform(-self.jitter, +self.jitter)
```

---

## Implementation Plan

### Step 0: Prerequisites Check & Timeout Recalibration Handoff

**Prerequisite**: Phase 0.5 ACK validation complete

**⚠️ CRITICAL HANDOFF PROCEDURE (Technical Review Finding 1.2 - Resolved)**

Before starting Phase 1b implementation, perform formal handoff review:

**Phase 0.5 → Phase 1b Handoff Checklist:**
- [ ] Verify Phase 0.5 ACK validation complete (deliverables #1-8 signed off)
- [ ] Review `docs/protocol/validation-report.md` for ACK msg_id presence findings
- [ ] **CRITICAL**: Review ACK latency measurements from Phase 0.5 Tier 2 criteria:
  - [ ] Confirm 100+ ACK samples captured per type (0x28, 0x7B, 0x88, 0xD8)
  - [ ] Extract measured p50, p95, p99 ACK latencies from validation report
  - [ ] Compare measured p99 to assumed value (800ms default)
- [ ] **Timeout Recalibration** (if measured p99 differs from 800ms):
  - [ ] Update `TimeoutConfig` default parameter: `measured_p99_ms=<actual_value>`
  - [ ] Recalculate all dependent timeouts using TimeoutConfig formulas:
    - ACK timeout = measured_p99 × 2.5
    - Handshake timeout = ACK timeout × 2.5
    - Heartbeat timeout = max(ACK timeout × 3, 10s)
    - Cleanup timeout = ACK timeout × 15
  - [ ] Document timeout adjustments in Phase 1b implementation notes
  - [ ] Verify no hardcoded timeout values in Phase 1b spec examples
- [ ] Check ACK confidence levels for all 4 ACK types (High/Medium/Low)
- [ ] Select implementation path based on findings (Parallel vs FIFO)

**Example Timeout Recalibration**:
```python
# If Phase 0.5 measured p99 ACK latency = 1200ms (instead of assumed 800ms):
timeouts = TimeoutConfig(measured_p99_ms=1200.0)
# Automatically calculates:
# - ack_timeout_seconds = 3.0s (was 2.0s)
# - handshake_timeout_seconds = 7.5s (was 5.0s)
# - heartbeat_timeout_seconds = 10.0s (unchanged - 3×3s < 10s minimum)
# - cleanup_timeout_seconds = 45s (was 30s)

# Use in initialization:
transport = ReliableTransport(
    connection=conn,
    protocol=protocol,
    ack_timeout=timeouts.ack_timeout_seconds,  # NOT hardcoded 2.0!
)
```

**Prerequisites Checklist (continued)**:

**Implementation Path Selection**:

Based on Phase 0.5 findings, choose approach:

**Path A: msg_id Present in ACK Packets** (if validated)
- Implementation: Parallel ACK matching using msg_id → correlation_id reverse-lookup
- Architecture: As specified in § ReliableTransport Class
- Proceed with: Main implementation plan (Steps 1-5 below)

**Path B: msg_id Absent in ACK Packets** (if not found)
- Implementation: FIFO request-response queue with serialized requests
- Architecture: Use fallback strategy (see § Fallback Strategy)
- Proceed with: Modified implementation plan

**Path C: Ambiguous Findings** (if inconsistent)
- Capture additional samples to clarify, or
- Implement FIFO approach (safer fallback)
- Document ambiguity

---

### Step 1: Connection Management
- Implement `ConnectionManager` class
- Connection state machine (disconnected, connecting, connected, reconnecting)
- Handshake flow (0x23 → 0x28)
- Reconnection with exponential backoff
- Unit tests for connection lifecycle

**Connection State Lock Implementation Checklist** (Critical for Correctness):

The state lock pattern prevents deadlock and race conditions between retry loops and reconnection logic. Verify each item during implementation:

**Lock Acquisition Rules**:
- [ ] Lock acquired BEFORE state check in `send_reliable()` retry loop
- [ ] Lock acquired BEFORE all state transitions (CONNECTING → CONNECTED, etc.)
- [ ] Lock released BEFORE network I/O operations (conn.send/recv)
- [ ] Lock held for minimal time (<1ms for typical state check + encoding)

**Network I/O Separation** (Deadlock Prevention):
- [ ] Network I/O (conn.send/recv) has separate timeout (2s), independent of lock
- [ ] Lock released before `await conn.send(packet)` call
- [ ] Lock released before `await conn.recv()` call
- [ ] State check → encoding → release lock → network I/O pattern verified

**Lock Hold Time Monitoring**:
- [ ] Lock hold time instrumented with timing wrapper
- [ ] Log warning if lock held > 10ms (indicates potential issue)
- [ ] Metric `tcp_comm_state_lock_hold_seconds` recorded (histogram)
- [ ] Lock hold warnings tracked in `_lock_hold_warnings` counter

**Unit Tests** (Verify Lock Correctness):
- [ ] Test: Verify no deadlock if network hangs (mock conn.send() to block indefinitely, verify timeout fires and lock released)
- [ ] Test: Verify reconnect during send_reliable() handles state correctly (trigger reconnect mid-retry, verify send_reliable() detects state change)
- [ ] Test: Verify concurrent sends work correctly (launch 10 send_reliable() calls with asyncio.gather, verify no race conditions)
- [ ] Test: Verify lock hold time < 10ms for typical operations (instrument and measure)

**Implementation Pattern Example**:
```python
for attempt in range(max_retries):
    # Acquire lock for state check + encoding (FAST operations only)
    async with self.conn_mgr._state_lock:
        if self.conn_mgr.state != ConnectionState.CONNECTED:
            return SendResult(success=False, reason="not_connected")

        # Track pending message
        self.pending_acks[correlation_id] = PendingMessage(...)

        # Encode packet (fast, no network)
        packet = self.protocol.encode_data_packet(...)

    # Lock released - perform network I/O outside critical section
    try:
        await asyncio.wait_for(self.conn.send(packet), timeout=2.0)
    except asyncio.TimeoutError:
        # Handle timeout with lock for cleanup
        async with self.conn_mgr._state_lock:
            self.pending_acks.pop(correlation_id, None)
        continue
```

**Code Review Focus**: Explicitly review lock pattern during retry logic implementation (Step 3) to ensure correct implementation.

**Enforcement Mechanism (Technical Review Finding 4.1 - Added)**:

**Option 1: Custom Linting Rule** (automated enforcement):
```python
# .ruff_custom_rules/state_lock_enforcement.py
"""Custom ruff rule to detect network I/O inside state lock critical sections."""

def check_lock_pattern_violation(node):
    """Flag conn.send() or conn.recv() calls inside 'async with self._state_lock' blocks.

    Detects anti-patterns like:
    ```python
    async with self._state_lock:
        await self.conn.send(packet)  # ❌ Network I/O inside lock!
    ```

    Allows correct patterns:
    ```python
    async with self._state_lock:
        packet = encode(...)  # ✅ Fast operation
    # Lock released
    await self.conn.send(packet)  # ✅ Network I/O outside lock
    ```
    """
    # Implementation: AST visitor detecting await expressions inside lock context
    # Check: If within "async with self._state_lock" block
    # Flag: Any await call to self.conn.send/recv/read/write
    pass
```

**Option 2: Unit Test Enforcement** (verifies runtime behavior):
```python
# tests/unit/transport/test_connection_lock_safety.py

async def test_no_deadlock_on_network_hang():
    """Verify lock released before network I/O (prevents deadlock)."""
    # Mock conn.send() to block indefinitely
    async def hung_send(data):
        await asyncio.sleep(1000000)  # Never returns

    conn = MockConnection(send=hung_send)
    transport = ReliableTransport(conn, ...)

    # send_reliable() should timeout after 2s, NOT deadlock
    start = time.time()
    result = await transport.send_reliable(b"test", timeout=2.0, max_retries=1)
    elapsed = time.time() - start

    assert result.success is False
    assert elapsed < 3.0  # Should timeout, not hang forever
    # If lock held during network I/O, this test would hang indefinitely

async def test_lock_released_before_network_io():
    """Verify lock hold time excludes network I/O duration."""
    conn = MockConnection(send_delay=1.0)  # 1 second network delay
    transport = ReliableTransport(conn, ...)

    await transport.send_reliable(b"test")

    # Lock hold time should be < 10ms (state check + encoding)
    # Network delay (1s) should NOT be included in lock hold time
    max_lock_hold = max(transport.conn_mgr._lock_hold_times)
    assert max_lock_hold < 0.01, f"Lock held during network I/O: {max_lock_hold}s"
```

**Option 3: Code Review Checklist** (manual verification):
```markdown
## Phase 1b Step 3 Lock Pattern Review

### Connection State Lock Rules Verification
- [ ] Lock acquired BEFORE state check in send_reliable() retry loop
- [ ] Lock released BEFORE await conn.send() call
- [ ] Lock released BEFORE await conn.recv() call
- [ ] Network I/O operations have separate timeout (2s), independent of lock
- [ ] Pattern verified: `async with lock: check + encode` → `release` → `await network_io()`

**Verification commands**:
```bash
# Search for potential violations (manual review needed)
# Flag any conn.send/recv calls that might be inside lock blocks
grep -A 5 "async with self._state_lock" src/transport/
```
```

**Recommended**: Use Option 2 (unit tests) + Option 3 (code review) for Phase 1b. Add Option 1 (linting) in Phase 2 if pattern violations recur.

### Step 2: Heartbeat & Core ReliableTransport (continued)
- Implement heartbeat loop (0xD3 → 0xD8)
- Implement `send_reliable()` with native ACK wait
- Implement `recv_reliable()` with auto-ACK
- ACK matching with 3-byte msg_id
- Unit tests for happy path

### Step 3: Retry Logic (continued)
- Implement retry loop with exponential backoff
- RetryPolicy class
- Pending message tracking with correlation_id keys and msg_id reverse-lookup
- ACK cleanup background task
- Unit tests for timeout scenarios
- **State lock pattern tests** - See Concurrency Testing section (lines 1629-1646) for lock correctness tests
- Metrics for retries

### Step 4: Deduplication Implementation + Strategy Validation (continued)

**Implementation**:
- Implement Full Fingerprint strategy (Option C) in `_make_dedup_key()`
- Implement LRUCache with dedup_key (deterministic hash from packet content)
- Integrate with `recv_reliable()`
- TTL-based expiry

**Strategy Validation** (this is the actual validation, not Phase 0.5):
- **Tests dedup effectiveness**: Confirms Full Fingerprint correctly identifies duplicate packets
- Run Phase 1d simulator with 20% packet drop to trigger automatic retries
- Verify zero false positives (different packets incorrectly marked as duplicates)
- Verify zero false negatives (duplicate packets not detected)
- Capture 20+ automatic retry sequences for validation
- Document findings: "Full Fingerprint strategy validated - correctly identifies all duplicates"

**Phase 0.5 vs Phase 1b Step 4**:
- **Phase 0.5**: Field verification - confirms required fields exist and are extractable
- **Phase 1b Step 4**: Strategy validation - tests that dedup actually works correctly

**Unit tests**:
- Test `_make_dedup_key()` returns same key for duplicate packets (determinism)
- Test `_make_dedup_key()` returns different key for distinct packets (uniqueness)
- Test dedup cache correctly detects duplicates (zero false positives/negatives)
- Test with retry packet examples from Phase 0.5 field verification

### Day 5: Integration & Testing

**Scope** (Group validation removed - moved to Phase 1d):
- Integrate all components (ConnectionManager, ReliableTransport, LRUCache, RetryPolicy)
- Create new `harness/toggler_v2.py` using real protocol with ReliableTransport
- End-to-end tests with all ACK types (0x28, 0x7B, 0x88, 0xD8)
- Connection/reconnection tests
- Metrics validation (all 25+ metrics reporting correctly)
- Deduplication tests with retry scenarios

**Removed from Phase 1b Day 5**: Group Operation Validation (moved to Phase 1d baseline tests)

**Rationale for Consolidation**:
- Group validation requires full stack (Phase 1c queues + Phase 1d simulator)
- Phase 1b Day 5 is too early (ReliableTransport may not be fully optimized yet)
- Single validation point (Phase 1d) provides clearer decision making
- Phase 1d simulator offers chaos testing capabilities for comprehensive group validation

**See Phase 1d**: `02e-phase-1d-simulator.md` (Group Operation Validation section) for authoritative group operation validation

---


---

## Acceptance Criteria

### Functional
- [ ] Native Cync ACK handling for all packet types (0x28, 0x7B, 0x88, 0xD8)
- [ ] Connection handshake (0x23 → 0x28) successful
- [ ] Keepalive/heartbeat (0xD3 → 0xD8) working
- [ ] Automatic reconnection on connection loss
- [ ] `send_reliable()` waits for appropriate ACK before returning
- [ ] ACK matching using correlation_id (UUID v7) with reverse-lookup from msg_id
- [ ] Automatic retries on timeout (up to max_retries)
- [ ] Exponential backoff with jitter for retries and reconnection
- [ ] Duplicate messages detected and dropped using dedup_key (Full Fingerprint strategy)
- [ ] LRU cache evicts oldest when full
- [ ] TTL-based expiry of cache entries
- [ ] Background cleanup of expired pending ACKs
- [ ] **Full Fingerprint strategy implemented** and tested (Step 4)
- [ ] **Full Fingerprint verified** with automatic retries (Step 4)
- [ ] **Test fixtures from Phase 0.5** used in unit tests

### Testing
- [ ] 25+ unit tests
- [ ] Test scenarios: connection, handshake, reconnection, heartbeat, success, timeout, retry, duplicate, cache full
- [ ] ACK matching tests with various msg_id formats
- [ ] Connection state transition tests
- [ ] **test_reconnect_during_send_retry()**: Integration test for reconnection interrupting send retry loop
- [ ] **test_dedup_cache_load()**: Load test with 10,000 messages + 5% duplicates, verify <1ms p99 lookup
- [ ] **test_ack_cleanup_task()**: Verify background cleanup removes expired ACKs (add 10 expired entries, wait, verify cleanup)
- [ ] 100% test pass rate
- [ ] No flaky tests

### Concurrency Testing (Critical for Correctness)
- [ ] **Lock correctness: No deadlock if network hangs**
  - Test: Mock conn.send() to block indefinitely (simulates network hang)
  - Expected: send_reliable() times out after 2s, lock released, other operations can proceed
  - Validates: Lock released before network I/O, timeout fires correctly
- [ ] **Lock correctness: Reconnect during send_reliable() detected**
  - Test: Trigger reconnect while send_reliable() is in retry loop
  - Expected: send_reliable() detects state change (RECONNECTING), fails gracefully
  - Validates: No deadlock, no stale connection writes, proper error returned
- [ ] **Lock correctness: Lock hold time < 10ms for typical operations**
  - Test: Instrument state lock with timing wrapper, measure hold duration
  - Expected: Lock held < 1ms for state check + encoding, < 10ms worst case
  - Validates: Metric `tcp_comm_state_lock_hold_seconds` recorded, warnings logged if > 10ms
- [ ] **Lock correctness: 10 concurrent send_reliable() calls work correctly**
  - Test: Launch 10 concurrent send_reliable() calls using asyncio.gather()
  - Expected: All complete successfully, no race conditions, no state corruption
  - Validates: All ACKs matched correctly, pending_acks cleaned up, no memory leaks

### Performance
- [ ] Retry delays match policy (250ms, 500ms, 1s, ...)
- [ ] Dedup check < 1ms per message
- [ ] Cache eviction < 5ms

### Quality
- [ ] No ruff errors
- [ ] No mypy errors (strict mode)
- [ ] Full type annotations
- [ ] Comprehensive logging

### Timeout Configuration
- [ ] **REQUIRED**: All timeout values use `TimeoutConfig` class (no hard-coded timeout arguments in constructors)
- [ ] Linting rule enforces TimeoutConfig pattern (rejects manual timeout values)
- [ ] `TimeoutConfig` initialized with Phase 0.5 measured p99 value

---

## Testing Strategy

### Unit Tests

```python
# test_reliable_transport.py

async def test_send_with_ack_success():
    """Send message, receive ACK, return success."""
    transport = ReliableTransport(mock_conn, mock_protocol)
    result = await transport.send_reliable(b"test payload")
    assert result.success is True
    assert result.retry_count == 0

async def test_send_retry_on_timeout():
    """Send message, timeout, retry, then success."""
    # Mock first send to timeout, second to succeed
    result = await transport.send_reliable(b"test", max_retries=2)
    assert result.success is True
    assert result.retry_count == 1

async def test_send_max_retries_exceeded():
    """All retries fail, return failure."""
    # Mock all sends to timeout
    result = await transport.send_reliable(b"test", max_retries=3)
    assert result.success is False
    assert result.retry_count == 3

async def test_recv_duplicate_dropped():
    """Receive duplicate message, send ACK, raise DuplicatePacketError."""
    # Add dedup_key to cache first (simulating already-seen message)
    dedup_key = "73:3987c857:0a141e:a3f2b9c4d8e1f6a2"  # Full Fingerprint
    await transport.dedup_cache.add(dedup_key, {"correlation_id": "01936d45-3c4e-7890-abcd-ef1234567890"})
    # Receive same message (with same dedup_key)
    with pytest.raises(DuplicatePacketError):
        packet = await transport.recv_reliable()
    # Verify ACK still sent

async def test_dedup_cache_lru_eviction():
    """Cache evicts oldest when full."""
    cache = LRUCache(max_size=3)
    # Use dedup_key (Full Fingerprint) as cache keys
    await cache.add("73:3987c857:000001:a1b2c3d4e5f6g7h8", {})
    await cache.add("73:3987c857:000002:a2b3c4d5e6f7g8h9", {})
    await cache.add("73:3987c857:000003:a3b4c5d6e7f8g9h0", {})
    await cache.add("73:3987c857:000004:a4b5c6d7e8f9g0h1", {})  # Should evict first
    assert await cache.contains("73:3987c857:000001:a1b2c3d4e5f6g7h8") is False
    assert await cache.contains("73:3987c857:000004:a4b5c6d7e8f9g0h1") is True
```

---

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| ACK timeout tuning | Medium | Lab testing with various network conditions; configurable timeouts |
| Dedup false negatives | Low | UUID v7 collision-resistant keys eliminate msg_id collision risk; comprehensive unit tests verify cache behavior |
| Retry storms | Medium | Exponential backoff with jitter; max retry limits |
| Cache memory growth | Low | LRU eviction + TTL expiry; monitor cache size metric |

---

## Dependencies

**Prerequisites**:
- Phase 1a complete (protocol codec working)
- Phase 0 TCPConnection available

**External**:
- None

---

## Next Phase

**Phase 1c**: Backpressure & Queues (3-4 days)
- Add bounded send/receive queues
- Overflow policies (block, drop, reject)
- Queue depth metrics

---

## Related Documentation

- **Phase 1 Program**: `02-phase-1-spec.md` - Architecture details
- **Phase 1a**: `02b-phase-1a-protocol-codec.md` - Protocol codec (prerequisite)
- **Phase 1c**: `02d-phase-1c-backpressure.md` - Next phase

