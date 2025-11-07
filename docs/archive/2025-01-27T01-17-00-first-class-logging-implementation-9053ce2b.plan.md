# 2025 01 27T01 17 00 First Class Logging Implementation 9053Ce2B.Plan

<!-- 9053ce2b-e509-4230-adcf-25596372ba59 91dc9654-cddb-4ee2-abfd-f85c17750ad5 -->

## First-Class Logging Implementation

## Overview

Upgrade the logging infrastructure to production-grade standards with structured logging, correlation tracking, and performance instrumentation for the IoT bridge application.

## Implementation Strategy

### 1. Create Logger Abstraction Layer

**File**: `src/cync_controller/logging_abstraction.py` (new)

Create a flexible logging abstraction similar to .NET's ILogger:

- `CyncLogger` class with dual-format output capability
- `JSONFormatter` for structured logs (machine-parseable)
- `HumanReadableFormatter` for developer-friendly logs
- Both formatters output simultaneously to different handlers
- Include correlation IDs, timestamps (ISO-8601), module/function context
- Support for structured context data (dict/kwargs)

**Configuration via environment variables**:

- `CYNC_LOG_FORMAT`: `json` | `human` | `both` (default: `both`)
- `CYNC_LOG_JSON_FILE`: path for JSON output (default: `/var/log/cync_controller.json`)
- `CYNC_LOG_HUMAN_FILE`: path for human output (default: stdout)

### 2. Implement Correlation ID System

**File**: `src/cync_controller/correlation.py` (new)

Automatic correlation tracking for async operations:

- Use `contextvars.ContextVar` for async-safe correlation storage
- Auto-generate correlation IDs for new async contexts
- Propagate correlation IDs across TCP → Server → MQTT → HA chain
- Include correlation ID in every log message
- Support manual override for testing: `with correlation_context(custom_id="test-123")`

**Pattern**:

```python
## Automatic in new async tasks
async def handle_connection():
    # correlation_id auto-generated and tracked
    logger.info("Connection started")  # includes correlation_id

## Manual override for testing
async def test_critical_path():
    with correlation_context("CRIT-PATH-001"):
        await process_command()
```

### 3. Add Performance Instrumentation

**File**: `src/cync_controller/instrumentation.py` (new)

Automatic timing for network operations:

- `@timed` decorator for automatic timing
- Apply to: TCP reads/writes, MQTT publishes, HTTP requests, packet parsing
- Configurable threshold: log warning if operation exceeds threshold
- Environment variables:
  - `CYNC_PERF_TRACKING`: `true` | `false` (default: `true`)
  - `CYNC_PERF_THRESHOLD_MS`: milliseconds (default: `100`)

**Log format**: `⏱️ [operation_name] completed in 125ms (threshold: 100ms)`

### 4. Update Configuration Constants

**File**: `src/cync_controller/const.py`

Add new logging configuration constants:

- `CYNC_LOG_FORMAT`: Log output format(s)
- `CYNC_LOG_JSON_FILE`: JSON log file path
- `CYNC_LOG_CORRELATION_ENABLED`: Enable correlation tracking
- `CYNC_PERF_TRACKING`: Enable performance tracking
- `CYNC_PERF_THRESHOLD_MS`: Performance threshold in milliseconds

### 5. Audit & Refactor Existing Logs

**Strategy**: Review all 542 existing log calls across 8 files and:

**Remove/Reduce**:

- Redundant "Entering function" logs without context
- Excessive debug logs in tight loops (replace with summaries)
- Logs that duplicate information already logged elsewhere
- Overly verbose device status logs (keep critical state changes only)

**Add Missing**:

- Entry/exit logs for async network operations
- State transition logs (device online/offline, connection state changes)
- Error context (include device ID, correlation ID, operation context)
- Command acknowledgment tracking
- Configuration loading/validation results

**Files to refactor** (priority order):

1. `server.py` - TCP server operations (82 log calls)
2. `devices.py` - Device management (199 log calls)
3. `mqtt_client.py` - MQTT operations (155 log calls)
4. `cloud_api.py` - Cloud API calls (46 log calls)
5. `main.py` - Application lifecycle (16 log calls)
6. `utils.py` - Utility functions (25 log calls)
7. `exporter.py` - Export server (18 log calls)
8. `structs.py` - Data structures (1 log call)

### 6. Implement Strategic Logging Patterns

**Critical Logging Points** (ensure comprehensive coverage):

**TCP Server Operations** (`server.py`):

- Connection lifecycle: connect, authenticate, ready, disconnect
- Packet send/receive with correlation IDs
- Bridge device pool status changes
- Cloud relay mode operations
- Error conditions with full context

**Device Management** (`devices.py`):

- Command sending with acknowledgment tracking
- State changes with before/after values
- Mesh refresh operations
- TCP device ready state transitions
- Fan controller preset mappings

**MQTT Operations** (`mqtt_client.py`):

- Connection/reconnection with retry attempts
- Message publish/receive with topics
- Discovery message generation
- State synchronization operations
- Subscription management

**Cloud API** (`cloud_api.py`):

- Authentication flow (OTP request/send)
- Token lifecycle (cached/expired/refreshed)
- API request/response with endpoints
- Device export operations

### 7. Logging Standards & Patterns

**Standardize all logs** to follow these patterns:

**Entry/Exit** (async operations):

```python
logger.info("→ Starting mesh refresh", extra={"device_count": len(devices)})
## ... operation ...
logger.info("✓ Mesh refresh completed", extra={"duration_ms": elapsed})
```

**State Changes**:

```python
logger.info("Device state change", extra={
    "device_id": device_id,
    "device_name": device.name,
    "old_state": "OFF",
    "new_state": "ON",
    "brightness": 75
})
```

**Errors** (always include context):

```python
logger.error("Command failed", extra={
    "device_id": device_id,
    "device_name": device.name,
    "command_type": "set_brightness",
    "error": str(e),
    "correlation_id": get_correlation_id()
}, exc_info=True)
```

**Performance** (automatic via decorator):

```python
@timed("mqtt_publish")
async def publish(topic, payload):
    # Automatically logs: "⏱️ mqtt_publish completed in 45ms"
```

### 8. Testing & Verification Phase

**Objective**: Validate the logging system works correctly in production environment

#### Pre-Deployment Testing

#### Step 1: Lint & Build Verification

```bash
npm run lint:python:fix            # Fix any linting issues
npm run format:python              # Format code
cd cync-controller && ./rebuild.sh # Rebuild addon
```

### Step 2: Dual-Format Output Verification

- Start the addon with `CYNC_LOG_FORMAT=both`
- Verify human-readable logs appear in stdout
- Verify JSON logs are written to `/var/log/cync_controller.json`
- Check that both formats contain the same information
- Validate JSON is properly formatted and parseable

### Step 3: Correlation ID Tracking

- Trigger a device command (e.g., turn on a light)
- Follow the correlation ID through the logs:
  - MQTT command received
  - TCP packet sent to device
  - Device ACK received
  - State update published
- Verify all related logs share the same correlation ID
- Test manual correlation ID override with `correlation_context("TEST-ID")`

### Step 4: Performance Instrumentation

- Monitor logs for performance timing entries
- Verify `@timed_async` decorators log execution times
- Test threshold warnings by setting `CYNC_PERF_THRESHOLD_MS=10`
- Confirm operations exceeding threshold log warnings
- Verify timing accuracy with known slow operations

### Step 5: Structured Context Validation

- Inspect JSON logs to ensure `extra` fields are properly included
- Verify no `name` field clashes (should use `device_name`, `group_name`)
- Check that visual prefixes (→, ✓, ✗, ⚠️) appear in human-readable logs
- Validate all critical operations log with structured context

#### Integration Testing

#### Step 6: End-to-End Workflow Testing

1. **Device Connection**:
   - Start addon
   - Verify bridge device connection logs
   - Check correlation ID is present

2. **Command Execution**:
   - Send MQTT command to turn on/off device
   - Verify command flow logging (MQTT → Server → Device → ACK)
   - Check performance timing logs

3. **State Updates**:
   - Trigger device state change
   - Verify state update propagation logs
   - Check group/subgroup aggregation logs

4. **Error Handling**:
   - Disconnect a device
   - Verify offline detection logs with proper context
   - Check error logs include full context

### Step 7: Configuration Testing

- Test `CYNC_LOG_FORMAT=json` (JSON only)
- Test `CYNC_LOG_FORMAT=human` (human-readable only)
- Test `CYNC_PERF_TRACKING=false` (disable timing)
- Verify environment variables work as expected

### Step 8: Log Analysis

- Review logs for noise reduction (should see ~20-30% fewer logs)
- Verify no extraneous debug logs in tight loops
- Check that critical operations are well-covered
- Ensure log messages are clear and actionable

## Implementation Order

1. Create logging abstraction layer (`logging_abstraction.py`)
2. Create correlation tracking system (`correlation.py`)
3. Create performance instrumentation (`instrumentation.py`)
4. Update constants with new configuration (`const.py`)
5. Refactor main entry point to use new logger (`main.py`)
6. Refactor each module in priority order (server → devices → mqtt → cloud → utils → exporter)
7. Update existing rule documentation (`logging-mandatory.mdc`)
8. Execute comprehensive testing phase (see Testing & Verification Phase above)

## Success Criteria

- All logs output in both JSON and human-readable formats simultaneously
- Every log message includes correlation ID for request tracing
- Network operations include automatic performance timing
- Reduced log noise (remove ~20-30% of low-value logs)
- Comprehensive coverage of critical operations
- Clear, searchable log messages with structured context
- Performance threshold violations clearly flagged
- Zero linting errors after changes

### To-dos

- [ ] Create logging_abstraction.py with CyncLogger class, JSON and human-readable formatters, dual-output capability
- [ ] Create correlation.py with contextvars-based correlation ID system, auto-generation, and manual override support
- [ ] Create instrumentation.py with @timed decorator, configurable thresholds, and on/off toggle
- [ ] Update const.py with new logging configuration environment variables and constants
- [ ] Refactor main.py to use new CyncLogger, add application lifecycle logging, remove low-value logs
- [ ] Refactor server.py TCP operations logging - add connection lifecycle, packet tracing, bridge pool status, reduce noise
- [ ] Refactor devices.py logging - add command acknowledgment tracking, state transitions, mesh operations, reduce verbose logs
- [ ] Refactor mqtt_client.py logging - add connection lifecycle, message publish/receive, discovery operations, reduce redundancy
- [ ] Refactor cloud_api.py logging - add authentication flow, token lifecycle, API request/response logging
- [ ] Refactor utils.py and exporter.py logging - add config parsing, utility operations, export server lifecycle
- [ ] Update .cursor/rules/logging-mandatory.mdc with new logging standards, patterns, and examples
- [ ] Run lint & build verification (npm run lint:python:fix, format, rebuild)
- [ ] Verify dual-format output (JSON + human-readable logs)
- [ ] Test correlation ID tracking through full request lifecycle
- [ ] Validate performance instrumentation and threshold warnings
- [ ] Verify structured context in JSON logs (no name field clashes)
- [ ] Execute end-to-end workflow testing (device connection, commands, state updates, errors)
- [ ] Test configuration options (CYNC_LOG_FORMAT, CYNC_PERF_TRACKING)
- [ ] Perform log analysis for noise reduction and coverage
- [ ] Verify all linting errors resolved (zero errors)
- [ ] Verify rebuild completes successfully
- [ ] Verify dual-format output working in production
- [ ] Verify correlation IDs present in all logs
- [ ] Verify performance timing operational
- [ ] Verify no G101 (name field clash) errors
- [ ] Verify visual prefixes appearing correctly
- [ ] Verify structured context in JSON logs
- [ ] Verify documentation updated (logging-mandatory.mdc, LOGGING_REFACTORING_GUIDE.md)
- [ ] Verify no breaking changes to existing functionality
