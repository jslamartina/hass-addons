# Phase 1 Program: Reliable Transport Layer

**Status**: Split into Sub-Phases (0.5, 1a, 1b, 1c, 1d)
**Dependencies**: Phase 0 complete ✓
**Execution**: Sequential solo implementation

---

## Architecture Context

**CRITICAL**: This is a **from-scratch rebuild** of the Cync controller in `python-rebuild-tcp-comm/`.

- The existing `cync-controller/` codebase is used **only as protocol reference**
- This is **NOT an integration project** - we're building it right from the ground up
- Eventually this new system will **completely replace** the legacy codebase
- All work stays in `python-rebuild-tcp-comm/` - no integration with legacy code

---

## Technical Review History

**Last Review**: November 6, 2025
**Findings**: 24 total (3 critical, 5 architectural, 7 inconsistencies, 5 missing details, 4 risks)
**Resolution**: All approved and addressed with spec updates

**Key Decisions Documented**:

- Finding 1.1: Strengthened Phase 0.5 exit criteria (definitive ACK findings required)
- Finding 1.2: Added Phase 0.5 → 1b handoff with timeout recalibration
- Finding 1.3: Clarified endpoint byte boundaries (no overlap with msg_id)
- Finding 2.1: Approved no send_queue (Phase 2 optimization if needed)
- Finding 2.2: Approved DNS hard requirement with escalation paths
- Finding 5.1: Added automatic deadlock recovery to Phase 1c

**Future Technical Reviews**: All findings marked with "Technical Review Finding X.Y" tags throughout specs for traceability. Search specs for these tags to see resolutions.

---

## Guidance for Technical Reviewers

**CRITICAL PRINCIPLE**: Phase 1 implementation depends on empirical protocol validation (Phase 0.5). Some protocol details **cannot be known in advance** and will only be discovered through packet capture and analysis.

**Known Unknowns** (resolved during Phase 0.5):

1. **ACK packet msg_id positions** - Unknown until real ACK packets captured and analyzed
2. **Queue ID/Endpoint byte overlap** - Derivation pattern unknown until handshake sequences captured
3. **Actual ACK latency distribution** - Timeout tuning depends on measured p99 from Phase 0.5
4. **Checksum algorithm edge cases** - May discover firmware-specific variations

**What Technical Reviewers Should NOT Flag (These Are EXPECTED, Not Risks)**:

❌ **DNS Redirection Requirement**

- Phase 0.5 REQUIRES DNS redirection - this is the ONLY capture method
- If DNS fails prerequisite validation, Phase 0.5 stops - this is expected behavior, not a "risk"
- Do NOT ask for "fallback strategies" or "alternative capture methods"
- Do NOT create "contingency plans" for DNS failure scenarios
- ACCEPT: This is a hard prerequisite. If it fails, we stop and escalate. No alternatives documented.

❌ **Timeline/Schedule/Duration/Time Estimates**

- This is a one-person hobby project executed sequentially
- Do NOT track days, hours, weeks, time-boxes, or duration estimates
- Do NOT create "contingency buffers" or "+X days" risk scenarios
- Do NOT flag "prescriptive daily breakdowns" as issues needing "more flexibility"
- Do NOT estimate "3-5 days to complete" or similar time predictions
- ACCEPT: Work proceeds at natural pace without schedule tracking or time management

❌ **Protocol Unknowns Before Data Collection**

- ACK structure unknown until Phase 0.5 → Implementation decision deferred to Phase 1b start (Step 0)
- Queue ID derivation unknown until Phase 0.5 → Implementation uses validated pattern from captures
- Checksum algorithm unknown until Phase 0.5 → Validation first, copy validated algorithm second
- Do NOT demand "elaborate decision trees" for every possible ambiguous outcome before data exists
- Do NOT request "pre-commitment to implementation approaches" when dealing with genuine unknowns
- Do NOT create detailed contingency plans for scenarios that may never occur
- ACCEPT: Fallback strategies already documented where needed (e.g., FIFO if no msg_id in Phase 1b § Fallback Strategy)

**What You're Doing Wrong If You Flag These As Issues**:
If an AI review flags any of the above as "risks", "blockers", "needs contingency planning", or "requires decision":

1. The AI has NOT read this guidance section carefully enough
2. The AI is pattern-matching on keywords ("DNS", "unknown", "day") without understanding they are expected
3. The review is WASTING TIME on non-issues
4. The review should be REJECTED and AI redirected to read this section again

**What Technical Reviewers Should NOT Do**:

- ❌ Create elaborate decision trees for every possible ambiguous outcome before data exists
- ❌ Demand pre-commitment to implementation approaches when dealing with genuine unknowns
- ❌ Request detailed contingency plans for scenarios that may never occur
- ❌ Re-review architectural decisions already settled in prior planning discussions

**What Technical Reviewers SHOULD Flag (These Are Actual Problems)**:

- ✅ **Actual Bugs**: Logic errors, race conditions, incorrect algorithms, missing edge case handling in code examples
- ✅ **Missing Implementation Guidance**: Gaps that would block actual coding work (missing byte positions, undefined behavior)
- ✅ **Spec Inconsistencies**: Contradictions within same spec or between different specs
- ✅ **Test Coverage Gaps**: Missing tests for critical scenarios (state lock verification, reconnection races, etc.)
- ✅ Verify that unknowns are clearly documented with "TBD - Phase 0.5 will validate" markers
- ✅ Confirm implementation plans accommodate multiple possible outcomes without over-specifying
- ✅ Accept that some decisions must be deferred until empirical data is available
- ✅ Focus review on known aspects (architecture patterns, testing strategy, quality criteria)

**Proper Handling of Uncertainty**:

**Example 1 - Byte Overlap**:

- **Don't demand**: "Create decision tree with 4 options for byte overlap handling"
- **Instead accept**: "Byte overlap unknown. Implementation will handle discovered pattern (Options A-D possible). Decision deferred to Phase 1a."

**Example 2 - ACK Ambiguity**:

- **Don't demand**: "Define thresholds for what counts as 'ambiguous' (80%? 90%?) and escalation criteria"
- **Instead accept**: "ACK structure unknown. If findings are ambiguous, document objectively and make implementation decision in Phase 1b Step 0 (Prerequisites Check)."

**Why This Matters**: Attempting to pre-plan for every possible ambiguous outcome is **expensive** (reviewer time + spec update churn) and **wasteful** (elaborate plans get replaced by simple reality once data is collected). Better approach: accept uncertainty, document it clearly, make informed decisions when empirical data becomes available.

---

### Core Architecture Principles

#### Principle 1: No Legacy Imports

Legacy code must **NEVER be imported or used as a dependency** in production code. Copy and adapt algorithms from `cync-controller/` as needed, treating it strictly as reference documentation. This ensures:

- Complete independence from legacy codebase
- No dependency conflicts or version coupling
- Clean migration path for eventual legacy retirement
- Ability to refactor/optimize without legacy constraints

### Import Rules: Allowed vs Forbidden

**ALLOWED** (Phase 0.5 validation scripts ONLY):

- `mitm/validate-checksum-REFERENCE-ONLY.py`: Can import `cync_controller.packet_checksum`
- `mitm/parse-capture.py`: Can import packet type constants for reference
- Test fixture comparison: Can use legacy packet examples for validation

**NEVER ALLOWED** (All phases, all production code):

- `src/protocol/*.py`: NO imports from `cync_controller.*`
- `src/transport/*.py`: NO imports from `cync_controller.*`
- `tests/unit/*.py`: NO imports from `cync_controller.*` (use copied code)
- `tests/integration/*.py`: NO imports from `cync_controller.*`
- `harness/*.py`: NO imports from `cync_controller.*`

**Enforcement**:

```bash
## Pre-commit hook to reject legacy imports in production code
grep -r "from cync_controller" src/ harness/ tests/ && exit 1
```

**Exception Scope Summary**:

| Code Type                        | Legacy Imports    | Rationale                                      |
| -------------------------------- | ----------------- | ---------------------------------------------- |
| **Phase 0.5 validation scripts** | ✅ Allowed         | One-time validation of legacy algorithms       |
| **Phase 1a-1d production code**  | ❌ Forbidden       | Must be independent, copy algorithms instead   |
| **Phase 1a-1d tests**            | ❌ Forbidden       | Test against copied code, not legacy           |
| **Helper scripts**               | ⚠️ Reference only | Can read legacy for comparison, not dependency |

**Common Mistakes to Avoid**:

- ❌ "It's just for testing" - NO, copy the code
- ❌ "It's a constant, not a function" - NO, copy constants too
- ❌ "We'll remove it later" - NO, never add legacy imports
- ✅ "I'll copy the algorithm and adapt it" - YES, this is correct

### Principle 2: No Nullability

Methods must **NEVER return `None` or `Optional[T]`** to indicate errors or absence. Fields must **NEVER initialize as `None`**. Instead:

- **For errors**: Raise specific exceptions (e.g., `PacketDecodeError`, `ConnectionError`)
- **For fields**: Initialize with empty values of correct type (e.g., `bytes = b""`, `str = ""`, `list = []`)

This eliminates an entire class of null pointer bugs and forces explicit error handling.

### Example transformations

```python
## ❌ Before (with Optional)
def decode_packet(data: bytes) -> Optional[CyncPacket]:
    if len(data) < 5:
        return None  # Implicit error
    return packet

## ✅ After (with Exception)
def decode_packet(data: bytes) -> CyncPacket:
    if len(data) < 5:
        raise PacketDecodeError("too_short", data)  # Explicit error
    return packet

## ❌ Before (nullable field)
class ConnectionManager:
    def __init__(self):
        self.endpoint: Optional[bytes] = None  # Can be null

## ✅ After (non-nullable field)
class ConnectionManager:
    def __init__(self):
        self.endpoint: bytes = b""  # Never null, empty until set
```

### Exception Handling Patterns for Edge Cases

The "No Nullability" principle applies to ALL return values and fields, including edge cases that commonly use `None` in Python. Here are the correct patterns:

#### Pattern 1: Optional Configuration Parameters

Optional config parameters are **allowed** but must have non-None defaults:

```python
## ✅ CORRECT: Optional with non-None default
def __init__(self, timeout: Optional[float] = None):
    # Convert to non-nullable immediately
    self.timeout: float = timeout if timeout is not None else 5.0
    # After init, self.timeout is NEVER None

## ✅ ALTERNATIVE: Use Union with sentinel
def __init__(self, timeout: float = 5.0):
    self.timeout: float = timeout  # Always has value, default or provided

## ❌ WRONG: Optional field that stays None
def __init__(self, timeout: Optional[float] = None):
    self.timeout: Optional[float] = timeout  # BAD - can be None after init!
```

**Rule**: Constructor parameters MAY be `Optional[T]` for convenience, but instance fields MUST be non-nullable after `__init__` completes.

### Pattern 2: Cache/Dict Lookups

Cache and dictionary lookups must NOT return `None` - use defaults or raise exceptions:

```python
## ✅ CORRECT: Use .get() with non-None default
value: str = cache.get(key, "")  # Returns empty string if missing
value: int = cache.get(key, 0)   # Returns 0 if missing

## ✅ CORRECT: Raise specific exception if key must exist
if key not in cache:
    raise CacheKeyNotFoundError(key)
value: str = cache[key]  # Guaranteed to exist

## ✅ CORRECT: Check existence explicitly
if key in cache:
    value: str = cache[key]
    process(value)
else:
    # Handle missing key explicitly
    logger.warning("Cache miss for key: %s", key)
    value = compute_default()

## ❌ WRONG: Implicit None on missing key
value: Optional[str] = cache.get(key)  # Can be None
if value is not None:  # Forces null checks everywhere!
    process(value)
```

**Rule**: Dict/cache lookups MUST use `.get(key, default)` with non-None default OR raise exception if key must exist.

### Pattern 3: Empty Network Responses

Network responses must raise exceptions for empty/invalid data, never return `None`:

```python
## ✅ CORRECT: Raise exception for empty response
async def recv(self) -> bytes:
    data = await self.reader.read(4096)
    if not data:
        raise PacketReceiveError("connection_closed")
    return data  # Always returns bytes, never None

## ✅ CORRECT: Distinguish empty vs closed
async def recv(self) -> bytes:
    data = await self.reader.read(4096)
    if data == b"":  # Connection closed
        raise ConnectionClosedError()
    return data

## ❌ WRONG: Return None for empty
async def recv(self) -> Optional[bytes]:
    data = await self.reader.read(4096)
    if not data:
        return None  # Implicit error - forces None checks!
    return data
```

**Rule**: Network I/O MUST raise exceptions for errors/empty responses. Use specific exception types to distinguish conditions.

### Pattern 4: Search/Query Results

Search operations must return empty collections or raise exceptions, not `None`:

```python
## ✅ CORRECT: Return empty list for no results
def find_devices(self, filter: str) -> List[Device]:
    results = [d for d in self.devices if filter in d.name]
    return results  # Returns [] if no matches - not None

## ✅ CORRECT: Raise exception if result required
def find_device_by_id(self, device_id: int) -> Device:
    for device in self.devices:
        if device.id == device_id:
            return device
    raise DeviceNotFoundError(device_id)

## ❌ WRONG: Return None for no results
def find_device(self, device_id: int) -> Optional[Device]:
    for device in self.devices:
        if device.id == device_id:
            return device
    return None  # Forces None checks in all callers
```

**Rule**: Collections return empty (not `None`), single-item lookups raise exception if not found.

### Type Checker Configuration

To enforce "No Nullability", configure mypy strict mode:

```ini
## pyproject.toml or mypy.ini
[tool.mypy]
strict = true
disallow_untyped_defs = true
no_implicit_optional = true  # Crucial - prevents implicit Optional
warn_return_any = true
```

With `no_implicit_optional`, this code **fails type check**:

```python
## Type checker error: "Incompatible return value type (got None, expected str)"
def process(self, data: bytes) -> str:
    if len(data) < 5:
        return None  # ❌ Caught by type checker!
    return data.decode()
```

### Summary Table

| Scenario              | Anti-Pattern (None)       | Correct Pattern                            | Rationale                            |
| --------------------- | ------------------------- | ------------------------------------------ | ------------------------------------ |
| Optional config       | Field stays `Optional[T]` | Convert to `T` in `__init__`               | Fields never None after construction |
| Cache miss            | `.get(key)` returns None  | `.get(key, default)` with non-None default | Avoids None checks in caller         |
| Required lookup       | `.get(key)` returns None  | `if key not in cache: raise ...`           | Explicit error handling              |
| Empty network         | Return None on empty      | Raise `ConnectionClosedError()`            | Distinguishes error conditions       |
| Search no results     | Return None               | Return `[]` (empty list)                   | Collections never None               |
| Single item not found | Return None               | Raise `NotFoundError()`                    | Forces explicit error handling       |

---

## Executive Summary

Phase 1 adds reliability primitives (ACK/NACK, idempotency, backpressure) and implements the real Cync device protocol. This program is **split into 5 focused sub-phases** to manage complexity and enable incremental validation.

### Why Split into Sub-Phases?

- Phase 0 used custom test protocol (0xF00D magic bytes) - need real protocol validation first
- Original Phase 1 bundled 3-4 weeks of work - too broad for effective tracking
- Focused phases allow validation at each step
- Each sub-phase delivers testable, incremental value

---

## Protocol Terminology Glossary

To avoid confusion, this glossary defines key protocol terms:

- **Endpoint**: 5-byte identifier in packets (bytes[5:10]). Appears in 0x23 handshake packets and 0x73/0x83 data packets. Assigned by cloud during initial authentication. Represents the connection context for routing messages.

  **Byte Position** (✅ VALIDATED IN PHASE 0.5):
  - Position: bytes[5:10] (5 bytes total)
  - Same position in ALL packet types (handshake and data packets)
  - Example: `0x39 0x87 0xC8 0x57 0x00`

  **Byte Boundaries** (✅ VALIDATED - NO OVERLAP):
  - endpoint: bytes 5-9 (packet[5:10])
  - msg_id: bytes 10-11 (packet[10:12])
  - **Clean boundaries**: No byte overlap between endpoint and msg_id

  **Phase 0.5 Validation Results**:
  - ✅ Confirmed 5-byte endpoint at bytes[5:10] in 0x23 handshake packet
  - ✅ Confirmed 5-byte endpoint at bytes[5:10] in 0x73/0x83 data packets
  - ✅ Confirmed msg_id at bytes[10:12] in 0x73/0x83 data packets
  - ✅ Confirmed NO overlap between endpoint and msg_id

- **msg_id**: 2-byte message identifier in wire protocol (bytes[10:12] in data packets). Generated sequentially for ACK matching. Part of the composite dedup_key (along with packet_type, endpoint, and payload hash) but NOT sufficient alone for deduplication. The full fingerprint is required (see dedup_key in Phase 1b).
- **correlation_id**: UUID v7 for internal tracking and observability. Generated per-message for logs, metrics, and tracing. NOT sent over wire. NOT used for deduplication (see dedup_key in Phase 1b).
- **dedup_key**: Deterministic hash of packet content used for duplicate detection. Generated from packet_type + endpoint + msg_id + payload hash. Same logical packet always produces same dedup_key (unlike correlation_id which is unique per reception). Uses Full Fingerprint strategy for maximum robustness.
- **Packet Type**: First byte of every packet (0x23, 0x73, 0x83, etc.). Determines packet structure and handling.
- **0x7e Markers**: Frame delimiters in data payloads (not in all packet types). Checksum calculated between markers.

### Technical Acronyms

For clarity, key acronyms used throughout Phase 1 documentation:

- **ACK**: Acknowledgment packet (network protocol confirmation)
- **TTL**: Time To Live (cache/session expiration time)
- **LRU**: Least Recently Used (cache eviction policy)
- **FIFO**: First In First Out (queue/matching strategy)
- **p50/p95/p99**: Latency percentiles (median, 95th percentile, 99th percentile)
- **UUID v7**: Universally Unique Identifier version 7 (time-ordered, monotonic)
- **MITM**: Man In The Middle (packet capture proxy)
- **SSL/TLS**: Secure Sockets Layer / Transport Layer Security (encryption)

---

## Sub-Phase Breakdown

### Phase 0.5: Real Protocol Validation (NEW - PREREQUISITE)

**Status**: Planned | **Spec**: `02a-phase-0.5-protocol-validation.md`

**Goal**: Capture and validate real Cync device protocol behavior

**Key Deliverables**:

- MITM proxy tool (`mitm/mitm-proxy.py`) for packet capture
- Packet captures using MITM proxy and cloud relay infrastructure
- **Checksum validation script (`mitm/validate-checksum-REFERENCE-ONLY.py`)** - Required for Phase 1a
- Documented flows (handshake, toggle, status, heartbeat)
- Validated packet structure
- Test fixtures with real packet bytes
- Protocol validation report

**Why First?** Phase 0 used custom test protocol. Need real-world validation (especially checksum algorithm) before implementation.

---

### Phase 1a: Cync Protocol Codec

**Status**: Specified | **Spec**: `02b-phase-1a-protocol-codec.md`

**Goal**: Implement real Cync protocol encoder/decoder

**Key Deliverables**:

- `protocol/cync_protocol.py` - Encode/decode all packet types
- `protocol/packet_framer.py` - TCP stream framing and packet extraction
- Support: 0x23, 0x73, 0x83, 0xD3, 0x43, etc.
- Packet framing with 0x7e markers and checksum
- 15+ unit tests
- Update Phase 0 toggler to use real protocol

**Dependencies**: Phase 0.5 complete (protocol validated)

---

### Phase 1b: Reliable Transport Layer

**Status**: Specified | **Spec**: `02c-phase-1b-reliable-transport.md`

**Goal**: Implement native Cync protocol ACK/response handling with reliability primitives

**Key Deliverables**:

- `transport/reliable_layer.py` - Native Cync ACK/response handling (0x28, 0x7B, 0x88, 0xD8)
- `transport/connection_manager.py` - Connection state machine and reconnection logic
- `transport/deduplication.py` - LRU cache for idempotency
- Exponential backoff with jitter for retries and reconnection
- Pending message tracking with ACK matching
- 25+ unit tests
- Enhanced metrics (25+ new metrics)

**Dependencies**: Phase 1a complete (protocol codec working)

---

### Phase 1c: Backpressure & Queues

**Status**: Specified | **Spec**: `02d-phase-1c-backpressure.md`

**Goal**: Implement bounded queues and flow control

**Key Deliverables**:

- `transport/bounded_queue.py` - Configurable overflow policies with automatic deadlock recovery
- Queue metrics (depth, full events, drops, policy switches)
- Integration with reliable layer
- 10+ unit tests
- Performance tests under load
- **Note**: No send_queue (bulk operations use asyncio.gather pattern) - validated in Phase 1d

**Dependencies**: Phase 1b complete (reliable transport working)

---

### Phase 1d: Device Simulator & Chaos Testing

**Status**: Specified | **Spec**: `02e-phase-1d-simulator.md`

**Goal**: Build realistic device simulator for integration testing

**Key Deliverables**:

- `tests/simulator/cync_device_simulator.py` - Speaks real protocol
- Configurable chaos (latency, loss, reordering, duplicates)
- 10+ integration tests
- 5+ chaos tests
- Performance validation (p99 < 800ms)

**Dependencies**: Phases 1a-1c complete (full stack working)

---

## Combined Goals (Across All Sub-Phases)

1. **Protocol Integration**: Support real Cync packet format (0x23, 0x73, 0x83, 0x43, 0xD3, etc.)
2. **Reliability**: Implement native Cync ACK/response handling (0x28, 0x7B, 0x88, 0xD8) with retries and idempotency
3. **Connection Management**: Handle connection lifecycle, handshake, reconnection, and keepalive
4. **Backpressure**: Implement bounded queues and flow control
5. **Testing**: Device simulator for integration and chaos tests
6. **Observability**: Enhanced metrics and correlation IDs

---

## Detailed Architecture

For detailed class structures, code examples, and implementation patterns, see the individual sub-phase specifications:

- **Protocol Codec**: See `02b-phase-1a-protocol-codec.md` (Architecture section)
- **Reliable Transport**: See `02c-phase-1b-reliable-transport.md` (Architecture section)
- **Backpressure/Queues**: See `02d-phase-1c-backpressure.md` (Architecture section)
- **Device Simulator**: See `02e-phase-1d-simulator.md` (Architecture section)

The sections below provide high-level summaries for coordination purposes.

---

## Phase Dependency Flow

Sequential execution order for solo implementation:

| Phase                             | Prerequisites         | Key Deliverables Needed                                                                                                        |
| --------------------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **Phase 0.5**                     | Phase 0 complete ✓    | All Phase 0 tests passing                                                                                                      |
| **Phase 1a** (Protocol Codec)     | Phase 0.5 complete    | - Protocol Capture Document - Checksum validation complete - Updated protocol documentation - Deduplication field verification |
| **Phase 1b** (Reliable Transport) | Phase 1a complete     | - All codec tests passing - ACK packet structure validated - Full Fingerprint strategy confirmed                               |
| **Phase 1c** (Backpressure)       | Phase 1b complete     | - All transport tests passing - ReliableTransport working - Integration tests passing                                          |
| **Phase 1d** (Simulator)          | Phases 1a-1c complete | - Full protocol stack working - Integration tests passing                                                                      |

### Sequential Execution Notes

**Phase Order**:

1. Phase 0.5 validates protocol → Phase 1a implements codec
2. Phase 1a provides codec → Phase 1b adds reliability
3. Phase 1b provides transport → Phase 1c adds backpressure
4. Phases 1a-1c complete → Phase 1d validates with simulator

**Key Validation Points**:

- Phase 0.5 measures ACK latency, validates checksum, documents ACK structure
- Phase 1a uses validated protocol information
- Phase 1b uses measured timeouts and validated ACK structure
- Each phase completes before next begins

---

## Architecture Summary

### 1. Protocol Codec (Phase 1a)

Implements encoder/decoder for real Cync protocol with support for all major packet types (0x23, 0x28, 0x43, 0x48, 0x73, 0x7B, 0x83, 0x88, 0xD3, 0xD8). Includes TCP stream framing with `PacketFramer` for handling partial/multi-packet reads, 0x7e payload markers, and checksum validation.

**Key Components**: `CyncProtocol`, `PacketFramer`, `ParsedPacket`
**Details**: See `02b-phase-1a-protocol-codec.md`

### 2. Reliable Transport (Phase 1b)

Provides reliable message delivery using native Cync ACK/response patterns. Handles connection lifecycle with handshake (0x23 → 0x28), automatic reconnection, periodic heartbeats (0xD3 → 0xD8), and exponential backoff retries. Uses triple-identifier strategy: 2-byte msg_id for wire protocol ACK matching, deterministic dedup_key (Full Fingerprint) for collision-resistant duplicate detection, and UUID v7 correlation_id for observability.

**Key Components**: `ReliableTransport`, `ConnectionManager`, `LRUCache`, `RetryPolicy`
**Details**: See `02c-phase-1b-reliable-transport.md`

### 3. Backpressure & Queues (Phase 1c)

Implements bounded send/receive queues with configurable overflow policies (BLOCK, DROP_OLDEST, REJECT). Prevents memory exhaustion under high load while maintaining flow control.

**Key Components**: `BoundedQueue`, `QueuePolicy`
**Details**: See `02d-phase-1c-backpressure.md`

### 4. Device Simulator (Phase 1d)

Mock Cync device for integration and chaos testing. Speaks real protocol with configurable network chaos (latency, packet loss, reordering, duplicates, corruption). Enables comprehensive testing without physical devices.

**Key Components**: `CyncDeviceSimulator`, `ChaosConfig`
**Details**: See `02e-phase-1d-simulator.md`

---

## Phase 1 Architecture Diagram

The following diagram illustrates the complete Phase 1 end-state architecture showing all layers, components, and data flow paths:

**Note**: See [architecture.mermaid](living/architecture.mermaid) for the standalone diagram file. Requires Mermaid-compatible viewer (GitHub, VS Code with Mermaid extension, or online Mermaid Live Editor).

_Alt text: Phase 1 architecture diagram showing application layer, backpressure layer (BoundedQueue), reliable transport layer (ConnectionManager, ReliableTransport, LRUCache, RetryPolicy), protocol codec layer (Encoder, Decoder, Framer, Checksum), network layer (TCP Socket), and testing infrastructure (ChaosConfig, CyncDeviceSimulator, CodecValidatorPlugin)._

<!-- [MermaidChart: 8e7a2f78-9ec7-4400-b3dd-24ca4030593e] -->

```mermaid
---
project_id: 9a2485fd-95c8-4328-8c5b-9887221e1055
id: 8e7a2f78-9ec7-4400-b3dd-24ca4030593e
config:
    layout: elk
---
graph TD
    subgraph Application["Application Layer"]
        Client[Client Code]
    end

    subgraph Backpressure["Backpressure Layer (Phase 1c)"]
        RecvQueue[BoundedQueue - Receive<br/>Policy: BLOCK/DROP_OLDEST/REJECT<br/>Max: 100 messages]
        BulkSend[Bulk Send Operations<br/>Uses asyncio.gather\(\)<br/>No queue layer]:::conceptNode
    end

    subgraph ReliableLayer["Reliable Transport Layer (Phase 1b)"]
        ConnMgr[ConnectionManager<br/>- Handshake: 0x23 → 0x28<br/>- Heartbeat: 0xD3 → 0xD8<br/>- Reconnection with backoff<br/>- State machine]
        ReliableTransport[ReliableTransport<br/>- send_reliable with ACK wait<br/>- recv_reliable with auto-ACK<br/>- Pending message tracking<br/>- ACK matching by msg_id]
        LRUCache[LRUCache<br/>Deduplication<br/>1000 entries, 5min TTL<br/>Key: dedup_key (Full Fingerprint)]
        RetryPolicy[RetryPolicy<br/>Exponential backoff + jitter<br/>Max 3 retries]
    end

    subgraph ProtocolLayer["Protocol Codec Layer (Phase 1a)"]
        Encoder[CyncProtocol.encode<br/>0x23, 0x73, 0x83, 0xD3, etc.<br/>Checksum calculation]
        Decoder[CyncProtocol.decode<br/>Packet type parsing<br/>Checksum validation]
        Framer[PacketFramer<br/>TCP stream buffering<br/>Header-based extraction<br/>Multi-packet handling]
        Checksum[Checksum Algorithm<br/>Sum % 256 between 0x7e markers]
    end

    subgraph Network["Network Layer"]
        TCPSocket[TCP Socket<br/>asyncio streams]
    end

    subgraph Testing["Testing Infrastructure (Phase 1d)"]
        Chaos[ChaosConfig<br/>- Latency injection<br/>- Packet loss<br/>- Reordering<br/>- Duplicates<br/>- Corruption]:::wideNode
        Simulator[CyncDeviceSimulator<br/>Speaks real protocol<br/>ACK/response handling]:::wißde
    end

    %% Send Path
    Client -->|send_reliable\(\)| ReliableTransport
    Client -.->|bulk: asyncio.gather\(\)| BulkSend
    BulkSend -.->|parallel send_reliable\(\)| ReliableTransport
    ReliableTransport -->|encode packet| Encoder
    ReliableTransport -.->|track pending ACK<br/>msg_id + correlation_id| ReliableTransport
    ReliableTransport -.->|retry on timeout| RetryPolicy
    Encoder -->|generate bytes| Checksum
    Checksum -->|validated packet| TCPSocket
    ConnMgr -.->|manage connection| TCPSocket

    %% Receive Path
    TCPSocket -->|raw bytes| Framer
    Framer -->|complete packets| Decoder
    Decoder -->|validate checksum| Checksum
    Decoder -->|parsed packet| ReliableTransport
    ReliableTransport -->|check duplicate| LRUCache
    LRUCache -.->|cache hit: drop| ReliableTransport
    LRUCache -.->|cache miss: process| RecvQueue
    ReliableTransport -->|ACK packets<br/>0x28, 0x7B, 0x88, 0xD8| ReliableTransport
    ReliableTransport -.->|match ACK by msg_id| ReliableTransport
    RecvQueue -->|deliver| Client

    %% Connection Management
    ConnMgr -.->|handshake 0x23 → 0x28| ReliableTransport
    ConnMgr -.->|periodic heartbeat<br/>0xD3 → 0xD8| ReliableTransport
    ConnMgr -.->|reconnect on failure| RetryPolicy

    %% Testing Path
    Simulator -.->|simulated device| TCPSocket
    Chaos -.->|chaos injection| Simulator

    %% Styling
    classDef appLayer fill:#e1f5ff,stroke:#0288d1,stroke-width:2px,color:#000,text-align:left
    classDef queueLayer fill:#fff3e0,stroke:#f57c00,stroke-width:2px,color:#000,text-align:left
    classDef reliableLayer fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#000,text-align:left
    classDef protocolLayer fill:#e8f5e9,stroke:#388e3c,stroke-width:2px,color:#000,text-align:left
    classDef networkLayer fill:#fce4ec,stroke:#c2185b,stroke-width:2px,color:#000,text-align:left
    classDef testingLayer fill:#fff9c4,stroke:#f9a825,stroke-width:2px,color:#000,text-align:left
    classDef wideNode fill:#fff9c4,stroke:#f9a825,stroke-width:2px,color:#000,min-width:300px,text-align:left
    classDef conceptNode fill:#f5f5f5,stroke:#9e9e9e,stroke-width:2px,stroke-dasharray: 5 5,color:#000,text-align:left

    class Client appLayer
    class RecvQueue queueLayer
    class BulkSend conceptNode
    class ConnMgr,ReliableTransport,LRUCache,RetryPolicy reliableLayer
    class Encoder,Decoder,Framer,Checksum protocolLayer
    class TCPSocket networkLayer
    class Simulator,Chaos testingLayer
```

**Architecture Diagram Note**: Phase 1c implements **only RecvQueue** (shown as solid node in diagram). The "Bulk Send Operations" node (dashed) represents the architectural pattern for group commands using `asyncio.gather()` for parallel execution, not an actual queue implementation. Single device commands call `send_reliable()` directly; group commands use `asyncio.gather([send_reliable(...) for device in devices])` for parallelism without queueing overhead. See Phase 1c "Send Queue Architecture Decision" for rationale.

### Key Architecture Patterns

**Layered Design**: Each phase (1a-1d) corresponds to a distinct architectural layer with clear responsibilities and interfaces.

**Triple Identifier Strategy**:

- **msg_id** (2 bytes): Wire protocol identifier for ACK matching over the network
- **dedup_key** (Full Fingerprint): Deterministic hash for collision-resistant duplicate detection (packet_type + endpoint + msg_id + payload hash)
- **correlation_id** (UUID v7): Internal identifier for observability and event tracing (NOT used for deduplication)

**Send Path Flow**:

1. Client → Send Queue (backpressure)
2. ReliableTransport dequeues and encodes via CyncProtocol
3. Track pending ACK with msg_id → correlation_id mapping
4. Send over TCP socket
5. Wait for ACK (0x28, 0x7B, 0x88, 0xD8) with retry/backoff

**Receive Path Flow**:

1. TCP socket → PacketFramer buffers and extracts complete packets
2. CyncProtocol decodes and validates checksum
3. ReliableTransport checks LRUCache for duplicates (by dedup_key)
4. If ACK packet: match by msg_id, resolve pending message
5. If data packet: auto-ACK and enqueue to Recv Queue
6. Client dequeues from Recv Queue

**Connection Lifecycle**: ConnectionManager handles handshake (0x23 → 0x28), periodic heartbeat (0xD3 → 0xD8), connection state transitions, and automatic reconnection with exponential backoff.

**Testing Strategy**: CyncDeviceSimulator implements real protocol for integration tests, with ChaosConfig enabling deterministic and probabilistic chaos testing (latency, loss, reordering, duplicates, corruption).

---

## Enhanced Metrics

Phase 1 adds **25+ new metrics** across 5 categories:

1. **ACK/Response Metrics** - Track native Cync ACK patterns (0x28, 0x7B, 0x88, 0xD8)
2. **Connection Metrics** - Monitor handshake, reconnection, heartbeat health
3. **Retry Metrics** - Count retry attempts, timeouts, abandoned messages
4. **Queue Metrics** - Track queue depth, full events, drops by policy
5. **Deduplication Metrics** - Monitor cache size, hits, evictions

**Details**: See `02c-phase-1b-reliable-transport.md` (lines 52-96) for complete metric definitions and recording point table

---

## Legacy Code Reference (NOT Integration)

**IMPORTANT**: The existing `cync-controller/` codebase is used **only as protocol reference**, not for integration.

### Useful Reference Files

**Protocol Documentation**:

- `cync-controller/src/cync_controller/packet_parser.py` - Packet type definitions and parsing examples
- `cync-controller/src/cync_controller/structs.py` - Packet structure definitions (DeviceStructs)
- `docs/protocol/packet_structure.md` - Protocol documentation
- `docs/protocol/findings.md` - Protocol analysis notes

**Reference Implementations** (for understanding only):

- `cync-controller/src/cync_controller/devices/tcp_device.py` - Legacy TCP handling
- `cync-controller/src/cync_controller/devices/tcp_packet_handler.py` - Legacy packet parsing
- `cync-controller/packet_checksum.py` - Checksum algorithm reference

**What to Reference**:

- Packet format and structure
- Checksum calculation
- Protocol flow examples
- Device behavior patterns

**What NOT to Do**:

- Import legacy code
- Integrate with legacy system
- Wrap or extend legacy classes
- Depend on legacy implementation

---

## Testing Strategy

Phase 1 includes **60+ total tests** across three categories:

### Test Distribution by Phase

- **Phase 1a** (Protocol Codec): 15+ unit tests for encoding/decoding, framing, checksum
- **Phase 1b** (Reliable Transport): 25+ unit tests for ACK handling, retries, deduplication, connection management
- **Phase 1c** (Backpressure): 10+ unit tests for queue policies and overflow handling
- **Phase 1d** (Simulator & Chaos): 10+ integration tests + 5+ chaos tests

### Chaos Testing Approach

Chaos tests use two strategies to ensure reliability without flakiness:

1. **Deterministic Tests** - Drop specific packets (e.g., every 5th) for predictable behavior
2. **High-Volume Probabilistic Tests** - Large samples (1000+ messages) to reduce variance

**Details**: See individual sub-phase specs for detailed test examples and patterns

---

## Acceptance Criteria (Combined Across Sub-Phases)

**NOTE**: These criteria apply to the **complete Phase 1 program** (all sub-phases 0.5-1d). Individual sub-phase specs contain their own focused criteria.

### Functional

- [ ] Native Cync protocol ACK/response handling (0x28, 0x7B, 0x88, 0xD8)
- [ ] Connection management with handshake (0x23 → 0x28) and reconnection
- [ ] Keepalive/heartbeat support (0xD3 → 0xD8)
- [ ] Automatic retries with exponential backoff (max 3)
- [ ] Idempotency with LRU deduplication
- [ ] Bounded queues with configurable overflow policy
- [ ] Full Cync protocol support (0x23, 0x28, 0x43, 0x48, 0x73, 0x7B, 0x83, 0x88, 0xD3, 0xD8)
- [ ] Device simulator with chaos injection

### Performance

- [ ] p99 latency < 800ms (lab, no chaos)
- [ ] Retransmit rate < 0.5% (lab, no chaos)
- [ ] Zero duplicates processed (100% dedup)
- [ ] Queue full events < 1% under load

### Testing

- [ ] 50+ unit tests (15 codec + 25 transport + 10 queues)
- [ ] 10+ integration tests (simulator)
- [ ] 5+ chaos tests (deterministic + high-volume probabilistic)
- [ ] All tests pass with >90% coverage

### Quality

- [ ] No ruff errors
- [ ] No mypy errors (strict mode)
- [ ] Enhanced metrics exposed
- [ ] Documentation complete

---

## Risks & Mitigation

| Risk                                | Impact | Probability | Mitigation                                               | Status    |
| ----------------------------------- | ------ | ----------- | -------------------------------------------------------- | --------- |
| Cync protocol incompatibility       | High   | Medium      | Device simulator + real device testing                   | Active    |
| Performance regression              | Medium | Low         | Benchmarks + SLO monitoring                              | Active    |
| Duplicate detection false negatives | High   | Low         | Comprehensive dedup tests                                | Active    |
| Queue exhaustion / BLOCK deadlock   | Medium | Medium      | Backpressure policies + automatic recovery (Finding 5.1) | Mitigated |
| ACK timeout tuning                  | Medium | Medium      | Lab testing + Phase 0.5 → 1b handoff (Finding 1.2)       | Mitigated |
| DNS redirection blocked             | High   | Low         | Day -1 validation + troubleshooting guide (Finding 2.2)  | Mitigated |

---

## Implementation Order

**Sequential Execution**: Phases execute in order: 0.5 → 1a → 1b → 1c → 1d. Each phase completes before next begins.

**Phase Dependencies**:

- Phase 0.5: Protocol validation (prerequisite for all implementation phases)
- Phase 1a: Protocol codec (uses Phase 0.5 validated protocol)
- Phase 1b: Reliable transport (uses Phase 1a codec + Phase 0.5 ACK validation)
- Phase 1c: Backpressure (uses Phase 1b reliable transport)
- Phase 1d: Simulator & chaos testing (validates complete stack from 1a-1c)

**Completion Criteria**: Each phase has acceptance criteria that must pass before next phase starts.

---

## Dependencies

**Internal**:

- Phase 0 complete ✓
- Access to real Cync devices for testing

**External**:

- None

---

## Success Metrics

**Performance Targets** (Balanced hierarchy - Option C):

- p50 latency < 100ms (feels instant to users)
- p95 latency < 300ms (acceptable responsiveness)
- p99 latency < 800ms (rare slow commands tolerable)
- Success rate > 99.9% (baseline, no chaos)

**Performance Target Rationale** (Option C - Balanced Hierarchy):

These targets are based on smart home user experience research and human perception thresholds:

**p50 < 100ms** (Instant Perception):

- Research: Humans perceive <100ms as "instantaneous" with no perceived delay
- User expectation: Light switch feels like physical switch (immediate response)
- Covers: 50% of commands should feel instant
- Trade-off: Achievable with local network, challenges reliability margin

**p95 < 300ms** (Acceptable Responsiveness):

- Research: <300ms is perceived as "responsive" with minimal lag
- User expectation: Slight delay acceptable but not frustrating
- Covers: 95% of commands should feel responsive
- Trade-off: Balances user satisfaction with realistic network conditions

**p99 < 800ms** (Rare Slow Commands Tolerable):

- Research: <1s is boundary before users perceive "broken" or "laggy"
- User expectation: Occasional slow command acceptable (1 in 100)
- Covers: 99% of commands complete before user frustration
- Trade-off: 800ms provides margin below 1s threshold for reliability under network jitter

**Success Rate > 99.9%** (Baseline):

- Maximum 1 failure per 1000 commands under ideal conditions
- Establishes reliability baseline before chaos testing
- With retries: Should achieve >99% even with 20% packet loss

**Alternative Options Considered**:

- **Option A (Aggressive)**: p50 < 50ms, p95 < 150ms, p99 < 300ms - Unrealistic for network-based protocol
- **Option B (Conservative)**: p50 < 200ms, p95 < 500ms, p99 < 1000ms - Too slow, users perceive as laggy
- **Option C (Balanced)**: Selected - balances user experience with achievable targets

**Validation**: Phase 1d baseline tests will measure actual performance. If targets not met, adjust expectations or optimize implementation.

**Timeout Configuration** (derived from targets):

- ACK timeout: 2000ms (2.5× p99 target)
- Heartbeat timeout: 10s (max(3× ACK, 10s))
- Global cleanup: 30s (safety margin for stuck ACKs)

**Reliability**:

- Chaos suite passes (5/5 tests)
- Retransmit rate < 0.5%
- Zero duplicate processing
- Zero data corruption

**Note**: Timeouts validated by Phase 0.5 ACK latency measurements. Adjust if measured p99 differs significantly from 800ms target.

---

## Phase 1 Completion Gate

Before proceeding to Phase 2 (Canary Deployment), ALL criteria must be met:

### Must-Pass Criteria

- [ ] All 5 sub-phases (0.5, 1a, 1b, 1c, 1d) complete with acceptance criteria met
- [ ] Chaos suite passes (5/5 tests, deterministic + high-volume probabilistic)
- [ ] Performance targets met:
  - p99 < 800ms (baseline, no chaos)
  - p99 < 1500ms (with 10% chaos)
  - Success rate > 99.9% (no chaos)
  - Success rate > 99% (with chaos + retries)
- [ ] Zero critical bugs in issue tracker (see Bug Severity Classification below)
- [ ] Protocol validated against real devices (not just simulator)
- [ ] All unit tests pass (90%+ coverage)
- [ ] No memory leaks (run overnight test with monitoring)
- [ ] Metrics validated (all 25+ metrics reporting correctly)

### Bug Severity Classification

Bug classification for Phase 1 completion:

**CRITICAL** (Must fix before completion):

- Data loss or corruption (messages dropped silently, state incorrect)
- Connection failure rate > 1% under normal conditions
- Memory leak > 10% growth per hour
- Security vulnerability (authentication bypass, code injection, etc.)
- p99 latency > 2× target (> 1600ms baseline, > 3000ms with chaos)
- Crash or unrecoverable error requiring restart

**HIGH** (Document and monitor):

- Rare edge case failure < 0.1% rate (e.g., 1 failure per 1000 operations)
- Performance degradation: p99 latency between 1× and 2× target
- Intermittent connection issues (automatic recovery within 30s)
- Incorrect metrics reporting (non-critical metrics)
- Retry exhaustion on specific device firmware versions

**MEDIUM** (Document and defer to Phase 2):

- UI inconsistencies (cosmetic issues, no functional impact)
- Non-critical metrics missing or incomplete
- Performance inefficiency (not impacting SLOs)
- Edge cases with documented workarounds
- Enhancement requests

**LOW** (Track in backlog):

- Documentation gaps or typos
- Code style issues (already passing linters)
- Feature requests for future phases
- Minor logging improvements

**Handling Bugs**:

- CRITICAL: Fix before Phase 1 complete
- HIGH: Document mitigation, add monitoring
- MEDIUM/LOW: Track in backlog for later phases

---

## Next Phase

Phase 2: Canary deployment with SLO monitoring (see `03-phase-2-spec.md`)
