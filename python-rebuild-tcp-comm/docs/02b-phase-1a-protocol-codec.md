# Phase 1a: Cync Protocol Codec

**Status**: Planning
**Dependencies**: Phase 0.5 (protocol validation) complete
**Execution**: Sequential solo implementation

---

## Overview

Phase 1a implements the real Cync device protocol encoder/decoder based on validated packet captures from Phase 0.5. This replaces Phase 0's custom test protocol (0xF00D magic bytes) with the actual protocol that Cync devices speak.

**See Also**: `02-phase-1-spec.md` for complete Phase 1 program architecture and context.

---

## Prerequisites

Phase 0.5 protocol validation provides:

**Checksum Algorithm**:

- Algorithm: `sum(packet[start+6:end-1]) % 256` between 0x7e markers
- See: `docs/phase-0.5/validation-report.md`

**Byte Positions**:

- endpoint: bytes[5:10] (5 bytes)
- msg_id: bytes[10:12] (2 bytes)
- padding: byte 12 (0x00 in 0x73 packets)
- See: `docs/phase-0.5/packet-structure-validated.md`

**Test Fixtures**:

- Location: `tests/fixtures/real_packets.py`
- Contains: 13 validated packets from diverse device types (handshake, toggle, status, heartbeat)

---

## Goals

1. Implement encoder/decoder for all major Cync packet types
2. Support packet framing with 0x7e markers and checksum validation
3. Validate implementation against Phase 0.5 real packet captures
4. Validate codec with MITM plugin against live traffic
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

**Visual Diagrams**: See `docs/phase-1a/architecture-comprehensive.mermaid` and `docs/phase-1a/data-flow.mermaid` for visual architecture and data flow diagrams.

```text
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

    def __init__(self, reason: str, data: bytes = b""):
        self.reason = reason
        # Security: Only store first 16 bytes to prevent credential leakage in logs/tracebacks
        self.data_preview = data[:16] if data else b""
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

**File Location**: `src/protocol/exceptions.py` (Phase 1a - implemented now)

#### Future Exception Preview (Phase 1b/1c - Reference Only)

Phase 1b and 1c will add additional exception types for connection and queue management:

```text
CyncProtocolError (Phase 1a - base)
├── CyncConnectionError (Phase 1b - planned)
├── HandshakeError (Phase 1b - planned)
├── PacketReceiveError (Phase 1b - planned)
├── DuplicatePacketError (Phase 1b - planned)
├── ACKTimeoutError (Phase 1b - planned)
└── QueueFullError (Phase 1c - planned)
```

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
# Required imports for protocol implementation
from dataclasses import dataclass
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

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
    msg_id: bytes    # 2 bytes - wire protocol message ID (bytes[10:12])
    data: bytes      # Inner payload (between 0x7e markers)
    checksum: int
    checksum_valid: bool

# ... (imports omitted for brevity - see lines 221-226)
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

        Known types (0x23, 0x28, 0x73, 0x83, etc.): Returns specific subclass
        Unknown types: Raises PacketDecodeError with reason="unknown_type"

        Raises:
            PacketDecodeError: If packet is malformed:
                - "too_short": Packet < 5 bytes
                - "invalid_checksum": Checksum validation failed
                - "unknown_type": Packet type byte not recognized
                - "invalid_length": Length field exceeds MAX_PACKET_SIZE
                - "missing_0x7e_markers": Data packet missing frame markers
        """

    @staticmethod
    def calculate_checksum(data: bytes) -> int:
        """Calculate checksum (sum % 256 between 0x7e markers)."""

# ... (imports omitted for brevity - see lines 221-226)
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

    **Recovery Loop Protection**:
    - Scans up to min(buffer_size, 5000) bytes before clearing buffer
    - Formula: MAX_RECOVERY_ATTEMPTS = min(1000, max(100, buffer_size // 5))
    - Time Complexity: O(n) where n = bytes scanned (max 5000)
    - Memory: O(1) additional (in-place buffer operations)
    - Example: 10KB corrupt buffer = 2048 attempts, scans 10KB, then clears
    - Bounded behavior: Will scan entire buffer once, then clear if no valid packets found

    Example:
        framer = PacketFramer()
        # First read: partial packet (header only)
        packets = framer.feed(b'\\x23\\x00\\x00\\x00\\x1a')
        assert packets == []  # Incomplete

        # Second read: remaining bytes
        packets = framer.feed(b'\\x39\\x87\\xc8\\x57...')
        assert len(packets) == 1  # Now complete
    """
    MAX_PACKET_SIZE = 4096  # 4KB max (observed max: 395 bytes)

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

        Performance Characteristics:
        - Time Complexity: O(n) where n = buffer size (single-pass)
        - Worst Case: O(n) even with corrupt packets (recovery limit prevents O(n²))
        - Memory: O(1) additional memory (in-place buffer operations)
        - Typical: Extracts 1-5 packets per call in normal operation

        Returns:
            List of complete packets; buffer retains incomplete data
        """
        packets = []
        recovery_attempts = 0
        # Recovery attempts proportional to buffer size (min 100, max 1000)
        # Formula: attempts = buffer_size // 5 (capped at 1000)
        # Examples: 500-byte buffer = 100 attempts; 5000-byte buffer = 1000 attempts
        # Each attempt scans 5 bytes, so max scanned = 5000 bytes worst case
        MAX_RECOVERY_ATTEMPTS = min(1000, max(100, len(self.buffer) // 5))

        while len(self.buffer) >= 5:
            # Check recovery limit
            # Log once per buffer clear event, not per recovery attempt
            if recovery_attempts > MAX_RECOVERY_ATTEMPTS:
                logger.error(
                    "Buffer cleared after max recovery attempts",
                    extra={
                        "max_attempts": MAX_RECOVERY_ATTEMPTS,
                        "buffer_size": len(self.buffer),
                        "bytes_scanned": recovery_attempts * 5,
                    }
                )
                self.buffer = bytearray()  # Clear corrupted buffer
                break

            # Parse header to get packet length
            multiplier = self.buffer[3]
            base_len = self.buffer[4]
            packet_length = (multiplier * 256) + base_len

            # Validate length before proceeding
            # Rate-limited: logs once per invalid length found, not per attempt
            if packet_length > self.MAX_PACKET_SIZE:
                logger.warning(
                    "Invalid packet length: %d (max %d), advancing 5 bytes to next potential header (attempt %d/%d, scanned %d bytes)",
                    packet_length, self.MAX_PACKET_SIZE, recovery_attempts + 1, MAX_RECOVERY_ATTEMPTS,
                    (recovery_attempts + 1) * 5,
                    extra={"buffer_size": len(self.buffer)}
                )
                # Fast-forward by header size (5 bytes) instead of 1 byte for performance
                # This maintains O(n) with bounded scan on malicious input
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

### Step 0: MITM Plugin Architecture (Foundation)

Build plugin infrastructure that allows Phase 1a codec to run as an observer in MITM proxy.

#### Architecture

- MITM proxy remains standalone in `mitm/` directory
- Phase 1a codec components live in `src/protocol/` package
- Plugin adapter bridges MITM events to Phase 1a function calls
- No networking between plugin and codec (in-process function calls)

#### Components to Create

**1. Observer Interface** (`mitm/interfaces/packet_observer.py`):

```python
from typing import Protocol
from enum import Enum

class PacketDirection(Enum):
    DEVICE_TO_CLOUD = "device_to_cloud"
    CLOUD_TO_DEVICE = "cloud_to_device"

class PacketObserver(Protocol):
    """Type protocol for MITM packet observers.

    Enforced by mypy at type-check time. No inheritance required.
    """

    def on_packet_received(
        self, direction: PacketDirection, data: bytes, connection_id: int
    ) -> None:
        """Called when packet received."""
        ...

    def on_connection_established(self, connection_id: int) -> None:
        """Called when connection established."""
        ...

    def on_connection_closed(self, connection_id: int) -> None:
        """Called when connection closed."""
        ...
```

**2. Refactor MITMProxy** (`mitm/mitm_proxy.py`):

Add observer pattern to existing `MITMProxy` class:

```python
class MITMProxy:
    def __init__(self, ...):
        # ... existing init ...
        self.observers: list[PacketObserver] = []

    def register_observer(self, observer: PacketObserver) -> None:
        """Register plugin to receive packet notifications."""
        self.observers.append(observer)

    async def _handle_device_to_cloud(self, data: bytes, conn_id: int):
        # ... existing forward logic ...

        # Notify observers (in-process function calls)
        for observer in self.observers:
            try:
                observer.on_packet_received(
                    PacketDirection.DEVICE_TO_CLOUD, data, conn_id
                )
            except Exception as e:
                # Observer failures don't break proxy
                print(f"Observer error: {e}")
```

**3. Codec Validator Plugin Stub** (`mitm/validation/codec_validator.py`):

Create stub that will wrap Phase 1a components (implemented after codec is built):

```python
from mitm.interfaces.packet_observer import PacketObserver, PacketDirection
import logging

logger = logging.getLogger(__name__)

class CodecValidatorPlugin:
    """Phase 1a codec validator plugin.

    Will wrap CyncProtocol and PacketFramer once they're implemented.
    For now, just logs packet events.
    """

    def __init__(self) -> None:
        self.framers: dict[int, Any] = {}  # Will use PacketFramer
        logger.info("CodecValidatorPlugin initialized (stub)")

    def on_packet_received(
        self, direction: PacketDirection, data: bytes, connection_id: int
    ) -> None:
        """Validate packet with Phase 1a codec."""
        logger.info(
            f"Packet received: {direction.value}, {len(data)} bytes, conn {connection_id}"
        )

    def on_connection_established(self, connection_id: int) -> None:
        logger.info(f"Connection established: {connection_id}")

    def on_connection_closed(self, connection_id: int) -> None:
        logger.info(f"Connection closed: {connection_id}")
        self.framers.pop(connection_id, None)
```

**4. Main Entry Point** (`mitm/main.py`):

```python
import argparse
from mitm.mitm_proxy import MITMProxy
from mitm.validation.codec_validator import CodecValidatorPlugin

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable-codec-validation", action="store_true")
    # ... existing args ...
    args = parser.parse_args()

    proxy = MITMProxy(
        listen_port=args.listen_port,
        upstream_host=args.upstream_host,
        upstream_port=args.upstream_port
    )

    if args.enable-codec-validation:
        proxy.register_observer(CodecValidatorPlugin())

    proxy.run()
```

#### Success Criteria

- [ ] `PacketObserver` Protocol interface defined
- [ ] `MITMProxy` refactored with observer pattern
- [ ] `CodecValidatorPlugin` stub created
- [ ] Plugin can be enabled via CLI flag
- [ ] mypy validates Protocol implementation
- [ ] Zero impact on existing MITM packet capture functionality

### Step 1: Packet Type Definitions

- Define packet type constants
- Create dataclass structures for each packet type
- Import Phase 0.5 test fixtures

### Step 2: Checksum Algorithm

Copy validated algorithm from legacy code into `src/protocol/checksum.py`:

- Algorithm: `sum(packet[start+6:end-1]) % 256` between 0x7e markers
- Reference: `docs/phase-0.5/validation-report.md`

### Important: NO LEGACY IMPORTS

Do not import from legacy `cync_controller` package. Copy algorithm implementation into new codebase.

**Implementation**:

1. Copy checksum algorithm from `cync_controller/packet_checksum.py` to `src/protocol/checksum.py`
2. Add type annotations for strict mypy compliance
3. Test against fixtures in `tests/fixtures/real_packets.py`
4. Verify no legacy imports: `grep -r "from cync_controller" src/ tests/`

### Step 3: Header Encoding/Decoding

- Implement header parser (5 bytes)
- Length calculation (multiplier \* 256 + base)
- Use byte positions: endpoint bytes[5:10], msg_id bytes[10:13]
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

The 3-byte counter wraps at 16,777,216 (2^24). This is safe because:

- ACK timeout (2s) clears old msg_ids before wrap-around possible
- Typical connection: 10-1000 messages (16,777× to 1,677,721× margin)
- Connection reset clears counter completely

**Monitoring**: Log wrap events (`tcp_comm_msg_id_wraps_total` metric), alert on multiple wraps per day.

**Example**: At 10 msg/sec (high usage), wrap occurs after 19.4 days. All msg_ids from 19.4 days ago cleared by ACK timeout.

### Edge Case: Device Reboot Scenario

**Scenario**:

1. Controller sends msg_id 100 to Device A
2. Device A reboots unexpectedly (power loss, firmware update, crash)
3. Controller TCP connection stays alive (TCP doesn't detect reboot immediately)
4. Controller retries or sends new command with msg_id 100
5. Device A (post-reboot) sees msg_id 100 as first message (lost pre-reboot context)

**Mitigation**:

- Random offset on init: Counter starts at random value 0-65535
- Session tracking prevents parallel connections
- TCP keepalive detects device disconnection

**Implementation**:

```python
# Required imports for ReliableTransport implementation
import secrets
import uuid
import asyncio
from typing import Dict

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
        # 16-bit range provides ~6.8 minutes safety window at peak rate (161 msg/sec)
        self._msg_id_counter: int = secrets.randbelow(0x10000)  # 0-65535

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

        Counter wraps at 16,777,216 (2^24) to cover full 3-byte range (0x000000 to 0xFFFFFF).
        Uses big-endian byte order.
        Random offset on init handles reboot edge case.
        """
        msg_id = (self._msg_id_counter % 0x1000000).to_bytes(3, 'big')  # 2^24 for full 3-byte range
        self._msg_id_counter += 1
        return msg_id
```

**Session Tracking**: Class-level registry prevents parallel connections to same device, eliminating msg_id collision risk.

### Step 6: Implement PacketFramer

- Create `PacketFramer` class after decoder is complete
- Implements buffering for incomplete packets across multiple TCP reads
- Header-based length extraction (byte[3]\*256 + byte[4])
- Multi-packet handling from single TCP read (extract all complete packets)
- Unit tests for edge cases:
  - Partial packet buffering (header only, then remaining bytes)
  - Multi-packet extraction (single read contains 2+ complete packets)
  - Empty buffer, exact boundaries, length overflow scenarios

### Step 7: Complete Codec Validator Plugin

Now that Phase 1a codec components are implemented, complete the plugin stub from Step 0.

**Update** (`mitm/validation/codec_validator.py`):

```python
from mitm.interfaces.packet_observer import PacketObserver, PacketDirection
from src.protocol.cync_protocol import CyncProtocol
from src.protocol.packet_framer import PacketFramer
from src.protocol.exceptions import PacketDecodeError, PacketFramingError
import logging

logger = logging.getLogger(__name__)

class CodecValidatorPlugin:
    """Phase 1a codec validator - validates packets using real codec."""

    def __init__(self) -> None:
        self.protocol = CyncProtocol()
        self.framers: dict[int, PacketFramer] = {}

    def on_packet_received(
        self, direction: PacketDirection, data: bytes, connection_id: int
    ) -> None:
        if connection_id not in self.framers:
            self.framers[connection_id] = PacketFramer()

        try:
            packets = self.framers[connection_id].feed(data)
            for packet in packets:
                decoded = self.protocol.decode_packet(packet)
                logger.info(
                    "Phase 1a codec validated",
                    extra={
                        "direction": direction.value,
                        "type": hex(decoded.packet_type),
                        "length": decoded.length
                    }
                )
        except (PacketDecodeError, PacketFramingError) as e:
            logger.error(f"Phase 1a validation failed: {e}")

    def on_connection_established(self, connection_id: int) -> None:
        self.framers[connection_id] = PacketFramer()

    def on_connection_closed(self, connection_id: int) -> None:
        self.framers.pop(connection_id, None)
```

**Testing**:

1. Start MITM with validation enabled:

   ```bash
   python mitm/main.py --upstream-host homeassistant.local --enable-codec-validation
   ```

2. Use Home Assistant UI to trigger commands (manual user intervention required)

3. Watch logs for validation results:
   - Successful decode: "Phase 1a validated type=0x73"
   - Failed decode: "Phase 1a validation failed: invalid checksum"

---

## Deliverables

### Code

- [ ] `src/protocol/cync_protocol.py` (150-200 lines)
- [ ] `src/protocol/packet_types.py` (50-75 lines)
- [ ] `src/protocol/packet_framer.py` (80-100 lines)
- [ ] `src/protocol/checksum.py` (30-40 lines)
- [ ] 15+ unit tests in `tests/unit/protocol/`
- [ ] `mitm/interfaces/packet_observer.py` (~50 lines)
- [ ] `mitm/validation/codec_validator.py` (~80 lines)
- [ ] `mitm/main.py` entry point (~50 lines)
- [ ] Updated `mitm/mitm_proxy.py` with observer pattern

### Documentation

- [ ] API documentation in docstrings
- [ ] Usage examples in module docs

### Validation

- [ ] All unit tests pass (100%)
- [ ] Validated against Phase 0.5 real packet captures
- [ ] Checksum algorithm matches legacy implementation
- [ ] No ruff or mypy errors

---

## Phase 1a Metrics

Phase 1a introduces error tracking metrics for protocol codec operations.

### Error Metrics

**Decode Error Counter**:

```python
tcp_comm_decode_errors_total{reason, packet_type}  # Counter
```

- **Description**: Total number of packet decode failures
- **Labels**:
  - `reason`: Specific failure reason
    - `"too_short"` - Packet smaller than minimum size
    - `"invalid_checksum"` - Checksum validation failed
    - `"unknown_type"` - Unrecognized packet type byte
    - `"invalid_length"` - Length field invalid or exceeds maximum
    - `"missing_0x7e_markers"` - Data packet missing frame markers
  - `packet_type`: Packet type byte as hex string
    - `"0x23"`, `"0x73"`, `"0x83"`, `"0xD3"` for known types
    - `"unknown"` if type byte unrecognized

**Framing Error Counter**:

```python
tcp_comm_framing_errors_total{reason}  # Counter
```

- **Description**: Total number of packet framing errors
- **Labels**:
  - `reason`: Specific failure reason
    - `"packet_too_large"` - Length exceeds MAX_PACKET_SIZE (4096 bytes)
    - `"invalid_length"` - Length field parsing failed
    - `"buffer_overflow"` - Buffer exceeded safe limits
    - `"recovery_failed"` - Max recovery attempts exceeded

### Metric Usage

**Increment on decode error**:

```python
try:
    packet = decode_packet(data)
except PacketDecodeError as e:
    logger.error("Decode failed", extra={"reason": e.reason})
    metrics.tcp_comm_decode_errors_total.labels(
        reason=e.reason,
        packet_type=f"0x{data[0]:02x}" if data else "unknown"
    ).inc()
    raise
```

**Increment on framing error**:

```python
if packet_length > MAX_PACKET_SIZE:
    metrics.tcp_comm_framing_errors_total.labels(
        reason="packet_too_large"
    ).inc()
    raise PacketFramingError(
        f"Packet length {packet_length} exceeds maximum {MAX_PACKET_SIZE}"
    )
```

---

## Acceptance Criteria

### Functional

- [ ] Encode all major packet types (0x23, 0x73, 0x83, 0xD3)
- [ ] Decode all major packet types
- [ ] Checksum calculation matches Phase 0.5 validated algorithm
- [ ] **Malformed packet handling**: Raise `PacketDecodeError` with specific reason + log error + define metric structure `tcp_comm_decode_errors_total{reason}`
- [ ] `decode_packet()` raises `PacketDecodeError` for all parse errors (no None returns)
- [ ] Supported error reasons: "too_short", "invalid_checksum", "unknown_type", "invalid_length", "missing_0x7e_markers"
- [ ] Endpoint/msg_id extracted correctly from valid packets
- [ ] No imports from `cync_controller` package (validate: `grep -r "from cync_controller" src/ tests/`)

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
- [ ] 90% code coverage for `src/protocol/` directory (MITM plugin in `mitm/` not counted toward 90% threshold but should have basic validation tests for critical paths)

### Quality

- [ ] No ruff errors
- [ ] No mypy errors (strict mode)
- [ ] Full type annotations
- [ ] Comprehensive docstrings

### Integration

- [ ] Can encode/decode packets successfully
- [ ] 3-byte msg_id generation implemented (Sequential strategy - Step 5.5)
- [ ] MITM codec validation plugin successfully decodes 100+ live packets
- [ ] MITM plugin detects and reports invalid checksums
- [ ] MITM plugin handles all packet types (0x23, 0x73, 0x83, 0xD3)
- [ ] Ready for Phase 1b (reliable transport) integration

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

@pytest.mark.parametrize("device_id,endpoint", [
    (123, bytes.fromhex("45 88 0f 3a 00")),
    (456, bytes.fromhex("32 5d 53 17 00")),
    (789, bytes.fromhex("38 e8 cf 46 00")),
])
def test_decode_handshake_parameterized(device_id, endpoint):
    """Test handshake decoding with various device IDs."""
    # Build handshake packet with parameterized endpoint
    auth_code = bytes.fromhex("31 65 30 37 64 38 63 65 30 61 36 31 37 61 33 37")
    packet = CyncProtocol.encode_handshake(endpoint, auth_code)

    decoded = CyncProtocol.decode_packet(packet)
    assert decoded.packet_type == 0x23
    assert decoded.endpoint == endpoint
```

### Integration Tests (with Phase 0.5 fixtures)

**Fixture Selection Guide**:

`tests/fixtures/real_packets.py` contains 13 validated packets organized by type:

- Handshake: `HANDSHAKE_0x23_DEV_TO_CLOUD`, `HELLO_ACK_0x28_CLOUD_TO_DEV`
- Toggle: `TOGGLE_ON_0x73_CLOUD_TO_DEV`, `TOGGLE_OFF_0x73_CLOUD_TO_DEV`, `DATA_ACK_0x7B_DEV_TO_CLOUD`
- Status: `STATUS_BROADCAST_0x83_DEV_TO_CLOUD`, `STATUS_ACK_0x88_CLOUD_TO_DEV`
- Heartbeat: `HEARTBEAT_DEV_0xD3_DEV_TO_CLOUD`, `HEARTBEAT_CLOUD_0xD8_CLOUD_TO_DEV`
- Device Info: `DEVICE_INFO_0x43_DEV_TO_CLOUD`, `INFO_ACK_0x48_CLOUD_TO_DEV`
- Checksum Validation: `DEVICE_INFO_0x43_FRAMED_1` through `STATUS_BROADCAST_0x83_FRAMED_11`

See file header (lines 1-26) for complete packet size distribution table.

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

### Integration Testing with MITM Plugin

**Manual validation against real traffic**:

1. Start MITM with codec validation:

   ```bash
   python mitm/main.py \
     --upstream-host homeassistant.local \
     --upstream-port 23779 \
     --enable-codec-validation
   ```

2. Trigger commands via Home Assistant UI:
   - Toggle lights on/off
   - Change brightness
   - Change colors
   - Various device types

3. Monitor logs for validation results:
   - All packets should decode successfully
   - Any decode failures indicate codec bugs

4. Compare with file captures for debugging:
   - MITM still writes to `mitm/captures/`
   - Cross-reference failed packets with hex dumps

#### Alternative: Automated Validation (CI-Friendly)

For automated testing without Home Assistant UI:

```bash
# Replay captured packets through MITM validation
python mitm/test-codec-validation.py \
  --replay mitm/captures/capture_20251107.txt \
  --enable-codec-validation
```

Replays real packet captures through codec validator, verifying 100% decode rate without manual intervention.

**Expected results**:

- 100% of HA-generated commands decode successfully
- 100% of device responses decode successfully
- All packet types (0x23, 0x28, 0x73, 0x7B, etc.) handled
- No checksum validation failures on real traffic

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

def test_framer_rejects_oversized_packet_with_metrics():
    """Test MAX_PACKET_SIZE validation AND metrics increment."""
    from metrics.registry import get_metrics_registry

    metrics = get_metrics_registry()
    initial_count = metrics.tcp_comm_framing_errors_total.labels(
        reason="packet_too_large"
    )._value.get()

    framer = PacketFramer()
    # Malicious packet: claims 5000 bytes (exceeds MAX_PACKET_SIZE=4096)
    malicious_header = bytes([0x73, 0x00, 0x00, 0x13, 0x88])
    packets = framer.feed(malicious_header)

    # Verify packet rejected
    assert packets == []
    assert len(framer.buffer) == 0

    # Verify metric incremented (Phase 1b implementation)
    final_count = metrics.tcp_comm_framing_errors_total.labels(
        reason="packet_too_large"
    )._value.get()
    assert final_count == initial_count + 1

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

**Runtime**:

- None (pure Python, stdlib only)

**Testing**:

- pytest >= 7.0
- pytest-asyncio >= 0.21
- pytest-cov >= 4.0

**Development**:

- ruff (linting)
- mypy (type checking)
- `types-prometheus-client` (type stubs for prometheus_client)

---

## Success Metrics

- All major packet types encodable/decodable
- 100% unit test pass rate
- Validated against Phase 0.5 captures
- Zero checksum mismatches
- Ready for Phase 1b integration

---

## Next Phase

**Phase 1b**: Reliable Transport Layer

- Use Phase 1a codec for packet encoding/decoding
- Add ACK/NACK handling
- Implement retry logic and idempotency

---

## Related Documentation

- **Phase 0.5**: `02a-phase-0.5-protocol-validation.md` - Protocol validation and captures
- **Phase 1 Program**: `02-phase-1-spec.md` - Overall architecture and context
- **Phase 1b**: `02c-phase-1b-reliable-transport.md` - Next phase (reliable transport)
- **Discovery**: `00-discovery.md` - Original protocol analysis
