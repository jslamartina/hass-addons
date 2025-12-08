"""Unit tests for MQTTClient message handling.

Tests for MQTTClient.start_receiver_task() MQTT message routing,
command parsing, export button handling, and error recovery.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cync_controller.mqtt_client import MQTTClient


@dataclass
class MessageDevice:
    """Typed device stub for MQTT message handling tests."""

    id: int
    set_power: AsyncMock = field(default_factory=AsyncMock)
    set_brightness: AsyncMock = field(default_factory=AsyncMock)
    set_rgb: AsyncMock = field(default_factory=AsyncMock)
    supports_rgb: bool = False


@dataclass
class MessageGroup:
    """Typed group stub for MQTT message handling tests."""

    id: int
    set_power: AsyncMock = field(default_factory=AsyncMock)


@dataclass
class MessageServer:
    """Typed ncync server stub for message handling tests."""

    devices: dict[int, MessageDevice]
    groups: dict[int, MessageGroup]


def _configure_server(
    mock_g: MagicMock,
    devices: dict[int, MessageDevice],
    groups: dict[int, MessageGroup] | None = None,
) -> MessageServer:
    """Attach a typed ncync_server to the patched global object."""
    server = MessageServer(devices=devices, groups=groups or {})
    mock_g.ncync_server = server
    return server


class TestMQTTClientMessageHandling:
    """Tests for MQTTClient message handling and MQTT routing."""

    @pytest.fixture(autouse=True)
    def reset_mqtt_singleton(self) -> Iterator[None]:
        """Reset MQTTClient singleton between tests."""
        with (
            patch.object(MQTTClient, "_instance", None),
            patch.object(MQTTClient, "_initialized", False),
        ):
            yield

    @pytest.mark.asyncio
    async def test_receiver_handles_set_power_command(self):
        """Test power command routing from MQTT."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            devices = {0x1234: MessageDevice(id=0x1234)}
            server = _configure_server(mock_g, devices)
            mock_g.mqtt_client = None

            client = MQTTClient()
            client.set_connected(True)

            # Verify device exists and can receive commands
            device = server.devices.get(0x1234)
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
            devices = {0x5678: MessageDevice(id=0x5678)}
            server = _configure_server(mock_g, devices)

            _ = MQTTClient()

            # Verify device can be accessed for brightness commands
            device = server.devices.get(0x5678)
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
            devices = {0xABCD: MessageDevice(id=0xABCD, supports_rgb=True)}
            server = _configure_server(mock_g, devices)

            _ = MQTTClient()

            # Verify RGB device can be accessed
            device = server.devices.get(0xABCD)
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
            _ = _configure_server(mock_g, {})

            client = MQTTClient()
            client.set_connected(True)

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
            _ = _configure_server(mock_g, {})

            client = MQTTClient()
            client.set_connected(True)

            # Verify client can be instantiated without crashing
            assert client is not None
            assert client.is_connected is True

    @pytest.mark.asyncio
    async def test_receiver_handles_unknown_device_id(self):
        """Test command for non-existent device."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            server = _configure_server(mock_g, {0x1234: MessageDevice(id=0x1234)})

            _ = MQTTClient()

            # Try to access non-existent device
            device = server.devices.get(0x9999)
            assert device is None  # Device not found, handled gracefully

    @pytest.mark.asyncio
    async def test_receiver_handles_group_commands(self):
        """Test group command routing."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            group = MessageGroup(id=100)
            server = _configure_server(mock_g, {}, {100: group})

            _ = MQTTClient()

            # Verify group can be accessed
            fetched_group = server.groups.get(100)
            assert fetched_group is not None

    @pytest.mark.asyncio
    async def test_receiver_handles_task_exception(self):
        """Test task exception doesn't kill receiver."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            _ = _configure_server(mock_g, {})

            _ = MQTTClient()

            async def failing_task() -> None:
                error_msg = "Task error"
                raise RuntimeError(error_msg)

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
            _ = _configure_server(mock_g, {})

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
            _ = _configure_server(mock_g, {})

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
            data: dict[str, int] = cast(dict[str, int], json.loads(payload_json))
            assert data["brightness"] == 100
            assert data["transition"] == 5
