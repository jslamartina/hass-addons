# Phase 1d: Device Simulator & Chaos Testing

**Status**: Planning
**Dependencies**: Phases 1a-1c complete (full stack working)
**Execution**: Sequential solo implementation

---

## Overview

Phase 1d builds a realistic Cync device simulator that speaks the real protocol and supports chaos engineering patterns (packet loss, latency, reordering, duplicates). This enables comprehensive integration and chaos testing without requiring physical devices.

**See Also**: `02-phase-1-spec.md` for architecture context.

---

## Goals

1. Build device simulator that speaks real Cync protocol
2. Support configurable chaos: latency, packet loss, reordering, duplicates, corruption
3. Create 10+ integration tests with simulator
4. Create 5+ chaos tests validating reliability under adverse conditions
5. Validate performance targets (p99 < 800ms) under various network conditions

---

## Deliverables

### Code
- [ ] `tests/simulator/cync_device_simulator.py` - Main simulator (~300-350 lines)
- [ ] `tests/simulator/chaos_config.py` - Chaos configuration (~80-100 lines)
- [ ] `tests/integration/test_simulator.py` - Integration tests (10+ tests)
- [ ] `tests/integration/test_chaos.py` - Deterministic chaos tests (4+ tests)
- [ ] `tests/integration/test_chaos_probabilistic.py` - Probabilistic chaos tests (1+ tests, nightly-only) - **Technical Review Finding 5.3**

### Features
- [ ] Simulator speaks real Cync protocol (uses Phase 1a codec)
- [ ] Responds to: handshake (0x23), data (0x73), heartbeat (0xD3)
- [ ] Sends: ACKs, status broadcasts, heartbeats
- [ ] Configurable device state (on/off, brightness, etc.)
- [ ] Network chaos injection: latency, loss, reordering, duplicates, corruption

### Testing
- [ ] 10+ integration tests (full protocol flows)
- [ ] 5+ chaos tests (reliability under adverse conditions)
- [ ] Performance validation (p99 < 800ms baseline, < 1500ms with chaos)

---

## Architecture

### CyncDeviceSimulator

```python
class CyncDeviceSimulator:
    """Mock Cync device for integration and chaos testing.

    Supports packet reordering through delay-based chaos injection (no buffering).
    Simplified algorithm eliminates race conditions and background task complexity.
    """

    def __init__(
        self,
        device_id: int,
        host: str = "127.0.0.1",
        port: int = 9000,  # Configurable via CLI or env var
        firmware_version: str = "1.2.3",
        chaos_config: Optional[ChaosConfig] = None,
    ):
        """Initialize device simulator.

        Args:
            device_id: Unique device identifier
            host: Bind address (default: localhost)
            port: TCP port (default: 9000, configurable for parallel tests)
                 Use port=0 for automatic allocation (pytest-xdist safe)
            firmware_version: Simulated firmware version
            chaos_config: Network chaos configuration (optional)

        Environment Variables:
            CYNC_SIM_PORT: Override default port (useful for parallel test execution)

        Parallel Test Support:
            Use find_free_port() helper to allocate unique ports per test.
            See tests/simulator/port_allocator.py for implementation.
        """
        self.device_id = device_id
        self.host = host
        self.port = port
        self.firmware_version = firmware_version
        self.chaos = chaos_config or ChaosConfig()
        self.state = DeviceState()
        self.server: Optional[asyncio.Server] = None
        self.protocol = CyncProtocol()  # From Phase 1a

    async def start(self):
        """Start simulator TCP server."""
        self.server = await asyncio.start_server(
            self.handle_connection,
            self.host,
            self.port,
        )

    async def stop(self):
        """Stop simulator server."""
        self.server.close()
        await self.server.wait_closed()

    async def handle_connection(self, reader, writer):
        """Handle client connection."""
        while True:
            # Read packet
            data = await reader.read(4096)
            if not data:
                break

            # Apply chaos (maybe drop, delay, corrupt)
            if self.chaos.should_drop_packet():
                continue

            if self.chaos.latency_ms > 0:
                await asyncio.sleep(self.chaos.get_latency())

            # Decode packet
            packet = self.protocol.decode_packet(data)

            # Handle packet type
            if packet.packet_type == 0x23:  # Handshake
                response = self.handle_handshake(packet)
            elif packet.packet_type == 0x73:  # Data channel
                response = self.handle_data(packet)
            elif packet.packet_type == 0xD3:  # Heartbeat
                response = self.handle_heartbeat(packet)
            else:
                response = None

            if response:
                # Send with chaos injection (simplified delay-based reordering)
                await self._send_with_chaos(response, writer)

                # Maybe duplicate
                if self.chaos.should_duplicate():
                    await self._send_with_chaos(response, writer)

    async def _send_with_chaos(self, packet: bytes, writer: asyncio.StreamWriter):
        """Send packet with chaos injection (delay-based reordering).

        Simplified reordering: adds random delay instead of buffering.
        This eliminates race conditions and background task complexity.
        """
        # Apply reordering delay if enabled
        if random.random() < self.chaos.reorder_rate:
            # Delay this packet to simulate out-of-order delivery
            delay_seconds = self.chaos.reorder_delay_ms / 1000.0
            await asyncio.sleep(delay_seconds)

        # Send packet
        try:
            writer.write(packet)
            await writer.drain()
        except Exception as e:
            # Connection closed or other error - ignore
            pass

    def handle_handshake(self, packet: CyncPacket) -> bytes:
        """Respond to 0x23 handshake."""
        # Send 0x28 HELLO_ACK
        return self.protocol.encode_hello_ack()

    def handle_data(self, packet: CyncDataPacket) -> bytes:
        """Handle 0x73 data packet (toggle, etc.)."""
        # Parse command
        # Update state
        self.state.on = not self.state.on
        # Send 0x7B DATA_ACK
        return self.protocol.encode_data_ack(packet.msg_id)

    def handle_heartbeat(self, packet: CyncPacket) -> bytes:
        """Respond to 0xD3 heartbeat."""
        # Send 0xD8 HEARTBEAT_ACK
        return self.protocol.encode_heartbeat_ack()
```

### ChaosConfig

```python
from dataclasses import dataclass, field

@dataclass
class ChaosConfig:
    """Network chaos configuration."""

    # Latency
    latency_ms: float = 0.0           # Base added latency
    latency_variance: float = 5.0     # Jitter (± variance)

    # Packet loss (probabilistic)
    packet_loss_rate: float = 0.0     # 0.0-1.0 (0% to 100%)

    # Packet loss (deterministic) - takes precedence if set
    drop_pattern: Optional[List[int]] = None  # Packet numbers to drop [1, 6, 11, ...]

    # Duplication
    duplicate_rate: float = 0.0       # 0.0-1.0

    # Reordering
    reorder_rate: float = 0.0         # 0.0-1.0
    reorder_delay_ms: float = 50.0    # Delay for reordered packets
    reorder_buffer_size: int = 10     # Max packets to buffer for reordering

    # Corruption
    corruption_rate: float = 0.0      # 0.0-1.0
    corruption_bytes: int = 1         # How many bytes to corrupt

    # Internal counter for deterministic dropping (not part of public API)
    _packet_counter: int = field(default=0, init=False, repr=False)

    def should_drop_packet(self) -> bool:
        """
        Decide whether to drop packet.

        Uses deterministic pattern if set, otherwise probabilistic rate.
        Deterministic pattern enables non-flaky chaos tests.
        """
        self._packet_counter += 1

        # Deterministic: check if current packet number in drop pattern
        if self.drop_pattern is not None:
            return self._packet_counter in self.drop_pattern

        # Probabilistic: random drop based on rate
        return random.random() < self.packet_loss_rate

    def should_duplicate(self) -> bool:
        """Random decision to duplicate packet."""
        return random.random() < self.duplicate_rate

    def get_latency(self) -> float:
        """Calculate latency with variance."""
        base = self.latency_ms / 1000.0  # Convert to seconds
        variance = random.uniform(-self.latency_variance, self.latency_variance) / 1000.0
        return max(0, base + variance)
```

### DeviceState

```python
@dataclass
class DeviceState:
    """Simulated device state."""
    on: bool = False
    brightness: int = 100
    color_temp: int = 3000
    rgb: tuple[int, int, int] = (255, 255, 255)
    online: bool = True
    toggle_count: int = 0  # For idempotency testing
```

---

## Implementation Plan

### Step 1: Basic Simulator
- Implement `CyncDeviceSimulator` class
- TCP server setup
- Handle handshake and data packets
- Implement port allocator (fcntl-based locking for parallel test support)
- Unit tests for simulator

### Step 2: Chaos Injection
- Implement `ChaosConfig` class
- Add latency, packet loss, duplication
- Configurable chaos parameters
- Unit tests for chaos behaviors

### Step 3: Integration Tests
- 10+ integration tests with simulator
- Test full protocol flows (handshake, toggle, heartbeat)
- Test reliability layer against simulator
- Performance measurement

### Step 4: Chaos Tests
- 5+ chaos tests with various network conditions
- Validate retries under packet loss
- Validate idempotency under duplication
- Validate performance under latency
- **Chaos Test Execution Strategy (Technical Review Finding 5.3 - Enhanced)**:
  - Deterministic tests (e.g., drop every 5th packet): Run in CI (every commit) - no flakiness
    - File: `tests/integration/test_chaos.py`
  - Probabilistic tests (e.g., 10% random drop): Separate file, nightly builds only
    - File: `tests/integration/test_chaos_probabilistic.py`
    - Marked: `@pytest.mark.chaos_probabilistic`
    - CI config: **Explicitly exclude** this file from CI runs (prevent accidental execution)
  - Rationale: Probabilistic tests have 1% false positive rate even with large samples - unsuitable for CI

**CI Configuration** (required to prevent flaky builds):
```yaml
# .github/workflows/ci.yml or pytest.ini
[tool:pytest]
addopts = --ignore=tests/integration/test_chaos_probabilistic.py  # Exclude from default runs

# Nightly build config
[tool:pytest:nightly]
addopts = tests/integration/test_chaos_probabilistic.py  # Run only probabilistic tests
```
- Performance validation report

---

## Integration Tests (10+ Tests)

```python
# test_simulator.py

async def test_handshake_flow():
    """Complete handshake with simulator."""
    simulator = CyncDeviceSimulator(device_id=123)
    await simulator.start()

    # Client connects and sends 0x23
    transport = ReliableTransport(...)
    success = await transport.handshake()
    assert success is True

    await simulator.stop()

async def test_toggle_light():
    """Toggle light on/off via simulator."""
    simulator = CyncDeviceSimulator(device_id=123)
    await simulator.start()

    transport = ReliableTransport(...)
    result = await transport.send_toggle_command(device_id=123, state=True)
    assert result.success is True
    assert simulator.state.on is True

    await simulator.stop()

async def test_status_broadcast():
    """Receive status broadcast from simulator."""
    simulator = CyncDeviceSimulator(device_id=123)
    await simulator.start()

    # Trigger state change
    simulator.state.on = True
    await simulator.send_status_broadcast()

    # Client receives 0x83
    transport = ReliableTransport(...)
    packet = await transport.recv_reliable()
    assert packet.packet_type == 0x83

    await simulator.stop()

async def test_heartbeat_keepalive():
    """Exchange heartbeats with simulator."""
    simulator = CyncDeviceSimulator(device_id=123)
    await simulator.start()

    transport = ReliableTransport(...)
    result = await transport.send_heartbeat()
    assert result.success is True

    await simulator.stop()

async def test_invalid_packet_handling():
    """Test codec handles malformed packets gracefully."""
    simulator = CyncDeviceSimulator(device_id=123)
    await simulator.start()

    transport = ReliableTransport(...)

    # Send packet with invalid checksum
    malformed_packet = b'\x73\x00\x00\x00\x10\x7e\x01\x02\x03\xFF\x7e'  # Wrong checksum
    await transport.conn.send(malformed_packet)

    # Should raise PacketDecodeError
    with pytest.raises(PacketDecodeError, match="invalid_checksum"):
        await transport.recv_reliable()

    await simulator.stop()

async def test_malformed_handshake():
    """Test handshake failure with invalid response."""
    simulator = CyncDeviceSimulator(device_id=123)
    # Configure simulator to send invalid handshake response
    simulator.send_invalid_handshake = True
    await simulator.start()

    transport = ReliableTransport(...)

    # Should retry and eventually fail
    with pytest.raises(HandshakeError, match="invalid response"):
        await transport.connect()

    await simulator.stop()

async def test_connection_during_reconnection():
    """Test handling of commands during reconnection."""
    simulator = CyncDeviceSimulator(device_id=123)
    await simulator.start()

    transport = ReliableTransport(...)
    await transport.connect()

    # Simulate connection loss
    await simulator.stop()

    # Trigger reconnection
    asyncio.create_task(transport.conn_mgr.reconnect("test"))
    await asyncio.sleep(0.1)  # Let reconnection start

    # Try to send during reconnection
    result = await transport.send_toggle_command(device_id=123, state=True)

    # Should fail gracefully with reason "not_connected"
    assert result.success is False
    assert "not_connected" in result.reason or "reconnecting" in result.reason

async def test_checksum_mismatch():
    """Test packet with checksum mismatch is rejected."""
    simulator = CyncDeviceSimulator(device_id=123)
    await simulator.start()

    transport = ReliableTransport(...)

    # Create packet with intentionally wrong checksum
    framer = PacketFramer()
    packets = framer.feed(b'\x73\x00\x00\x00\x0c\x7e\x01\x02\x03\x04\x05\x99\x7e')  # 0x99 is wrong

    # Decode should raise PacketDecodeError
    with pytest.raises(PacketDecodeError, match="invalid_checksum"):
        protocol.decode_packet(packets[0])

    await simulator.stop()

async def test_command_timeout():
    """Test command timeout handling."""
    # Simulator with high packet loss (100% - all ACKs dropped)
    chaos = ChaosConfig(packet_loss_rate=1.0)
    simulator = CyncDeviceSimulator(device_id=123, chaos_config=chaos)
    await simulator.start()

    transport = ReliableTransport(..., max_retries=2, ack_timeout_seconds=1)

    # Send command - should timeout and fail after retries
    result = await transport.send_toggle_command(device_id=123, state=True)

    assert result.success is False
    assert result.retry_count == 2  # All retries exhausted

    await simulator.stop()
```

---

## Chaos Tests (5+ Tests)

```python
# test_chaos.py

@pytest.mark.chaos
async def test_deterministic_packet_loss():
    """Verify reliability with deterministic 20% loss.

    Technical Review Finding 3.7 - Sample size rationale:
    Uses 100 messages (smaller than probabilistic 5000) because deterministic
    drop pattern (every 5th packet) has zero variance - no flakiness regardless
    of sample size. Deterministic tests validate retry logic correctness, not
    statistical confidence.
    """
    # Drop every 5th packet (1, 6, 11, 16, 21, ...) for deterministic testing
    chaos = ChaosConfig(drop_pattern=[i for i in range(1, 101) if i % 5 == 1])
    simulator = CyncDeviceSimulator(device_id=123, chaos_config=chaos)
    await simulator.start()

    transport = ReliableTransport(..., max_retries=5)

    # Send 100 commands - 20 will be dropped on first attempt
    success_count = 0
    for i in range(100):
        result = await transport.send_toggle_command(device_id=123, state=True)
        if result.success:
            success_count += 1

    # All should eventually succeed via retries (deterministic, no flakiness)
    assert success_count == 100

    await simulator.stop()

@pytest.mark.chaos
@pytest.mark.chaos_probabilistic  # Run in nightly builds only (not CI) - 1% false positive rate
async def test_high_volume_probabilistic():
    """Verify reliability with probabilistic loss over large sample.

    Uses statistical confidence interval to avoid flaky test failures from
    random variance while still catching real reliability issues.

    **NOTE**: Marked as probabilistic chaos test - run in nightly builds only.
    Even with 5000 samples and 99% confidence, has 1% false positive rate.
    Not suitable for CI (use deterministic tests instead).
    """
    # Increased sample size from 1000 to 5000 to reduce flakiness
    chaos = ChaosConfig(packet_loss_rate=0.1)  # 10% random
    simulator = CyncDeviceSimulator(device_id=123, chaos_config=chaos)
    await simulator.start()

    transport = ReliableTransport(..., max_retries=5)

    # Send 5000 commands (larger sample reduces variance significantly)
    success_count = 0
    for i in range(5000):
        result = await transport.send_toggle_command(device_id=123, state=True)
        if result.success:
            success_count += 1

    # Use statistical confidence interval instead of fixed threshold
    # Expected success rate: 99% with retries (p=0.99, n=5000)
    # Calculate 99% confidence interval lower bound using binomial distribution
    # This accounts for statistical variance and reduces false positive test failures
    import scipy.stats as stats
    expected_success_rate = 0.99
    sample_size = 5000
    confidence_level = 0.01  # 99% confidence (1% false positive rate)

    # Calculate lower bound of confidence interval
    lower_bound = stats.binom.ppf(confidence_level, sample_size, expected_success_rate)
    # Example: lower_bound ≈ 4935 (accounts for statistical variance)

    assert success_count >= lower_bound, \
        f"Success rate below {100*(1-confidence_level)}% confidence interval: {success_count}/{sample_size} (expected ≥{lower_bound})"

    await simulator.stop()

@pytest.mark.chaos
async def test_500ms_latency():
    """Verify system handles high latency."""
    chaos = ChaosConfig(latency_ms=500.0, latency_variance=50.0)
    simulator = CyncDeviceSimulator(device_id=123, chaos_config=chaos)
    await simulator.start()

    transport = ReliableTransport(..., timeout=2.0)

    start = time.time()
    result = await transport.send_toggle_command(device_id=123, state=True)
    elapsed = time.time() - start

    assert result.success is True
    assert elapsed > 0.5  # Should take at least 500ms
    assert elapsed < 1.5  # But not timeout

    await simulator.stop()

@pytest.mark.chaos
async def test_duplicate_delivery():
    """Verify idempotency with duplicate packets."""
    chaos = ChaosConfig(duplicate_rate=0.5)
    simulator = CyncDeviceSimulator(device_id=123, chaos_config=chaos)
    await simulator.start()

    transport = ReliableTransport(...)

    # Send command (will be duplicated by chaos)
    result = await transport.send_toggle_command(device_id=123, state=True)
    assert result.success is True

    # Verify device state changed only once (idempotent)
    assert simulator.state.toggle_count == 1  # Not 2

    await simulator.stop()

@pytest.mark.chaos
async def test_reordering():
    """Verify correct handling of reordered packets."""
    chaos = ChaosConfig(reorder_rate=0.3, reorder_delay_ms=100.0)
    simulator = CyncDeviceSimulator(device_id=123, chaos_config=chaos)
    await simulator.start()

    transport = ReliableTransport(...)

    # Send 10 commands rapidly
    results = []
    for i in range(10):
        result = await transport.send_toggle_command(device_id=123, state=True)
        results.append(result)

    # All should succeed eventually
    assert all(r.success for r in results)

    await simulator.stop()

@pytest.mark.chaos
async def test_network_partition():
    """Verify reconnection after network partition."""
    simulator = CyncDeviceSimulator(device_id=123)
    await simulator.start()

    transport = ReliableTransport(..., max_retries=10)

    # Send successful command
    result = await transport.send_toggle_command(device_id=123, state=True)
    assert result.success is True

    # Simulate partition (stop simulator)
    await simulator.stop()

    # Commands should fail during partition
    result = await transport.send_toggle_command(device_id=123, state=False)
    assert result.success is False

    # Restart simulator (partition healed)
    await simulator.start()

    # Commands should succeed after healing
    result = await transport.send_toggle_command(device_id=123, state=True)
    assert result.success is True

    await simulator.stop()
```

---

## Performance Validation

### Baseline Performance Targets (No Chaos)

**Architectural Decision**: Balanced performance hierarchy (Option C from performance target review)

**Targets based on smart home UX requirements:**
- User perceives < 200ms as "instant"
- User accepts < 1s for commands
- Anything > 2s feels "broken"

| Metric | Aspirational Target | Adjusted Target (If Phase 0.5 Differs) | Validation Target | Phase 1 Measured |
|--------|---------------------|----------------------------------------|-------------------|------------------|
| p50 latency | < 100ms | < (measured_p50 + 20ms) | Use adjusted | TBD |
| p95 latency | < 300ms | < (measured_p95 + 50ms) | Use adjusted | TBD |
| p99 latency | < 800ms | < (measured_p99 + 100ms) | Use adjusted | TBD |
| Success rate | > 99.9% | > 99.9% (non-negotiable) | Same for both | TBD |

**Updated from original**: p95 target reduced from 500ms to 300ms, p99 target reduced from 1000ms to 800ms based on balanced hierarchy decision.

**Target Interpretation (Technical Review Finding 2.5 - Simplified to Two Tiers)**:

**Two-Tier Target System** (approved simplification):
- **Aspirational Targets**: Design goals based on UX research (p50 < 100ms, p95 < 300ms, p99 < 800ms)
  - Purpose: Guide optimization efforts
  - Status: Documentation only (not validation criteria)
- **Adjusted Targets**: Reality-based validation criteria from Phase 0.5 measurements
  - Purpose: Phase 1d validation pass/fail criteria
  - Formula: `adjusted_target = measured_p99 + margin`
  - **This is what we validate against**

**Example Adjustment**:
- Phase 0.5 measures p99 ACK latency = 1200ms (instead of assumed 800ms)
- **Aspirational target** = 800ms (unchanged - design goal)
- **Adjusted target** = 1200ms + 100ms = 1300ms
- **Phase 1d validation**: p99 latency < 1300ms ✅ (validates against adjusted, not aspirational)
- Document: "Aspirational goal: < 800ms | Validation target: < 1300ms (based on measured baseline)"

**Why This Matters**: Aspirational targets may be unachievable if network latency is higher than assumptions. Adjusted targets ensure validation criteria are realistic and based on empirical measurements from Phase 0.5.

**Acceptance Criteria Clarification**: Phase 1d acceptance criteria use **adjusted targets**, not aspirational targets.

**Measurement Method:**
- Run Phase 1d simulator with no chaos
- Send 1000 toggle commands
- Measure end-to-end latency (send → ACK received)
- Calculate percentiles using standard distribution

**ACK Latency Measurement**:

Phase 1d baseline tests measure ACK latency to validate timeout configuration (supplements Phase 0.5 Tier 2 measurements):

1. **Measure ACK latency for all 4 ACK types**:
   - 0x28 (handshake ACK): Send 100+ handshakes, measure time from 0x23 sent to 0x28 received
   - 0x7B (data ACK): Send 100+ data commands, measure time from 0x73 sent to 0x7B received
   - 0x88 (status ACK): Trigger 100+ status broadcasts, measure time from 0x83 sent to 0x88 received
   - 0xD8 (heartbeat ACK): Send 100+ heartbeats, measure time from 0xD3 sent to 0xD8 received

2. **Calculate percentiles** (p50, p95, p99, max) for each ACK type

3. **Validate timeout configuration**:
   - Current ACK timeout: 2s (based on assumption of p99 = 800ms)
   - If measured p99 > 800ms: Consider adjusting ACK timeout using formula: `timeout = p99 × 2.5`
   - Example: If measured p99 = 1200ms, recommended timeout = 1200ms × 2.5 = 3000ms (3s)
   - Document findings in `docs/decisions/phase-1d-ack-latency-validation.md`

4. **Decision criteria**:
   - If measured p99 ≤ 800ms: Current 2s timeout validated, no changes needed
   - If measured p99 > 800ms AND < 1600ms: Timeout may be too aggressive, consider adjustment
   - If measured p99 > 1600ms: Timeout too low, adjust and re-test

**Group Operation Validation**:

Phase 1d baseline tests validate the "no send_queue" architectural decision (authoritative validation):

1. **Test Setup**:
   - Create 10 simulated devices (or use real devices if available)
   - Prepare group command: Turn on all 10 devices simultaneously

2. **Measurements Required**:
   - **p50/p95/p99 latency** for 10-device parallel bulk operation
   - **Success rate** for group operations
   - **State lock hold time** during group operations (expected: <1ms per device)
   - **Device internal queue depth** (if devices buffer commands)
   - **Retry rate** and **timeout rate** for group operations
   - Execution method: `results = await asyncio.gather([device.transport.send_reliable(cmd) for device in devices])`
   - Timing: Measure total time from first send_reliable() call to last ACK received

3. **Purpose**: These measurements validate Phase 1c "no send_queue" architectural decision

4. **Re-evaluation Criteria**:
   - **If p99 < 2s**: No send_queue decision validated, proceed as specified
   - **If p99 ≥ 2s**: Document findings, proceed without send_queue (optimization deferred to Phase 2)

5. **Diagnostic Measurements** (if p99 ≥ 2s):
   - Measure state lock hold time during group operations
   - Check for lock contention (time spent waiting for lock)
   - Profile: Is delay from lock contention, network I/O, or device processing?
   - Document: Bottleneck analysis

6. **Acceptable Outcome**:
   - Phase 1 proceeds without send_queue regardless of findings
   - If p99 ≥ 2s, document need for send_queue in Phase 2 backlog
   - Phase 1 focuses on single-device reliability; group optimization deferred to Phase 2

**Note**: No baseline comparison against Phase 0 performance - Phase 0 used custom test protocol (0xF00D test framing) that is not directly comparable to real Cync protocol performance. Phase 1 is first implementation of real protocol.

### With Chaos (20% loss, 100ms latency)

| Metric | Target | Measurement |
|--------|--------|-------------|
| p99 latency | < 1500ms | TBD |
| Success rate | > 99% | TBD |
| Retransmit rate | < 5% | TBD |

**Chaos targets unchanged**: p99 < 1500ms with chaos is acceptable (allows for retry overhead).

---

## Acceptance Criteria

### Functional
- [ ] Simulator speaks real Cync protocol
- [ ] Handles handshake, data, heartbeat packets
- [ ] Configurable chaos parameters
- [ ] Device state updates correctly

### Testing
- [ ] 10+ integration tests pass
- [ ] 5+ chaos tests pass (deterministic + high-volume probabilistic)
- [ ] 100% test pass rate
- [ ] 90% code coverage
- [ ] No flaky tests

### Performance
- [ ] p99 latency < 800ms (no chaos) - or adjusted target from Phase 0.5
- [ ] p99 latency < 1500ms (with chaos)
- [ ] Success rate > 99.9% (no chaos)
- [ ] Success rate > 99% (20% packet loss)

### Memory Leak Detection (Technical Review Finding 5.4 - Added)
- [ ] Memory leak test executed for 9 hours minimum
- [ ] Memory growth < 5% over 8-hour window (after 1-hour warmup)
- [ ] No unbounded cache/dict growth observed
- [ ] Measurement method:
  - **Tool**: Python `tracemalloc` module
  - **Baseline**: Measure memory after 1 hour steady-state (warmup complete)
  - **Test**: Send 100 messages/minute for next 8 hours
  - **Measurement**: Track `tracemalloc.get_traced_memory()` every 15 minutes
  - **Acceptance**: Memory growth < 5% from baseline to end
  - **Failure**: Growth >= 5% indicates leak → investigate with `tracemalloc.take_snapshot()`
- [ ] Test implementation in `tests/integration/test_memory_leak.py`:
  ```python
  import tracemalloc

  async def test_no_memory_leak_9_hour():
      """Verify no memory leak over 9-hour operation."""
      tracemalloc.start()

      # Warmup: 1 hour
      await run_steady_traffic(duration_seconds=3600, rate_per_min=100)
      baseline_memory = tracemalloc.get_traced_memory()[0]

      # Monitoring: 8 hours
      measurements = []
      for hour in range(8):
          await run_steady_traffic(duration_seconds=3600, rate_per_min=100)
          current_memory = tracemalloc.get_traced_memory()[0]
          growth_pct = ((current_memory - baseline_memory) / baseline_memory) * 100
          measurements.append(growth_pct)
          logger.info("Hour %d: Memory growth = %.2f%%", hour + 1, growth_pct)

      # Final growth check
      final_growth = measurements[-1]
      assert final_growth < 5.0, f"Memory leak detected: {final_growth:.2f}% growth"

      tracemalloc.stop()
  ```

### Quality
- [ ] No ruff errors
- [ ] No mypy errors (strict mode)
- [ ] Full type annotations
- [ ] Documented chaos patterns

---

## Chaos Test Matrix

| Test | Packet Loss | Latency | Duplicates | Reorder | Expected Outcome |
|------|-------------|---------|------------|---------|------------------|
| Baseline | 0% | 0ms | 0% | 0% | p99 < 800ms, 100% success |
| Mild Loss | 5% | 0ms | 0% | 0% | p99 < 900ms, > 99.5% success |
| High Loss | 20% | 0ms | 0% | 0% | p99 < 1200ms, > 99% success |
| High Latency | 0% | 500ms | 0% | 0% | p99 < 1500ms, 100% success |
| Duplicates | 0% | 0ms | 50% | 0% | Idempotency, 100% success |
| Reordering | 0% | 0ms | 0% | 30% | Correct order, 100% success |
| Combined | 10% | 100ms | 10% | 10% | p99 < 1500ms, > 98% success, 1000+ msg sample |

**Note**: Combined test is the most realistic chaos scenario - validates production readiness under multiple concurrent failure modes.

---

## Parallel Test Support: Port Allocation Helper

**Problem**: Running tests in parallel (pytest-xdist) causes port collisions if all simulators use port 9000.

**Solution**: File-based locking during port allocation to prevent race conditions.

**Implementation**:

```python
# tests/simulator/port_allocator.py

import socket
import fcntl
from contextlib import closing

def find_free_port(start: int = 9000, end: int = 9100) -> int:
    """Find available port in range using file-based locking.

    Uses fcntl.flock() for exclusive locking during port probing to prevent
    race conditions in parallel test execution (pytest-xdist).

    Works for all test execution modes: serial, parallel, pytest-xdist.

    Handles port exhaustion by expanding search range if initial range full.

    Args:
        start: Start of port range (default: 9000)
        end: End of port range (default: 9100)

    Returns:
        Available port number

    Raises:
        RuntimeError: If no free ports in range after 3 attempts
    """
    lock_file = "/tmp/pytest_port_allocation.lock"

    # Try up to 3 range expansions (9000-9100, 9100-9200, 9200-9300)
    for attempt in range(3):
        range_start = start + (attempt * 100)
        range_end = end + (attempt * 100)

        # Acquire exclusive lock during port probing
        with open(lock_file, "w") as lock_fd:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)  # Block until lock acquired

                # Probe port range while holding exclusive lock
                for port in range(range_start, range_end):
                    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                        try:
                            sock.bind(('127.0.0.1', port))
                            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                            return port
                        except OSError:
                            continue  # Port in use, try next
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)  # Release lock

    # All ranges exhausted (Technical Review Finding 4.3 - Troubleshooting added)
    raise RuntimeError(
        f"Port exhaustion - no free ports in ranges {start}-{end + 200}. "
        f"Troubleshooting: (1) Kill stale processes: 'pkill -f cync_device_simulator', "
        f"(2) Use port=0 for OS-assigned ports, (3) Check 'netstat -tuln | grep 90' for port usage"
    )
```

**Usage in Tests**:

```python
# tests/integration/test_simulator.py

import pytest
from tests.simulator.port_allocator import find_free_port
from tests.simulator.cync_device_simulator import CyncDeviceSimulator

@pytest.fixture
def simulator_port():
    """Allocate unique port per test for parallel execution.

    Uses file-based locking to prevent port collisions across parallel test workers.
    """
    return find_free_port()

@pytest.fixture
async def simulator(simulator_port):
    """Create simulator with unique port."""
    sim = CyncDeviceSimulator(device_id=123, port=simulator_port)
    await sim.start()
    yield sim
    await sim.stop()

async def test_handshake_flow(simulator, simulator_port):
    """Test handshake with dynamically allocated port."""
    transport = ReliableTransport(...)

    # Connect to simulator on allocated port
    await transport.connect(host="localhost", port=simulator_port)

    success = await transport.handshake()
    assert success is True
```

**Test Execution Strategy (Technical Review Finding 4.4 - Added)**

**Which tests run in parallel vs serial:**

| Test Category | Execution Mode | Rationale | Example Command |
|---------------|----------------|-----------|-----------------|
| **Unit tests** | Always parallel | Isolated, no shared state | `pytest -n auto tests/unit/` |
| **Integration tests** | Parallel with port allocation | File-based locking prevents port collisions | `pytest -n 4 tests/integration/test_simulator.py` |
| **Chaos tests (deterministic)** | Parallel | Zero flakiness (deterministic drop patterns) | `pytest -n 4 -m "chaos and not chaos_probabilistic"` |
| **Chaos tests (probabilistic)** | Serial OR nightly-only | 1% false positive rate (statistical variance) | `pytest -m chaos_probabilistic` (nightly builds only) |
| **Load tests** | Serial | Measures system capacity (parallel would interfere) | `pytest tests/integration/test_performance.py` |
| **Memory leak tests** | Serial | Long-running (9 hours), measures growth | `pytest tests/integration/test_memory_leak.py` |

**Parallel Test Execution**:

```bash
# Run tests in parallel (4 workers) - excludes probabilistic chaos
pytest -n 4 tests/integration/ -m "not chaos_probabilistic"

# Each worker allocates unique ports via file-based locking
# Worker 1 gets first available port (e.g., 9000)
# Worker 2 gets next available port (e.g., 9001)
# Worker 3 gets next available port (e.g., 9002)
# Worker 4 gets next available port (e.g., 9003)

# Run probabilistic chaos tests separately (nightly builds only, serial execution)
pytest tests/integration/test_chaos_probabilistic.py -m chaos_probabilistic
```

**Race Condition Prevention**:

**File-Based Locking**:
- Uses `fcntl.flock()` for exclusive lock during port probing
- Lock file: `/tmp/pytest_port_allocation.lock`
- Blocks concurrent port probes until lock released
- **Works for all test execution modes** (serial, parallel, pytest-xdist)
- No worker count limitations (supports any number of workers)

**Benefits**:
- ✅ No port collisions in parallel tests (race-free)
- ✅ Works with pytest-xdist out of the box
- ✅ No manual port management needed
- ✅ Faster test execution (parallel > sequential)
- ✅ Simple single-method implementation (~40 lines vs ~80 lines for dual-method)
- ✅ No worker count limitations

---

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Simulator doesn't match real devices | High | Validate against Phase 0.5 captures; test with real device |
| Chaos tests too slow | Low | Run in parallel; mark with `@pytest.mark.chaos` for selective execution |
| Performance targets not met | Medium | Profile code; optimize hot paths; adjust targets if unrealistic |

---

## Dependencies

**Prerequisites**:
- Phases 1a-1c complete (protocol codec, reliable transport, queues)
- Phase 0.5 protocol validation available

**External**:
- None

---

## Next Phase

**Phase 2**: Canary Deployment with SLO Monitoring
See `03-phase-2-spec.md`

---

## Related Documentation

- **Phase 1 Program**: `02-phase-1-spec.md` - Architecture
- **Phase 0.5**: `02a-phase-0.5-protocol-validation.md` - Protocol validation
- **Phase 1a-1c**: Prerequisites
- **Phase 2**: `03-phase-2-spec.md` - Next major phase

