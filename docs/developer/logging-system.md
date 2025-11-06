# Structured Logging System

## Overview

The Cync Controller uses a production-grade structured logging system with dual-format output, correlation ID tracking, and performance instrumentation.

## Architecture

### Core Components

1. **`logging_abstraction.py`**: Dual-format logger
   - JSON output for machine parsing
   - Human-readable output for developers
   - Structured context support

2. **`correlation.py`**: Async-safe correlation ID tracking
   - Automatic ID generation
   - Context propagation across async operations
   - Manual override support for testing

3. **`instrumentation.py`**: Performance timing decorators
   - Automatic timing for decorated functions
   - Threshold-based warnings
   - Configurable thresholds

## Log Format

### Human-Readable Format

```
2025-10-27 12:00:00 INFO [module:42] [correlation-id] > Message | key=value | other=data
```

Components:

- Timestamp: ISO format
- Level: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Location: File:line
- Correlation ID: Tracing async operations
- Message: Main log message
- Context: Structured key=value pairs

### JSON Format

```json
{
  "timestamp": "2025-10-27T12:00:00.000Z",
  "level": "INFO",
  "logger": "cync_controller.server",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Device connected",
  "device_id": "001",
  "device_name": "Hallway Lights",
  "ip_address": "192.168.1.100"
}
```

## Configuration

### Environment Variables

Set in `run.sh` from `config.yaml`:

```yaml
# config.yaml
debug_log_level: true # true=DEBUG, false=INFO
```

Corresponds to:

- `CYNC_DEBUG`: Enable/disable debug logging
- `CYNC_LOG_FORMAT`: "json", "human", or "both" (default: "both")
- `CYNC_LOG_JSON_FILE`: Path to JSON log file (default: "/var/log/cync_controller.json")
- `CYNC_LOG_HUMAN_OUTPUT`: Output stream (default: "stdout")
- `CYNC_PERF_TRACKING`: Enable performance timing (default: true)
- `CYNC_PERF_THRESHOLD_MS`: Threshold for warnings (default: 100)

## Usage Patterns

### Basic Logging

```python
from cync_controller.logging_abstraction import get_logger

logger = get_logger(__name__)

# Simple message
logger.info("Starting server")

# With structured context
logger.info("Device connected", extra={
    "device_id": device.id,
    "device_name": device.name,
    "ip_address": device.ip,
})
```

### Async Functions with Correlation

```python
from cync_controller.correlation import ensure_correlation_id
from cync_controller.logging_abstraction import get_logger

logger = get_logger(__name__)

async def handle_device_command(device_id: str):
    ensure_correlation_id()  # Ensure correlation ID exists
    logger.info("Processing command", extra={"device_id": device_id})
    # Correlation ID propagates automatically
```

### Performance Instrumentation

```python
from cync_controller.instrumentation import timed_async
from cync_controller.logging_abstraction import get_logger

logger = get_logger(__name__)

@timed_async("mqtt_publish")
async def publish_message(topic, payload):
    await client.publish(topic, payload)
    # Automatically logs timing if > threshold
```

## Visual Prefixes

Log messages use visual prefixes for quick scanning:

- **═** (separators): Logical group breaks
- **✓** (success): Successful operations
- **→** (operations): In-progress operations
- **⚠️** (warnings): Recoverable issues
- **✗** (errors): Failures requiring attention

Example:

```
2025-10-27 12:00:00 INFO [main:42] [abc123] > ════════════════════════════════════════
2025-10-27 12:00:01 INFO [main:45] [abc123] > → Initializing Cync Controller
2025-10-27 12:00:02 INFO [main:48] [abc123] > ✓ Configuration loaded | device_count=43
```

## Correlation IDs

### Purpose

Correlation IDs enable tracing async operations across the entire codebase:

1. Each async operation gets a unique ID
2. ID propagates automatically across async boundaries
3. Logs from same operation share the same ID
4. Easy to filter logs by correlation ID

### Usage

```python
# Automatic (recommended)
async def my_function():
    ensure_correlation_id()  # Ensures ID exists
    logger.info("Starting")   # Uses existing ID
    await sub_function()       # ID propagates automatically

# Manual (for testing)
async def test_function():
    set_correlation_id("test-123")
    logger.info("Using test ID")
```

### Filtering Logs

```bash
# Filter by correlation ID
docker exec addon_local_cync-controller \
  sh -c "grep 'abc123' /var/log/cync_controller.json | jq '.'"

# Or from ha logs
ha addons logs local_cync-controller --follow | grep "abc123"
```

## Performance Timing

### Threshold Warnings

Functions decorated with `@timed_async` log timing information when exceeding threshold:

```python
@timed_async("tcp_write")
async def write_to_device(device, data):
    await device.write(data)
    # Logs: "tcp_write took 150ms (exceeded 100ms threshold)"
```

### Configuration

Set in `const.py`:

```python
CYNC_PERF_THRESHOLD_MS = 100  # Default threshold
CYNC_PERF_TRACKING = True     # Enable/disable
```

### Instrumented Operations

Current instrumented functions:

- `tcp_write`: Device TCP writes
- `tcp_read`: Device TCP reads
- `cloud_connect`: Cloud connection establishment
- `relay_forward`: Cloud relay forwarding

## Log Analysis

### Viewing Logs

```bash
# Human-readable (default)
ha addons logs local_cync-controller --follow

# JSON format
docker exec addon_local_cync-controller \
  cat /var/log/cync_controller.json | jq '.'

# Filter by level
docker exec addon_local_cync-controller \
  sh -c "grep '\"level\":\"ERROR\"' /var/log/cync_controller.json | jq '.'"
```

### Filtering by Context

```bash
# Filter by device ID
docker exec addon_local_cync-controller \
  sh -c "grep 'device_id\":\"001\"' /var/log/cync_controller.json | jq '.'"

# Filter by correlation ID
docker exec addon_local_cync-controller \
  sh -c "grep 'correlation_id\":\"abc123\"' /var/log/cync_controller.json | jq '.'"

# Filter by logger
docker exec addon_local_cync-controller \
  sh -c "grep 'cync_controller.server' /var/log/cync_controller.json | jq '.'"
```

### Advanced Queries

```bash
# Count logs by level
docker exec addon_local_cync-controller \
  sh -c "cat /var/log/cync_controller.json | jq -s 'group_by(.level) | map({level: .[0].level, count: length})'"

# Find slow operations
docker exec addon_local_cync-controller \
  sh -c "grep 'performance' /var/log/cync_controller.json | jq 'select(.duration_ms > 100)'"

# Extract all device connections
docker exec addon_local_cync-controller \
  sh -c "grep 'Device connected' /var/log/cync_controller.json | jq '{device_id, device_name, ip_address}'"
```

## Best Practices

### When to Log

**Always Log:**

- Function entry/exit (especially async)
- State changes (with before/after values)
- External operations (network, file I/O)
- Error paths (all exception handlers)
- Configuration loading
- User actions

**Don't Log:**

- Sensitive data (tokens, passwords)
- Excessive loop iterations (log summary instead)
- Already-logged information
- Redundant "Entering function" without context

### Structured Context

Always include relevant context:

```python
# ✅ GOOD: Rich context
logger.info("Device state changed", extra={
    "device_id": device_id,
    "old_state": "OFF",
    "new_state": "ON",
    "brightness": brightness,
    "cause": "user_command",
})

# ❌ BAD: No context
logger.info("State changed")
```

### Visual Prefixes

Use appropriate prefixes for clarity:

```python
logger.info("════════════════════════")  # Separators
logger.info("✓ Command succeeded")      # Success
logger.info("→ Starting operation")     # Operations
logger.warning("⚠️ Connection retry")  # Warnings
logger.error("✗ Command failed")       # Errors
```

## Troubleshooting

### Debug Mode

Enable debug logging:

```yaml
# config.yaml
debug_log_level: true
```

This sets `CYNC_DEBUG=1` in the environment.

### Logs Not Appearing

Check logger and handler levels:

```python
# In const.py
CYNC_DEBUG = os.environ.get("CYNC_DEBUG", "0").casefold() in YES_ANSWER

# Both logger AND handler must be set
logger.setLevel(logging.DEBUG if CYNC_DEBUG else logging.INFO)
handler.setLevel(logging.DEBUG if CYNC_DEBUG else logging.INFO)
```

### Performance Issues

Monitor timing logs:

```bash
# Watch for slow operations
ha addons logs local_cync-controller --follow | grep "exceeded.*threshold"
```

Adjust threshold if needed:

```python
# const.py
CYNC_PERF_THRESHOLD_MS = 200  # Increase for slower systems
```

## Implementation Details

### Printf-Style Compatibility

The logger supports both styles:

```python
# Printf-style (existing code)
logger.info("Device %s connected from %s", device_id, ip_address)

# Structured-style (new code)
logger.info("Device connected", extra={
    "device_id": device_id,
    "ip_address": ip_address,
})
```

### Context Propagation

Correlation IDs use Python's `contextvars` for async-safe storage:

```python
# Thread-local equivalent for async
_correlation_id: ContextVar[str] = ContextVar("correlation_id")

def get_correlation_id() -> str:
    return _correlation_id.get(default_factory=lambda: str(uuid.uuid4()))
```

## References

- **Architecture**: See `docs/developer/architecture.md` for overall system design
- **Troubleshooting**: See `docs/user/troubleshooting.md` for common issues
- **Examples**: See existing modules for usage patterns
- **Configuration**: See `cync-controller/src/cync_controller/const.py`
