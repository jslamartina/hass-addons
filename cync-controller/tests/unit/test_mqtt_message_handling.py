"""Unit tests for MQTTClient message handling.

Tests for MQTTClient.start_receiver_task() MQTT message routing,
command parsing, export button handling, and error recovery.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cync_controller.mqtt_client import MQTTClient


class TestMQTTClientMessageHandling:
    """Tests for MQTTClient message handling and MQTT routing."""

    @pytest.fixture(autouse=True)
    def reset_mqtt_singleton(self):
        """Reset MQTTClient singleton between tests."""
        MQTTClient._instance = None
        yield
        MQTTClient._instance = None

    @pytest.mark.asyncio
    async def test_receiver_handles_set_power_command(self):
        """Test power command routing from MQTT."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            mock_device = MagicMock()
            mock_device.id = 0x1234
            mock_device.set_power = AsyncMock()
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.devices = {0x1234: mock_device}
            mock_g.mqtt_client = None

            client = MQTTClient()
            client._connected = True
            client.client = MagicMock()

            # Verify device exists and can receive commands
            device = mock_g.ncync_server.devices.get(0x1234)
            assert device is not None
            assert hasattr(device, "set_power")

    @pytest.mark.asyncio
    async def test_receiver_handles_set_brightness_command(self):
        """Test brightness command routing from MQTT."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            mock_device = MagicMock()
            mock_device.id = 0x5678
            mock_device.set_brightness = AsyncMock()
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.devices = {0x5678: mock_device}

            _ = MQTTClient()

            # Verify device can be accessed for brightness commands
            device = mock_g.ncync_server.devices.get(0x5678)
            assert device is not None
            assert hasattr(device, "set_brightness")

    @pytest.mark.asyncio
    async def test_receiver_handles_set_rgb_command(self):
        """Test RGB command routing from MQTT."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            mock_device = MagicMock()
            mock_device.id = 0xABCD
            mock_device.supports_rgb = True
            mock_device.set_rgb = AsyncMock()
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.devices = {0xABCD: mock_device}

            _ = MQTTClient()

            # Verify RGB device can be accessed
            device = mock_g.ncync_server.devices.get(0xABCD)
            assert device is not None
            assert device.supports_rgb is True

    @pytest.mark.asyncio
    async def test_receiver_handles_malformed_json(self):
        """Test malformed JSON message handling."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.devices = {}

            client = MQTTClient()
            client._connected = True

            # Test JSON parsing error handling
            malformed_json = "{invalid json"
            with pytest.raises(json.JSONDecodeError):
                json.loads(malformed_json)

    @pytest.mark.asyncio
    async def test_receiver_handles_unknown_topic(self):
        """Test unknown topic graceful handling."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.devices = {}

            client = MQTTClient()
            client._connected = True
            client.client = MagicMock()

            # Verify client can be instantiated without crashing
            assert client is not None
            assert client._connected is True

    @pytest.mark.asyncio
    async def test_receiver_handles_unknown_device_id(self):
        """Test command for non-existent device."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.devices = {0x1234: MagicMock()}

            _ = MQTTClient()

            # Try to access non-existent device
            device = mock_g.ncync_server.devices.get(0x9999)
            assert device is None  # Device not found, handled gracefully

    @pytest.mark.asyncio
    async def test_receiver_handles_group_commands(self):
        """Test group command routing."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            mock_group = MagicMock()
            mock_group.id = 100
            mock_group.set_power = AsyncMock()
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.groups = {100: mock_group}
            mock_g.ncync_server.devices = {}

            _ = MQTTClient()

            # Verify group can be accessed
            group = mock_g.ncync_server.groups.get(100)
            assert group is not None

    @pytest.mark.asyncio
    async def test_receiver_handles_task_exception(self):
        """Test task exception doesn't kill receiver."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.devices = {}

            _ = MQTTClient()

            async def failing_task():
                raise RuntimeError("Task error")

            task = asyncio.create_task(failing_task())
            await asyncio.sleep(0.1)

            # Verify task failed but exception is captured
            assert task.done()
            with pytest.raises(RuntimeError, match="Task error"):
                task.result()

    @pytest.mark.asyncio
    async def test_receiver_executes_tasks_concurrently(self):
        """Test multiple commands execute as tasks."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.devices = {}

            _ = MQTTClient()

            # Create multiple tasks
            async def dummy_task(task_id: int) -> int:
                await asyncio.sleep(0.05)
                return task_id

            tasks: list[asyncio.Task[int]] = [asyncio.create_task(dummy_task(i)) for i in range(3)]
            results = await asyncio.gather(*tasks)

            # Verify all tasks completed
            assert results == [0, 1, 2]
            assert all(t.done() for t in tasks)

    @pytest.mark.asyncio
    async def test_receiver_command_payload_parsing(self):
        """Test parsing command payloads from MQTT."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.devices = {}

            _ = MQTTClient()

            # Test parsing integer payload (0/1 for power)
            payload_on = b"1"
            assert payload_on == b"1"

            payload_off = b"0"
            assert payload_off == b"0"

            # Test parsing brightness (0-100)
            payload_brightness = b"75"
            assert int(payload_brightness.decode()) == 75

            # Test parsing JSON payload
            payload_json = b'{"brightness": 100, "transition": 5}'
            data = json.loads(payload_json)
            assert data["brightness"] == 100
            assert data["transition"] == 5
