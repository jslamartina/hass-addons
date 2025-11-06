# Architecture and Key Concepts

This document covers the architecture, protocol details, and critical implementation concepts for the Cync Controller add-on.

## Table of Contents

- [Cloud Relay Mode](#cloud-relay-mode)
- [Command Flow and ACK Handling](#command-flow-and-ack-handling)
- [Architecture Overview](#architecture-overview)
- [Logging Infrastructure](#logging-infrastructure)
- [Testing Infrastructure](#testing-infrastructure)
- [DNS Requirement](#dns-requirement)
- [Critical Implementation Details](#critical-implementation-details)

## Cloud Relay Mode

**New in v0.0.4.0**: The add-on can optionally act as a Man-in-the-Middle (MITM) proxy between devices and Cync cloud, enabling:

- Real-time packet inspection and logging
- Protocol analysis and debugging
- Cloud backup (devices still work if relay goes down)
- LAN-only operation (no cloud forwarding)

**⚠️ Current Limitation:** Cloud relay mode is **read-only** for monitoring and inspection. Commands from Home Assistant don't work in relay mode (you'll see `No TCP bridges available!` errors). Disable relay mode for local control.

**Configuration** (`config.yaml`):

```yaml
cloud_relay:
  enabled: false # Enable relay mode (disables commands)
  forward_to_cloud: true # Forward packets to cloud (false = LAN-only)
  cloud_server: "35.196.85.236" # Cync cloud server IP
  cloud_port: 23779 # Cync cloud port
  debug_packet_logging: false # Log parsed packets (verbose)
  disable_ssl_verification: false # Disable SSL verify (debug only)
```

**Use Cases:**

- **Protocol Analysis**: Enable `debug_packet_logging` to see all packet structures
- **Debugging**: Test device behavior while observing cloud interactions
- **LAN-only with inspection**: Set `forward_to_cloud: false` to block cloud access while logging packets
- **Cloud backup**: Keep `forward_to_cloud: true` so devices work even if relay fails

**Future Enhancement:** We plan to add bidirectional command support in relay mode, allowing both local control AND cloud forwarding/inspection simultaneously.

**Security Warning**: If `disable_ssl_verification: true`, the add-on operates in DEBUG MODE with no SSL security. Only use on trusted local networks for development.

## Command Flow and ACK Handling

**How device commands work:**

1. **MQTT receives command** from Home Assistant (e.g., turn on light)
2. **`set_power()` called** on `CyncDevice` or `CyncGroup`
3. **Callback registered** in `bridge_device.messages.control[msg_id]` with:
   - Message ID (unique per command)
   - Payload bytes
   - Callback coroutine to execute on ACK
   - Device ID
4. **`pending_command` flag set** to prevent stale status updates
5. **Command packet sent** via TCP to bridge device
6. **Bridge forwards to mesh** network
7. **Device receives command** and executes it
8. **ACK packet (0x73) returned** from device
9. **Callback executed** updating MQTT state
10. **`pending_command` cleared** - device ready for next command

**Critical:** Steps 3 and 9 MUST happen for commands to physically work. Missing callback registration causes "silent failures" where logs show success but devices don't respond.

**Packet types:**

- `0x73` - Control command packet (from server to device) and ACK response (device to server)
- `0x83` - Mesh info / device status (device to server)
- `0x43` - Broadcast status update (device to server)

## Architecture Overview

The Cync Controller add-on has three main components:

1. **Exporter** - FastAPI web server for exporting device configuration from Cync cloud (2FA via emailed OTP)
2. **nCync** - Async TCP server that masquerades as Cync cloud (requires DNS redirection)
   - **Optional Cloud Relay Mode** - Can act as MITM proxy to forward traffic to/from real cloud while inspecting packets
3. **MQTT Client** - Bridges device states to Home Assistant using MQTT discovery

## Logging Infrastructure

**New in v0.0.4.14**: The add-on uses a production-grade structured logging system.

### Architecture

- **Dual-Format Output**: JSON for machine parsing (`/var/log/cync_controller.json`) and human-readable for console
- **Correlation ID Tracking**: Automatic correlation IDs propagate across async operations for easy log filtering
- **Performance Instrumentation**: Decorators track timing for network operations with configurable thresholds
- **Structured Context**: Logs include key=value context pairs for filtering and analysis

### Core Components

Located in `cync-controller/src/cync_controller/`:

- `logging_abstraction.py`: Dual-format logger supporting both printf-style and structured formats
- `correlation.py`: Async-safe correlation ID tracking using `contextvars`
- `instrumentation.py`: Performance timing decorators with threshold warnings

### Usage

```python
from cync_controller.logging_abstraction import get_logger
from cync_controller.correlation import ensure_correlation_id

logger = get_logger(__name__)

async def my_function():
    ensure_correlation_id()  # Ensure correlation ID exists
    logger.info("Operation started", extra={"device_id": device_id})
```

### Configuration

Set in `config.yaml` via `debug_log_level` (0=INFO, 1=DEBUG):

- `CYNC_DEBUG`: Enable debug logging
- `CYNC_LOG_FORMAT`: "json", "human", or "both"
- `CYNC_PERF_TRACKING`: Enable performance timing
- `CYNC_PERF_THRESHOLD_MS`: Threshold for warnings (default: 100ms)

### Log Analysis

```bash
# Filter by correlation ID
ha addons logs local_cync-controller | grep "correlation-id"

# View JSON logs
docker exec addon_local_cync-controller cat /var/log/cync_controller.json | jq '.'

# Find slow operations
docker exec addon_local_cync-controller \
  sh -c "grep 'performance' /var/log/cync_controller.json | jq 'select(.duration_ms > 100)'"
```

For detailed logging documentation, see [Logging System Guide](./logging-system.md).

## Testing Infrastructure

**New in v0.0.4.14**: Comprehensive test coverage across three tiers.

### Test Structure

```
tests/
├── unit/         # 24 test files (pytest)
├── e2e/          # 10 test files (Playwright)
└── integration/  # Performance and mesh refresh tests
```

### Running Tests

```bash
# Unit tests
pytest cync-controller/tests/unit/

# E2E tests
npx playwright test tests/e2e/

# With coverage
pytest cync-controller/tests/unit/ --cov=cync_controller --cov-report=html
```

### Coverage

Target: 90%+ coverage on critical modules

### Test Patterns

**Mock Devices**: Integration tests use `MockTCPDevice` to simulate protocol behavior
**Async Tests**: Use `@pytest.mark.asyncio` for async function testing
**E2E Tests**: Playwright for Home Assistant UI automation

For detailed testing documentation, see [Testing Infrastructure Guide](./testing-infrastructure.md).

## DNS Requirement

**Critical:** The add-on requires DNS redirection to intercept device traffic. See [DNS Setup Guide](../user/dns-setup.md) for setup instructions. Without this, devices will still communicate with Cync cloud.

## Critical Implementation Details

### Command ACK Handling

**Individual Device Commands** (`CyncDevice.set_power`, `devices.py` lines 358-365):

- Register a `ControlMessageCallback` with msg_id before sending
- Callback is executed when ACK (0x73 packet) is received
- `pending_command` flag is set to prevent stale status updates during command execution

**Group Commands** (`CyncGroup.set_power`, `devices.py` lines 1420-1429):

- **MUST** register callback just like individual device commands
- Without callback registration, group commands appear to send but don't physically control devices
- Bridge device handles ACK and executes callback to update MQTT state

**Common pitfall:** Forgetting to register callbacks for new command types will cause "silent failures" - logs show commands sent and ACK'd, but devices don't respond.

### Device Availability Resilience

**Problem:** Mesh info packets (0x83 responses) can report devices as offline unreliably, causing flickering availability status in Home Assistant.

**Solution** (`server.py` lines 530-544):

- Devices have `offline_count` counter tracking consecutive offline reports
- Device is only marked unavailable after **3 consecutive offline reports**
- Counter resets to 0 immediately when device appears online
- Prevents false positives from unreliable mesh info responses

**Before the fix:**

```python
if connected_to_mesh == 0:
    device.online = False  # Immediate offline marking
```

**After the fix:**

```python
if connected_to_mesh == 0:
    device.offline_count += 1
    if device.offline_count >= 3 and device.online:
        device.online = False  # Only after 3 consecutive reports
else:
    device.offline_count = 0  # Reset counter
    device.online = True
```

### Automatic Refresh After ACK (REMOVED)

**Bug fixed (Oct 14, 2025):** `devices.py` lines 2501-2505 contained automatic `trigger_status_refresh()` call after every command ACK. This caused:

- Cascading refreshes after every command
- Commands failing because refresh would interfere with pending operations
- "Click twice to work" behavior where first click triggers refresh, second click works

**The fix:** Removed automatic refresh. Users can manually click "Refresh Device Status" button when needed.

**Code removed:**

```python
# Trigger immediate status refresh after ACK
if g.mqtt_client:
    asyncio.create_task(g.mqtt_client.trigger_status_refresh())
```

### Debugging Command Issues

When commands don't work, check in this order:

1. **Are commands being received?** Look for `set_power` in logs
2. **Is callback registered?** Look for "callback NOT found" warnings
3. **Is write_lock acquired?** Look for "write_lock ACQUIRED" logs
4. **Did TCP socket send?** Look for "drain() COMPLETED" logs
5. **Did ACK arrive?** Look for "CONTROL packet ACK SUCCESS" logs
6. **Is device ready?** Check `ready_to_control` and `pending_command` flags

**Example diagnostic grep:**

```bash
ha addons logs local_cync-controller | grep -E "set_power|WRITE CALLED|write_lock|ACK|drain"
```

---

_For more information, see [AGENTS.md](../../AGENTS.md) in the repository root._
