# Phase 1a → Phase 1b Handoff Document

**Handoff Date**: November 11, 2025
**Phase 1a Status**: Complete ✅ (All acceptance criteria met)
**Phase 1b Status**: Ready to begin

---

## Document Purpose

This handoff document consolidates validated protocol findings from Phase 1a and provides integration guidance for Phase 1b implementation. All information is based on validated implementation and real packet analysis, not assumptions.

---

## 1. Prerequisites Checklist

Before starting Phase 1b implementation, verify:

- [x] **Phase 1a Complete**: All acceptance criteria met
- [x] **Protocol Codec Working**: CyncProtocol + PacketFramer functional
- [x] **Tests Passing**: 18+ Phase 1a tests passing with >90% coverage
- [x] **Validation Report**: phase-1a-validation-report.md reviewed
- [x] **Living Docs Updated**: docs/living/ synchronized with Phase 1a findings
- [x] **No Legacy Imports**: `grep -r "from cync_controller" src/ tests/` returns zero matches
- [x] **Technical Review**: P0/P1 issues resolved (msg_id corrected to 2 bytes)

**Status**: ✅ All prerequisites met - Phase 1b ready to begin

---

## 2. Validated Protocol Findings (Authoritative)

These findings are **validated against real packets** and are **authoritative** for Phase 1b implementation.

### 2.1 Critical Protocol Fields

| Field       | Length      | Position         | Validation Source                                              |
| ----------- | ----------- | ---------------- | -------------------------------------------------------------- |
| **msg_id**  | **2 bytes** | **bytes[10:12]** | Phase 1a validation (corrected from initial 3-byte assumption) |
| endpoint    | 5 bytes     | bytes[5:10]      | Phase 0.5 + Phase 1a validation                                |
| packet_type | 1 byte      | byte[0]          | Phase 0.5 + Phase 1a validation                                |

**CRITICAL**: msg_id is **2 bytes at bytes[10:12]**, NOT 3 bytes. This was discovered during Phase 1a implementation (Step 6) and validated against real packet captures.

**Evidence**: `phase-1a-validation-report.md` line 105 states:

> "**Critical Fix**: Corrected msg_id from 3 bytes to 2 bytes based on packet analysis (Step 6 discovery)"

### 2.2 Supported Packet Types

**Fully Implemented** (encode + decode + tests):

| Type | Name             | Direction     | Framed | Purpose                    |
| ---- | ---------------- | ------------- | ------ | -------------------------- |
| 0x23 | HANDSHAKE        | DEV→CLOUD     | No     | Connection establishment   |
| 0x28 | HELLO_ACK        | CLOUD→DEV     | No     | Handshake acknowledgment   |
| 0x43 | DEVICE_INFO      | DEV→CLOUD     | No     | Device information request |
| 0x48 | INFO_ACK         | CLOUD→DEV     | No     | Device info acknowledgment |
| 0x73 | DATA_CHANNEL     | Bidirectional | Yes    | Data commands/responses    |
| 0x7B | DATA_ACK         | DEV→CLOUD     | No     | Data acknowledgment        |
| 0x83 | STATUS_BROADCAST | DEV→CLOUD     | Yes    | Device status updates      |
| 0x88 | STATUS_ACK       | CLOUD→DEV     | No     | Status acknowledgment      |
| 0xD3 | HEARTBEAT_DEV    | DEV→CLOUD     | No     | Device keepalive           |
| 0xD8 | HEARTBEAT_CLOUD  | CLOUD→DEV     | No     | Cloud keepalive response   |

**Framed packets** (0x73, 0x83): Have 0x7e markers and checksum validation

### 2.3 Checksum Algorithm

**Algorithm**: `sum(packet[start+6:end-1]) % 256` between 0x7e markers

**Validation**: 100% success rate on 24,960 real packets

**Implementation**: `src/protocol/checksum.py::calculate_checksum()`

**Usage**:

```python
from protocol.checksum import calculate_checksum

# For framed packets (0x73, 0x83)
checksum = calculate_checksum(packet_bytes)
```

### 2.4 PacketFramer Configuration

**MAX_PACKET_SIZE**: 4096 bytes (4KB)

**Validation**: Largest observed packet = 395 bytes (10× safety margin)

**Buffer Overflow Protection**: Implemented and tested (7 security tests passing)

**Implementation**: `src/protocol/packet_framer.py`

---

## 3. Phase 1a Deliverables Ready for Use

### 3.1 Core Protocol Components

**Location**: `src/protocol/`

#### CyncProtocol (`cync_protocol.py`)

**Encoder Methods**:

```python
@staticmethod
def encode_handshake(endpoint: bytes, auth_code: bytes) -> bytes:
    """Encode 0x23 handshake packet."""

@staticmethod
def encode_data_packet(endpoint: bytes, msg_id: bytes, payload: bytes) -> bytes:
    """Encode 0x73 data channel packet."""

@staticmethod
def encode_status_broadcast(endpoint: bytes, msg_id: bytes, payload: bytes) -> bytes:
    """Encode 0x83 status broadcast packet."""

@staticmethod
def encode_heartbeat() -> bytes:
    """Encode 0xD3 heartbeat packet."""
```

**Decoder Method**:

```python
@staticmethod
def decode_packet(data: bytes) -> CyncPacket:
    """Decode any Cync packet type.

    Returns:
        - CyncDataPacket for 0x73, 0x83 (with endpoint, msg_id, checksum validation)
        - CyncPacket for other types

    Raises:
        PacketDecodeError: Malformed packet, invalid checksum, unknown type
    """
```

**Utility Methods**:

```python
@staticmethod
def calculate_checksum(data: bytes) -> int:
    """Calculate checksum (sum % 256 between 0x7e markers)."""

@staticmethod
def extract_endpoint_and_msg_id(packet: CyncDataPacket) -> tuple[bytes, bytes]:
    """Extract endpoint (5 bytes) and msg_id (2 bytes) from data packet."""
```

#### PacketFramer (`packet_framer.py`)

**Usage**:

```python
framer = PacketFramer()

# Feed incoming TCP bytes
packets = framer.feed(tcp_data)  # Returns list of complete packets

# Handle partial packets automatically
first_read = framer.feed(b'\x23\x00\x00\x00\x1a')  # Partial packet
assert first_read == []  # Incomplete

second_read = framer.feed(b'\x39\x87\xc8...')  # Rest of packet
assert len(second_read) == 1  # Now complete
```

**Key Features**:

- Automatic TCP stream buffering
- Header-based length extraction
- Multi-packet handling (single read → multiple packets)
- Buffer overflow protection (MAX_PACKET_SIZE enforcement)

#### Exception Hierarchy (`exceptions.py`)

```python
CyncProtocolError  # Base exception
├── PacketDecodeError  # Malformed packets, invalid checksums
└── PacketFramingError  # Buffer overflow, oversized packets
```

**Usage Pattern**:

```python
try:
    packet = protocol.decode_packet(data)
except PacketDecodeError as e:
    logger.error("Decode failed: %s", e.reason)
    # e.reason: "too_short", "invalid_checksum", "unknown_type", etc.
except CyncProtocolError as e:
    logger.error("Protocol error: %s", e)
```

### 3.2 Test Fixtures

**Location**: `tests/fixtures/real_packets.py`

**Contents**: 13 validated real packet bytes from Phase 0.5 captures

**Usage**:

```python
from tests.fixtures.real_packets import (
    HANDSHAKE_0x23_DEV_TO_CLOUD,
    TOGGLE_ON_0x73_CLOUD_TO_DEV,
    DATA_ACK_0x7B_DEV_TO_CLOUD,
    HEARTBEAT_DEV_0xD3_DEV_TO_CLOUD,
    # ... and more
)

def test_decode_real_handshake():
    packet = protocol.decode_packet(HANDSHAKE_0x23_DEV_TO_CLOUD)
    assert packet.packet_type == 0x23
    assert packet.length == 26
```

### 3.3 MITM Codec Validation Plugin

**Location**: `mitm/validation/codec_validator.py`

**Status**: Implemented and tested against live traffic

**Usage**:

```bash
# Start MITM with codec validation
python mitm/mitm-proxy.py \
  --upstream-host homeassistant.local \
  --upstream-port 23779 \
  --enable-codec-validation
```

**Validation Results**: Successfully validated 100+ live packets from Home Assistant commands

---

## 4. Key Architectural Decisions from Phase 1a

### 4.1 No Nullability Principle

**Rule**: Methods MUST NOT return `None` or `Optional[T]` to indicate errors or absence.

**Instead**: Raise specific exceptions

**Examples**:

```python
# ✅ CORRECT - Exception-based error handling
def decode_packet(data: bytes) -> CyncPacket:
    if len(data) < 5:
        raise PacketDecodeError("too_short", data)
    return packet

# ❌ WRONG - None return for error
def decode_packet(data: bytes) -> Optional[CyncPacket]:
    if len(data) < 5:
        return None  # Implicit error
    return packet
```

**Enforcement**: Mypy strict mode with `no_implicit_optional = true`

### 4.2 No Legacy Imports

**Rule**: NEVER import from `cync_controller` package in production code.

**Rationale**: Complete independence from legacy codebase for clean migration path.

**Verification**:

```bash
grep -r "from cync_controller" src/ tests/
# Should return: (no matches)
```

**Status**: ✅ Phase 1a has zero legacy imports (validated)

### 4.3 Full Type Annotations

**Rule**: All functions MUST have complete type hints (mypy strict mode).

**Example**:

```python
async def send_reliable(
    self,
    payload: bytes,
    msg_id: bytes,  # 2 bytes
    timeout: float = 2.0,
) -> SendResult:
    ...
```

**Enforcement**: `poetry run mypy src tests` must pass with strict=true

### 4.4 Structured Logging

**Pattern**: JSON-structured logs with `extra` dict

**Example**:

```python
logger.info(
    "Packet decoded",
    extra={
        "packet_type": hex(packet.packet_type),
        "length": packet.length,
        "checksum_valid": packet.checksum_valid,
    }
)
```

---

## 5. Integration Points for Phase 1b

### 5.1 Using CyncProtocol in ReliableTransport

**Basic Usage**:

```python
from protocol.cync_protocol import CyncProtocol
from protocol.exceptions import PacketDecodeError

class ReliableTransport:
    def __init__(self, connection, protocol: CyncProtocol):
        self.protocol = protocol

    async def send_reliable(self, payload: bytes, msg_id: bytes) -> SendResult:
        # Encode packet
        packet = self.protocol.encode_data_packet(
            endpoint=self.endpoint,
            msg_id=msg_id,  # 2 bytes!
            payload=payload
        )

        # Send via TCP connection
        await self.conn.send(packet)

    async def recv_reliable(self) -> TrackedPacket:
        # Receive raw bytes
        raw_data = await self.conn.recv()

        # Decode using protocol
        try:
            packet = self.protocol.decode_packet(raw_data)
        except PacketDecodeError as e:
            logger.error("Decode failed: %s", e.reason)
            raise

        return TrackedPacket(packet=packet, ...)
```

### 5.2 Using PacketFramer for TCP Streams

**Connection-Specific Pattern**:

```python
from protocol.packet_framer import PacketFramer

class ReliableTransport:
    def __init__(self):
        self.framer = PacketFramer()  # One framer per connection

    async def _packet_router(self):
        """Background task routing incoming packets."""
        while True:
            # Read from TCP socket
            tcp_data = await self.conn.recv()

            # Feed to framer
            complete_packets = self.framer.feed(tcp_data)

            # Process each complete packet
            for packet_bytes in complete_packets:
                packet = self.protocol.decode_packet(packet_bytes)
                # Route to appropriate handler
                await self._handle_packet(packet)
```

**Critical**: One PacketFramer instance per TCP connection (maintains stream state)

### 5.3 msg_id Generation (2 bytes, Sequential)

**Implementation** (from Phase 1a Step 5.5):

```python
class ReliableTransport:
    def __init__(self):
        self._msg_id_counter: int = secrets.randbelow(0x10000)  # Random start (0-65535)

    def generate_msg_id(self) -> bytes:
        """Generate sequential 2-byte msg_id.

        Counter wraps at 65,536 (2^16) to cover full 2-byte range.
        Random offset on init handles reboot edge case.
        """
        msg_id = (self._msg_id_counter % 0x10000).to_bytes(2, 'big')  # 2^16 for 2 bytes
        self._msg_id_counter += 1
        return msg_id
```

**Key Points**:

- **Length**: 2 bytes (NOT 3)
- **Wrap value**: 0x10000 (65,536) NOT 0x1000000
- **Encoding**: Big-endian
- **Random start**: Prevents collision on device reboot

### 5.4 ACK msg_id Extraction (Hybrid Strategy)

**From Phase 0.5 Validation**:

| ACK Type           | msg_id Present? | Position     | Matching Strategy       |
| ------------------ | --------------- | ------------ | ----------------------- |
| 0x7B DATA_ACK      | ✅ YES           | bytes[10:12] | Parallel (msg_id match) |
| 0x28 HELLO_ACK     | ❌ NO            | N/A          | FIFO queue              |
| 0x88 STATUS_ACK    | ❌ NO            | N/A          | FIFO queue              |
| 0xD8 HEARTBEAT_ACK | ❌ NO            | N/A          | FIFO queue              |

**Implementation Guidance**:

```python
def extract_ack_msg_id(ack_packet: bytes) -> bytes | None:
    """Extract msg_id from ACK packet if present."""
    ack_type = ack_packet[0]

    if ack_type == 0x7B and len(ack_packet) >= 12:
        return ack_packet[10:12]  # 2 bytes
    else:
        return None  # Use FIFO queue for this ACK type
```

---

## 6. Known Issues and Limitations

### 6.1 No Known Functional Issues

Phase 1a has **zero known functional bugs** - all acceptance criteria met.

### 6.2 Performance Characteristics

**PacketFramer Performance**:

- Time Complexity: O(n) where n = buffer size
- Worst Case: O(n) even with corrupt packets (recovery limit prevents O(n²))
- Memory: O(1) additional (in-place buffer operations)
- Typical: Extracts 1-5 packets per call

**Decoder Performance**:

- Checksum calculation: O(n) where n = payload size
- Typical packet decode: <1ms

### 6.3 Limitations

**Not Implemented in Phase 1a** (deferred to Phase 1b+):

- ACK/response handling
- Retries and reliability primitives
- Connection state management
- Deduplication
- Metrics (basic structure only)

---

## 7. Timeout Recalibration (Phase 0.5 → Phase 1b)

### 7.1 Measured ACK Latencies (Phase 0.5)

| ACK Type           | p50    | p95     | p99      | Sample Size |
| ------------------ | ------ | ------- | -------- | ----------- |
| 0x28 HELLO_ACK     | 45.9ms | 129.4ms | -        | 25          |
| 0x7B DATA_ACK      | 21.4ms | 30.4ms  | **51ms** | 9           |
| 0x88 STATUS_ACK    | 41.7ms | 47.7ms  | -        | 97          |
| 0xD8 HEARTBEAT_ACK | 43.5ms | 50.9ms  | 84.1ms   | 21,441      |

**Note**: DATA_ACK sample size is small (9 pairs). Phase 1d should validate timeout assumptions under load.

### 7.2 Recommended Timeout Configuration

**Use TimeoutConfig class** (implements formulas):

```python
from transport.retry_policy import TimeoutConfig

# Default: Uses Phase 0.5 measured p99=51ms for DATA_ACK
timeouts = TimeoutConfig(measured_p99_ms=51.0)

# Automatically calculates:
# - ack_timeout_seconds = 0.128s (51ms × 2.5)
# - handshake_timeout_seconds = 0.32s (128ms × 2.5)
# - heartbeat_timeout_seconds = 10.0s (max(384ms, 10s))
# - cleanup_timeout_seconds = 1.92s (128ms × 15)
```

**Use in ReliableTransport**:

```python
timeouts = TimeoutConfig()  # Uses validated Phase 0.5 defaults

transport = ReliableTransport(
    connection=conn,
    protocol=protocol,
    ack_timeout=timeouts.ack_timeout_seconds,  # NOT hardcoded!
)

conn_mgr = ConnectionManager(
    connection=conn,
    protocol=protocol,
    handshake_timeout=timeouts.handshake_timeout_seconds,
    heartbeat_timeout=timeouts.heartbeat_timeout_seconds,
)
```

**Adjustment After Phase 1d Testing**:

If Phase 1d baseline tests reveal higher actual p99:

```python
# Example: Phase 1d measured p99=200ms (higher than Phase 0.5 small sample)
timeouts_adjusted = TimeoutConfig(measured_p99_ms=200.0)
# Automatically recalculates: ack=0.5s, handshake=1.25s, heartbeat=10.0s
```

### 7.3 Heartbeat Timeout Formula

**Formula**: `max(3 × ack_timeout, 10s)`

**Rationale**: 10s minimum threshold accounts for network jitter and device processing variance, even with low ACK timeouts.

**Example**:

- ACK timeout = 128ms (default) → Heartbeat = max(0.384s, 10s) = **10s**
- ACK timeout = 2s → Heartbeat = max(6s, 10s) = **10s**
- ACK timeout = 5s → Heartbeat = max(15s, 10s) = **15s**

---

## 8. Testing Strategy Continuity

### 8.1 Phase 1a Test Fixtures Available

**Real Packets**: 13 validated packets in `tests/fixtures/real_packets.py`

**Coverage**: Handshake, toggle, status, heartbeat, device info

**Usage in Phase 1b**: Use same fixtures for integration tests

### 8.2 Phase 1a Test Patterns

**Unit Test Structure**:

```python
@pytest.mark.unit
async def test_send_reliable_basic():
    """Test basic send with ACK."""
    mock_conn = AsyncMock()
    transport = ReliableTransport(mock_conn, protocol)

    result = await transport.send_reliable(b"test")

    assert result.success is True
    mock_conn.send.assert_called_once()
```

**Parameterized Tests**:

```python
@pytest.mark.parametrize("device_id,endpoint", [
    (123, bytes.fromhex("45 88 0f 3a 00")),
    (456, bytes.fromhex("32 5d 53 17 00")),
])
def test_with_multiple_devices(device_id, endpoint):
    # Test across different devices
    ...
```

### 8.3 MITM Validation Workflow

**Development Testing**:

```bash
# 1. Start MITM with validation
python mitm/mitm-proxy.py --enable-codec-validation

# 2. Issue commands from Home Assistant UI
# (triggers real packet flow through MITM)

# 3. Observe validation logs
grep "codec validated" mitm/captures/mitm_*.log
```

---

## 9. Next Steps for Phase 1b

### Step 0: Review Handoff and Prerequisites

- [x] Read this handoff document completely
- [ ] Review Phase 1b spec (`02c-phase-1b-reliable-transport.md`)
- [ ] Verify Phase 0.5 ACK validation results
- [ ] Confirm timeout configuration values
- [ ] Choose ACK matching implementation path (Hybrid recommended)

### Step 1: Connection Management

**Tasks**:

- Implement `ConnectionManager` with state machine
- Handshake flow (0x23 → 0x28) using Phase 1a codec
- State lock pattern for concurrency
- Unit tests for connection lifecycle

**Key Integration Point**: Use `CyncProtocol.encode_handshake()` and `decode_packet()` from Phase 1a

### Step 2: Core ReliableTransport

**Tasks**:

- Implement `send_reliable()` with 2-byte msg_id generation
- Implement `recv_reliable()` with auto-ACK
- ACK matching (hybrid strategy: msg_id for 0x7B, FIFO for others)
- Pending message tracking

**Key Integration Point**: Use `PacketFramer` for TCP stream handling

### Step 3: Retry Logic

**Tasks**:

- Implement retry loop with exponential backoff
- ACK timeout handling (use TimeoutConfig!)
- Pending ACK cleanup background task
- Metrics recording

### Step 4: Deduplication

**Tasks**:

- Implement LRU cache with Full Fingerprint strategy
- Integrate with `recv_reliable()`
- TTL-based expiry
- Unit tests for dedup effectiveness

### Step 5: Integration & Testing

**Tasks**:

- Create `harness/toggler_v2.py` using ReliableTransport
- End-to-end tests with all ACK types
- Connection/reconnection tests
- Metrics validation

---

## 10. Quick Reference

### File Locations

| Component      | File                                 | Status      |
| -------------- | ------------------------------------ | ----------- |
| Protocol Codec | `src/protocol/cync_protocol.py`      | ✅ Complete      |
| Packet Framer  | `src/protocol/packet_framer.py`      | ✅ Complete      |
| Exceptions     | `src/protocol/exceptions.py`         | ✅ Complete      |
| Checksum       | `src/protocol/checksum.py`           | ✅ Complete      |
| Test Fixtures  | `tests/fixtures/real_packets.py`     | ✅ Complete      |
| MITM Validator | `mitm/validation/codec_validator.py` | ✅ Complete      |

### Key Constants

```python
MAX_PACKET_SIZE = 4096  # PacketFramer buffer limit
MSG_ID_LENGTH = 2       # bytes (NOT 3!)
ENDPOINT_LENGTH = 5     # bytes
MSG_ID_WRAP = 0x10000   # 65,536 (2^16 for 2 bytes)
```

### Common Operations

**Encode data packet**:

```python
packet = protocol.encode_data_packet(endpoint, msg_id, payload)
```

**Decode any packet**:

```python
try:
    packet = protocol.decode_packet(raw_bytes)
except PacketDecodeError as e:
    logger.error("Decode failed: %s", e.reason)
```

**Generate msg_id**:

```python
msg_id = (counter % 0x10000).to_bytes(2, 'big')  # 2 bytes, big-endian
```

**Extract msg_id from data packet**:

```python
msg_id = packet_bytes[10:12]  # 2 bytes at bytes[10:12]
```

### Troubleshooting

**Issue**: "PacketDecodeError: too_short"

- **Cause**: Incomplete packet received
- **Solution**: Use PacketFramer to buffer TCP stream

**Issue**: "PacketDecodeError: invalid_checksum"

- **Cause**: Corrupted packet or wrong checksum algorithm
- **Solution**: Verify packet is framed (0x73, 0x83), not unframed packet type

**Issue**: "ImportError: cannot import from cync_controller"

- **Cause**: Accidentally importing from legacy package
- **Solution**: Remove import, copy implementation if needed

**Issue**: msg_id length mismatch

- **Cause**: Using 3 bytes instead of 2
- **Solution**: Update to 2 bytes at bytes[10:12], wrap at 0x10000

---

## Appendix: Phase 1a Validation Report Summary

**Source**: `phase-1a-validation-report.md`

**Key Achievements**:

- ✅ All 10 packet types encoded/decoded successfully
- ✅ 18 unit tests passing (100% pass rate)
- ✅ >90% code coverage achieved
- ✅ Zero ruff errors, zero mypy errors (strict mode)
- ✅ PacketFramer security tests passing (buffer overflow protection)
- ✅ MITM codec validation successful (100+ live packets)
- ✅ No legacy imports (package isolation verified)
- ✅ msg_id corrected from 3 bytes to 2 bytes (critical fix)

**Coverage Metrics**:

- `cync_protocol.py`: 98.18% (1 line uncovered)
- `packet_framer.py`: 91.67% (3 lines uncovered)
- `checksum.py`: 100.00%
- `exceptions.py`: 100.00%

**Critical Discoveries**:

1. msg_id is 2 bytes at bytes[10:12] (NOT 3 bytes as initially assumed)
2. Padding byte at position 12 in 0x73 packets (absent in 0x83)
3. PacketFramer requires recovery limit to prevent infinite loop on corrupt buffer

---

## Sign-Off

**Phase 1a Status**: ✅ **COMPLETE** - All deliverables met, ready for Phase 1b handoff

**Phase 1b Readiness**: ✅ **READY TO BEGIN** - All prerequisites satisfied

**Critical Reminder**: msg_id is **2 bytes at bytes[10:12]**. Verify all Phase 1b implementations use correct length.

**Handoff Approved**: November 11, 2025

---

**Next Action**: Begin Phase 1b Step 0 (Prerequisites Check & Timeout Recalibration)
