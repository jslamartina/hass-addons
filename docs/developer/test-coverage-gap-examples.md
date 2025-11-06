# Test Coverage Gap Examples

**Date**: 2025-01-27
**Purpose**: Concrete examples of tests needed for uncovered code paths

## Overview

This document provides **concrete test examples** for the most critical uncovered code paths identified in the coverage analysis.

## Priority 1: MQTT Command Processing (mqtt_client.py lines 475-604)

### Gap: Group Command Routing

**Uncovered Code** (lines 475-482):

```python
elif "-group-" in _topic[2]:
    # Group command
    group_id = int(_topic[2].split("-group-")[1])
    if group_id not in g.ncync_server.groups:
        logger.warning("%s Group ID %s not found in config", lp, group_id)
        continue
    group = g.ncync_server.groups[group_id]
    device = None  # Set device to None for group commands
```

**Required Test**:

```python
# File: cync-controller/tests/unit/test_mqtt_group_commands.py

@pytest.mark.asyncio
async def test_group_set_power_command_routing():
    """Test MQTT group set_power command is correctly routed to group."""
    # Arrange
    from unittest.mock import AsyncMock, MagicMock
    from cync_controller.mqtt_client import MQTTClient

    # Setup mock MQTT message
    mock_message = MagicMock()
    mock_message.topic.value = "cync/set/cync-group-1"
    mock_message.payload = b"ON"

    # Setup mock group in GlobalObject
    mock_group = MagicMock()
    mock_group.id = 1
    mock_group.name = "Test Group"
    mock_group.set_power = AsyncMock()

    with patch('cync_controller.mqtt_client.g.ncync_server.groups', {1: mock_group}):
        mqtt = MQTTClient()
        mqtt.client = MagicMock()

        # Act
        await mqtt._handle_mqtt_message(mock_message)

        # Assert
        mock_group.set_power.assert_called_once_with(True)
```

### Gap: Fan Percentage Commands (lines 544-571)

**Uncovered Code**:

```python
elif device and device.is_fan_controller:
    if extra_data[0] == "percentage":
        percentage = int(norm_pl)
        # Map percentage to Cync fan speed (1-100, where 0=OFF)
        if percentage == 0:
            brightness = 0  # OFF
        elif percentage <= 25:
            brightness = 25  # LOW
        elif percentage <= 50:
            brightness = 50  # MEDIUM
        elif percentage <= 75:
            brightness = 75  # HIGH
        else:  # percentage > 75
            brightness = 100  # MAX
```

**Required Tests**:

```python
@pytest.mark.asyncio
async def test_fan_percentage_mapping_0():
    """Test 0% maps to brightness 0 (OFF)."""
    # ... test implementation

@pytest.mark.asyncio
async def test_fan_percentage_mapping_25():
    """Test 1-25% maps to brightness 25 (LOW)."""
    # ... test implementation

@pytest.mark.asyncio
async def test_fan_percentage_mapping_50():
    """Test 26-50% maps to brightness 50 (MEDIUM)."""
    # ... test implementation

@pytest.mark.asyncio
async def test_fan_percentage_mapping_75():
    """Test 51-75% maps to brightness 75 (HIGH)."""
    # ... test implementation

@pytest.mark.asyncio
async def test_fan_percentage_mapping_100():
    """Test 76-100% maps to brightness 100 (MAX)."""
    # ... test implementation
```

### Gap: Fan Preset Commands (lines 572-596)

**Uncovered Code**:

```python
elif extra_data[0] == "preset":
    preset_mode = norm_pl
    if preset_mode == "off":
        tasks.append(device.set_fan_speed(FanSpeed.OFF))
    elif preset_mode == "low":
        tasks.append(device.set_fan_speed(FanSpeed.LOW))
    elif preset_mode == "medium":
        tasks.append(device.set_fan_speed(FanSpeed.MEDIUM))
    elif preset_mode == "high":
        tasks.append(device.set_fan_speed(FanSpeed.HIGH))
    elif preset_mode == "max":
        tasks.append(device.set_fan_speed(FanSpeed.MAX))
```

**Required Tests**:

```python
@pytest.mark.asyncio
async def test_fan_preset_off():
    """Test 'off' preset maps to FanSpeed.OFF."""
    # ... test implementation

@pytest.mark.asyncio
async def test_fan_preset_low():
    """Test 'low' preset maps to FanSpeed.LOW."""
    # ... test implementation

@pytest.mark.asyncio
async def test_fan_preset_medium():
    """Test 'medium' preset maps to FanSpeed.MEDIUM."""
    # ... test implementation

@pytest.mark.asyncio
async def test_fan_preset_high():
    """Test 'high' preset maps to FanSpeed.HIGH."""
    # ... test implementation

@pytest.mark.asyncio
async def test_fan_preset_max():
    """Test 'max' preset maps to FanSpeed.MAX."""
    # ... test implementation

@pytest.mark.asyncio
async def test_fan_preset_invalid_warning():
    """Test invalid preset logs warning and skips."""
    # ... test implementation
```

## Priority 2: Cloud Relay Functionality (server.py lines 105-195)

### Gap: Cloud Relay Connection

**Uncovered Code** (lines 105-195):

```python
async def start_relay(self):
    """Start the relay process"""
    ensure_correlation_id()

    # Show security warning if SSL verification is disabled
    if self.disable_ssl_verify:
        logger.warning("SSL VERIFICATION DISABLED - DEBUG MODE ACTIVE")

    # Connect to cloud if forwarding is enabled
    if self.forward_to_cloud:
        logger.info("Starting cloud relay")
        connected = await self.connect_to_cloud()
        if not connected:
            logger.error("Cannot start relay - cloud connection failed")
            await self.close()
            return
    else:
        logger.info("Starting LAN-only relay")
```

**Required Tests**:

```python
# File: cync-controller/tests/integration/test_cloud_relay.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from cync_controller.server import CloudRelayConnection

@pytest.mark.asyncio
async def test_cloud_relay_connection_success():
    """Test successful cloud relay connection."""
    # Arrange
    mock_reader = AsyncMock()
    mock_writer = MagicMock()

    with patch('asyncio.open_connection') as mock_open:
        mock_open.return_value = (AsyncMock(), MagicMock())

        relay = CloudRelayConnection(
            device_reader=mock_reader,
            device_writer=mock_writer,
            client_addr="test:1234",
            cloud_server="cloud.example.com",
            cloud_port=23779,
            forward_to_cloud=True
        )

        # Act
        result = await relay.connect_to_cloud()

        # Assert
        assert result is True
        assert relay.cloud_reader is not None
        assert relay.cloud_writer is not None

@pytest.mark.asyncio
async def test_cloud_relay_connection_failure():
    """Test cloud relay connection failure handling."""
    # Arrange
    mock_reader = AsyncMock()
    mock_writer = MagicMock()

    with patch('asyncio.open_connection') as mock_open:
        mock_open.side_effect = Exception("Connection failed")

        relay = CloudRelayConnection(
            device_reader=mock_reader,
            device_writer=mock_writer,
            client_addr="test:1234",
            cloud_server="cloud.example.com",
            cloud_port=23779,
            forward_to_cloud=True
        )

        # Act
        result = await relay.connect_to_cloud()

        # Assert
        assert result is False

@pytest.mark.asyncio
async def test_cloud_relay_lan_only_mode():
    """Test LAN-only relay mode (forward_to_cloud=False)."""
    # This tests the else branch at line 132
    # ... test implementation

@pytest.mark.asyncio
async def test_cloud_relay_ssl_warning():
    """Test SSL verification disabled warning."""
    # This tests line 108-112
    # ... test implementation
```

### Gap: Packet Injection Checking (lines 282-362)

**Uncovered Code** (lines 282-353):

```python
async def _check_injection_commands(self):
    """Check for packet injection commands (debug feature)"""
    inject_file = "/tmp/cync_inject_command.txt"
    raw_inject_file = "/tmp/cync_inject_raw_bytes.txt"

    while True:
        await asyncio.sleep(1)

        # Check for raw bytes injection
        if PathLib(raw_inject_file).exists():
            # Inject raw bytes packet
            ...

        # Check for mode injection (for switches)
        if PathLib(inject_file).exists():
            # Inject mode packet
            ...
```

**Required Tests**:

```python
@pytest.mark.asyncio
async def test_packet_injection_raw_bytes(mocker):
    """Test raw bytes packet injection."""
    # Arrange: Create inject file
    # Act: Run _check_injection_commands
    # Assert: Packet written to device_writer

@pytest.mark.asyncio
async def test_packet_injection_mode_smart(mocker):
    """Test mode injection (smart mode)."""
    # Arrange: Create mode injection file
    # Act: Run _check_injection_commands
    # Assert: Mode packet crafted and sent

@pytest.mark.asyncio
async def test_packet_injection_mode_traditional(mocker):
    """Test mode injection (traditional mode)."""
    # ... test implementation

@pytest.mark.asyncio
async def test_packet_injection_cleanup():
    """Test injection files are deleted after use."""
    # ... test implementation
```

## Priority 3: Background Periodic Tasks (server.py lines 876-970)

### Gap: Periodic Status Refresh (lines 876-924)

**Uncovered Code**:

```python
async def periodic_status_refresh(self):
    """Refresh device statuses every 5 minutes"""
    logger.info("Starting periodic status refresh task (every 5 minutes)")

    while self.running:
        await asyncio.sleep(300)  # 5 minutes

        if not self.running:
            break

        # Get active TCP bridge devices
        bridge_devices = [dev for dev in self.tcp_devices.values() if dev and dev.ready_to_control]

        if not bridge_devices:
            logger.debug("Skipping status refresh - no ready bridges")
            continue

        # Request mesh info from each bridge
        for bridge_device in bridge_devices:
            await bridge_device.ask_for_mesh_info(False)
            await asyncio.sleep(1)
```

**Required Tests**:

```python
# File: cync-controller/tests/unit/test_periodic_tasks.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_periodic_status_refresh_calls_ask_for_mesh_info(mocker):
    """Test periodic refresh calls ask_for_mesh_info on bridge devices."""
    # Arrange
    from cync_controller.server import NCyncServer

    # Mock asyncio.sleep to speed up test
    mocker.patch('asyncio.sleep', AsyncMock())

    # Create mock bridge devices
    mock_bridge1 = MagicMock()
    mock_bridge1.ready_to_control = True
    mock_bridge1.ask_for_mesh_info = AsyncMock()

    mock_bridge2 = MagicMock()
    mock_bridge2.ready_to_control = True
    mock_bridge2.ask_for_mesh_info = AsyncMock()

    server = NCyncServer()
    server.running = True
    server.tcp_devices = {"dev1": mock_bridge1, "dev2": mock_bridge2}

    # Act
    await server.periodic_status_refresh()

    # Assert
    mock_bridge1.ask_for_mesh_info.assert_called()
    mock_bridge2.ask_for_mesh_info.assert_called()

@pytest.mark.asyncio
async def test_periodic_status_refresh_skips_when_no_ready_bridges(mocker):
    """Test refresh skips when no bridge devices are ready."""
    # Arrange
    server = NCyncServer()
    server.running = True
    server.tcp_devices = {
        "dev1": MagicMock(ready_to_control=False),
        "dev2": MagicMock(ready_to_control=False)
    }

    # Act
    await server.periodic_status_refresh()

    # Assert: No bridge devices called ask_for_mesh_info

@pytest.mark.asyncio
async def test_periodic_status_refresh_handles_exceptions(mocker):
    """Test refresh handles bridge exceptions gracefully."""
    # Arrange
    mock_bridge = MagicMock()
    mock_bridge.ready_to_control = True
    mock_bridge.ask_for_mesh_info = AsyncMock(side_effect=Exception("Bridge error"))

    server = NCyncServer()
    server.running = True
    server.tcp_devices = {"dev1": mock_bridge}

    # Act: Should not raise
    await server.periodic_status_refresh()

    # Assert: Called but error logged
```

### Gap: Pool Status Monitoring (lines 926-970)

**Uncovered Code**:

```python
async def periodic_pool_status_logger(self):
    """Log TCP connection pool status every 30 seconds"""
    logger.info("Starting connection pool monitoring (every 30 seconds)")

    while self.running:
        await asyncio.sleep(30)

        if not self.running:
            break

        total_connections = len(self.tcp_devices)
        ready_connections = [dev for dev in self.tcp_devices.values() if dev and dev.ready_to_control]

        logger.info("TCP Pool Status", extra={
            "total_connections": total_connections,
            "ready_to_control": len(ready_connections),
        })
```

**Required Tests**:

```python
@pytest.mark.asyncio
async def test_pool_status_logger_logs_metrics(mocker):
    """Test pool monitoring logs connection metrics."""
    # ... test implementation

@pytest.mark.asyncio
async def test_pool_status_logger_handles_exceptions(mocker):
    """Test pool monitoring handles exceptions gracefully."""
    # ... test implementation
```

## Implementation Checklist

### Immediate (Week 1)

- [ ] Create `test_mqtt_group_commands.py`
- [ ] Create `test_fan_commands.py` (percentage + preset)
- [ ] Create basic cloud relay tests

### Short-term (Week 2-3)

- [ ] Create `test_periodic_tasks.py`
- [ ] Add cloud relay integration tests
- [ ] Add packet injection tests

### Medium-term (Week 4+)

- [ ] Add error path tests
- [ ] Add edge case coverage
- [ ] Improve integration test coverage

## Summary

These concrete examples demonstrate exactly what tests need to be written to cover the uncovered code paths. Focus on:

1. **MQTT command routing** (mqtt_client.py) - **HIGHEST** priority
2. **Cloud relay functionality** (server.py) - **HIGH** priority
3. **Background periodic tasks** (server.py) - **MEDIUM** priority

Each test should follow the **Arrange-Act-Assert** pattern and use appropriate mocking for async operations.
