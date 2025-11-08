# Phase 1a: Cync Protocol Codec

**Status**: Planning
**Dependencies**: Phase 0.5 (protocol validation) complete
**Execution**: Sequential solo implementation

---

## Overview

Phase 1a implements the real Cync device protocol encoder/decoder based on validated packet captures from Phase 0.5. This replaces Phase 0's custom test protocol (0xF00D magic bytes) with the actual protocol that Cync devices speak.

**See Also**: `02-phase-1-spec.md` for complete Phase 1 program architecture and context.

---

## Phase 0.5 Prerequisites ✅ Complete

Phase 0.5 validation completed 2025-11-07 with all blocking requirements met:

**Checksum Algorithm** (✅ Validated):

- Algorithm: `sum(packet[start+6:end-1]) % 256` between 0x7e markers
- Validation: 100% match rate across 13 packets (2 legacy + 11 real)
- Reference: `docs/phase-0.5/validation-report.md`
- Status: Ready for Phase 1a implementation

**Byte Positions** (✅ Confirmed):

- endpoint: bytes[5:10] (5 bytes)
- msg_id: bytes[10:13] (3 bytes)
- No byte overlap confirmed
- Reference: `docs/phase-0.5/packet-structure-validated.md`

**Test Fixtures** (✅ Available):

- Location: `tests/fixtures/real_packets.py`
- Coverage: 13 validated packets from diverse device types
- Includes: Handshake, toggle, status, heartbeat packets
- Reference: Phase 0.5 Deliverable #3

---

## Goals

1. Implement encoder/decoder for all major Cync packet types
2. Support packet framing with 0x7e markers and checksum validation
3. Validate implementation against Phase 0.5 real packet captures
4. Update Phase 0 toggler to use real protocol
5. Create comprehensive unit tests for all codec operations

---

## Scope

**In Scope**:

- Packet encoding (Python → bytes)
- Packet decoding (bytes → Python dataclass)
- Packet types: 0x23, 0x28, 0x43, 0x48, 0x73, 0x7B, 0x83, 0x88, 0xD3, 0xD8
- Header parsing (type, length, multiplier)
- Endpoint/msg_id extraction
- 0x7e framing and checksum validation
- Unit tests (15+ tests)

**Out of Scope**:

- ACK/NACK handling (Phase 1b)
- Retries and reliability (Phase 1b)
- Queue management (Phase 1c)
- Device simulator (Phase 1d)
- TLS/encryption
- Cloud relay integration

---

## Architecture

### File Structure

```sql
src/protocol/
├── __init__.py
├── cync_protocol.py      # Main encoder/decoder
├── packet_types.py       # Packet type definitions
├── packet_framer.py      # TCP stream framing/buffering
└── checksum.py           # Checksum algorithm

tests/unit/protocol/
├── __init__.py
├── test_encoder.py       # Encoding tests
├── test_decoder.py       # Decoding tests
├── test_framer.py        # Framing tests
└── test_checksum.py      # Checksum tests

tests/fixtures/
└── real_packets.py       # From Phase 0.5 captures
```

### Custom Exceptions (Phase 1a)

Following the **No Nullability** principle, all error cases raise specific exceptions instead of returning `None`.

#### Base Exception

```python
class CyncProtocolError(Exception):
    """Base exception for all Cync protocol errors.

    All protocol-related exceptions inherit from this base class,
    enabling catch-all error handling when needed while maintaining
    specific exception types for detailed handling.
    """
    pass
```

**Usage**:

```python
try:
    packet = protocol.decode_packet(data)
except CyncProtocolError as e:
    # Catch any protocol-related error
    logger.error("Protocol error: %s", e)
```

#### PacketDecodeError

Raised when packet cannot be decoded (malformed, invalid checksum, unknown type, etc.)

```python
class PacketDecodeError(CyncProtocolError):
    """Packet cannot be decoded"""

    def __init__(self, reason: str, data: bytes):
        self.reason = reason
        self.data = data
        super().__init__(f"Packet decode failed: {reason}")
```

**Reasons**: `"too_short"`, `"invalid_checksum"`, `"unknown_type"`, `"invalid_length"`, `"missing_0x7e_markers"`

**Usage**:

```python
def decode_packet(data: bytes) -> CyncPacket:
    if len(data) < 5:
        raise PacketDecodeError("too_short", data)
    # ... decode logic
```

#### PacketFramingError

Raised by PacketFramer for TCP stream framing errors (invalid length, buffer overflow, etc.)

```python
class PacketFramingError(CyncProtocolError):
    """TCP stream framing error"""

    def __init__(self, reason: str, buffer_size: int = 0):
        self.reason = reason
        self.buffer_size = buffer_size
        super().__init__(f"Packet framing failed: {reason}")
```

**Reasons**: `"packet_too_large"`, `"invalid_length"`, `"buffer_overflow"`

**Usage**:

```python
def _extract_packets(self) -> List[bytes]:
    if packet_length > self.MAX_PACKET_SIZE:
        raise PacketFramingError("packet_too_large", len(self.buffer))
```

#### Exception Hierarchy

**Phase 1a Exceptions** (defined in this phase):

```text
CyncProtocolError (base)
├── PacketDecodeError
└── PacketFramingError
```

**Complete Phase 1 Hierarchy** (includes Phase 1b and 1c):

```text
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

**File Locations**:

- Base exception: `src/protocol/exceptions.py` (this phase)
- Phase 1a exceptions: `src/protocol/exceptions.py` (this phase)
- Phase 1b exceptions: `src/transport/exceptions.py` (Phase 1b)
- Phase 1c exceptions: `src/transport/exceptions.py` (Phase 1c)

**Testing Pattern**:

```python
import pytest

def test_packet_decode_error():
    """Test decode error raised for invalid packet."""
    with pytest.raises(PacketDecodeError, match="too_short"):
        protocol.decode_packet(b'\x23\x00')  # Too short
```

### Key Classes

```python
@dataclass
class CyncPacket:
    """Base packet structure."""
    packet_type: int
    length: int
    payload: bytes
    raw: bytes  # Full packet bytes

@dataclass
class CyncDataPacket(CyncPacket):
    """0x73 data channel packet."""
    endpoint: bytes  # 5 bytes (bytes[5:10])
    msg_id: bytes    # 3 bytes - wire protocol message ID
    data: bytes      # Inner payload (between 0x7e markers)
    checksum: int
    checksum_valid: bool
    # Note: correlation_id is added in Phase 1b for tracking/observability

class CyncProtocol:
    """Cync protocol encoder/decoder."""

    @staticmethod
    def encode_handshake(endpoint: bytes, auth_code: bytes) -> bytes:
        """Encode 0x23 handshake packet."""

    @staticmethod
    def encode_data_packet(endpoint: bytes, msg_id: bytes, payload: bytes) -> bytes:
        """Encode 0x73 data channel packet."""

    @staticmethod
    def decode_packet(data: bytes) -> CyncPacket:
        """
        Decode any Cync packet type.

        Raises:
            PacketDecodeError: If packet is malformed (invalid checksum, too short,
                             unknown type, etc.)
        """

    @staticmethod
    def calculate_checksum(data: bytes) -> int:
        """Calculate checksum (sum % 256 between 0x7e markers)."""

class PacketFramer:
    """
    Extract complete packets from TCP byte stream.

    TCP reads may return partial packets, multiple packets, or exact boundaries.
    PacketFramer buffers incoming bytes and extracts complete packets based on
    the header length field.

    Security: Validates packet length against MAX_PACKET_SIZE to prevent
    buffer exhaustion from malicious/corrupted packets.

    Algorithm:

    1. Buffer all incoming bytes
    2. Check if buffer has at least 5 bytes (header)
    3. Parse header to get packet length (byte[3]*256 + byte[4])
    4. Validate length <= MAX_PACKET_SIZE (4096 bytes)
    5. If buffer has full packet (5 + length), extract it
    6. Repeat until buffer exhausted

    Handles:
    - Buffering incomplete packets across multiple reads
    - Header-based length calculation
    - Multi-packet extraction from single read
    - Partial packet handling
    - Length overflow protection (discards buffer on invalid length)

    **Recovery Loop Protection (Technical Review Finding 3.6 - Clarified)**:
    - Recovery limit (100 attempts) prevents infinite loop on corrupt buffer
    - Without limit: 10KB corrupt stream would scan all bytes (O(n²) worst case)
    - With limit: Scans first 500 bytes (100 × 5-byte jumps), then clears buffer
    - Bounded behavior protects against malicious/corrupted input

    Example:
        framer = PacketFramer()
        # First read: partial packet (header only)
        packets = framer.feed(b'\\x23\\x00\\x00\\x00\\x1a')
        assert packets == []  # Incomplete

        # Second read: remaining bytes
        packets = framer.feed(b'\\x39\\x87\\xc8\\x57...')
        assert len(packets) == 1  # Now complete
    """
    MAX_PACKET_SIZE = 4096  # 4KB max data length (generous for protocol)

    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data: bytes) -> List[bytes]:
        """
        Add data to buffer and return list of complete packets.

        Args:
            data: Incoming bytes from TCP read

        Returns:
            List of complete packet bytes (may be empty if no complete packets)
        """
        self.buffer.extend(data)
        return self._extract_packets()

    def _extract_packets(self) -> List[bytes]:
        """
        Extract all complete packets from buffer.

        Validates packet length against MAX_PACKET_SIZE to prevent buffer
        exhaustion from malicious/corrupted packets.

        Implements recovery limit to prevent infinite loop on corrupt buffer.

        Returns:
            List of complete packets; buffer retains incomplete data
        """
        packets = []
        recovery_attempts = 0
        MAX_RECOVERY_ATTEMPTS = 100  # With 5-byte jumps, 100 attempts = 500 bytes scanned

        while len(self.buffer) >= 5:
            # Check recovery limit
            if recovery_attempts > MAX_RECOVERY_ATTEMPTS:
                logger.error(
                    "Max recovery attempts exceeded (%d), clearing buffer - potentially corrupt stream (Technical Review Finding 3.6)",
                    MAX_RECOVERY_ATTEMPTS,
                    extra={"buffer_size": len(self.buffer), "scanned_bytes": recovery_attempts * 5}
                )
                self.buffer = bytearray()  # Clear corrupted buffer
                break

            # Parse header to get packet length
            multiplier = self.buffer[3]
            base_len = self.buffer[4]
            packet_length = (multiplier * 256) + base_len

            # Validate length before proceeding
            if packet_length > self.MAX_PACKET_SIZE:
                logger.warning(
                    "Invalid packet length: %d (max %d), advancing 5 bytes to next potential header (attempt %d/%d, scanned %d bytes)",
                    packet_length, self.MAX_PACKET_SIZE, recovery_attempts + 1, MAX_RECOVERY_ATTEMPTS,
                    (recovery_attempts + 1) * 5,
                    extra={"buffer_size": len(self.buffer)}
                )
                # Fast-forward by header size (5 bytes) instead of 1 byte for performance
                # This prevents O(n²) behavior on malicious input
                advance_bytes = min(5, len(self.buffer))
                self.buffer = self.buffer[advance_bytes:]
                recovery_attempts += 1
                continue  # Retry parsing from new position

            # Reset recovery counter on valid packet
            recovery_attempts = 0

            total_length = 5 + packet_length  # Header (5 bytes) + data

            if len(self.buffer) >= total_length:
                # Extract complete packet
                packet = bytes(self.buffer[:total_length])
                packets.append(packet)
                self.buffer = self.buffer[total_length:]
            else:
                # Incomplete packet, wait for more data
                break

        return packets
```

---

## Implementation Plan

### Step 1: Packet Type Definitions

- Define packet type constants
- Create dataclass structures for each packet type
- **Import Phase 0.5 test fixtures AND checksum validation results**
- **Review `docs/protocol/checksum-validation.md` to confirm validated algorithm**

### Step 2: Checksum Algorithm

**Prerequisite**: Phase 0.5 checksum validation complete ✅

**Phase 0.5 Validation Results**:

- ✅ Validation PASSED: 100% match rate (13/13 packets)
- ✅ Algorithm confirmed: `sum(packet[start+6:end-1]) % 256` between 0x7e markers
- ✅ Tested against 2 legacy fixtures + 11 real packets from diverse devices
- ✅ Reference: `docs/phase-0.5/validation-report.md`

**Implementation**:
Copy validated algorithm from legacy code into `src/protocol/checksum.py` (see implementation steps below)

**Contingency Plan** (NOT NEEDED - Validation Passed):

**Contingency Plan: Reverse-Engineer Checksum Algorithm** (Time-boxed: 4 hours maximum)

### Step 1: Isolate Mismatch Pattern

- Compare 10+ packets with mismatches
- Question: Which packets have mismatches? All types or specific types only?
- **Pattern A** (all packets mismatch): Algorithm fundamentally incorrect
- **Pattern B** (specific types): Type-dependent algorithm or byte position variation

### Step 2: Hypothesis Testing Framework

Create automated test script: `scripts/reverse-engineer-checksum.py`

```python
#!/usr/bin/env python3
"""Reverse-engineer checksum algorithm from captured packets."""

def test_checksum_hypothesis(packet: bytes, expected_checksum: int):
    """Test multiple checksum algorithms against captured packet."""

    # Hypothesis 1: Sum between different byte positions
    print("Testing sum-based checksums...")
    for start in range(0, len(packet)-1):
        for end in range(start+1, len(packet)):
            calculated = sum(packet[start:end]) % 256
            if calculated == expected_checksum:
                print(f"✅ MATCH: sum(packet[{start}:{end}]) % 256 = {expected_checksum}")

    # Hypothesis 2: XOR-based checksums
    print("Testing XOR-based checksums...")
    for start in range(0, len(packet)-1):
        xor_sum = 0
        for byte in packet[start:]:
            xor_sum ^= byte
        if xor_sum == expected_checksum:
            print(f"✅ MATCH: XOR from byte {start} = {expected_checksum}")

    # Hypothesis 3: CRC-8 variants
    print("Testing CRC-8 checksums...")
    for poly in [0x07, 0x31, 0x9B, 0xD5, 0xEA]:
        crc = calculate_crc8(packet, poly)
        if crc == expected_checksum:
            print(f"✅ MATCH: CRC-8 polynomial 0x{poly:02x} = {expected_checksum}")

def calculate_crc8(data: bytes, polynomial: int) -> int:
    """Calculate CRC-8 with given polynomial."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ polynomial
            else:
                crc = crc << 1
        crc &= 0xFF
    return crc

if __name__ == "__main__":
    # Test against all captured packets with mismatches
    from tests.fixtures.real_packets import FIXTURES

    for packet_name, packet_bytes in FIXTURES.items():
        expected = extract_checksum_from_packet(packet_bytes)
        print(f"\n=== Testing {packet_name} ===")
        test_checksum_hypothesis(packet_bytes, expected)
```

### Step 3: Validate Discovered Algorithm

- Test discovered algorithm against 20+ additional packets
- If 100% match on all packets: Algorithm found
- If < 100% match: Continue hypothesis testing or consider firmware-specific variations

### Step 4: Document and Implement

- Document discovered algorithm in `docs/protocol/checksum-validation.md`
- Implement in `src/protocol/checksum.py`
- Update test fixtures with validation results

### If 4 Hours Elapsed Without Solution (Technical Review Finding 3.5 - Escalation Procedure Added)

If reverse-engineering time-box (4 hours) expires without finding algorithm:

**Step 1: Stop Investigation** (do not extend time-box without approval)

**Step 2: Escalate to User** with three documented options:

**Option A: Continue Investigation** (extend time-box)

- User approves extending investigation (e.g., +4 hours)
- Document additional time spent
- Risk: May not find algorithm even with more time

### Option B: Contact Device Manufacturer

- Request protocol documentation from manufacturer
- May require NDA or formal request process
- Timeline uncertain (days to weeks)

**Option C: Pause Phase 1a** (pending protocol clarification)

- Document blocker: Checksum algorithm cannot be reverse-engineered
- Phase 1a paused until algorithm obtained
- Consider: Use legacy cloud relay logs for reference (if available)

### Step 3: User Decision Required

- Present options with pros/cons
- User selects path forward
- Document decision and proceed accordingly

**Success Criteria** (before escalation): 100% checksum match on 30+ packets with diverse types (0x23, 0x73, 0x83, 0xD3, etc.)

### Important: NO LEGACY IMPORTS IN PRODUCTION CODE

The Phase 0.5 validation script (`mitm/validate-checksum-REFERENCE-ONLY.py`) imports legacy code, but this is a **one-time exception for validation only**. Phase 1a production code MUST NOT import from legacy codebase.

**❌ FORBIDDEN Pattern** (will be rejected in code review):

```python
## WRONG - DO NOT DO THIS IN PHASE 1a!
from cync_controller.packet_checksum import calculate_checksum_between_markers

## Using legacy import directly
checksum = calculate_checksum_between_markers(packet)
```

**✅ CORRECT Pattern** (copy and adapt):

```python
## CORRECT - Copy implementation into new codebase
## File: src/protocol/checksum.py

def calculate_checksum_between_markers(packet: bytes) -> int:
    """Calculate checksum between 0x7E markers.

    Algorithm copied from validated legacy implementation.
    Validated against 10+ real packets in Phase 0.5.
    See docs/protocol/checksum-validation.md for validation results.
    """
    # [Copy algorithm implementation here]
    # No imports from legacy codebase!
    pass
```

**Implementation Steps** (only after prerequisite met):

1. **Read** `docs/protocol/checksum-validation.md` from Phase 0.5
   - Confirm all packets validated successfully (100% match rate)
   - Review algorithm specification and edge cases
   - Note any firmware-specific variations documented

2. **Copy** checksum algorithm from legacy code (`cync_controller/packet_checksum.py`)
   - Create new file: `src/protocol/checksum.py`
   - Copy `calculate_checksum_between_markers()` function with full docstrings
   - **NO LEGACY IMPORTS** - Copy implementation, do not import from legacy code

3. **Adapt** for new codebase standards:
   - Update imports (use new codebase conventions)
   - Add type annotations (strict mypy compliance)
   - Add structured logging if needed

4. **Test** against Phase 0.5 validated fixtures:
   - Use real packet bytes from Phase 0.5 test fixtures
   - All tests should pass (algorithm pre-validated in Phase 0.5)
   - If tests fail: algorithm copy error, not algorithm issue

**Success Criteria**:

- ✅ `src/protocol/checksum.py` created with validated algorithm
- ✅ Unit tests pass using Phase 0.5 fixtures (100%)
- ✅ No ruff or mypy errors
- ✅ Ready for Step 3 (Header Encoding/Decoding)

### Step 3: Header Encoding/Decoding

- Implement header parser (5 bytes)
- Length calculation (multiplier \* 256 + base)
- Use endpoint and msg_id byte positions from Phase 0.5 Deliverable #2
  - Phase 0.5 validated exact positions (no byte overlap)
  - endpoint: bytes[5:10], msg_id: bytes[10:13]
- Unit tests for all packet types

### Step 4: Packet Encoders

- Implement encoders for each packet type
- 0x7e framing for data packets
- Endpoint/msg_id insertion
- Unit tests with expected output

### Step 5: Packet Decoders

- Implement decoders for each packet type
- Handle malformed packets gracefully
- Validate checksums
- Unit tests with Phase 0.5 captures

### Step 5.5: msg_id Generation Strategy (Sequential - DECIDED)

**Architectural Decision**: Sequential msg_id generation (Option B selected)

**Rationale**:

- Zero collision risk within single connection
- Deterministic behavior aids debugging (sequential IDs in logs)
- Simple state management (single counter)
- No dependency on Phase 0.5 device behavior (we control controller generation)
- Counter wraps at 16.7M (2^24) which exceeds typical connection lifetimes

**Counter Wrap-Around Safety**:

The 3-byte msg_id counter wraps at **16,777,216** (2^24) messages. This section explains why wrap-around is safe and collision-free.

**Wrap-Around Mechanics**:

- Counter starts at 0, increments by 1 for each message
- After msg_id `0xFF FF FF` (16,777,215), next msg_id wraps to `0x00 00 00`
- Wrap-around is automatic via modulo: `(counter % 0xFFFFFF).to_bytes(3, 'big')`

**Why Wrap-Around is Safe**:

1. **Old msg_ids cleared by ACK timeout**: Messages awaiting ACKs are tracked in `pending_acks` dict with timeout (default: 2s). After timeout, pending message is removed. By the time counter wraps (16.7M messages), all old pending ACKs have expired and been cleaned up.

2. **Collision requires improbable conditions**: Collision only possible if:
   - Counter wraps around (16.7M messages sent)
   - **AND** a message with same msg_id is still in `pending_acks` (not ACKed/timed out)
   - **AND** connection hasn't been reset

   This requires connection to stay alive for 16.7M messages WITHOUT a single ACK or timeout clearing old msg_id - impossible in practice.

3. **Typical connection lifetimes**: Smart home usage patterns:
   - Average: 10-100 messages per connection session
   - High usage: 1,000-10,000 messages per session
   - Wrap-around threshold: 16,777,216 messages
   - **Gap**: 1,677× to 16,777× margin before wrap-around

4. **Automatic reset on reconnect**: If connection drops and reconnects, counter resets (new ReliableTransport instance), eliminating any wrap-around concerns.

**Monitoring & Observability**:

- Log counter wrap events for observability: `logger.info("msg_id counter wrapped at 16,777,216")`
- Metric: `tcp_comm_msg_id_wraps_total` (counter, increments on wrap)
- Alert if multiple wraps within short period (indicates unexpected high message rate)

**Example Calculation**:

- Message rate: 10 messages/sec (high usage)
- Time to wrap: 16,777,216 / 10 = 1,677,721 seconds = **19.4 days**
- Typical ACK timeout: 2 seconds
- By wrap time, all msg_ids from 19.4 days ago have been cleared

**Collision Impossibility**: For collision to occur, a pending ACK would need to survive 19.4 days without being ACKed, timed out, or cleaned up - this violates multiple system invariants (ACK timeout, cleanup task, connection lifetime).

**Conclusion**: Sequential msg_id with wrap-around is safe for production use. Collision risk is mathematically zero under normal operating conditions.

### ⚠️ Edge Case: Device Reboot Scenario (Technical Review Finding 2.4 - Documented)

**Edge case identified**: Device reboots while controller connection survives.

**Scenario**:

1. Controller sends msg_id 100 to Device A
2. Device A reboots unexpectedly (power loss, firmware update, crash)
3. Controller TCP connection stays alive (TCP doesn't detect reboot immediately)
4. Controller retries or sends new command with msg_id 100
5. Device A (post-reboot) sees msg_id 100 as first message (lost pre-reboot context)

**Mitigation**:

- **Random offset on init** (line 610): Counter starts at random value 0-4095, not 0
  - Reduces collision window after device reboot
  - Different starting point post-reconnect vs pre-reboot counter
- **Session tracking** (line 599): Prevents parallel connections but doesn't prevent device reboot scenario
- **TCP keepalive**: Connection should detect device reboot via TCP keepalive probes (eventual detection)

**Risk Assessment**:

- **Probability**: Very low (device reboots rare during active command, TCP usually detects disconnection)
- **Impact**: Medium (one command might be misinterpreted by rebooted device)
- **Severity**: Acceptable for smart home use case

**Accepted risk**: Smart home usage patterns make this edge case extremely rare. Benefits of sequential generation outweigh low-probability edge case.

**Implementation** (Phase 1b ReliableTransport with session identification):

```python
import secrets
import uuid

class ReliableTransport:
    """Reliable transport with session tracking to prevent parallel connections.

    **Session Identification**: Class-level registry prevents parallel connections
    to same device, eliminating msg_id collision risk from independent counter instances.
    """

    # Class-level registry prevents parallel connections to same device
    _active_sessions: Dict[str, 'ReliableTransport'] = {}
    _session_lock = asyncio.Lock()

    def __init__(self, device_id: str, ...):
        """Initialize transport with session tracking.

        Args:
            device_id: Unique device identifier for session tracking
        """
        self.device_id = device_id
        self.session_id = str(uuid.uuid4())
        # Random offset eliminates collision risk on reboot edge cases
        self._msg_id_counter: int = secrets.randbelow(0x1000)

    async def connect(self, endpoint: bytes, auth_code: bytes):
        """Connect with parallel connection prevention.

        Raises:
            CyncConnectionError: If parallel connection attempt detected
        """
        async with self._session_lock:
            if self.device_id in self._active_sessions:
                raise CyncConnectionError(
                    f"Parallel connection to device {self.device_id} rejected - "
                    "only one connection per device allowed to prevent msg_id collisions"
                )
            self._active_sessions[self.device_id] = self

        # ... proceed with handshake (implementation in Phase 1b)

    async def disconnect(self):
        """Disconnect and remove from session registry."""
        async with self._session_lock:
            self._active_sessions.pop(self.device_id, None)
        # ... cleanup (implementation in Phase 1b)

    def generate_msg_id(self) -> bytes:
        """Generate sequential 3-byte msg_id.

        Counter wraps at 16,777,216 (2^24 - 1).
        Uses big-endian byte order.
        Random offset on init handles reboot edge case.
        """
        msg_id = (self._msg_id_counter % 0xFFFFFF).to_bytes(3, 'big')
        self._msg_id_counter += 1
        return msg_id
```

**Benefits**:

- ✅ No collision handling needed (Phase 1b simplified)
- ✅ Predictable msg_ids aid troubleshooting
- ✅ No collision analysis required (removed from Phase 1b spec)
- ✅ Parallel connection prevention eliminates multi-instance collision risk
- ✅ Random offset handles device reboot edge case (device reboots, controller connection survives)

**Session Identification Rationale**:

- **Problem**: Multiple parallel connections to same device create independent msg_id counters → collision risk
- **Solution**: Class-level session registry prevents parallel connections
- **Trade-off**: One connection per device (acceptable for smart home use case)
- **Benefit**: Zero collision risk without disk persistence complexity

**Phase 0.5 Observation** (informative, not blocking):

- Phase 0.5 can still observe device msg_id patterns for reference
- Device behavior doesn't constrain controller generation strategy
- Controller acts independently when sending commands

### Step 5.6: Implement PacketFramer

- Create `PacketFramer` class after decoder is complete
- Implements buffering for incomplete packets across multiple TCP reads
- Header-based length extraction (byte[3]\*256 + byte[4])
- Multi-packet handling from single TCP read (extract all complete packets)
- Unit tests for edge cases:
  - Partial packet buffering (header only, then remaining bytes)
  - Multi-packet extraction (single read contains 2+ complete packets)
  - Empty buffer, exact boundaries, length overflow scenarios

### Step 6: Create New Toggler

**Phase 1a Scope** (minimal viable test using codec directly):

- Create `harness/toggler_v2.py` using real Cync protocol
- **Phase 1a Implementation** (direct codec usage):
  - Uses `CyncProtocol.encode()` and `CyncProtocol.decode()` directly
  - Manual handshake: encode 0x23, send, recv 0x28, decode
  - Manual toggle: encode 0x73, send, recv 0x7B, decode
  - Simple timeout (5s), fail immediately if no response
  - NO retry logic (fail fast on first timeout)
  - NO deduplication (not needed for single command test)
  - NO heartbeat keepalive (short-lived test script)
  - Log success/failure with timing metrics

**Phase 1b Refactoring** (will replace manual logic):

Once Phase 1b `ReliableTransport` is implemented, `toggler_v2.py` will be refactored to:

- Replace manual handshake with `ConnectionManager.connect()`
- Replace manual send/recv with `ReliableTransport.send_reliable()`
- Inherit automatic retries from ReliableTransport
- Inherit deduplication from ReliableTransport
- Inherit heartbeat from ConnectionManager

**Example Progression**:

```python
## Phase 1a version (direct codec):
protocol = CyncProtocol()
handshake_packet = protocol.encode_handshake(endpoint, auth_code)
writer.write(handshake_packet)
await writer.drain()
response = await asyncio.wait_for(reader.read(4096), timeout=5.0)
ack_packet = protocol.decode_packet(response)
assert ack_packet.packet_type == 0x28

## Phase 1b version (ReliableTransport wrapper):
transport = ReliableTransport(conn, protocol)
await transport.connect()  # Handles handshake + retries
result = await transport.send_reliable(toggle_payload)  # Handles ACK + retries
assert result.success
```

**Phase 1a vs 1b Boundary**:

- **Phase 1a**: Codec works (can encode/decode packets correctly)
- **Phase 1b**: Reliability works (automatic retries, deduplication, reconnection)
- **toggler_v2.py**: Simple test harness that evolves with each phase

**Connection Target**:

- Default: localhost:9000 (for Phase 1d simulator)
- Optional: Real device IP via CLI argument

**Legacy Comparison**:

- `toggler.py` = Phase 0 test harness (custom 0xF00D protocol) - UNCHANGED
- `toggler_v2.py` = Phase 1a+ with real Cync protocol - EVOLVING

**Example Usage**:

```bash
## Test with simulator (Phase 1d)
python harness/toggler_v2.py --host localhost --port 9000

## Test with real device
python harness/toggler_v2.py --host 192.168.1.100 --port 23779
```

---

## Deliverables

### Code

- [ ] `src/protocol/cync_protocol.py` (150-200 lines)
- [ ] `src/protocol/packet_types.py` (50-75 lines)
- [ ] `src/protocol/packet_framer.py` (80-100 lines)
- [ ] `src/protocol/checksum.py` (30-40 lines)
- [ ] 15+ unit tests in `tests/unit/protocol/`
- [ ] New `harness/toggler_v2.py` using real Cync protocol

### Documentation

- [ ] API documentation in docstrings
- [ ] Usage examples in module docs
- [ ] Update `README.md` with Phase 1a completion

### Validation

- [ ] All unit tests pass (100%)
- [ ] Validated against Phase 0.5 real packet captures
- [ ] Checksum algorithm matches legacy implementation
- [ ] No ruff or mypy errors

---

## Acceptance Criteria

### Functional

- [ ] Encode all major packet types (0x23, 0x73, 0x83, 0xD3)
- [ ] Decode all major packet types
- [ ] Checksum calculation matches Phase 0.5 validated algorithm
- [ ] **Malformed packet handling**: Raise `PacketDecodeError` with specific reason + log error + increment `tcp_comm_decode_errors_total{reason}`
- [ ] `decode_packet()` raises `PacketDecodeError` for all parse errors (no None returns)
- [ ] Supported error reasons: "too_short", "invalid_checksum", "unknown_type", "invalid_length", "missing_0x7e_markers"
- [ ] Endpoint/msg_id extracted correctly from valid packets

### Security (PacketFramer Buffer Overflow Protection)

- [ ] PacketFramer rejects packets with length > MAX_PACKET_SIZE (4096 bytes)
- [ ] PacketFramer handles integer overflow (multiplier=255, base=255 → 65535 bytes)
- [ ] PacketFramer discards buffer and logs error on invalid length
- [ ] PacketFramer clears buffer state after overflow detection
- [ ] Metric `tcp_comm_decode_errors_total{reason="invalid_length"}` incremented on overflow
- [ ] No memory exhaustion under malicious packet stream (validated in load test)

### Testing

- [ ] 15+ unit tests covering all packet types
- [ ] Tests use Phase 0.5 real packet fixtures
- [ ] Device IDs parameterized (not hardcoded): `@pytest.mark.parametrize("device_id", [123, 456, 789])`
- [ ] Edge cases tested (length overflow, invalid checksum, malformed headers)
- [ ] PacketFramer tests cover:
  - Partial packet buffering (header-only read, then completion)
  - Multi-packet extraction (single read with 2+ complete packets)
  - Exact boundary reads (complete packet in one read)
  - Empty buffer and zero-length scenarios
  - Large packets requiring length multiplier (byte[3] > 0)
- [ ] 100% test pass rate
- [ ] 90% code coverage

### Quality

- [ ] No ruff errors
- [ ] No mypy errors (strict mode)
- [ ] Full type annotations
- [ ] Comprehensive docstrings

### Integration

- [ ] New toggler_v2.py created using real Cync protocol
- [ ] Can encode/decode packets successfully
- [ ] 3-byte msg_id generation implemented (Sequential strategy - Step 5.5)
- [ ] Ready for Phase 1b (reliable transport) integration
- [ ] Note: correlation_id will be added in Phase 1b for tracking/observability

**Note**: msg_id generation uses Sequential strategy (decided in Step 5.5) - no Phase 0.5 dependency.

---

## Testing Strategy

### Unit Tests (pytest)

```python
## test_encoder.py
def test_encode_handshake():
    """Test 0x23 handshake encoding."""
    endpoint = bytes.fromhex("39 87 c8 57")
    auth_code = bytes.fromhex("31 65 30 37...")
    packet = CyncProtocol.encode_handshake(endpoint, auth_code)
    assert packet[0] == 0x23
    assert packet[5:9] == endpoint

def test_encode_data_packet():
    """Test 0x73 data packet encoding with 0x7e framing."""
    endpoint = bytes.fromhex("1b dc da 3e 00")
    msg_id = bytes.fromhex("13 00 00")
    payload = bytes.fromhex("0d 01 00...")
    packet = CyncProtocol.encode_data_packet(endpoint, msg_id, payload)
    assert packet[0] == 0x73
    assert 0x7e in packet  # Has framing marker
```

### Integration Tests (with Phase 0.5 fixtures)

```python
## test_real_packets.py
from tests.fixtures.real_packets import HANDSHAKE_0x23_DEV_TO_CLOUD

def test_decode_real_handshake():
    """Decode real captured handshake packet."""
    packet = CyncProtocol.decode_packet(HANDSHAKE_0x23_DEV_TO_CLOUD)
    assert packet.packet_type == 0x23
    assert packet.length == 26
    # Validate endpoint extraction...
```

### Security Tests (Buffer Overflow Protection)

```python
## test_framer_security.py

def test_framer_rejects_oversized_packet():
    """Test MAX_PACKET_SIZE validation."""
    framer = PacketFramer()

    # Malicious packet: claims 5000 bytes (exceeds MAX_PACKET_SIZE=4096)
    # multiplier=19, base=136 → 19*256 + 136 = 5000
    malicious_header = bytes([0x73, 0x00, 0x00, 0x13, 0x88])

    packets = framer.feed(malicious_header)

    # Should discard buffer and return empty list
    assert packets == []
    assert len(framer.buffer) == 0  # Buffer cleared for safety

def test_framer_handles_integer_overflow():
    """Test integer overflow protection (multiplier=255, base=255)."""
    framer = PacketFramer()

    # Extreme values: 255*256 + 255 = 65535 bytes
    overflow_header = bytes([0x73, 0x00, 0x00, 0xFF, 0xFF])

    packets = framer.feed(overflow_header)

    # Should reject and clear buffer
    assert packets == []
    assert len(framer.buffer) == 0

def test_framer_survives_malicious_stream():
    """Test that framer doesn't exhaust memory under malicious input."""
    framer = PacketFramer()

    # Send 1000 malicious packets with invalid lengths
    for i in range(1000):
        malicious = bytes([0x73, 0x00, 0x00, 0xFF, 0xFF, 0x00, 0x01, 0x02])
        packets = framer.feed(malicious)
        assert packets == []  # All rejected

    # Buffer should remain empty (not accumulating rejected data)
    assert len(framer.buffer) == 0

def test_framer_large_corrupt_stream():
    """Test framer with >500 byte corrupt stream (exceeds 100 recovery attempts × 5 bytes)."""
    framer = PacketFramer()

    # Create 600-byte corrupt stream (no valid header)
    corrupt_stream = bytes([0xFF] * 600)

    packets = framer.feed(corrupt_stream)

    # After 100 recovery attempts (scanning 500 bytes), buffer cleared
    assert packets == []
    assert len(framer.buffer) == 0  # Buffer cleared after max attempts exceeded

@pytest.mark.parametrize("device_id", [123, 456, 789])
def test_encode_handshake_parameterized(device_id):
    """Test handshake encoding with various device IDs."""
    endpoint = device_id.to_bytes(4, 'big')
    auth_code = b"\x00" * 16

    packet = CyncProtocol.encode_handshake(endpoint, auth_code)

    assert packet[0] == 0x23
    assert packet[5:9] == endpoint  # Endpoint correctly embedded
```

---

## Risks & Mitigation

| Risk                           | Impact | Mitigation                                                |
| ------------------------------ | ------ | --------------------------------------------------------- |
| Protocol mismatch vs. captures | High   | Validate every encoder/decoder against Phase 0.5 fixtures |
| Checksum algorithm incorrect   | Medium | Test against 10+ real packets with known checksums        |
| Length calculation edge cases  | Medium | Test with large packets (multiplier > 0)                  |
| Firmware version differences   | Low    | Document variations; implement most common version        |

---

## Dependencies

**Prerequisites**:

- Phase 0.5 complete (protocol validation, packet captures)
- Test fixtures available (`tests/fixtures/real_packets.py`)

**External**:

- None (pure Python implementation)

**Development**:

- `types-prometheus-client` - Type stubs for mypy strict mode (already in Phase 0 pyproject.toml)

---

## Success Metrics

- ✅ All major packet types encodable/decodable
- ✅ 100% unit test pass rate
- ✅ Validated against Phase 0.5 captures
- ✅ Phase 0 toggler working with real protocol
- ✅ Zero checksum mismatches
- ✅ Ready for Phase 1b integration

---

## Next Phase

**Phase 1b**: Reliable Transport Layer (1 week)

- Use Phase 1a codec for packet encoding/decoding
- Add ACK/NACK handling on top of codec
- Implement retry logic and idempotency

---

## Related Documentation

- **Phase 0.5**: `02a-phase-0.5-protocol-validation.md` - Protocol validation and captures
- **Phase 1 Program**: `02-phase-1-spec.md` - Overall architecture and context
- **Phase 1b**: `02c-phase-1b-reliable-transport.md` - Next phase (reliable transport)
- **Discovery**: `00-discovery.md` - Original protocol analysis
