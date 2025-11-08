# Testing Guide

**Purpose:** Document testing patterns, best practices, and conventions established during Phase 1 and Phase 2 of the multi-tiered testing plan.

\*Last Updated:\*\* October 24, 2025

---

## Overview

This guide captures the testing patterns and best practices we've established while building the unit test suite for the Cync Controller add-on. Use this as a reference when writing new tests or extending existing test coverage.

### Current Test Suite

- **192 unit tests** across 7 test files
- **35.33% overall coverage** (critical modules at 95-100%)
- **< 0.4s execution time** for full suite ⚡

---

## Table of Contents

- [Project Context](#project-context)
- [Test Organization](#test-organization)
- [Common Patterns](#common-patterns)
- [Module-Specific Patterns](#module-specific-patterns)
- [Mocking Strategies](#mocking-strategies)
- [Common Pitfalls](#common-pitfalls)
- [Running Tests](#running-tests)

---

## Project Context

### Why These Tests Exist

The Cync Controller add-on has complex async workflows involving:

- TCP packet parsing and validation (critical for protocol correctness)
- MQTT communication with Home Assistant
- Device state management and command handling
- Cloud API authentication and device export

### Key Testing Goals

1. ✅ Enable confident refactoring of packet parsing logic
2. ✅ Prevent regressions in core business logic
3. ✅ Document expected behavior through tests
4. ✅ Provide fast feedback loops (< 1 second for unit tests)

### What We Don't Test (Yet)

- **Full integration workflows** - Requires real MQTT broker (Phase 3)
- **Network protocols** - Requires real TCP connections (Phase 3)
- **UI interactions** - Requires browser automation (Phase 3/4)
- **Entry points** - `main.py`, `exporter.py` (integration-level testing)

---

## Test Organization

### Directory Structure

```bash
cync-controller/tests/
├── unit/
│ ├── __init__.py
│ ├── conftest.py             # Shared fixtures
│ ├── test_packet_parser.py   # 41 tests - packet parsing
│ ├── test_packet_checksum.py # 28 tests - checksum calculation
│ ├── test_devices.py         # 48 tests - device/group models
│ ├── test_mqtt_client.py     # 36 tests - MQTT client
│ ├── test_server.py          # 19 tests - server and cloud relay
│ └── test_cloud_api.py       # 20 tests - authentication/export
├── integration/              # Phase 3 (planned)
└── e2e/                      # Phase 3/4 (planned)
```

### Test File Naming

- **Pattern:** `test_<module_name>.py`
- **Example:** `test_devices.py` for `cync_lan/devices.py`
- **Classes:** Group related tests in classes (for example, `TestCyncDevice`, `TestCyncGroup`)

### Test Class Organization

```python
class TestCyncDevice:
    """Tests for CyncDevice class"""

    # Organize by functionality:
    # 1. Initialization tests
    # 2. Property tests
    # 3. Validation tests
    # 4. Command tests
    # 5. State management tests
```

---

## Common Patterns

### Pattern 1: Basic Test Structure

```python
def test_feature_description(self):
    """Test that feature behaves as expected"""
    # Arrange - Set up test data
    device = CyncDevice(cync_id=0x1234)

    # Act - Execute the code under test
    result = device.some_method()

    # Assert - Verify expectations
    assert result == expected_value
```

### Pattern 2: Async Test Pattern

```python
@pytest.mark.asyncio
async def test_async_feature(self):
    """Test async method"""
    with patch("module.g") as mock_g:
        mock_g.mqtt_client = AsyncMock()

        result = await async_method()

        assert result is True
```

### Pattern 3: Error Validation

```python
def test_validation_rejects_invalid_input(self):
    """Test that invalid input raises appropriate error"""
    device = CyncDevice(cync_id=0x1234)

    with pytest.raises(ValueError, match="Brightness must be between 0 and 255"):
        device.brightness = -1
```

### Pattern 4: Parametrized Tests

```python
@pytest.mark.parametrize("input_value,expected", [
    (0, "min_value"),
    (50, "mid_value"),
    (100, "max_value"),
])
def test_conversion(self, input_value, expected):
    """Test conversion for multiple values"""
    result = convert_function(input_value)
    assert result == expected
```

### Pattern 5: Singleton Reset

For modules using singletons (MQTTClient, CyncCloudAPI, NCyncServer):

```python
@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton between tests"""
    MyClass._instance = None
    yield
    MyClass._instance = None
```

---

## Module-Specific Patterns

### Packet Parser Tests

**Focus:** Correctness of parsing logic, edge cases

```python
class TestParseCyncPacket:
    def test_parse_control_packet(self):
        """Test parsing valid 0x73 control packet"""
        packet = bytes.fromhex("73 00 00 00 1e ...")

        result = parse_cync_packet(packet)

        assert result is not None
        assert result["packet_type"] == "0x73"
        assert result["packet_type_name"] == "DATA_CHANNEL"
```

### Key Patterns (Packet Parser)

- Use `bytes.fromhex()` for readability
- Test both valid and malformed packets
- Parametrize for multiple packet types
- Verify None is returned for invalid input

### Device Model Tests

**Focus:** Initialization, property validation, state management

```python
class TestCyncDevice:
    def test_property_validation(self):
        """Test property validates input range"""
        device = CyncDevice(cync_id=0x1234)

        # Valid range
        device.brightness = 128
        assert device.brightness == 128

        # Invalid range
        with pytest.raises(ValueError):
            device.brightness = 256
```

### Key Patterns (Device Model)

- Test initialization with/without optional params
- Validate property setters enforce constraints
- Mock global state (`g`) to avoid dependencies
- Mock event loops for properties that trigger MQTT publishes

```python
with patch("cync_lan.devices.g") as mock_g, \
     patch("cync_lan.devices.asyncio.get_running_loop") as mock_loop:
    mock_g.tasks = []
    mock_g.mqtt_client = AsyncMock()
    mock_loop.return_value.create_task = MagicMock()

    device.online = True  # This triggers MQTT publish
```

### MQTT Client Tests

**Focus:** Connection handling, publishing, discovery, conversions

```python
class TestMQTTClient:
    @pytest.mark.asyncio
    async def test_publish(self):
        """Test publishing message to MQTT"""
        with patch("cync_lan.mqtt_client.g") as mock_g:
            client = MQTTClient()
            client._connected = True  # Required for publish
            client.client.publish = AsyncMock()

            result = await client.publish("topic", b"payload")

            assert result is True
```

### Key Patterns (MQTT Client)

- Reset singleton between tests with `@pytest.fixture(autouse=True)`
- Set `_connected = True` for methods that check connection
- Mock `aiomqtt.Client` to avoid actual MQTT connections
- Mock internal methods (for example, `send_device_status`) for state update tests

### Server Tests

**Focus:** Initialization, TCP device management, SSL configuration, cloud relay

```python
class TestNCyncServer:
    def test_init_with_devices(self):
        """Test server initialization"""
        with patch("cync_lan.server.g") as mock_g, \
             patch("cync_lan.server.asyncio.get_event_loop") as mock_loop:
            mock_g.reload_env = MagicMock()
            mock_g.env.cync_cloud_relay_enabled = False
            # ... set all required env vars

            server = NCyncServer(devices={})

            assert server.shutting_down is False
```

### Key Patterns (Server)

- Mock all environment variables via `mock_g.env`
- Mock event loop to avoid runtime errors
- Use real `CyncTCPDevice` instances for device management tests
- Mock `g.mqtt_client.publish` for methods that publish connection counts

### Cloud API Tests

**Focus:** Authentication flow, token management, API error handling

```python
class TestCyncCloudAPI:
    @pytest.mark.asyncio
    async def test_send_otp_success(self):
        """Test successful OTP submission"""
        api = CyncCloudAPI()

        # Mock HTTP session with complete response
        mock_response.json = AsyncMock(return_value={
            "user_id": "test-user",
            "access_token": "test-token",
            "authorize": "test-auth",
            "expire_in": 604800,  # Note: expire_in not expires_in
            "refresh_token": "test-refresh-token",
        })

        api.write_token_cache = AsyncMock(return_value=True)

        result = await api.send_otp(123456)
        assert result is True
```

### Key Patterns (Cloud API)

- Mock `aiohttp.ClientSession` and responses
- Use correct field names (`expire_in` not `expires_in`, `refresh_token`)
- Reset singleton between tests
- Mock file I/O for token cache operations

---

## Mocking Strategies

### Mocking Global State

The codebase uses a global `GlobalObject` (`g`) extensively. Mock it consistently:

```python
with patch("cync_lan.devices.g") as mock_g:
    mock_g.ncync_server = MagicMock()
    mock_g.mqtt_client = AsyncMock()
    mock_g.tasks = []
    mock_g.env.mqtt_topic = "cync_lan"

    # Your test code here
```

### Mocking Async Methods

```python
## For methods that return a value
mock_obj.async_method = AsyncMock(return_value=True)

## For methods that raise exceptions
mock_obj.async_method = AsyncMock(side_effect=Exception("Error"))

## For methods used in asyncio.gather()
mock_device.write = AsyncMock()  # Not just MagicMock()
```

### Mocking Event Loops

When testing properties/methods that create async tasks:

```python
with patch("cync_lan.devices.asyncio.get_running_loop") as mock_loop:
    mock_loop.return_value.create_task = MagicMock()

    # Now can safely set properties that trigger task creation
    device.online = True
```

### Mocking External Libraries

```python
## Mock aiomqtt.Client
with patch("cync_lan.mqtt_client.aiomqtt.Client") as mock_client_class:
    mock_instance = AsyncMock()
    mock_instance.publish = AsyncMock()
    mock_client_class.return_value = mock_instance

    client = MQTTClient()
    # client.client is now the mock_instance
```

### Mocking File I/O

```python
## For reading
with patch("cync_lan.cloud_api.Path") as mock_path, \
     patch("cync_lan.cloud_api.pickle.load") as mock_pickle:
    mock_pickle.return_value = expected_data

    result = await api.read_token_cache()

## For writing
with patch("cync_lan.cloud_api.Path") as mock_path:
    mock_file_handle = MagicMock()
    mock_path.return_value.open = MagicMock(return_value=mock_file_handle)
    mock_file_handle.__enter__ = MagicMock(return_value=mock_file_handle)
    mock_file_handle.__exit__ = MagicMock(return_value=False)

    with patch("cync_lan.cloud_api.pickle.dump"):
        result = await api.write_token_cache(token)
```

---

## Common Pitfalls

### Pitfall 1: Forgetting to Reset Singletons

**Problem:** Tests interfere with each other when singletons persist.

#### Solution

```python
@pytest.fixture(autouse=True)
def reset_singleton():
    MyClass._instance = None
    yield
    MyClass._instance = None
```

### Pitfall 2: Using MagicMock for Async Methods

**Problem:** `asyncio.gather()` fails with "An asyncio. Future, a coroutine or an awaitable is required"

#### Solution

```python
## ❌ WRONG
mock_device.write = MagicMock()

## ✅ CORRECT
mock_device.write = AsyncMock()
```

### Pitfall 3: Missing \_connected Flag

**Problem:** MQTT publish methods return False instead of True.

#### Solution

```python
client = MQTTClient()
client._connected = True  # Required!
client.client.publish = AsyncMock()
```

### Pitfall 4: Incorrect Field Names

**Problem:** Pydantic validation errors due to wrong field names.

**Solution:** Check the actual struct definition:

```python
## ❌ WRONG
ComputedTokenData(expires_in=3600)

## ✅ CORRECT
ComputedTokenData(expire_in=3600, refresh_token="...")
```

### Pitfall 5: Not Mocking Event Loops

**Problem:** "RuntimeError: no running event loop" when setting properties.

#### Solution

```python
with patch("cync_lan.devices.asyncio.get_running_loop") as mock_loop:
    mock_loop.return_value.create_task = MagicMock()
    device.online = True  # Safe now
```

### Pitfall 6: Device ID Byte Size Issues

**Problem:** Large device IDs cause "bytes must be in range(0, 256)" errors.

#### Solution

```python
## ❌ PROBLEMATIC
device = CyncDevice(cync_id=0x1234)  # Large ID in packet creation

## ✅ BETTER FOR TESTING
device = CyncDevice(cync_id=0x12)  # Small ID fits in one byte
```

---

## Shared Fixtures

### Available Fixtures (`conftest.py`)

```python
## TCP Device Mock
def test_something(mock_tcp_device):
    mock_tcp_device.ready_to_control = True
    mock_tcp_device.write = AsyncMock()

## MQTT Client Mock
def test_mqtt(mock_mqtt_client):
    mock_mqtt_client.publish = AsyncMock()

## Sample Packets
def test_parsing(sample_control_packet, sample_mesh_info_packet):
    result = parse_cync_packet(sample_control_packet)

## Device/Group Data
def test_config(sample_device_data, sample_group_data):
    device = CyncDevice(**sample_device_data)

## Mock Device/Group Objects
def test_with_mocks(mock_device, mock_group, mock_global_object):
    mock_device.set_power = AsyncMock()
```

### Creating New Fixtures

Add to `conftest.py`:

```python
@pytest.fixture
def your_fixture_name():
    """
    Brief description of what this fixture provides.
    """
    # Setup
    mock_obj = MagicMock()
    mock_obj.some_property = "value"

    # Return or yield
    return mock_obj  # Or: yield mock_obj
```

---

## Assertions and Validation

### Property Assertions

```python
## Basic equality
assert device.brightness == 75

## Type checking
assert isinstance(device.metadata, DeviceTypeInfo)

## Collection membership
assert 0x1234 in server.devices

## Method calls
assert mock_client.publish.called
mock_client.publish.assert_called_once()
mock_client.publish.assert_called_with("topic", b"payload")
```

### Exception Assertions

```python
## Basic exception
with pytest.raises(ValueError):
    device.brightness = -1

## With message matching
with pytest.raises(ValueError, match="must be between 0 and 255"):
    device.brightness = 256

## Specific exception type
with pytest.raises(CyncAuthenticationError):
    await api.request_devices()
```

---

## Test Execution

### Running Tests

```bash
## All unit tests
pytest tests/unit/

## Specific file
pytest tests/unit/test_devices.py

## Specific test
pytest tests/unit/test_devices.py::TestCyncDevice::test_init

## With coverage
pytest tests/unit/ --cov=src/cync_lan --cov-report=html

## Fast fail
pytest tests/unit/ -x

## Verbose output
pytest tests/unit/ -v

## Show print statements
pytest tests/unit/ -s
```

### NPM Scripts

```bash
npm run test:unit      # Run all unit tests
npm run test:unit:cov  # Run with coverage report
npm run test:unit:fast # Fast fail on first error
```

### Coverage Reports

After running tests with coverage:

```bash
## View HTML report
open cync-controller/htmlcov/index.html

## Terminal summary shows module-by-module coverage
```

---

## Best Practices Summary

### DO ✅

- ✅ **Test behavior, not implementation** - Focus on observable outcomes
- ✅ **Use descriptive test names** - `test_offline_threshold_requires_three_reports` not `test_offline`
- ✅ **Mock external dependencies** - Don't call real MQTT brokers or APIs
- ✅ **Reset singletons** - Use `autouse=True` fixtures
- ✅ **Test edge cases** - Empty input, None, boundary values, invalid input
- ✅ **Keep tests fast** - Unit tests should run in < 1 second total
- ✅ **Use pytest markers** - `@pytest.mark.asyncio` for async tests
- ✅ **Document complex tests** - Add comments explaining non-obvious assertions

### DON'T ❌

- ❌ **Don't test implementation details** - Avoid asserting on internal variables
- ❌ **Don't depend on test order** - Each test should be independent
- ❌ **Don't use real network calls** - Always mock HTTP/MQTT/TCP
- ❌ **Don't hardcode assumptions** - Use fixtures and parametrize
- ❌ **Don't ignore warnings** - They often indicate real issues
- ❌ **Don't skip singleton resets** - Causes test interference
- ❌ **Don't use MagicMock for async** - Use AsyncMock instead

---

## Coverage Targets by Module

Based on Phase 1 & 2 results:

| Module                   | Target | Achieved | Status          | Notes                                 |
| ------------------------ | ------ | -------- | --------------- | ------------------------------------- |
| `packet_parser.py`       | 90%+   | 95.76%   | ✅ **EXCEEDED** | Critical - enables protocol work      |
| `packet_checksum.py`     | 95%+   | 100%     | ✅ **EXCEEDED** | Critical - validates packet integrity |
| `const.py`               | 90%+   | 90.70%   | ✅ **MET**      | Configuration constants               |
| `structs.py`             | 70%+   | 76.62%   | ✅ **EXCEEDED** | Data structures                       |
| `metadata/model_info.py` | 70%+   | 70.77%   | ✅ **MET**      | Device type info                      |
| `cloud_api.py`           | 50%+   | 45.93%   | 🟡 Close        | Complex HTTP workflows                |
| `devices.py`             | 40%+   | 33.80%   | 🟡 Partial      | Large module, many integration points |
| `mqtt_client.py`         | 40%+   | 27.28%   | 🟡 Partial      | Complex MQTT workflows                |
| `server.py`              | 40%+   | 26.67%   | 🟡 Partial      | TCP server, async connections         |

**Overall:** 35.33% - Focused on critical paths in each module

---

## Future Testing Work

### Phase 3: Integration Tests

- Docker-based test environment
- Real MQTT broker (EMQX)
- Mock Cync devices
- End-to-end command flows

### Phase 4: E2E Tests (Happy Path - ACTIVE)

**Status:** ✅ Active & In Use
\*Last Updated:\*\* October 26, 2025

The project includes a Playwright-based end-to-end (e2e) test that validates the happy path: login → verify discovery → toggle a real device entity.

#### Setup

One-time browser installation:

```bash
npm run playwright:install
```

#### Pre-requisites

- Devcontainer running HA Supervisor and EMQX
- DNS redirection configured (see `docs/user/dns-setup.md`)
- Add-on running in baseline LAN mode
- A real Cync device reachable on the network

#### Optional: Clean Environment Before Testing

For a deterministic test run, remove stale MQTT entities:

```bash
## Preview what will be deleted
sudo python3 scripts/delete-mqtt-safe.py --dry-run

## Delete and restart addon
sudo python3 scripts/delete-mqtt-safe.py
ha addons restart local_cync-controller

## OR use the Playwright cleanup script
npm run playwright:delete-all-except-bridge
RESTART_ADDON=true npm run playwright:delete-all-except-bridge
```

#### Running E2E Tests

```bash
## Run all Playwright tests
npm run playwright:test

## Run with visible browser (headed mode)
npx playwright test --headed

## Run specific test file
npx playwright test cync-controller/tests/e2e/happy-path.spec.ts

## Run with specific browser
npx playwright test --project=chromium
```

#### Test Flow

The happy path test (`cync-controller/tests/e2e/happy-path.spec.ts`) performs these steps:

1. **Login** - Authenticates to Home Assistant (defaults: dev/dev)
2. **Verify MQTT Integration** - Ensures MQTT integration is installed
3. **Verify Bridge Device** - Confirms "Cync Controller" bridge device exists
4. **Find Device Entities** - Navigates to Entities page, filters by domain (switch/light) and integration (MQTT)
5. **Toggle Device** - Clicks a device toggle → waits for state to flip → toggles back to original state
6. **Verify Round-trip** - Ensures device returned to original state

#### Environment Variables

```bash
## Customize Home Assistant URL and credentials
HA_BASE_URL=http://localhost:8123 \
  HA_USERNAME=dev \
  HA_PASSWORD=dev \
  npm run playwright:test
```

#### Artifacts and Debugging

Test results are saved to `test-results/` and `playwright-report/`:

```text
test-results/
├── screenshots/        # Screenshots at each step (on failure)
├── videos/            # Video recordings (on failure)
├── traces/            # Playwright traces (on failure)
└── <timestamp>/       # Run-specific directory

playwright-report/     # HTML report (open in browser)
```

View the HTML report:

```bash
npx playwright show-report
```

#### Best Practices for E2E Tests

- **Role-based selectors** - Use `getByRole()` for accessibility and resilience
- **Explicit waits** - Playwright autowaits, but use `toBeVisible()` for dynamic content
- **Timeout configuration** - Defaults: 120s per test. Increase if device ACKs are slow
- **No `force: true` clicks** - Avoid bypassing actionability checks (causes flakiness)
- **See `docs/developer/browser-automation.md`** for detailed Playwright patterns

#### Troubleshooting

#### Test times out waiting for state flip

- Device may be offline or slow to ACK
- Increase timeout in test: `toPass({ timeout: 30000 })`
- Check `ha addons logs local_cync-controller` for errors

### "Element intercepts pointer events" errors

- Use click helpers or parent container clicks
- See `docs/developer/browser-automation.md` for solutions

### MQTT entities not found

- Run optional cleanup (above) to ensure entities are published
- Check `ha addons logs local_cync-controller | grep -i discovery`

### Login fails

- Verify credentials in `hass-credentials.env`
- Clear browser session: `rm -rf ~/.cache/ms-playwright`
- Check HA logs: `ha logs --follow`

---

## Troubleshooting Tests

### Common Test Failures

#### "RuntimeError: No running event loop"

```python
## Fix: Mock get_running_loop
with patch("module.asyncio.get_running_loop") as mock_loop:
    mock_loop.return_value.create_task = MagicMock()
```

## "TypeError: Object MagicMock can't be used in 'await' expression"

```python
## Fix: Use AsyncMock instead of MagicMock
mock_obj.async_method = AsyncMock()  # Not MagicMock()
```

## "assert False is True" (method returns False unexpectedly)

```python
## Common causes:
## 1. Missing _connected flag (MQTT methods)
client._connected = True

## 2. Missing mock return value
mock_method = AsyncMock(return_value=True)  # Add return_value!

## 3. Method calls unmocked dependency
## Fix: Mock all dependencies that method calls
```

## Pydantic validation errors

```python
## Fix: Check actual struct definition for required fields
## Example: ComputedTokenData needs expire_in, refresh_token, etc.
```

---

## References

- [Multi-Tiered Testing Plan](../archive/2025-10-27T00-07-33-multi-tiered-testing-plan.md) - Overall testing strategy (archived)
- [AGENTS.md](../../AGENTS.md) - Development guidelines
- [Architecture Guide](architecture.md) - System design
- [pytest Documentation](https://docs.pytest.org/)

---

Last updated: October 26, 2025
