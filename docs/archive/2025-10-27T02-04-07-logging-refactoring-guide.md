# Logging Refactoring Guide

## Overview

This guide documents the new logging system and refactoring patterns for upgrading all Python files to use first-class logging with structured context, correlation tracking, and performance instrumentation.

## New Logging Infrastructure

### 1. Logging Abstraction (`logging_abstraction.py`)

#### Features

- Dual-format output (JSON + human-readable)
- Structured context support via `extra` parameter
- Automatic correlation ID injection
- Configurable via environment variables

### Usage

```python
from cync_controller.logging_abstraction import get_logger

logger = get_logger(__name__)

## Simple log
logger.info("Server started")

## Log with structured context
logger.info(
    "Device connected",
    extra={
        "device_id": device_id,
        "device_name": device.name,
        "ip_address": ip_addr,
    },
)

## Error with context
logger.exception(
    "✗ Command failed",
    extra={
        "device_id": device_id,
        "command_type": "set_brightness",
        "error": str(e),
    },
)
```text

### 2. Correlation Tracking (`correlation.py`)

#### Features

- Async-safe correlation ID storage
- Auto-generation for new contexts
- Manual override for testing

### Usage

```python
from cync_controller.correlation import correlation_context, ensure_correlation_id

## Auto-generate correlation ID for async context
async def handle_connection():
    ensure_correlation_id()  # Ensures correlation ID exists
    logger.info("Connection started")  # Automatically includes correlation ID

## Manual correlation ID for testing
async def test_critical_path():
    with correlation_context("TEST-123"):
        await process_command()
```text

### 3. Performance Instrumentation (`instrumentation.py`)

#### Features

- Automatic timing for operations
- Configurable threshold warnings
- On/off toggle via environment variable

### Usage

```python
from cync_controller.instrumentation import timed_async

@timed_async("tcp_read")
async def read_packet(reader):
    data = await reader.read(4096)
    return data
    # Automatically logs: "⏱️ [tcp_read] completed in 45ms"
```text

## Refactoring Patterns

### Pattern 1: Replace Old Logger with New Logger

#### Before

```python
import logging
logger = logging.getLogger(CYNC_LOG_NAME)
```text

### After

```python
from cync_controller.logging_abstraction import get_logger
logger = get_logger(__name__)
```text

### Pattern 2: Remove `lp` (Log Prefix) Pattern

#### Before

```python
def some_method(self):
    lp = f"{self.lp}some_method:"
    logger.info("%s Starting operation", lp)
    logger.error("%s Operation failed: %s", lp, error)
```text

### After

```python
def some_method(self):
    logger.info("→ Starting operation")
    logger.error(
        "✗ Operation failed",
        extra={"error": str(error)},
    )
```text

### Pattern 3: Add Structured Context

#### Before

```python
logger.info("Device %s connected at %s", device_id, ip_addr)
```text

### After

```python
logger.info(
    "✓ Device connected",
    extra={
        "device_id": device_id,
        "ip_address": ip_addr,
    },
)
```text

### Pattern 4: Improve Error Logging

#### Before

```python
except Exception:
    logger.exception("Error in operation")
```text

### After

```python
except Exception as e:
    logger.exception(
        "✗ Operation failed",
        extra={
            "operation": "device_connect",
            "device_id": device_id,
            "error": str(e),
        },
    )
```text

### Pattern 5: Add Entry/Exit Logging for Async Operations

#### Before

```python
async def process_command(device_id, command):
    # No entry/exit logging
    result = await send_command(device_id, command)
    return result
```text

### After

```python
async def process_command(device_id, command):
    ensure_correlation_id()  # Ensure correlation tracking

    logger.info(
        "→ Processing command",
        extra={
            "device_id": device_id,
            "command_type": command.type,
        },
    )

    result = await send_command(device_id, command)

    logger.info(
        "✓ Command processed",
        extra={
            "device_id": device_id,
            "command_type": command.type,
            "result": result,
        },
    )
    return result
```text

### Pattern 6: Add Performance Timing

#### Before

```python
async def publish_message(topic, payload):
    await client.publish(topic, payload)
```text

### After

```python
@timed_async("mqtt_publish")
async def publish_message(topic, payload):
    await client.publish(topic, payload)
    # Automatically logs timing
```text

## Log Message Standards

### Prefixes for Visual Clarity

- `→` - Starting an operation
- `✓` - Successfully completed
- `✗` - Failed operation
- `⚠️` - Warning
- `⏱️` - Performance timing (automatically added by @timed_async)

### Log Levels

- **DEBUG**: Detailed diagnostic information (packet contents, internal state)
- **INFO**: Important events (connections, state changes, command execution)
- **WARNING**: Unexpected situations that don't prevent operation
- **ERROR**: Errors that prevent specific operations
- **CRITICAL**: System-wide failures

### What to Remove

1. **Redundant "Entering function" logs** without meaningful context
2. **Excessive debug logs in tight loops** (replace with summaries)
3. **Duplicate information** already logged elsewhere
4. **Old `lp` variable declarations** and string formatting

### What to Add

1. **Entry/exit logs** for async operations with context
2. **State transition logs** with before/after values
3. **Error context** (device ID, operation, correlation ID)
4. **Command acknowledgment tracking**
5. **Performance timing** for network operations

## File-by-File Refactoring Checklist

### ✅ Completed

- [x] `logging_abstraction.py` - Created
- [x] `correlation.py` - Created
- [x] `instrumentation.py` - Created
- [x] `const.py` - Added configuration constants
- [x] `main.py` - Fully refactored

### ⏳ Partially Complete

- [~] `server.py` - CloudRelayConnection and NCyncServer init refactored
  - Still needs: `parse_status`, `periodic_status_refresh`, `periodic_pool_status_logger`, `start`, `stop`, `_register_new_connection`

### 🔲 Pending

- [ ] `devices.py` - 199 log calls to refactor
  - Priority: Command sending, state changes, mesh refresh, TCP device lifecycle
- [ ] `mqtt_client.py` - 155 log calls to refactor
  - Priority: Connection lifecycle, message publish/receive, discovery operations
- [ ] `cloud_api.py` - 46 log calls to refactor
  - Priority: Authentication flow, token lifecycle, API requests
- [ ] `utils.py` - 25 log calls to refactor
  - Priority: Config parsing, utility operations
- [ ] `exporter.py` - 18 log calls to refactor
  - Priority: Export server lifecycle, API endpoints

## Configuration

### Environment Variables

Add to your `.env` or environment configuration:

```bash
## Logging format: "json", "human", or "both"
CYNC_LOG_FORMAT=both

## JSON log output file
CYNC_LOG_JSON_FILE=/var/log/cync_controller.json

## Human-readable log output: "stdout", "stderr", or file path
CYNC_LOG_HUMAN_OUTPUT=stdout

## Enable/disable correlation tracking
CYNC_LOG_CORRELATION_ENABLED=true

## Enable/disable performance tracking
CYNC_PERF_TRACKING=true

## Performance threshold in milliseconds
CYNC_PERF_THRESHOLD_MS=100
```text

## Testing

### Verify Dual Output

1. Run the application
2. Check stdout for human-readable logs with correlation IDs
3. Check `/var/log/cync_controller.json` for JSON logs
4. Verify correlation IDs match between formats

### Verify Correlation Tracking

1. Trigger a device command
2. Follow the correlation ID through logs:
   - Command received
   - TCP packet sent
   - ACK received
   - MQTT state published

### Verify Performance Instrumentation

1. Enable performance tracking
2. Trigger slow operations
3. Verify timing logs appear with threshold warnings

## Next Steps

1. Continue refactoring remaining files using the patterns above
2. Remove low-value logs (aim for 20-30% reduction)
3. Add missing strategic logs for observability
4. Run linting after each file: `npm run lint:python:fix && npm run format:python`
5. Test each refactored module
6. Update documentation as patterns evolve

## Examples from Refactored Code

See `main.py` and `server.py` for complete examples of:

- Application lifecycle logging
- Cloud relay connection logging
- TCP device management logging
- Structured context usage
- Correlation tracking integration
- Performance instrumentation
