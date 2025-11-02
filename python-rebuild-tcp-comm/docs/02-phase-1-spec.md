# Phase 1 Specification: Reliable Frame Layer + Device Integration

**Status**: Planning
**Effort**: Medium (~21 SP, 3-4 weeks)
**Dependencies**: Phase 0 complete ✓
**Team**: 2-3 Engineers

---

## Executive Summary

Phase 1 adds reliability primitives (ACK/NACK, idempotency, backpressure) and integrates with the real Cync protocol. This creates a production-ready transport layer that can replace the legacy TCP path while maintaining compatibility with existing device firmware.

---

## Goals

1. **Reliability**: Add ACK/NACK with retries and idempotency
2. **Protocol Integration**: Support real Cync packet format (0x73, 0x83, 0x43, etc.)
3. **Backpressure**: Implement bounded queues and flow control
4. **Testing**: Device simulator for integration and chaos tests
5. **Observability**: Enhanced metrics and correlation IDs

---

## Architecture

### 1. Reliable Transport Layer

**File**: `src/rebuild_tcp_comm/transport/reliable_layer.py`

```python
class ReliableTransport:
    """
    Reliable message delivery over TCP with ACK/NACK.

    Features:
    - Per-message correlation (msg_id)
    - Automatic retries with exponential backoff
    - Idempotency via LRU deduplication
    - Bounded send/receive queues
    - ACK/NACK frame handling
    """

    def __init__(
        self,
        connection: TCPConnection,
        max_send_queue: int = 100,
        max_recv_queue: int = 100,
        dedup_cache_size: int = 1000,
        dedup_ttl_seconds: int = 300,
    ):
        self.conn = connection
        self.send_queue = asyncio.Queue(maxsize=max_send_queue)
        self.recv_queue = asyncio.Queue(maxsize=max_recv_queue)
        self.pending_acks: Dict[str, PendingMessage] = {}
        self.dedup_cache = LRUCache(max_size=dedup_cache_size)

    async def send_reliable(
        self,
        payload: bytes,
        msg_id: Optional[str] = None,
        timeout: float = 5.0,
        max_retries: int = 3,
    ) -> bool:
        """Send message and wait for ACK."""

    async def recv_reliable(self) -> Optional[Message]:
        """Receive message, send ACK, deduplicate."""
```

**Key Classes**:

```python
@dataclass
class Message:
    msg_id: str  # UUID v7 for sortability
    payload: bytes
    timestamp: float
    retry_count: int = 0

@dataclass
class PendingMessage:
    message: Message
    ack_event: asyncio.Event
    sent_at: float
    timeout: float
```

### 2. Cync Protocol Integration

**File**: `src/rebuild_tcp_comm/protocol/cync_protocol.py`

Support for real Cync packet types:

```python
class CyncProtocol:
    """
    Cync protocol encoder/decoder.

    Packet types:
    - 0x23: Handshake (IDENTIFICATION KEY)
    - 0x43: Device info / broadcast status
    - 0x73: Control / response (our main transport)
    - 0x83: Status broadcast
    - 0xD3: Heartbeat (device ping)

    Frame structure (0x73):
    [0x73][0x00][0x00][multiplier][length][queue_id:5][msg_id:3][payload]
    """

    @staticmethod
    def encode_control_packet(
        msg_id: bytes,  # 3 bytes
        queue_id: bytes,  # 5 bytes
        payload: bytes,
        wrap_in_7e: bool = True,
    ) -> bytes:
        """Encode 0x73 control packet."""

    @staticmethod
    def decode_packet(data: bytes) -> Optional[ParsedPacket]:
        """Decode any Cync packet type."""

    @staticmethod
    def encode_ack(msg_id: bytes) -> bytes:
        """Encode ACK for received message."""
```

**ParsedPacket Structure**:

```python
@dataclass
class ParsedPacket:
    packet_type: int  # 0x23, 0x43, 0x73, 0x83, etc.
    msg_id: bytes  # 3 bytes from header
    queue_id: bytes  # 5 bytes from header
    payload: bytes
    length: int
    checksum_valid: bool
    timestamp: float
```

### 3. Idempotency & Deduplication

**File**: `src/rebuild_tcp_comm/transport/deduplication.py`

```python
class LRUCache:
    """
    LRU cache for deduplicating messages.

    Features:
    - Fixed size with LRU eviction
    - TTL-based expiry
    - Thread-safe operations
    """

    def __init__(self, max_size: int, ttl_seconds: int = 300):
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl_seconds
        self.lock = asyncio.Lock()

    async def contains(self, msg_id: str) -> bool:
        """Check if message was already processed."""

    async def add(self, msg_id: str, metadata: dict) -> None:
        """Add message to cache."""

    async def cleanup_expired(self) -> int:
        """Remove expired entries, return count removed."""

@dataclass
class CacheEntry:
    msg_id: str
    timestamp: float
    metadata: dict
    processed_at: float
```

### 4. Backpressure & Flow Control

**Bounded Queues**:
- Send queue: 100 messages (configurable)
- Receive queue: 100 messages (configurable)
- Drop oldest DEBUG logs under pressure

**Queue Policies**:

```python
class QueuePolicy(Enum):
    DROP_OLDEST = "drop_oldest"  # Drop oldest message when full
    BLOCK = "block"  # Block sender until space available
    REJECT = "reject"  # Return error immediately

class BoundedQueue:
    """Async queue with configurable overflow policy."""

    def __init__(
        self,
        maxsize: int,
        policy: QueuePolicy = QueuePolicy.BLOCK,
    ):
        self.queue = asyncio.Queue(maxsize=maxsize)
        self.policy = policy
        self.dropped_count = 0

    async def put(self, item: Any, timeout: float = None) -> bool:
        """Add item with overflow handling."""
```

### 5. Retry Logic

**Exponential Backoff**:

```python
class RetryPolicy:
    """Configurable retry policy with exponential backoff."""

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
        """Calculate delay for given attempt."""
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        jitter_amount = random.uniform(0, self.jitter)
        return delay + jitter_amount
```

---

## Device Simulator

**File**: `tests/simulator/cync_device_simulator.py`

```python
class CyncDeviceSimulator:
    """
    Mock Cync device for integration and chaos testing.

    Features:
    - Speaks real Cync protocol
    - Configurable latency/packet loss
    - Simulates firmware versions
    - Network chaos injection
    """

    def __init__(
        self,
        device_id: int,
        host: str = "127.0.0.1",
        port: int = 9000,
        latency_ms: float = 10.0,
        packet_loss_rate: float = 0.0,
        duplicate_rate: float = 0.0,
    ):
        self.device_id = device_id
        self.server: Optional[asyncio.Server] = None
        self.chaos_config = ChaosConfig(
            latency_ms=latency_ms,
            packet_loss_rate=packet_loss_rate,
            duplicate_rate=duplicate_rate,
        )

    async def start(self):
        """Start simulator server."""

    async def handle_connection(self, reader, writer):
        """Handle client connection."""

    async def send_packet(self, packet: bytes, apply_chaos: bool = True):
        """Send packet with optional chaos."""

    def set_state(self, state: DeviceState):
        """Update simulated device state."""

@dataclass
class ChaosConfig:
    """Network chaos configuration."""
    latency_ms: float = 0.0  # Additional latency
    latency_variance: float = 5.0  # Jitter
    packet_loss_rate: float = 0.0  # 0.0-1.0
    duplicate_rate: float = 0.0  # 0.0-1.0
    reorder_rate: float = 0.0  # 0.0-1.0
    corruption_rate: float = 0.0  # 0.0-1.0
```

**Chaos Testing**:

```python
class ChaosTestSuite:
    """Chaos engineering test suite."""

    async def test_high_latency(self):
        """Verify system handles 500ms+ latency."""

    async def test_packet_loss(self):
        """Verify retries work with 20% loss."""

    async def test_reordering(self):
        """Verify idempotency with reordered packets."""

    async def test_partition(self):
        """Verify reconnection after network partition."""

    async def test_duplicate_delivery(self):
        """Verify idempotency with duplicates."""
```

---

## Enhanced Metrics

**New Metrics** (add to existing):

```python
# Reliability metrics
tcp_comm_ack_received_total{device_id, outcome}
tcp_comm_ack_timeout_total{device_id}
tcp_comm_idempotent_drop_total{device_id}  # Duplicates dropped

# Queue metrics
tcp_comm_send_queue_size{device_id}
tcp_comm_recv_queue_size{device_id}
tcp_comm_queue_full_total{device_id, queue_type}

# Retry metrics
tcp_comm_retry_attempts_total{device_id, attempt_number}
tcp_comm_message_abandoned_total{device_id, reason}

# Dedup cache metrics
tcp_comm_dedup_cache_size
tcp_comm_dedup_cache_hits_total
tcp_comm_dedup_cache_evictions_total
```

---

## Integration Points

### 1. Replace Legacy TCP Path

**Current** (`cync_controller/devices/tcp_device.py`):
```python
async def write(self, data: bytes) -> bool:
    dev.writer.write(data)
    await asyncio.wait_for(dev.writer.drain(), timeout=2.0)
```

**New** (with reliable layer):
```python
async def write_reliable(self, data: bytes) -> bool:
    result = await self.reliable_transport.send_reliable(
        payload=data,
        timeout=5.0,
        max_retries=3,
    )
    return result.success
```

### 2. Control Message Callbacks

**Integrate** with existing `ControlMessageCallback`:
```python
# In structs.py
class ControlMessageCallback:
    # Add fields
    msg_id_uuid: str  # New UUID-based ID
    ack_received: bool = False
    nack_reason: Optional[str] = None
```

### 3. Packet Handler Integration

**Wrap** existing `TCPPacketHandler`:
```python
class ReliablePacketHandler:
    """Wrapper around TCPPacketHandler with reliability."""

    def __init__(self, tcp_device, reliable_transport):
        self.legacy_handler = TCPPacketHandler(tcp_device)
        self.reliable = reliable_transport

    async def handle_packet(self, packet: bytes):
        # Check for ACK/NACK first
        if self.is_ack_packet(packet):
            await self.handle_ack(packet)
        # Check for duplicate
        elif await self.is_duplicate(packet):
            await self.send_ack(packet)  # ACK again
            # Drop silently
        else:
            # New message - process and ACK
            await self.legacy_handler.parse_packet(packet)
            await self.send_ack(packet)
```

---

## Testing Strategy

### Unit Tests

```python
# test_reliable_transport.py
async def test_send_with_ack():
    """Verify message sent and ACK received."""

async def test_retry_on_timeout():
    """Verify retry after ACK timeout."""

async def test_max_retries_exceeded():
    """Verify failure after max retries."""

# test_deduplication.py
async def test_duplicate_detection():
    """Verify duplicate messages dropped."""

async def test_lru_eviction():
    """Verify LRU eviction when cache full."""

async def test_ttl_expiry():
    """Verify expired entries removed."""

# test_backpressure.py
async def test_queue_full_blocks():
    """Verify sender blocks when queue full."""

async def test_queue_full_drops():
    """Verify oldest dropped with DROP_OLDEST policy."""
```

### Integration Tests

```python
# test_simulator.py
async def test_end_to_end_toggle():
    """Toggle simulated device end-to-end."""

async def test_handshake_flow():
    """Complete Cync handshake with simulator."""

async def test_status_broadcast():
    """Receive 0x83 status from simulator."""
```

### Chaos Tests

```python
# test_chaos.py
@pytest.mark.chaos
async def test_20_percent_packet_loss():
    """Verify reliability with 20% loss."""

@pytest.mark.chaos
async def test_500ms_latency():
    """Verify system handles high latency."""

@pytest.mark.chaos
async def test_reordering():
    """Verify idempotency with reordered packets."""
```

---

## Acceptance Criteria

### Functional

- [x] Reliable send/receive with ACK/NACK
- [x] Automatic retries with exponential backoff (max 3)
- [x] Idempotency with LRU deduplication
- [x] Bounded queues with configurable overflow policy
- [x] Cync protocol support (0x73, 0x83, 0x43, etc.)
- [x] Device simulator with chaos injection

### Performance

- [x] p99 latency < 800ms (lab, no chaos)
- [x] Retransmit rate < 0.5% (lab, no chaos)
- [x] Zero duplicates processed (100% dedup)
- [x] Queue full events < 1% under load

### Testing

- [x] 30+ unit tests (reliability + dedup + queues)
- [x] 10+ integration tests (simulator)
- [x] 5+ chaos tests (loss, latency, reorder)
- [x] All tests pass with >90% coverage

### Quality

- [x] No ruff errors
- [x] No mypy errors (strict mode)
- [x] Enhanced metrics exposed
- [x] Documentation complete

---

## Migration Path

### Step 1: Add Reliability Layer (Non-Breaking)
- Implement `ReliableTransport` as wrapper
- No changes to existing code
- Enable via feature flag

### Step 2: Integrate with Legacy Handler
- Wrap `TCPPacketHandler`
- Add ACK/NACK handling
- Test with canary device

### Step 3: Enable for Subset
- Route 10% of traffic through new layer
- Monitor metrics and SLOs
- Expand or rollback based on results

---

## Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Cync protocol incompatibility | High | Medium | Device simulator + real device testing |
| Performance regression | Medium | Low | Benchmarks + SLO monitoring |
| Duplicate detection false negatives | High | Low | Comprehensive dedup tests |
| Queue exhaustion | Medium | Medium | Backpressure policies + metrics |
| ACK timeout tuning | Medium | Medium | Lab testing with latency injection |

---

## Timeline

**Week 1**: Reliable transport + dedup
**Week 2**: Cync protocol integration + simulator
**Week 3**: Integration testing + chaos tests
**Week 4**: Documentation + handoff

---

## Dependencies

**Internal**:
- Phase 0 complete ✓
- Access to real Cync devices for testing

**External**:
- None

---

## Success Metrics

- Chaos suite passes (5/5 tests)
- p99 latency < 800ms
- Retransmit rate < 0.5%
- Zero duplicate processing
- Zero data corruption

---

## Next Phase

Phase 2: Canary deployment with SLO monitoring (see `03-phase-2-spec.md`)

