# Integration Tests - Phase 0

This directory contains integration tests for Phase 0 TCP communication. Unlike unit tests that use mocks, these tests use a real asyncio TCP server to validate the complete end-to-end flow.

## Overview

Integration tests validate:
- **Packet framing**: Correct Phase 0 packet format (magic bytes, version, length, JSON payload)
- **TCP communication**: Real socket operations with timeouts and error handling
- **Retry logic**: Exponential backoff with jitter
- **Metrics**: Prometheus endpoint accessibility and data validation
- **Error scenarios**: Connection failures, timeouts, disconnections

## Running Tests

### Run Only Integration Tests

```bash
# Default mode
./scripts/test-integration.sh

# Verbose output
./scripts/test-integration.sh --verbose

# With HTML report
./scripts/test-integration.sh --html
```

### Run Only Unit Tests

```bash
# Fast unit tests with mocks
./scripts/test-unit.sh

# With coverage
./scripts/test-unit.sh --coverage
```

### Run All Tests

```bash
# Both unit and integration tests
./scripts/test.sh
```

## Test Structure

### Fixtures (`conftest.py`)

#### `MockTCPServer`
A real asyncio-based TCP server with configurable response modes:

- **SUCCESS**: Immediate ACK response (default)
- **DELAY**: Delayed response (simulates slow network)
- **DISCONNECT**: Accepts connection, then closes immediately
- **TIMEOUT**: Never responds (simulates timeout)
- **REJECT**: Refuses connection

**Example usage:**
```python
async def test_example(mock_tcp_server: MockTCPServer):
    # Server automatically started and stopped
    result = await toggle_device_with_retry(
        device_id="TEST_DEVICE",
        device_host=mock_tcp_server.host,
        device_port=mock_tcp_server.port,
        state=True,
        max_attempts=2,
    )

    # Verify received packets
    assert len(mock_tcp_server.received_packets) == 1
    packet = mock_tcp_server.received_packets[0]
    assert packet.payload["opcode"] == "toggle"
```

#### `unique_device_id`
Generates a unique device ID for each test to avoid metric collisions.

#### `unique_metrics_port`
Provides a fixed port for the Prometheus metrics server (19400).

### Test Cases (`test_toggler_integration.py`)

| Test | Description |
|------|-------------|
| `test_happy_path_toggle_success` | Successful toggle with immediate response |
| `test_packet_format_validation` | Validates exact Phase 0 packet structure |
| `test_retry_intermittent_connection_failure` | Retry when first connection fails |
| `test_retry_intermittent_timeout` | Retry when first attempt times out |
| `test_all_attempts_timeout` | Failure when all attempts timeout |
| `test_connection_refused` | Failure when no server is listening |
| `test_connection_closed_during_recv` | Failure when server closes connection |
| `test_metrics_endpoint_accessible` | Validates Prometheus metrics endpoint |

## Phase 0 Packet Format

Integration tests validate the exact packet structure:

```
┌────────┬─────────┬────────┬─────────┐
│ Magic  │ Version │ Length │ Payload │
│ 2 bytes│ 1 byte  │ 4 bytes│ N bytes │
└────────┴─────────┴────────┴─────────┘
  0xF00D     0x01   uint32_be  JSON
```

**JSON Payload:**
```json
{
  "opcode": "toggle",
  "device_id": "DEVICE123",
  "msg_id": "abc123def456",
  "state": true
}
```

## Key Technical Details

### Port Management
- Tests use `port=0` for OS-assigned ports to avoid conflicts
- Metrics server uses a fixed high port (19400) but is idempotent

### Async Coordination
- Server and client run concurrently using asyncio
- Fixtures handle server lifecycle (start/stop) automatically

### Timeouts
- Integration tests use default timeouts (1.0s connect, 1.5s I/O)
- Faster than production for test speed
- Long enough to validate timeout scenarios

### Metrics Isolation
- Each test gets a unique device_id
- Prevents metric collision between tests
- Metrics server is global and reused (idempotent)

## Adding New Tests

1. **Create test function** in `test_toggler_integration.py`
2. **Use fixtures** for server and device_id
3. **Verify behavior** using server's received_packets
4. **Mark as integration**: `@pytest.mark.asyncio` (implicit via module marker)

Example:
```python
@pytest.mark.asyncio
async def test_my_scenario(
    mock_tcp_server: MockTCPServer,
    unique_device_id: str,
    unique_metrics_port: int,
) -> None:
    """Test my specific scenario."""
    start_metrics_server(unique_metrics_port)

    # Your test logic here
    result = await toggle_device_with_retry(...)

    # Assertions
    assert result is True
    assert len(mock_tcp_server.received_packets) == 1
```

## Troubleshooting

### Tests Hang
- Check if metrics server port (19400) is already in use
- Increase timeouts in `TCPConnection` if network is slow

### Connection Refused Errors
- Ensure `MockTCPServer` fixture is properly initialized
- Check that server port is accessible (localhost)

### Metric Collisions
- Use `unique_device_id` fixture to avoid collisions
- Run tests sequentially (not in parallel)

## Performance

- **Unit tests**: ~1-2 seconds (all 11 tests)
- **Integration tests**: ~8-10 seconds (all 8 tests)
- **Total**: ~10-12 seconds for complete test suite

Integration tests are slower due to real TCP operations and timeouts.

## Related Documentation

- **Phase 0 Spec**: `docs/rebuild-tcp-comm/01-phase-0.md`
- **Unit Tests**: `tests/test_toggler.py`
- **Helper Scripts**: `scripts/README.md`

