# Phase 1c: Backpressure & Queues

**Status**: Planning
**Dependencies**: Phase 1b (reliable transport) complete
**Execution**: Sequential solo implementation

---

## Overview

Phase 1c adds bounded queues and flow control to prevent buffer bloat and memory exhaustion under high load. This implements backpressure mechanisms with configurable overflow policies.

**See Also**: `02-phase-1-spec.md` for architecture context.

---

## Phase 0.5 Prerequisites ✅ Complete

Phase 0.5 validation completed 2025-11-07 with backpressure behavior analysis:

**Device Backpressure Behavior** (✅ Analyzed):

- Peak throughput: 161 packets/second observed
- Aggressive device buffering: 52,597 rapid sequences (<100ms between packets)
- Devices can handle backpressure (tolerate slow consumers)
- Quick reconnection: avg 2.6 seconds after disconnect
- Reference: `docs/phase-0.5/backpressure-behavior.md`

**Preliminary Recommendations** (from Phase 0.5):

- recv_queue size: **100 packets** (preliminary - validate in Phase 1d)
  - Calculation: 100 packets ÷ 161 pkts/sec = ~620ms buffer at peak
  - Conservative sizing for typical smart home usage patterns
- recv_queue policy: **BLOCK** (preliminary - validate in Phase 1d)
  - Rationale: Devices tolerate backpressure (confirmed via analysis)
  - Prevents message loss while maintaining flow control
- **Note**: These are preliminary recommendations pending Phase 1d chaos testing validation

---

## Architectural Scope: Phase 1 vs Phase 2

**Phase 1 Scope** (This Phase): Single-Device Reliability

- **Target**: 1-10 devices per controller instance
- **Group commands**: Best-effort using `asyncio.gather()` pattern (acceptable if p99 < 5s)
- **Performance**: Optimized for single-device latency (p99 < 800ms for individual commands)
- **Queue Architecture**: Receive queue only (no send queue)

**Phase 2 Scope** (Future): Multi-Device Scalability

- **Target**: 10-100 devices per controller instance
- **Group commands**: Guaranteed performance (p99 < 2s for 10-device groups)
- **Implementation**: Add send_queue + connection pooling **only if** Phase 1b/1d validations show need
- **Optimization**: State lock contention, parallel processing improvements

**Decision Criteria** (from Phase 1d group validation):

- **If p99 < 2s**: Phase 1 architecture validated for typical smart home (5-10 devices)
- **If p99 >= 2s but < 5s**: Phase 1 acceptable for small deployments, Phase 2 adds scaling optimizations
- **If p99 >= 5s**: Document as limitation, Phase 2 required for production use

**User Expectation**: Phase 1 delivers **reliable single-device control**. Multi-device optimization is a Phase 2 enhancement, not a Phase 1 requirement. Group command performance is validated but not optimized in Phase 1.

---

## Goals

1. Implement bounded receive queue with configurable overflow policies
2. Support three overflow policies (BLOCK, DROP_OLDEST, REJECT)
3. Add queue depth and overflow metrics
4. Performance test under load conditions
5. Integrate recv queue with Phase 1b reliable transport

**Note**: No send queue implemented - bulk operations use `asyncio.gather()` pattern (see Architecture Decision)

---

## Deliverables

### Code

- [ ] `src/transport/bounded_queue.py` - BoundedQueue class (~120-150 lines)
- [ ] `src/transport/queue_policy.py` - Overflow policy enum (~40-50 lines)
- [ ] Integration with `ReliableTransport` from Phase 1b
- [ ] 10+ unit tests for queue behaviors

### Features

- [ ] Bounded receive queue (default: 100 messages)
- [ ] Three overflow policies: BLOCK, DROP_OLDEST, REJECT
- [ ] Queue depth tracking
- [ ] Overflow event counting
- [ ] No send queue (bulk operations use `asyncio.gather()` pattern)

### Metrics (New)

```python
tcp_comm_recv_queue_size{device_id}              # Gauge
tcp_comm_queue_full_total{device_id, queue_type} # Counter
tcp_comm_queue_dropped_total{device_id, queue_type, reason}  # Counter
```

**Note**: No send_queue in Phase 1c - bulk operations use `asyncio.gather()` pattern without queueing layer. All metrics shown are recv_queue only. The `queue_type="recv"` label is included for future extensibility (if send_queue added in Phase 2 based on Phase 1b group validation), but Phase 1c only uses "recv" value.

### Metrics Recording Points

The table below specifies where each metric should be recorded in the codebase.

**⚠️ Line Number Guidance (Technical Review Finding 4.5 - Enhanced)**: Line numbers are **approximate** and WILL drift during implementation/refactoring. Use method names and trigger events as **primary reference**.

**Best Practices**:

- Mark recording locations with comments: `# METRIC: tcp_comm_recv_queue_size`
- After implementation: Update table to remove line numbers, keep method names only
- Focus on trigger events (e.g., "after successful put()") not exact line positions

| Metric                         | Code Location                                                 | Trigger Event                             | Labels                                                                                         |
| ------------------------------ | ------------------------------------------------------------- | ----------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `tcp_comm_recv_queue_size`     | `BoundedQueue.put()` / `BoundedQueue.get()` (after operation) | After successful put() or get() operation | Set gauge to `self.queue.qsize()`. Labels: `device_id`, `queue_type="recv"`                    |
| `tcp_comm_queue_full_total`    | `BoundedQueue.put()` (before overflow handling)               | When `queue.full()` condition detected    | Record for all policies (BLOCK/DROP_OLDEST/REJECT). Labels: `device_id`, `queue_type="recv"`   |
| `tcp_comm_queue_dropped_total` | `BoundedQueue.put()` (DROP_OLDEST policy, after drop)         | After oldest item dropped from queue      | Record with `reason="overflow"`. Labels: `device_id`, `queue_type="recv"`, `reason="overflow"` |

**Implementation Notes**:

- Record `tcp_comm_recv_queue_size` gauge AFTER put/get completes (reflects current state)
- Record `tcp_comm_queue_full_total` counter BEFORE overflow handling (tracks full events)
- Record `tcp_comm_queue_dropped_total` counter AFTER dropping item (tracks data loss)
- All metrics use `queue_type="recv"` label (no send_queue in Phase 1c)
- Include `device_id` label for per-device tracking (obtained from connection context)
- **Mark recording locations** with comments: `# METRIC: tcp_comm_recv_queue_size`
- **Line numbers are approximate** - use method names and trigger events as primary reference

**Example Recording**:

```python
## In BoundedQueue.put() - DROP_OLDEST policy
if self.queue.full():
    # Record full event
    QUEUE_FULL_COUNTER.labels(device_id=device_id, queue_type="recv").inc()

    # Drop oldest
    try:
        self.queue.get_nowait()
        self.dropped_count += 1
        # Record drop event
        QUEUE_DROPPED_COUNTER.labels(
            device_id=device_id,
            queue_type="recv",
            reason="overflow"
        ).inc()
    except asyncio.QueueEmpty:
        pass

    # Add new item
    self.queue.put_nowait(item)

    # Update size gauge
    QUEUE_SIZE_GAUGE.labels(device_id=device_id, queue_type="recv").set(self.queue.qsize())
```

---

## Architecture

### Custom Exceptions

Following the **No Nullability** principle and extending the exception hierarchy from Phase 1a-1b:

```python
from protocol.exceptions import CyncProtocolError  # From Phase 1a

class QueueFullError(CyncProtocolError):
    """Queue is full and cannot accept new items

    Raised when:
    - REJECT policy and queue is full
    - BLOCK policy with timeout expired
    - Queue overflow detected

    This exception enables explicit backpressure signaling to callers.
    """

    def __init__(self, queue_name: str, policy: str, queue_size: int):
        self.queue_name = queue_name
        self.policy = policy
        self.queue_size = queue_size
        super().__init__(f"Queue '{queue_name}' full ({queue_size} items, policy: {policy})")
```

**Complete Exception Hierarchy** (Phases 1a-1c):

```python

CyncProtocolError (Phase 1a - base)
├── PacketDecodeError (Phase 1a)
├── PacketFramingError (Phase 1a)
├── CyncConnectionError (Phase 1b)
├── HandshakeError (Phase 1b)
├── PacketReceiveError (Phase 1b)
├── DuplicatePacketError (Phase 1b)
├── ACKTimeoutError (Phase 1b)
└── QueueFullError (Phase 1c)

```

**Note**: This hierarchy is referenced from Phase 1a and 1b specs. Update this section if new exception types are added in future phases.

#### Exception Handling Pattern: Queue Backpressure

```python
try:
    result = await queue.put(item, timeout=10.0)
    if not result.success:
        logger.warning("Queue full: %s", result.reason)
except QueueFullError as e:
    # REJECT policy raises exception
    logger.error("Cannot enqueue: %s", e.queue_name)
    # Apply backpressure to caller
```

#### Quick Reference: Phase 1c Exception

| Exception        | When Raised              | Typical Action     |
| ---------------- | ------------------------ | ------------------ |
| `QueueFullError` | Queue cannot accept item | Apply backpressure |

**Import Pattern** (Phase 1c imports from Phase 1a):

```python
from protocol.exceptions import CyncProtocolError

class QueueFullError(CyncProtocolError):
    ...
```

---

### Queue Policy Selection Guide (Phase 1c)

This guide helps select the appropriate queue overflow policy based on traffic type.

#### Quick Decision Tree

**Control commands** (toggle, brightness, scene) → **BLOCK**
**Status updates** (device reports state) → **DROP_OLDEST**
**Both mixed in same queue** → **Separate queues** with different policies

#### The Three Queue Policies

#### BLOCK (Default - Recommended for Control Commands)

**Behavior**: Wait until queue has space
**Best for**: Control commands where order and completeness matter
**Trade-off**: May slow sender if consumer is slow

**When to use**:

- Toggle commands (on/off)
- Brightness adjustments
- Color changes
- Scene activations
- Any command where user expects all operations to complete

**Why**: User triggers these commands intentionally. Dropping them would cause:

- Missing state changes
- Inconsistent UI
- User confusion ("I pressed the button, why didn't it work?")

**Example**:

```python
## Control command queue
control_queue = BoundedQueue(
    maxsize=100,
    policy=QueuePolicy.BLOCK,
    name="control_commands"
)

## Application code
await control_queue.put(toggle_command, timeout=10.0)
## Will wait up to 10s for space (acceptable for user-triggered commands)
```

## DROP_OLDEST (Best for Status Updates)

**Behavior**: Drop oldest item when queue full, add new one
**Best for**: Status broadcasts where latest value is most important
**Trade-off**: May lose historical state changes

**When to use**:

- Device status broadcasts (device reports current state)
- Sensor readings (temperature, motion, etc.)
- Heartbeat messages
- Any update where only latest value matters

**Why**: Status updates are informational. If queue fills:

- Latest status is most relevant (shows current device state)
- Old status updates become stale/irrelevant
- Better to have current state than old history

**Example**:

```python
## Status update queue
status_queue = BoundedQueue(
    maxsize=50,
    policy=QueuePolicy.DROP_OLDEST,
    name="status_updates"
)

## Device sends status broadcast
await status_queue.put(status_update)
## If queue full, drops oldest status (no longer relevant)
```

## REJECT (Advanced - Use for Circuit Breakers)

**Behavior**: Return error immediately if queue full
**Best for**: Explicit backpressure signaling, rate limiting
**Trade-off**: Requires error handling at application layer

**When to use**:

- Circuit breaker patterns
- Rate limiting enforcement
- Explicit load shedding
- When caller needs immediate feedback about overload

**Why**: Enables application to detect overload and take action:

- Stop sending temporarily
- Switch to degraded mode
- Alert user about system issues

**Example**:

```python
## Rate-limited queue with circuit breaker
limited_queue = BoundedQueue(
    maxsize=20,
    policy=QueuePolicy.REJECT,
    name="rate_limited"
)

## Application code with error handling
result = await limited_queue.put(item)
if not result.success:
    logger.warning("Queue full - system overloaded")
    # Take action: pause, alert, switch mode
```

### Policy Comparison Table

| Policy          | Control Commands  | Status Updates    | Sensor Data       | Use Case             |
| --------------- | ----------------- | ----------------- | ----------------- | -------------------- |
| **BLOCK**       | ✅ Best           | ⚠️ May block      | ⚠️ May block      | Event-driven control |
| **DROP_OLDEST** | ❌ Loses commands | ✅ Best           | ✅ Best           | Latest value matters |
| **REJECT**      | ⚠️ Needs handling | ⚠️ Needs handling | ⚠️ Needs handling | Circuit breaker      |

#### Traffic Type Classification

**Control Commands (Use BLOCK)**:

- 0x73 data packets sent from controller to device
- Toggle, brightness, color, scene commands
- User-triggered actions
- Must not be dropped

**Status Updates (Use DROP_OLDEST)**:

- 0x83 status broadcasts from device to controller
- Device state changes (button pressed, state changed)
- Passive updates, not user-triggered
- Latest is most important

**Heartbeats (Use DROP_OLDEST)**:

- 0xD3/0xD8 heartbeat packets
- Only purpose is connection health check
- Latest heartbeat sufficient

#### Phase 1c Default Recommendation

**Recommended Starting Point**: Single BLOCK queue (simple, preserves order)

- Covers most smart home use cases
- No data loss
- Preserves event order
- Simplest implementation

**If Phase 1d Testing Shows Frequent Queue Fills**: Split into separate queues

- **Control commands** (user-triggered): BLOCK policy (must not lose)
  - Toggle, brightness, color, scene commands
  - Queue size: 100 messages
  - Example: `control_queue = BoundedQueue(100, QueuePolicy.BLOCK, "control")`
- **Status updates** (device-triggered): DROP_OLDEST policy (latest matters)
  - Device status broadcasts, sensor readings, heartbeats
  - Queue size: 50 messages
  - Example: `status_queue = BoundedQueue(50, QueuePolicy.DROP_OLDEST, "status")`

**Re-evaluate** during Phase 1d testing:

- If queue fills frequently → Split queues by traffic type
- If consumer is consistently slow → Investigate root cause
- If specific traffic type causes issues → Apply appropriate policy per type

**Decision Process (Technical Review Finding 3.3 - Clarified)**: Start simple (single BLOCK queue). Add complexity only if Phase 1d measurements show need.

**Explicit Re-evaluation Criteria**:

- **Monitor**: `tcp_comm_queue_full_total` metric during Phase 1d
- **Threshold**: If queue_full events > 5% of total messages → Requires action
- **Actions if threshold exceeded**:
  1. Increase queue size (if memory allows)
  2. Split queues by traffic type (control: BLOCK, status: DROP_OLDEST)
  3. Optimize consumer speed (if bottleneck identified)

- **Default validated**: If queue_full < 5% → BLOCK policy works as-is (no changes needed)

This resolves apparent contradiction: BLOCK is correct default AND we monitor for edge cases requiring optimization.

---

### QueuePolicy Enum

```python
class QueuePolicy(Enum):
    """Queue overflow handling policies."""
    BLOCK = "block"          # Block sender until space available
    DROP_OLDEST = "drop_oldest"  # Drop oldest item, add new one
    REJECT = "reject"        # Return error immediately
```

### BoundedQueue Class

```python
class BoundedQueue:
    """Async queue with configurable overflow policy."""

    def __init__(
        self,
        maxsize: int,
        policy: QueuePolicy = QueuePolicy.BLOCK,
        name: str = "queue",
    ):
        self.queue = asyncio.Queue(maxsize=maxsize)
        self.policy = policy
        self.name = name
        self.dropped_count = 0
        self.full_events = 0

    async def put(self, item: Any, timeout: Optional[float] = None) -> PutResult:
        """Add item with overflow handling."""
        if self.policy == QueuePolicy.BLOCK:
            # Block until space (with timeout)
            try:
                await asyncio.wait_for(self.queue.put(item), timeout=timeout)
                return PutResult(success=True, dropped=False)
            except asyncio.TimeoutError:
                self.full_events += 1
                return PutResult(success=False, dropped=False, reason="timeout")
            except asyncio.QueueFull:
                self.full_events += 1
                return PutResult(success=False, dropped=False, reason="queue_full")

        elif self.policy == QueuePolicy.DROP_OLDEST:
            # Try to add without blocking
            try:
                self.queue.put_nowait(item)
                return PutResult(success=True, dropped=False)
            except asyncio.QueueFull:
                # Queue is full, drop oldest and retry
                self.full_events += 1
                try:
                    self.queue.get_nowait()
                    self.dropped_count += 1
                except asyncio.QueueEmpty:
                    pass
                # Try again (should succeed now)
                try:
                    self.queue.put_nowait(item)
                    return PutResult(success=True, dropped=True)
                except asyncio.QueueFull:
                    # Extremely rare race condition - queue filled again
                    return PutResult(success=False, dropped=True, reason="queue_full_after_drop")

        elif self.policy == QueuePolicy.REJECT:
            # Try to add without blocking, reject if full
            try:
                self.queue.put_nowait(item)
                return PutResult(success=True, dropped=False)
            except asyncio.QueueFull:
                self.full_events += 1
                return PutResult(success=False, dropped=False, reason="queue_full")

    async def get(self, timeout: Optional[float] = None) -> Any:
        """Get item from queue.

        Args:
            timeout: Maximum time to wait for item (seconds).
                    None = block indefinitely until item available.
                    Use finite timeout for applications needing timeouts.

        Returns:
            Next item from queue

        Raises:
            asyncio.TimeoutError: If timeout expires before item available
        """
        return await asyncio.wait_for(self.queue.get(), timeout=timeout)

    def qsize(self) -> int:
        """Current queue size."""
        return self.queue.qsize()
```

### Integration with ReliableTransport

```python
class ReliableTransport:
    """Updated to use bounded recv queue (no send queue - see architecture notes)."""

    def __init__(
        self,
        connection: TCPConnection,
        protocol: CyncProtocol,
        dedup_cache_size: int = 1000,
        dedup_ttl_seconds: int = 300,
        recv_queue_size: int = 100,
        recv_queue_policy: QueuePolicy = QueuePolicy.BLOCK,  # Default: preserves event ordering
    ):
        # Initialize deduplication cache (from Phase 1b)
        self.dedup_cache = LRUCache(dedup_cache_size, dedup_ttl_seconds)

        # Initialize bounded recv queue only (Phase 1c)
        self.recv_queue = BoundedQueue(recv_queue_size, recv_queue_policy, "recv")

        # No send_queue - bulk operations use asyncio.gather() pattern
        # See "Send Queue Architecture Decision" below

        # ... rest of init from Phase 1b
```

### Send Queue Architecture Decision

**Status**: No send_queue in Phase 1c implementation

**Technical Review Finding 2.1 - Resolved**: Approved proceeding without send_queue, accepting potential Phase 2 refactoring if validation shows need.

### Rationale

- `send_reliable()` already provides retry logic and ACK waiting (Phase 1b)
- Bulk operations (group commands to multiple devices) use `asyncio.gather()` for parallelism
- Request-response pattern doesn't benefit from queuing layer
- Simplifies architecture - fewer moving parts
- **Risk accepted**: If Phase 1d finds p99 >= 2s, send_queue deferred to Phase 2 (not Phase 1 blocker)

### Bulk Operation Pattern

```python
## User turns on "Living Room" group (10 devices)
devices = get_devices_in_group("living_room")

## Send commands in parallel using asyncio.gather
tasks = [
    device.transport.send_reliable(encode_turn_on_command(device))
    for device in devices
]

results = await asyncio.gather(*tasks, return_exceptions=True)

## Check results
failures = [r for r in results if isinstance(r, Exception) or not r.success]
if failures:
    logger.warning("Group command had %d failures", len(failures))
```

### Performance Estimate

- 10 devices × (1ms state lock + 5ms encoding) = ~60ms (serial lock acquisition)
- ACK waits happen in parallel (with asyncio.gather) = ~100-200ms
- **Total: ~260-300ms for 10-device group** (optimistic, assuming perfect parallelism)
- **Worst case: ~1000-1500ms** (if state lock contention or network jitter)
- ✅ Acceptable for smart home UX (user expectation: commands complete within 1-2 seconds)

### ⚠️ RE-EVALUATION TRIGGER

**Phase 1d Group Validation** provides measurements for validation:

1. **Single device command latency** (p50, p95, p99)
2. **10-device parallel bulk operation timing** using asyncio.gather pattern
3. **State lock hold time** during send operations
4. **Device queue depth** (if devices have internal buffering)

See Phase 0.5 spec (Deliverable #11: Group Operation Performance Validation) for measurement methodology.

### Re-evaluation criteria for adding send_queue in future phase

- Measured p99 latency > **2 seconds** for group operations (updated from 1 second)
- **State lock contention** observed (>10% of time waiting for lock)
- Protocol limitations discovered that prevent parallel sends
- Need for "fire and forget" semantics (caller doesn't wait for ACK)
- Device-side rate limiting observed

**Decision Process**:

- Phase 1d provides authoritative group validation measurements
- If Phase 1d shows p99 < 2s: "No send_queue" decision validated
- If Phase 1d shows p99 > 2s: Document findings, proceed without send_queue (optimization deferred to Phase 2)

Until re-evaluation trigger, **send_queue remains out of scope**.

### recv_queue Policy Selection

**Default Policy** (Recommended):

```python
recv_queue_policy=QueuePolicy.BLOCK  # Default for event-driven systems
recv_queue_size=100  # Sufficient for typical smart home usage patterns
```

### Rationale for BLOCK as Default

1. **Event Ordering**: Smart home state synchronization requires ordered event processing
2. **Data Loss Prevention**: Status updates must not be silently dropped (causes UI inconsistency)
3. **Traffic Characteristics**: Low message rate (1-10 msgs/sec typical) makes blocking acceptable
4. **Failure Mode**: If queue fills, system waits rather than loses data (fail-safe behavior)

### When BLOCK is Appropriate

- Event-driven systems where order matters
- Low-frequency updates (< 100 msgs/sec)
- State synchronization requirements
- Acceptable for consumer to pause sender temporarily

**Alternative Policy: DROP_OLDEST** (use case: high-frequency sensors):

```python
recv_queue_policy=QueuePolicy.DROP_OLDEST  # Latest data prioritized
```

- Use when: Latest value more important than all values
- Example: Temperature sensor (only current reading matters)
- ⚠️ Warning: May lose critical state changes in smart home context

**Alternative Policy: REJECT** (use case: explicit error handling):

```python
recv_queue_policy=QueuePolicy.REJECT  # Fast failure with errors
```

- Use when: Need explicit backpressure signals
- Requires error handling at application layer
- Good for circuit breaker patterns

**Phase 0.5 Validation** (Optional Enhancement):

Phase 0.5 Deliverable #9 can optionally test device backpressure behavior:

- Test: Stop reading from TCP socket, observe device behavior
- Expected: Device may timeout/disconnect after 30-60s
- Impact: Confirms BLOCK policy acceptable for normal operation

### Policy Trade-offs

| Policy                  | Use Case                         | Pros                          | Cons                               |
| ----------------------- | -------------------------------- | ----------------------------- | ---------------------------------- |
| **BLOCK** (recommended) | Event-driven systems, state sync | No data loss, preserves order | May slow sender if consumer lags   |
| **DROP_OLDEST**         | High-frequency sensors, metrics  | Latest data prioritized       | ⚠️ May lose critical state changes |
| **REJECT**              | Rate limiting, circuit breaker   | Fast failure, explicit errors | Requires error handling logic      |

**Recommendation**: Use BLOCK for event-driven smart home control, contingent on Phase 0.5 validation.

---

## Implementation Plan

### Step 1: BoundedQueue Implementation

- Implement `BoundedQueue` class
- Three overflow policies
- Unit tests for each policy
- Metrics integration

### Step 2: Integration with ReliableTransport

- Add recv_queue to `ReliableTransport.__init__()`
- Update `recv_reliable()` to enqueue received messages to recv_queue
- Update application code to dequeue from recv_queue
- Metrics for recv_queue depth only (no send_queue - use asyncio.gather for bulk operations)

### Step 3: Performance Testing

- Load test with 1000+ messages/sec
- Verify BLOCK policy doesn't deadlock
- Verify DROP_OLDEST evicts correctly
- Verify REJECT returns errors promptly

### Step 4: Documentation & Validation

- Update API documentation
- Performance benchmarks
- Prepare for Phase 1d integration

---

## Acceptance Criteria

### Functional

- [ ] Bounded recv queue enforces max size
- [ ] BLOCK policy blocks until space available
- [ ] DROP_OLDEST policy evicts oldest item
- [ ] REJECT policy returns error immediately
- [ ] Queue depth tracked in real-time
- [ ] Overflow events counted
- [ ] No send_queue implemented (bulk operations use asyncio.gather pattern)

### Testing

- [ ] 10+ unit tests covering all policies
- [ ] Load test: 1000 msgs/sec for 60 seconds
- [ ] No deadlocks under BLOCK policy
- [ ] Correct eviction under DROP_OLDEST
- [ ] Fast rejection under REJECT policy
- [ ] 100% test pass rate
- [ ] 90% code coverage

### Performance

- [ ] `put()` completes in < 10ms (no overflow)
- [ ] `get()` completes in < 5ms (queue not empty)
- [ ] DROP_OLDEST eviction < 1ms
- [ ] Queue size check < 0.1ms

### Quality

- [ ] No ruff errors
- [ ] No mypy errors (strict mode)
- [ ] Full type annotations
- [ ] Logging for all overflow events

---

## Testing Strategy

### Unit Tests

```python

## test_bounded_queue.py

async def test_queue_block_policy():
"""BLOCK policy blocks when queue full."""
queue = BoundedQueue(maxsize=2, policy=QueuePolicy.BLOCK)
await queue.put("item1")
await queue.put("item2")

# Third put should timeout
result = await queue.put("item3", timeout=0.1)
assert result.success is False
assert result.reason == "timeout"

async def test_queue_drop_oldest_policy():
"""DROP_OLDEST evicts oldest item."""
queue = BoundedQueue(maxsize=2, policy=QueuePolicy.DROP_OLDEST)
await queue.put("item1")
await queue.put("item2")

result = await queue.put("item3")  # Should drop item1
assert result.success is True
assert result.dropped is True
assert queue.dropped_count == 1

# Queue should contain item2, item3
assert await queue.get() == "item2"
assert await queue.get() == "item3"

async def test_queue_reject_policy():
"""REJECT returns error when full."""
queue = BoundedQueue(maxsize=2, policy=QueuePolicy.REJECT)
await queue.put("item1")
await queue.put("item2")

result = await queue.put("item3")
assert result.success is False
assert result.reason == "queue_full"

```

### Load Tests

`````python

## test_queue_performance.py

async def test_high_load_block_policy():
"""Test BLOCK policy under high load."""
queue = BoundedQueue(maxsize=100, policy=QueuePolicy.BLOCK)

# Producer: 1000 msgs/sec
async def producer():
    for i in range(1000):
        await queue.put(f"msg{i}")
        await asyncio.sleep(0.001)

# Consumer: 900 msgs/sec (slower)
async def consumer():
    for _ in range(1000):
        await queue.get()
        await asyncio.sleep(0.0011)

await asyncio.gather(producer(), consumer())
assert queue.qsize() < 100  # Should never overflow

```sql

---

## Configuration Examples

**Note**: All examples use recv_queue only. Bulk operations (e.g., group commands) use `asyncio.gather()` instead of send_queue. See "Send Queue Architecture Decision" above for rationale.

### Conservative (Low Memory, Reject Overload)

```text

transport = ReliableTransport(
connection=conn,
protocol=protocol,
recv_queue_size=50,
recv_queue_policy=QueuePolicy.REJECT,
)

## Bulk operations: use asyncio.gather() for parallelism

tasks = [transport.send_reliable(cmd) for cmd in commands]
results = await asyncio.gather(\*tasks, return_exceptions=True)

```markdown
### Aggressive (High Throughput, Drop Old Data)
```

transport = ReliableTransport(
connection=conn,
protocol=protocol,
recv_queue_size=200,
recv_queue_policy=QueuePolicy.DROP_OLDEST,
)

## Bulk operations: asyncio.gather() with timeout

tasks = [transport.send_reliable(cmd, timeout=2.0) for cmd in commands]
results = await asyncio.wait_for(
asyncio.gather(\*tasks, return_exceptions=True),
timeout=10.0
)

```python

### Balanced (Default, Block on Overload)

```

transport = ReliableTransport(
connection=conn,
protocol=protocol,
recv_queue_size=100,
recv_queue_policy=QueuePolicy.BLOCK, # Default: preserve event ordering
)

## Bulk operations: asyncio.gather() for group commands

## Example: Turn on "Living Room" group (10 devices)

devices = get_devices_in_group("living_room")
tasks = [
device.transport.send_reliable(encode_turn_on_command(device))
for device in devices
]
results = await asyncio.gather(\*tasks, return_exceptions=True)

## Check for failures

failures = [r for r in results if isinstance(r, Exception) or not r.success]
if failures:
logger.warning("Group command had %d failures", len(failures))

```text

---

## BLOCK Policy Deadlock Prevention

**Risk**: BLOCK policy can cause deadlock if consumer crashes while queue full.

**Scenario**:

1. Consumer crashes or hangs
2. Producer continues sending → queue fills
3. All producers block indefinitely
4. System deadlock

**Mitigation Layers**:

**Layer 1: Timeout on put()** (Phase 1c implementation)

```

result = await queue.put(item, timeout=10.0)
if not result.success:
logger.error("Queue full timeout - consumer may be stuck")

```python

**Layer 2: Queue Full Alerts** (Phase 1c implementation)

```

## After 10 consecutive full events, escalate alert

if queue.full_events > 10:
logger.error("Queue persistently full - system degraded")
record_metric("tcp_comm_queue_degraded_total")

````python

**Layer 3: Automatic Policy Switch** (Phase 1c implementation - Technical Review Finding 5.1 - Resolved)

**Approved enhancement**: Add simplified automatic recovery to Phase 1c (not deferred to Phase 2):

```python

class BoundedQueue:
"""Async queue with automatic deadlock recovery."""

    def __init__(self, maxsize: int, policy: QueuePolicy = QueuePolicy.BLOCK, name: str = "queue"):
        self.queue = asyncio.Queue(maxsize=maxsize)
        self.policy = policy
        self.original_policy = policy  # Remember original for restoration
        self.name = name
        self.dropped_count = 0
        self.full_events = 0
        self.consecutive_timeouts = 0  # Track timeout streak
        self.policy_switched_at = None  # Track when policy switched

    async def put(self, item: Any, timeout: Optional[float] = None) -> PutResult:
        """Add item with automatic deadlock recovery."""

        # Check if policy should be restored (after temporary switch)
        if self.policy != self.original_policy and self._should_restore_policy():
            logger.info("Queue recovered - restoring %s policy", self.original_policy.value)
            self.policy = self.original_policy
            self.consecutive_timeouts = 0
            self.policy_switched_at = None

        # Standard BLOCK behavior
        if self.policy == QueuePolicy.BLOCK:
            try:
                await asyncio.wait_for(self.queue.put(item), timeout=timeout)
                self.consecutive_timeouts = 0  # Reset on success
                return PutResult(success=True, dropped=False)
            except asyncio.TimeoutError:
                self.full_events += 1
                self.consecutive_timeouts += 1

                # Automatic policy switch after 10 consecutive timeouts
                if self.consecutive_timeouts >= 10 and self.policy == self.original_policy:
                    logger.warning(
                        "Queue '%s' persistently full (%d consecutive timeouts) - "
                        "automatically switching to DROP_OLDEST to prevent deadlock",
                        self.name, self.consecutive_timeouts
                    )
                    self.policy = QueuePolicy.DROP_OLDEST
                    self.policy_switched_at = time.time()
                    record_metric("tcp_comm_queue_policy_switch_total", reason="deadlock_prevention")

                return PutResult(success=False, dropped=False, reason="timeout")

        # DROP_OLDEST and REJECT behaviors unchanged...
        elif self.policy == QueuePolicy.DROP_OLDEST:
            # ... existing implementation
            pass

    def _should_restore_policy(self) -> bool:
        """Check if policy should be restored to original.

        Restore conditions:
        - Policy was temporarily switched (not original)
        - At least 60s elapsed since switch
        - Queue below 50% capacity
        """
        if self.policy_switched_at is None:
            return False

        time_since_switch = time.time() - self.policy_switched_at
        if time_since_switch < 60:
            return False  # Wait at least 60s

        return self.qsize() < (self.queue.maxsize * 0.5)

```python

**Benefits of simplified Layer 3**:

- ✅ Automatic recovery from consumer crashes (no manual intervention)
- ✅ Simpler than full circuit breaker (no sliding window complexity)
- ✅ Preserves original policy preference (restores BLOCK after recovery)
- ✅ Safe gradual recovery (waits 60s + queue drains before restoring)

**Layer 3: Full Circuit Breaker Pattern** (Optional - Phase 2 enhancement if needed)

For production deployments, consider automatic policy switching:

```python

class AdaptiveQueue(BoundedQueue):
"""Queue with circuit breaker for deadlock prevention."""

    def __init__(self, maxsize: int, policy: QueuePolicy = QueuePolicy.BLOCK):
        super().__init__(maxsize, policy)
        self.original_policy = policy
        self.circuit_open_time = None
        self.full_rate_window = []  # Track full events over time

    async def put(self, item: Any, timeout: Optional[float] = None) -> PutResult:
        # Check circuit breaker status
        if self._should_open_circuit():
            # Temporarily switch to DROP_OLDEST to prevent deadlock
            logger.warning("Circuit breaker OPEN - switching to DROP_OLDEST temporarily")
            self.policy = QueuePolicy.DROP_OLDEST
            self.circuit_open_time = time.time()

        # Check if circuit can close
        if self._should_close_circuit():
            logger.info("Circuit breaker CLOSED - resuming BLOCK policy")
            self.policy = self.original_policy
            self.circuit_open_time = None

        return await super().put(item, timeout)

    def _should_open_circuit(self) -> bool:
        """Open circuit if queue full rate > 10% over 60s window."""
        now = time.time()
        # Track full events in sliding window
        self.full_rate_window = [t for t in self.full_rate_window if now - t < 60]

        if self.full_events > len(self.full_rate_window):
            self.full_rate_window.append(now)

        # Open if >10% of puts resulted in full event over 60s
        full_rate = len(self.full_rate_window) / max(1, self.full_events)
        return full_rate > 0.10 and self.circuit_open_time is None

    def _should_close_circuit(self) -> bool:
        """Close circuit if queue < 50% full for 60s."""
        if self.circuit_open_time is None:
            return False

        # Wait 60s after opening
        if time.time() - self.circuit_open_time < 60:
            return False

        # Check queue depth
        return self.qsize() < (self.queue.maxsize * 0.5)

```text

**Implementation Decision (Updated - Technical Review Finding 5.1)**:

- **Phase 1c**: Layers 1 + 2 + 3 (timeout + alerts + automatic policy switch)
- **Phase 2**: Add full circuit breaker (Layer 3 enhanced) if production metrics show need for sliding window logic

## Risks & Mitigation

| Risk                            | Impact | Mitigation                                                                                                                                             |
| ------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| BLOCK policy deadlock           | High   | Layer 1: Timeout (10s); Layer 2: Alerts after 10 full events; Layer 3: Automatic policy switch to DROP_OLDEST after 10 consecutive timeouts (Phase 1c) |
| DROP_OLDEST loses critical data | Medium | Use REJECT for critical paths; log drops                                                                                                               |
| Queue size tuning               | Low    | Make configurable; monitor metrics                                                                                                                     |
| Performance regression          | Low    | Benchmark before/after; target < 10ms overhead                                                                                                         |

---

## Dependencies

**Prerequisites**:

- Phase 1b complete (reliable transport working)

**External**:

- None (uses asyncio.Queue)

---

## Next Phase

**Phase 1d**: Device Simulator & Chaos Testing (1 week)

- Build realistic device simulator
- Chaos engineering tests
- Performance validation

---

## Related Documentation

- **Phase 1 Program**: `02-phase-1-spec.md` - Architecture
- **Phase 1b**: `02c-phase-1b-reliable-transport.md` - Prerequisite
- **Phase 1d**: `02e-phase-1d-simulator.md` - Next phase
`````
