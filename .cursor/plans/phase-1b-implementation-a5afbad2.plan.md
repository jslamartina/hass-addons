<!-- a5afbad2-603f-4e25-949f-76685d43910a 84008f12-bf66-4ec1-96b0-8cd05c0214b6 -->

# Phase 1b: Reliable Transport Layer Implementation

## Prerequisites Status

- Phase 1a complete: Protocol codec (`src/protocol/cync_protocol.py`, `packet_framer.py`) validated
- Phase 0.5 complete: ACK validation confirms hybrid matching strategy (0x7B has msg_id, others use FIFO)
- Handoff document reviewed: `docs/phase-0.5/phase-1a-to-1b-handoff.md` provides integration guidance
- Timeout measurements: p99=51ms for DATA_ACK (default timeout=128ms = 51ms × 2.5)

## Architectural Decisions (Resolved)

### Packet Routing Architecture: Packet Router Only

**Decision**: `_packet_router()` is the **ONLY** reader from `conn.recv()`. This prevents race conditions and packet loss.

**Architecture**:

- `_packet_router()` reads from TCPConnection, feeds PacketFramer
- PacketFramer extracts complete packets from TCP stream
- Decode packets in `_packet_router()` (single decode point)
- Route ACKs (0x28, 0x7B, 0x88, 0xD8) to `ack_handler` callback
- Route data packets (0x73, 0x83) to simple `asyncio.Queue` (Phase 1b) - decoded `CyncPacket` objects
- `recv_reliable()` reads from queue, **NOT** from `conn.recv()` directly
- Phase 1c will replace simple queue with `BoundedQueue` (bounded, with policies)

**Rationale**: Single reader prevents race conditions. PacketFramer handles TCP stream fragmentation. Decode once, queue decoded objects for efficiency.

### ACK Routing: Callback Pattern

**Decision**: Use callback pattern to avoid circular dependency.

**Architecture**:

- ConnectionManager accepts optional `ack_handler: Optional[Callable[[CyncPacket], Awaitable[None]]]` in constructor
- `_packet_router()` calls `await ack_handler(ack_packet)` for ACK types when handler provided
- ReliableTransport registers `handle_ack` as callback during initialization
- Avoids circular dependency (ConnectionManager doesn't need ReliableTransport reference)

### Endpoint Initialization: Via connect() Method

**Decision**: Endpoint provided at connection time, not construction.

**Architecture**:

- `ReliableTransport.__init__()` accepts optional `endpoint: Optional[bytes]` parameter
- `ReliableTransport.connect(endpoint: bytes, auth_code: bytes)` sets `self.endpoint` and calls `conn_mgr.connect(endpoint, auth_code)`
- `send_reliable()` uses stored `self.endpoint` for encoding
- Endpoint not required until connection is established

## Implementation Steps

**CRITICAL CHECKPOINT PROCESS**: After each step, pause to:

1. Run linting: `npm run lint` (must pass)
2. Run formatting: `npm run format` (if needed)
3. Create/update unit tests for the step
4. Run unit tests: `pytest tests/unit/transport/` (must pass)
5. Verify code coverage for new code
6. Only proceed to next step after all checks pass

### Step 0: Prerequisites Review & Core Types (MANDATORY FIRST STEP)

**Files**:

- `src/transport/retry_policy.py` (new)
- `src/transport/exceptions.py` (new)
- `src/transport/types.py` (new)

**Tasks**:

#### Part A: TimeoutConfig and RetryPolicy

- Implement `TimeoutConfig` class with formula-based timeout calculation
- Default: `measured_p99_ms=51.0` (from Phase 0.5)
- Calculate: `ack_timeout = p99 × 2.5`, `handshake_timeout = ack × 2.5`, `heartbeat_timeout = max(ack × 3, 10s)`
- **Cleanup interval**: `max(10, min(60, ack_timeout / 3))` seconds (NOT 15× timeout - this is the interval, not timeout)
- Implement `RetryPolicy` class with exponential backoff + jitter

#### Part B: Exception Definitions

- Create `src/transport/exceptions.py` extending `CyncProtocolError`
- Define: `CyncConnectionError`, `HandshakeError`, `PacketReceiveError`, `DuplicatePacketError`, `ACKTimeoutError`
- All exceptions include reason codes and relevant metadata

#### Part C: Dataclass Definitions

- Create `src/transport/types.py` with core dataclasses
- Define `SendResult` (success, correlation_id, reason, retry_count)
- Define `TrackedPacket` (packet, correlation_id, recv_time, dedup_key)
- Define `PendingMessage` (msg_id, correlation_id, sent_at, ack_event, retry_count)

#### ⚠️ OPEN QUESTION 3: UUID v7 Dependency

**STOP HERE** and ask user:

**Question**: What should be the fallback strategy if `uuid_extensions` package is not available?

**Options**:

- **Option A**: Use `uuid.uuid4()` as fallback (acceptable for correlation_id, less time-ordered)
- **Option B**: Add `uuid_extensions` to dependencies (requires package installation)
- **Option C**: Use alternative UUID v7 implementation (if available)

**Current State**: `device_operations.py` line 23 uses `uuid_extensions` package. Need to verify if it's in `pyproject.toml` dependencies.

**Recommendation**: Option A (fallback to uuid4) - correlation_id doesn't require strict time ordering, uuid4 is sufficient for observability.

**Action**: **PAUSE** - Wait for user decision before proceeding.

**Critical**: All timeout values MUST use `TimeoutConfig` - no hardcoded values in constructors.

**After Step 0 - Checkpoint**:

- [ ] Run `npm run lint` (must pass)
- [ ] Run `npm run format` (if needed)
- [ ] Create `tests/unit/transport/test_retry_policy.py` with tests for TimeoutConfig and RetryPolicy
- [ ] Create `tests/unit/transport/test_exceptions.py` with tests for exception hierarchy
- [ ] Create `tests/unit/transport/test_types.py` with tests for dataclasses
- [ ] Run `pytest tests/unit/transport/ -v` (must pass)
- [ ] Verify code coverage for all new modules

**Reference**: `docs/02c-phase-1b-reliable-transport.md` lines 275-356, 520-593, 844-860

### Step 0.5: Metrics Registry Setup

**File**: `src/metrics/registry.py` (extend existing)

**Tasks**:

- Add all 25+ Phase 1b metrics to existing registry
- **ACK metrics**: `tcp_comm_ack_received_total`, `tcp_comm_ack_timeout_total`, `tcp_comm_idempotent_drop_total`, `tcp_comm_retry_attempts_total`, `tcp_comm_message_abandoned_total`
- **Connection metrics**: `tcp_comm_connection_state`, `tcp_comm_handshake_total`, `tcp_comm_reconnection_total`, `tcp_comm_heartbeat_total`
- **Dedup cache metrics**: `tcp_comm_dedup_cache_size`, `tcp_comm_dedup_cache_hits_total`, `tcp_comm_dedup_cache_evictions_total`
- **Performance metrics**: `tcp_comm_state_lock_hold_seconds`
- **Device operation metrics**: `tcp_comm_mesh_info_request_total`, `tcp_comm_device_info_request_total`, `tcp_comm_device_struct_parsed_total`, `tcp_comm_primary_device_violations_total`
- **Create helper functions** for recording each metric type:
- `record_ack_received(device_id: str, ack_type: str, outcome: str)`
- `record_ack_timeout(device_id: str)`
- `record_idempotent_drop(device_id: str)`
- `record_retry_attempt(device_id: str, attempt_number: int)`
- `record_message_abandoned(device_id: str, reason: str)`
- `record_connection_state(device_id: str, state: str)`
- `record_handshake(device_id: str, outcome: str)`
- `record_reconnection(device_id: str, reason: str)`
- `record_heartbeat(device_id: str, outcome: str)`
- `record_dedup_cache_size(size: int)`
- `record_dedup_cache_hit()`
- `record_dedup_cache_eviction()`
- `record_state_lock_hold(hold_seconds: float)`
- `record_mesh_info_request(device_id: str, outcome: str)`
- `record_device_info_request(device_id: str, outcome: str)`
- `record_device_struct_parsed(device_id: str)`
- `record_primary_device_violation()`

**After Step 0.5 - Checkpoint**:

- [ ] Run `npm run lint` (must pass)
- [ ] Run `npm run format` (if needed)
- [ ] Update `tests/unit/metrics/test_registry.py` with tests for new metrics
- [ ] Run `pytest tests/unit/metrics/ -v` (must pass)
- [ ] Verify all metrics have correct labels and types

**Reference**: `docs/02c-phase-1b-reliable-transport.md` lines 119-187

### Step 1: Connection Management

**File**: `src/transport/connection_manager.py` (new)

**Tasks**:

#### Part A: Core State Machine

- Implement `ConnectionState` enum (DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING)
- Implement `ConnectionManager` class with state machine
- Store `endpoint` (5 bytes) and `auth_code` for reconnection
- State lock pattern: `_state_lock = asyncio.Lock()`
- Lock hold time instrumentation (target <1ms, warn >10ms, critical >100ms)
- Track `_lock_hold_warnings` counter
- **Optional helper**: Implement `with_state_check(operation, action)` helper method that:
- Acquires lock, checks state, releases lock before executing action
- Monitors lock hold time, logs warnings if > 10ms
- Records `tcp_comm_state_lock_hold_seconds` metric
- Enforces correct lock pattern (lock released before network I/O)

#### Part B: Handshake Flow

- Handshake using raw TCPConnection: send 0x23 → wait for 0x28 ACK
- Use `CyncProtocol.encode_handshake(endpoint, auth_code)`
- Retry with exponential backoff (use `RetryPolicy`)
- Store credentials for reconnection

#### Part C: FIFO Queue for Non-msg_id ACKs

- Import `from collections import deque`
- Add `pending_requests: Deque[PendingMessage] = deque()` in ConnectionManager
- Used for: 0x28 (HELLO_ACK), 0x88 (STATUS_ACK), 0xD8 (HEARTBEAT_ACK)
- **FIFO matching pattern**:
- Handshake: append `PendingMessage` to deque before sending 0x23, pop from deque when 0x28 received
- Heartbeat: append before sending 0xD3, pop when 0xD8 received
- Status ACK: append before sending 0x83, pop when 0x88 received (if applicable)
- FIFO ensures ACKs match requests in order (no msg_id to match)

#### Part D: Packet Router & Heartbeat (CRITICAL ARCHITECTURE)

- Create `self.framer = PacketFramer()` in ConnectionManager `__init__()` (one per connection)
- Create simple `asyncio.Queue` for data packets: `self._data_packet_queue = asyncio.Queue()` (Phase 1b, unbounded)
- Accept optional `ack_handler: Optional[Callable[[CyncPacket], Awaitable[None]]]` in constructor
- Background `_packet_router()` task: routes packets + monitors heartbeat
- **PacketFramer integration**:
- Read raw bytes: `tcp_data = await conn.recv()` (ONLY reader from TCP)
- Feed to framer: `complete_packets = self.framer.feed(tcp_data)` (returns list of complete packets)
- Process each complete packet from return value
- Framer handles partial packets automatically (buffers internally)
- **Packet routing** (decode once, route by type):
- Decode packet: `packet = self.protocol.decode_packet(packet_bytes)` (single decode point)
- Route ACKs (0x28, 0x7B, 0x88, 0xD8):
- If `ack_handler` provided: call `await ack_handler(packet)` for all ACK types
- 0xD8 (heartbeat ACK): also handle directly for connection health monitoring
- Route data packets (0x73, 0x83): queue decoded `CyncPacket` objects to `_data_packet_queue`
- Unknown types: log and queue to `_data_packet_queue`
- **Heartbeat**:
- Send 0xD3 heartbeat every 60s
- Wait for 0xD8 with 10s timeout
- Handle heartbeat ACK timeout: trigger reconnection if 0xD8 not received within 10s

#### Part E: Reconnection & Task Cleanup

- Implement `reconnect()` with exponential backoff
- Use stored `endpoint` and `auth_code`
- Task cleanup in `disconnect()`: packet_router → reconnect → connection (order matters)
- Proper asyncio task cancellation
- Set `packet_router_task = None` after cleanup

**Lock Pattern Critical**:

- Lock acquired for state check + encoding only (<1ms)
- Lock released before `await conn.send()` and `await conn.recv()`
- Pattern: `async with lock: check + encode` → `release` → `await network_io()`

**After Step 1 - Checkpoint**:

- [ ] Run `npm run lint` (must pass)
- [ ] Run `npm run format` (if needed)
- [ ] Create `tests/unit/transport/test_connection_manager.py` with tests for:
- State machine transitions
- Handshake success/failure with FIFO queue
- Reconnection with backoff
- Heartbeat timeout
- PacketFramer integration (feed TCP bytes, get complete packets)
- Simple asyncio.Queue for data packets (Phase 1b, not BoundedQueue)
- ACK handler callback pattern
- Task cleanup
- Lock pattern (no deadlock, lock hold time < 10ms)
- FIFO queue matching (handshake, heartbeat)
- [ ] Run `pytest tests/unit/transport/test_connection_manager.py -v` (must pass)
- [ ] Verify code coverage for `connection_manager.py`
- [ ] Verify lock pattern tests pass

**Reference**: `docs/02c-phase-1b-reliable-transport.md` lines 1230-1548, 2031-2202

### Step 2: Core ReliableTransport

**File**: `src/transport/reliable_layer.py` (new)

**Tasks**:

#### Part A: Class Setup & Integration

- Implement `ReliableTransport` class
- **Endpoint initialization pattern**:
- `__init__()` accepts optional `endpoint: Optional[bytes]` parameter (5 bytes)
- `connect(endpoint: bytes, auth_code: bytes)` method sets `self.endpoint` and calls `conn_mgr.connect(endpoint, auth_code)`
- `send_reliable()` uses stored `self.endpoint` for encoding
- Create `ConnectionManager` instance: `self.conn_mgr = ConnectionManager(connection, protocol, ack_handler=self.handle_ack)`
- Register `handle_ack` as ACK handler callback to avoid circular dependency
- Access `conn_mgr._state_lock` for state checks
- **Data packet queue**: Read from `conn_mgr._data_packet_queue` in `recv_reliable()` (packets routed by `_packet_router()`)
- Background ACK cleanup task: `_cleanup_expired_acks()` with interval `max(10, min(60, ack_timeout / 3))` seconds
- Implement `async def stop()` method:
- Cancel ACK cleanup task (`_ack_cleanup_task`)
- Call `await conn_mgr.disconnect()` to cleanup connection manager tasks

#### Part B: send_reliable() Implementation

- Generate 2-byte msg_id (sequential counter, wrap at 0x10000, random start with `secrets.randbelow(0x10000)`)
- Generate correlation_id (UUID v7) for tracking
- **Lock pattern**: Acquire lock for state check + encoding, release before network I/O
- Encode packet: `self.protocol.encode_data_packet(endpoint, msg_id, payload)`
- Store in `pending_acks[correlation_id]` and `msg_id_to_correlation[msg_id.hex()]`
- Send via TCPConnection, wait for ACK with timeout
- Return `SendResult` dataclass

#### Part C: recv_reliable() Implementation

- **Packet source**: Read from `conn_mgr._data_packet_queue` (packets routed by `_packet_router()` from TCPConnection)
- NOT reading directly from `conn.recv()` to avoid race condition with `_packet_router()`
- `_packet_router()` feeds PacketFramer, routes data packets to queue as decoded `CyncPacket` objects
- Packet is already decoded (from `_packet_router()`), use directly
- Generate correlation_id (UUID v7) for reception
- Check dedup cache before processing
- Send appropriate ACK via `_send_ack()` helper
- Return `TrackedPacket` dataclass
- Raise `DuplicatePacketError` if cache hit

#### Part D: ACK Matching (Hybrid Strategy)

- msg_id matching for 0x7B DATA_ACK: extract msg_id from bytes[10:12], reverse lookup to correlation_id
- FIFO matching for others: 0x28, 0x88, 0xD8 use ConnectionManager's FIFO queue
- `handle_ack()` called by `_packet_router()` via callback pattern

#### Part E: Helper Methods

- `_send_ack(packet)`: Map packet type to ACK type (0x23→0x28, 0x73→0x7B, 0x83→0x88, 0xD3→0xD8)
- **ACK encoding**: Construct ACK packets manually or use protocol methods if available
- For 0x7B DATA_ACK: encode with msg_id from original packet
- For 0x28 HELLO_ACK: encode simple ACK packet
- For 0x88 STATUS_ACK: encode simple ACK packet
- For 0xD8 HEARTBEAT_ACK: encode simple ACK packet
- Send via TCPConnection
- `handle_ack(ack_packet)`: Match ACK to pending message, set event, cleanup
- Called by ConnectionManager's `_packet_router()` via callback pattern
- Extract msg_id from ACK packet (position varies by ACK type)
- For 0x7B: extract msg_id from bytes[10:12], reverse lookup correlation_id
- For 0x28/0x88/0xD8: use FIFO queue (pop from ConnectionManager's `pending_requests`)
- Set `ack_event` to unblock sender, record metrics, cleanup mappings
- `_cleanup_expired_acks()`: Background task removes expired entries
- **Cleanup interval**: `max(10, min(60, ack_timeout / 3))` seconds (runs 3× per timeout period, bounded 10-60s)
- Removes entries where `(now - sent_at) > ack_timeout`
- Safety net for stuck ACKs (primary timeout is `asyncio.wait_for()` in `send_reliable()`)

**After Step 2 - Checkpoint**:

- [ ] Run `npm run lint` (must pass)
- [ ] Run `npm run format` (if needed)
- [ ] Create `tests/unit/transport/test_reliable_layer.py` with tests for:
- send_reliable with ACK success
- recv_reliable reading from data packet queue (not direct TCP)
- ACK matching (hybrid: 0x7B parallel via msg_id, others FIFO via ConnectionManager)
- Endpoint initialization (via connect() method)
- \_send_ack() helper with ACK encoding
- handle_ack() callback from packet router
- Background cleanup task with correct interval formula
- stop() method for cleanup
- [ ] Run `pytest tests/unit/transport/test_reliable_layer.py -v` (must pass)
- [ ] Verify code coverage for `reliable_layer.py`
- [ ] Verify hybrid ACK matching tests pass

**Reference**: `docs/phase-0.5/phase-1a-to-1b-handoff.md` lines 387-436, `docs/02c-phase-1b-reliable-transport.md` lines 867-1105

### Step 3: Retry Logic

**File**: `src/transport/reliable_layer.py` (extend)

**Tasks**:

- Implement retry loop in `send_reliable()` with exponential backoff
- Use `RetryPolicy.get_delay(attempt)` for delay calculation (with jitter)
- Track retry attempts in `SendResult.retry_count`
- Handle ACK timeout: wait for ACK with `asyncio.wait_for()`, retry on timeout up to `max_retries`
- State lock pattern in retry loop: acquire lock for state check, release before network I/O
- Cleanup on timeout: remove from `pending_acks` and `msg_id_to_correlation` (with lock)
- Metrics: record `tcp_comm_retry_attempts_total`, `tcp_comm_ack_timeout_total`, `tcp_comm_message_abandoned_total`

**Lock Pattern Tests** (Critical):

- Test: Network hang doesn't deadlock (mock `conn.send()` to block, verify timeout fires)
- Test: Reconnect during `send_reliable()` detected (trigger reconnect mid-retry, verify state check fails gracefully)
- Test: Concurrent sends work (10 concurrent `send_reliable()` calls with `asyncio.gather()`)
- Test: Lock hold time < 10ms (instrument and measure)

**After Step 3 - Checkpoint**:

- [ ] Run `npm run lint` (must pass)
- [ ] Run `npm run format` (if needed)
- [ ] Add retry logic tests to `tests/unit/transport/test_reliable_layer.py`:
- Retry on timeout
- Max retries exceeded
- Lock correctness (no deadlock on network hang)
- Reconnect during send detected
- Concurrent sends (10 parallel)
- Lock hold time measurement
- [ ] Run `pytest tests/unit/transport/test_reliable_layer.py -v` (must pass)
- [ ] Verify all lock pattern tests pass
- [ ] Verify code coverage for retry logic

**Reference**: `docs/02c-phase-1b-reliable-transport.md` lines 913-975, 2211-2219, 2763-2780

### Step 4: Deduplication

**File**: `src/transport/deduplication.py` (new)

**Tasks**:

#### Part A: LRUCache Implementation

- Implement `LRUCache` class with `OrderedDict` (max_size=1000, ttl=300s)
- `add(key, value)`: Add entry, evict oldest if full
- `contains(key)`: Check if key exists (cache hit)
- `cleanup()`: Remove expired entries (TTL-based)
- Background cleanup task runs periodically
- Metrics: record size, hits, evictions

#### Part B: Full Fingerprint Strategy

- Implement `_make_dedup_key(packet)` with Full Fingerprint algorithm
- Extract: `packet_type`, `endpoint` (5 bytes), `msg_id` (2 bytes), `payload`
- Hash payload with SHA256, take first 16 hex chars
- Format: `"{packet_type:02x}:{endpoint.hex()}:{msg_id.hex()}:{payload_hash[:16]}"`
- Handle edge cases: missing endpoint (use 00000), missing msg_id (use 0000)

#### Part C: Integration with recv_reliable()

- Check cache before processing: `if await self.dedup_cache.contains(dedup_key):`
- Add to cache after validation: `await self.dedup_cache.add(dedup_key, {"correlation_id": correlation_id})`
- Send ACK even for duplicates (idempotent)
- Raise `DuplicatePacketError` on cache hit

**After Step 4 - Checkpoint**:

- [ ] Run `npm run lint` (must pass)
- [ ] Run `npm run format` (if needed)
- [ ] Create `tests/unit/transport/test_deduplication.py` with tests for:
- LRU cache add/contains/eviction
- TTL expiry
- Cache full scenario
- \_make_dedup_key() determinism (same packet → same key)
- \_make_dedup_key() uniqueness (different packets → different keys)
- Edge cases (missing endpoint, missing msg_id)
- [ ] Run `pytest tests/unit/transport/test_deduplication.py -v` (must pass)
- [ ] Verify code coverage for `deduplication.py`
- [ ] Verify Full Fingerprint strategy tests pass

**Reference**: `docs/02c-phase-1b-reliable-transport.md` lines 1736-1764, 2221-2250

### Step 5: DeviceOperations Integration

**File**: `src/transport/device_operations.py` (already exists, update to use ReliableTransport)

**Tasks**:

- Update `DeviceOperations.__init__()` to accept real `ReliableTransport` instance
- Replace Protocol stubs with actual ReliableTransport calls
- Complete `_build_device_info_request()` implementation (currently placeholder)
- Verify mesh info flow: send 0x73 → receive 0x7B ACK → collect 0x83 broadcasts (10s timeout)
- Verify device info flow: send 0x73 → receive 0x7B ACK → wait for 0x43 response (5s timeout)
- Complete 24-byte device struct parsing in `_parse_device_struct()` (currently simplified)
- Primary device enforcement: raise `MeshInfoRequestError` if not primary
- Replace `record_metric()` placeholder with actual metric calls
- Metrics: record all device operation metrics

**After Step 5 - Checkpoint**:

- [ ] Run `npm run lint` (must pass)
- [ ] Run `npm run format` (if needed)
- [ ] Update `tests/unit/transport/test_device_operations.py` with tests for:
- ReliableTransport integration
- Mesh info success with 0x83 parsing
- Device info success with 0x43 parsing
- Primary enforcement (non-primary raises error)
- Device struct parsing (24 bytes)
- Metric recording
- [ ] Run `pytest tests/unit/transport/test_device_operations.py -v` (must pass)
- [ ] Verify code coverage for updated `device_operations.py`
- [ ] Verify all device operation flows work

**Reference**: `docs/02c-phase-1b-reliable-transport.md` lines 2275-2712

### Step 6: Integration Testing & Metrics

**Files**: All test files (consolidate and extend)

**Tasks**:

- Create comprehensive unit test suite (30+ tests total across all modules)
- Test scenarios: connection lifecycle, handshake, heartbeat, send/recv, retries, duplicates, cache eviction
- Integration test: `test_reconnect_during_send_retry()` - reconnection interrupting retry loop
- Load test: `test_dedup_cache_load()` - 10,000 messages + 5% duplicates, verify <1ms p99 lookup
- Background task test: `test_ack_cleanup_task()` - verify expired ACKs cleaned up (add 10 expired, wait, verify cleanup)
- Verify all 25+ metrics recording correctly (use test fixtures from Phase 0.5)
- End-to-end test: full flow from connect → send → receive → ACK
- Verify packet router is single reader (no race conditions)
- Verify no flaky tests (run suite multiple times)

**After Step 6 - Final Checkpoint**:

- [ ] Run `npm run lint` (must pass with zero errors)
- [ ] Run `npm run format` (ensure all files formatted)
- [ ] Run full test suite: `pytest tests/unit/transport/ -v` (all tests must pass)
- [ ] Verify code coverage: `pytest --cov=src/transport tests/unit/transport/` (target >90%)
- [ ] Verify all 25+ metrics are recorded correctly
- [ ] Run mypy: `poetry run mypy src/transport` (strict mode, must pass)
- [ ] Verify no flaky tests (run test suite 3-5 times)
- [ ] Run integration scenarios (connect, send, receive, disconnect, reconnect)
- [ ] Verify packet router architecture (single reader, queue-based)
- [ ] Document any remaining TODOs or known limitations

**Reference**: `docs/02c-phase-1b-reliable-transport.md` lines 2803-2924, 2724-2800

## Key Files to Create/Modify

**New Files**:

- `src/transport/types.py` (~80 lines) - Dataclasses
- `src/transport/exceptions.py` (~120 lines) - Exception hierarchy
- `src/transport/retry_policy.py` (~80 lines) - TimeoutConfig and RetryPolicy
- `src/transport/connection_manager.py` (~350 lines) - Connection state machine with packet router
- `src/transport/reliable_layer.py` (~450 lines) - ReliableTransport with retries
- `src/transport/deduplication.py` (~120 lines) - LRU cache and Full Fingerprint
- `tests/unit/transport/test_types.py` (~100 lines)
- `tests/unit/transport/test_exceptions.py` (~80 lines)
- `tests/unit/transport/test_retry_policy.py` (~150 lines)
- `tests/unit/transport/test_connection_manager.py` (~350 lines)
- `tests/unit/transport/test_reliable_layer.py` (~550 lines)
- `tests/unit/transport/test_deduplication.py` (~150 lines)

**Existing Files to Update**:

- `src/metrics/registry.py` (add 25+ metrics)
- `src/transport/device_operations.py` (integrate with ReliableTransport)
- `tests/unit/metrics/test_registry.py` (add metric tests)
- `tests/unit/transport/test_device_operations.py` (update for ReliableTransport)

## Critical Implementation Requirements

1. **TimeoutConfig Mandatory**: All timeout values MUST use `TimeoutConfig` class - no hardcoded values
2. **msg_id is 2 bytes**: At bytes[10:12], wrap at 0x10000 (NOT 3 bytes)
3. **Hybrid ACK Matching**: msg_id for 0x7B (parallel), FIFO queue for 0x28/0x88/0xD8
4. **State Lock Pattern**: Lock for state check + encoding only, release before network I/O
5. **Full Fingerprint Dedup**: `packet_type:endpoint:msg_id:payload_hash` format
6. **Metrics Recording**: All 25+ metrics with proper labels and trigger events
7. **Endpoint Storage**: ReliableTransport stores endpoint via `connect()` method
8. **Packet Router Architecture**: `_packet_router()` is ONLY reader from TCPConnection
9. **PacketFramer Integration**: One PacketFramer per connection in `_packet_router()`
10. **Queue Architecture**: Phase 1b uses simple `asyncio.Queue`, Phase 1c upgrades to `BoundedQueue`
11. **ACK Routing**: Callback pattern (ack_handler) to avoid circular dependency
12. **Packet Decode**: Single decode point in `_packet_router()`, queue decoded `CyncPacket` objects
13. **Exception Hierarchy**: All exceptions extend `CyncProtocolError` with reason codes
14. **Dataclasses**: Use dataclasses for `SendResult`, `TrackedPacket`, `PendingMessage`
15. **Cleanup Interval**: `max(10, min(60, ack_timeout / 3))` seconds (NOT 15× timeout)

## Dependencies

- Phase 1a: `CyncProtocol`, `PacketFramer`, `CyncPacket` classes
- Phase 0.5: ACK validation findings, timeout measurements
- Existing: `TCPConnection` (`src/transport/socket_abstraction.py`), `DeviceInfo` (`src/transport/device_info.py`)
- External: `uuid_extensions` package (verify in dependencies, fallback to `uuid.uuid4()` if not available)

## Acceptance Criteria

- [ ] All 30+ unit tests passing
- [ ] No ruff/mypy errors (strict mode)
- [ ] All 25+ metrics recording correctly
- [ ] Lock pattern verified (no deadlocks, <10ms hold time)
- [ ] TimeoutConfig used everywhere (no hardcoded timeouts)
- [ ] Hybrid ACK matching working (0x7B parallel, others FIFO)
- [ ] Deduplication working (Full Fingerprint strategy)
- [ ] DeviceOperations integrated with ReliableTransport
- [ ] All dataclasses and exceptions defined
- [ ] Endpoint parameter handled correctly (via connect() method)
- [ ] PacketFramer integrated in \_packet_router() (single decode point)
- [ ] Packet router is single reader (no race conditions)
- [ ] Simple asyncio.Queue used (Phase 1b, not BoundedQueue)
- [ ] ACK handler callback pattern implemented (no circular dependency)
- [ ] Background tasks cleanup properly (stop() method, disconnect() cleanup order)
- [ ] Cleanup interval formula correct: `max(10, min(60, ack_timeout / 3))`
- [ ] FIFO queue implementation complete (deque import, append/pop pattern)
- [ ] All ACK types routed correctly (0x28, 0x7B, 0x88, 0xD8)

### To-dos

- [ ] Part A: Implement TimeoutConfig and RetryPolicy classes in src/transport/retry_policy.py with correct cleanup interval formula
- [ ] Part B: Create exception hierarchy in src/transport/exceptions.py extending CyncProtocolError
- [ ] Part C: Define SendResult, TrackedPacket, PendingMessage dataclasses in src/transport/types.py
- [ ] After Step 0: Run linting, formatting, create unit tests for retry_policy/exceptions/types, run tests, verify coverage
- [ ] Add all 25+ Phase 1b metrics to src/metrics/registry.py with all helper functions listed
- [ ] After Step 0.5: Run linting, formatting, update metric tests, verify all metrics defined
- [ ] Part A: Implement ConnectionState enum and ConnectionManager with state lock, instrumentation, and optional with_state_check helper
- [ ] Part B: Implement handshake flow (0x23→0x28) using raw TCPConnection with retry
- [ ] Part C: Add FIFO queue (pending_requests deque) for non-msg_id ACKs with append/pop pattern
- [ ] Part D: Implement \_packet_router() with PacketFramer (single TCP reader), decode once, route ACKs via callback, route data packets to simple asyncio.Queue
- [ ] Part E: Implement reconnect() and task cleanup in disconnect()
- [ ] After Step 1: Run linting, formatting, create comprehensive connection manager tests, verify packet router architecture, verify lock pattern
- [ ] Part A: Implement ReliableTransport class setup with ConnectionManager integration, endpoint via connect() method, and stop() method
- [ ] Part B: Implement send_reliable() with msg_id generation, lock pattern, and pending tracking
- [ ] Part C: Implement recv_reliable() reading from data packet queue (decoded CyncPacket objects), not direct TCP
- [ ] Part D: Implement hybrid ACK matching (msg_id for 0x7B, FIFO for others) via handle_ack() callback
- [ ] Part E: Implement \_send_ack() with ACK encoding, handle_ack() callback,\_cleanup_expired_acks() with correct interval formula
- [ ] After Step 2: Run linting, formatting, create ReliableTransport tests, verify packet router integration, verify hybrid ACK matching
- [ ] Add retry loop with exponential backoff to send_reliable() using RetryPolicy
- [ ] After Step 3: Run linting, formatting, add retry and lock pattern tests, verify no deadlocks
- [ ] Part A: Implement LRUCache with OrderedDict (max_size=1000, ttl=300s)
- [ ] Part B: Implement \_make_dedup_key() with Full Fingerprint strategy (packet_type:endpoint:msg_id:payload_hash)
- [ ] Part C: Integrate LRUCache with recv_reliable(), raise DuplicatePacketError on cache hit
- [ ] After Step 4: Run linting, formatting, create deduplication tests, verify Full Fingerprint determinism
- [ ] Update DeviceOperations to use ReliableTransport and complete device struct parsing
- [ ] After Step 5: Run linting, formatting, update device operation tests, verify integration
- [ ] Create comprehensive unit test suite (30+ tests) with integration, load, and background task tests, verify packet router architecture
- [ ] Final checkpoint: Run full linting, formatting, all tests, coverage, mypy, verify metrics, check for flaky tests, verify single reader architecture
