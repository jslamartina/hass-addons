# Testing Infrastructure

## Overview

The Cync Controller add-on includes comprehensive test coverage across three tiers:

- **Unit Tests**: 24 test files covering all core modules with pytest
- **E2E Tests**: 10 test files for browser automation with Playwright
- **Integration Tests**: Performance and mesh refresh testing

## Directory Structure

```text
cync-controller/tests/
├── unit/               # Unit tests (pytest)
│   ├── test_cloud_api.py
│   ├── test_correlation.py
│   ├── test_device_*.py (multiple)
│   ├── test_helpers.py
│   ├── test_instrumentation.py
│   ├── test_mqtt_client.py
│   ├── test_packet_*.py
│   ├── test_server.py
│   ├── test_structs.py
│   ├── test_tcp_device_*.py (multiple)
│   ├── test_utils.py
│   └── conftest.py
├── integration/        # Integration tests
│   └── test_mesh_refresh_performance.py
└── e2e/               # E2E tests (Playwright)
    ├── test_basic_commands.py
    ├── test_cloud_relay.py
    ├── test_config_changes.py
    ├── test_device_discovery.py
    ├── test_group_control.py
    ├── test_log_levels.py
    ├── test_mqtt_recovery.py
    ├── test_state_sync.py
    ├── test_restart_button.py
    └── conftest.py
```

## Running Tests

### Unit Tests

```bash
## Run all unit tests (parallel - fastest, ~17s)
npm run test:unit

## Run specific test file
pytest cync-controller/tests/unit/test_devices.py

## Run with coverage (sequential - required for coverage tools)
npm run test:unit:cov

## Run specific test
pytest cync-controller/tests/unit/test_devices.py::test_set_power

## Sequential execution (for debugging)
npm run test:unit:serial
```

#### Parallel Execution (pytest-xdist)

The test suite uses **pytest-xdist** for parallel execution by default, configured in `pytest.ini`:

- **Configuration**: Set in `pytest.ini` line 50 with `-n auto` (uses all available CPU cores, typically 16)
- **Speed**: 3x faster than sequential (51s → 17s)
- **Serial mode**: Use `npm run test:unit:serial` or `-n 0` when debugging individual tests
- **Coverage**: Must run sequentially due to coverage tool limitations
- **Compatible**: Works perfectly with pytest-asyncio and async tests

**Configuration location**: `cync-controller/pytest.ini` - Change `-n auto` to `-n 8` or `-n 4` to limit worker count

**Why not disable verbose output?** 67 tests use the `caplog` fixture to verify logging behavior (errors, warnings, debug output). These tests ensure critical logging works correctly. Verbose output has zero performance impact, and parallel execution provides the 3x speedup without breaking these tests.

### E2E Tests

```bash
## Run all E2E tests
npx playwright test tests/e2e/

## Run specific test file
npx playwright test tests/e2e/test_group_control.py

## Run with UI mode
npx playwright test tests/e2e/ --ui

## Run with debug mode
npx playwright test tests/e2e/ --debug
```

### Integration Tests

```bash
## Run integration tests
pytest cync-controller/tests/integration/
```

## Test Coverage

**Current Status (Updated: January 2025)**:

- **Overall Coverage**: 67.62% (+2.97% improvement)
- **Total Tests**:
  - Unit: 599 passing, 7 skipped, 0 failures
  - E2E: 47 passing, 7 failing, 3 skipped (failures expected when infrastructure missing)
- **Test Files**: 24 unit test files + 10 E2E test files covering all core modules

**Note:** E2E tests now fail instead of skipping when infrastructure is missing, making test requirements clear.

### Coverage by Module

| Module           | Coverage | Status        | Notes               |
| ---------------- | -------- | ------------- | ------------------- |
| `utils.py`       | 95.88%   | ✅ Excellent  | Exceeded 80% target |
| `main.py`        | 70.80%   | ⚠️ Good       | Close to 80% target |
| `server.py`      | 49.48%   | ⚠️ Needs work | +15.5% improvement  |
| `mqtt_client.py` | 48.35%   | ⚠️ Needs work | Added 5 new tests   |

### Recent Improvements (October 2025)

- **Fixed 25 failing tests** across multiple modules
- **Added 19 new unit tests**:
  - 9 tests for `server.py` (parse_status, device state management)
  - 5 tests for `mqtt_client.py` (register_single_device)
  - 5 tests for `utils.py` (parse_config)
- **Test count**: 580 → 599 (+19 tests)
- **Overall coverage**: 64.65% → 67.62% (+2.97%)

### Coverage Details

Current coverage includes:

- Core modules: `main.py`, `server.py`, `devices.py`, `mqtt_client.py`
- Infrastructure: `logging_abstraction.py`, `correlation.py`, `instrumentation.py`
- Protocol handling: packet parsing, checksum calculation
- Cloud API: authentication, token management

### Remaining Gaps

#### server.py (49.48% coverage)

- Missing: Cloud relay mode (lines 105-195)
- Missing: Connection management edge cases
- Recommendation: Add integration tests for cloud relay scenarios

### mqtt_client.py (48.35% coverage)

- Missing: Command processor queue management
- Missing: Group state synchronization
- Recommendation: Add integration tests for MQTT message handling

## Unit Test Patterns

### Mock Device Implementation

Integration tests use mock devices that simulate real Cync protocol behavior:

```python
## Example from conftest.py
@pytest.fixture
def mock_tcp_device():
    device = MockTCPDevice(device_id="test-001")
    yield device
    device.cleanup()
```

### Async Test Pattern

Most operations are async, use pytest-asyncio:

```python
import pytest

@pytest.mark.asyncio
async def test_device_command():
    device = create_test_device()
    await device.set_power(True)
    assert device.power == True
```

### Testing Logging Behavior (caplog Fixture)

67 tests across 10 files use the `caplog` fixture to verify logging behavior:

```python
import pytest

@pytest.mark.asyncio
async def test_error_logging(caplog):
    """Test that errors are properly logged."""
    with caplog.at_level(logging.ERROR):
        await device.send_invalid_command()
        assert "Invalid command" in caplog.text
```

### Why this matters

- Ensures critical errors, warnings, and debug messages are logged correctly
- Tests logging behavior at appropriate levels
- Uses `caplog` fixture from pytest-logging plugin (included by default)
- **Never disable logging plugin** (`-p no:logging`) - it breaks these tests

## E2E Test Patterns

### Browser Automation

E2E tests use Playwright for Home Assistant UI testing:

```python
## Example from test_group_control.py
async def test_group_toggle(page, addon):
    # Navigate to dashboard
    await page.goto("http://localhost:8123")

    # Click group toggle
    await page.get_by_role("switch", name="Hallway Lights").click()

    # Verify state changed
    await expect(page.get_by_text("ON")).to_be_visible()
```

### Addon Lifecycle

Use fixtures for addon state management:

```python
@pytest.fixture
async def addon_with_devices(addon):
    # Wait for devices to connect
    await addon.wait_for_devices(count=43)
    return addon
```

## Integration Test Setup

Integration tests require real devices to be connected:

1. Ensure DNS redirection is configured
2. Have 4-6 always-on devices available
3. Stop add-on before running integration tests
4. Run tests with:

```bash
cd cync-controller
pytest tests/integration/ -v
```

## Mock Devices

### MockTCPDevice

Simulates protocol handshake and basic operations:

- SSL connection establishment
- 0x7B ACK responses
- Status packet (0x83) generation
- Protocol compliance validation

### Usage

```python
from tests.unit.conftest import MockTCPDevice

async def test_command_acknowledgment():
    device = MockTCPDevice(device_id="test-001")
    async with device:
        # Simulate command
        await device.receive_command()
        # Mock device automatically sends ACK
        # Verify callback was triggered
```

## Test Configuration

Configuration files:

- `cync-controller/pytest.ini`: Pytest configuration (includes `-n auto` for parallel execution by default)
- `playwright.config.ts`: Playwright browser settings
- `cync-controller/pyproject.toml`: Test dependencies (includes pytest-xdist)

### Configuring Worker Count

To change the number of parallel workers, edit `cync-controller/pytest.ini` line 50:

```ini
addopts =
    # ... other options ...
    -n auto      # Uses all CPU cores (default, typically 16)
    -n 8         # Use 8 workers
    -n 4         # Use 4 workers
```

Or override temporarily:

```bash
pytest -n 4 # Use 4 workers for this run
```

## CI/CD Integration

Tests run automatically:

- Unit tests on every commit
- E2E tests on pull requests
- Coverage reports generated via GitHub Actions

## Best Practices

1. **Isolation**: Each test should be independent
2. **Async First**: Use async/await patterns throughout
3. **Mocking**: Mock external dependencies (MQTT, TCP)
4. **Fixtures**: Reuse common setup in `conftest.py`
5. **Coverage**: Maintain 90%+ coverage on critical paths
6. **Naming**: Descriptive test names explaining the scenario

## Debugging Tests

### Unit Tests

```bash
## Show print statements
pytest -s tests/unit/

## Run single test with output
pytest tests/unit/test_devices.py::test_set_power -v -s

## Drop into debugger on failure
pytest --pdb tests/unit/
```

### E2E Tests

```bash
## Run with UI mode to see browser
npx playwright test tests/e2e/ --ui

## Run with headed mode
npx playwright test tests/e2e/ --headed

## Pause execution for debugging
npx playwright test tests/e2e/ --pause
```

## Performance Testing

Integration tests include performance benchmarks:

- Mesh refresh latency
- Command acknowledgment timing
- MQTT publish throughput
- TCP connection handling

See `tests/integration/test_mesh_refresh_performance.py` for examples.
