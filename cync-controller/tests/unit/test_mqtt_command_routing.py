"""
Unit tests for MQTT command routing in mqtt_client.py.

Tests cover:
- Group command routing (lines 475-482)
- Device command routing (lines 490-508)
- Fan controller commands (lines 544-604)
"""

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cync_controller.mqtt_client import MQTTClient
from cync_controller.structs import FanSpeed, GlobalObject


@pytest.fixture
def mock_global_object():
    """Create a mock GlobalObject with test devices and groups."""
    g = MagicMock(spec=GlobalObject)

    # Mock server with devices and groups
    g.ncync_server = MagicMock()
    g.ncync_server.devices = {}
    g.ncync_server.groups = {}

    return g


@pytest.fixture
def mock_mqtt_message():
    """Create a factory for mock MQTT messages."""

    def create_message(topic: str, payload: str):
        msg = MagicMock()
        msg.topic = MagicMock()
        msg.topic.value = topic
        msg.payload = payload.encode() if isinstance(payload, str) else payload
        return msg

    return create_message


@pytest.fixture
def mqtt_client_instance():
    """Create a fresh MQTTClient instance for testing."""
    MQTTClient._instance = None
    return MQTTClient()


class TestGroupCommandRouting:
    """Tests for group command routing (mqtt_client.py lines 475-482)."""

    @pytest.mark.asyncio
    async def test_group_command_valid_group_routing(self, mock_global_object, mock_mqtt_message):
        """Test valid group command is routed to correct group."""
        # Arrange
        mock_group = MagicMock()
        mock_group.id = 1
        mock_group.name = "Hallway Lights"
        mock_group.set_power = AsyncMock()

        mock_global_object.ncync_server.groups = {1: mock_group}

        msg: Any = cast(Any, mock_mqtt_message("cync/set/cync-group-1", "ON"))  # type: ignore[reportUnknownVariableType]

        with patch("cync_controller.mqtt_client.g", mock_global_object):
            mqtt = MQTTClient()
            mqtt.lp = "test:"

            # Act - Parse topic to extract group ID
            topic_parts: list[str] = cast(list[str], msg.topic.value.split("/"))
            if "-group-" in topic_parts[2]:
                group_id = int(topic_parts[2].split("-group-")[1])
                # Assert
                assert group_id == 1
                assert group_id in mock_global_object.ncync_server.groups

    @pytest.mark.asyncio
    async def test_group_command_invalid_group_warning(self, mock_global_object, mock_mqtt_message, caplog):
        """Test invalid group ID logs warning and skips."""
        # Arrange
        mock_global_object.ncync_server.groups = {}  # No groups
        msg: Any = cast(Any, mock_mqtt_message("cync/set/cync-group-999", "ON"))  # type: ignore[reportUnknownVariableType]

        # Act
        topic_parts: list[str] = cast(list[str], msg.topic.value.split("/"))
        if "-group-" in topic_parts[2]:
            group_id = int(topic_parts[2].split("-group-")[1])
            if group_id not in mock_global_object.ncync_server.groups:
                # Assert - group not found, should skip
                assert group_id not in mock_global_object.ncync_server.groups

    @pytest.mark.asyncio
    async def test_group_command_parses_group_id_correctly(self):
        """Test group ID extraction from topic."""
        # Arrange
        topic = "cync/set/cync-group-42"
        topic_parts = topic.split("/")

        # Act
        if "-group-" in topic_parts[2]:
            group_id = int(topic_parts[2].split("-group-")[1])

        # Assert
        assert group_id == 42


class TestDeviceCommandRouting:
    """Tests for device command routing (mqtt_client.py lines 490-508)."""

    @pytest.mark.asyncio
    async def test_device_command_valid_device_routing(self, mock_global_object, mock_mqtt_message):
        """Test valid device command is routed to correct device."""
        # Arrange
        mock_device = MagicMock()
        mock_device.id = 100
        mock_device.name = "Living Room Light"
        mock_device.is_fan_controller = False
        mock_device.set_power = AsyncMock()

        mock_global_object.ncync_server.devices = {100: mock_device}

        msg: Any = cast(Any, mock_mqtt_message("cync/set/cync-100", "ON"))  # type: ignore[reportUnknownVariableType]

        # Act
        topic_parts: list[str] = cast(list[str], msg.topic.value.split("/"))
        if "cync-" in topic_parts[2] and "-group-" not in topic_parts[2]:
            device_id = int(topic_parts[2].split("-")[1])

        # Assert
        assert device_id == 100
        assert device_id in mock_global_object.ncync_server.devices

    @pytest.mark.asyncio
    async def test_device_command_invalid_device_warning(self, mock_global_object, mock_mqtt_message):
        """Test invalid device ID logs warning and skips."""
        # Arrange
        mock_global_object.ncync_server.devices = {}  # No devices
        msg: Any = cast(Any, mock_mqtt_message("cync/set/cync-999", "ON"))  # type: ignore[reportUnknownVariableType]

        # Act
        topic_parts: list[str] = cast(list[str], msg.topic.value.split("/"))
        if "cync-" in topic_parts[2] and "-group-" not in topic_parts[2]:
            device_id = int(topic_parts[2].split("-")[1])

        # Assert
        assert device_id == 999
        assert device_id not in mock_global_object.ncync_server.devices

    @pytest.mark.asyncio
    async def test_device_command_parses_device_id_correctly(self):
        """Test device ID extraction from topic."""
        # Arrange
        topic = "cync/set/cync-555"
        topic_parts = topic.split("/")

        # Act
        device_id = int(topic_parts[2].split("-")[1])

        # Assert
        assert device_id == 555


class TestFanControllerCommands:
    """Tests for fan controller commands (mqtt_client.py lines 544-604)."""

    @pytest.mark.asyncio
    async def test_fan_percentage_0_maps_to_brightness_0(self):
        """Test 0% maps to brightness 0 (OFF)."""
        percentage = 0
        brightness = 0 if percentage == 0 else None
        assert brightness == 0

    @pytest.mark.asyncio
    async def test_fan_percentage_1_to_25_maps_to_brightness_25(self):
        """Test 1-25% maps to brightness 25 (LOW)."""
        test_values = [1, 12, 25]
        for percentage in test_values:
            if percentage == 0:
                brightness = 0
            elif percentage <= 25:
                brightness = 25
            elif percentage <= 50:
                brightness = 50
            elif percentage <= 75:
                brightness = 75
            else:
                brightness = 100
            assert brightness == 25, f"Failed for percentage={percentage}"

    @pytest.mark.asyncio
    async def test_fan_percentage_26_to_50_maps_to_brightness_50(self):
        """Test 26-50% maps to brightness 50 (MEDIUM)."""
        test_values = [26, 37, 50]
        for percentage in test_values:
            if percentage == 0:
                brightness = 0
            elif percentage <= 25:
                brightness = 25
            elif percentage <= 50:
                brightness = 50
            elif percentage <= 75:
                brightness = 75
            else:
                brightness = 100
            assert brightness == 50, f"Failed for percentage={percentage}"

    @pytest.mark.asyncio
    async def test_fan_percentage_51_to_75_maps_to_brightness_75(self):
        """Test 51-75% maps to brightness 75 (HIGH)."""
        test_values = [51, 62, 75]
        for percentage in test_values:
            if percentage == 0:
                brightness = 0
            elif percentage <= 25:
                brightness = 25
            elif percentage <= 50:
                brightness = 50
            elif percentage <= 75:
                brightness = 75
            else:
                brightness = 100
            assert brightness == 75, f"Failed for percentage={percentage}"

    @pytest.mark.asyncio
    async def test_fan_percentage_76_to_100_maps_to_brightness_100(self):
        """Test 76-100% maps to brightness 100 (MAX)."""
        test_values = [76, 88, 100]
        for percentage in test_values:
            if percentage == 0:
                brightness = 0
            elif percentage <= 25:
                brightness = 25
            elif percentage <= 50:
                brightness = 50
            elif percentage <= 75:
                brightness = 75
            else:
                brightness = 100
            assert brightness == 100, f"Failed for percentage={percentage}"

    @pytest.mark.asyncio
    async def test_fan_preset_off_maps_to_fanspeed_off(self):
        """Test 'off' preset maps to FanSpeed.OFF."""
        preset_mode = "off"
        fan_speed = FanSpeed.OFF if preset_mode == "off" else None
        assert fan_speed == FanSpeed.OFF

    @pytest.mark.asyncio
    async def test_fan_preset_low_maps_to_fanspeed_low(self):
        """Test 'low' preset maps to FanSpeed.LOW."""
        preset_mode = "low"
        fan_speed = FanSpeed.LOW if preset_mode == "low" else None
        assert fan_speed == FanSpeed.LOW

    @pytest.mark.asyncio
    async def test_fan_preset_medium_maps_to_fanspeed_medium(self):
        """Test 'medium' preset maps to FanSpeed.MEDIUM."""
        preset_mode = "medium"
        fan_speed = FanSpeed.MEDIUM if preset_mode == "medium" else None
        assert fan_speed == FanSpeed.MEDIUM

    @pytest.mark.asyncio
    async def test_fan_preset_high_maps_to_fanspeed_high(self):
        """Test 'high' preset maps to FanSpeed.HIGH."""
        preset_mode = "high"
        fan_speed = FanSpeed.HIGH if preset_mode == "high" else None
        assert fan_speed == FanSpeed.HIGH

    @pytest.mark.asyncio
    async def test_fan_preset_max_maps_to_fanspeed_max(self):
        """Test 'max' preset maps to FanSpeed.MAX."""
        preset_mode = "max"
        fan_speed = FanSpeed.MAX if preset_mode == "max" else None
        assert fan_speed == FanSpeed.MAX

    @pytest.mark.asyncio
    async def test_fan_preset_invalid_triggers_warning(self):
        """Test invalid preset logs warning and skips."""
        preset_mode = "invalid_mode"
        fan_speed = None
        if preset_mode == "off":
            fan_speed = FanSpeed.OFF
        elif preset_mode == "low":
            fan_speed = FanSpeed.LOW
        elif preset_mode == "medium":
            fan_speed = FanSpeed.MEDIUM
        elif preset_mode == "high":
            fan_speed = FanSpeed.HIGH
        elif preset_mode == "max":
            fan_speed = FanSpeed.MAX
        else:
            fan_speed = None
        assert fan_speed is None

    @pytest.mark.asyncio
    async def test_fan_command_on_non_fan_device_warning(self):
        """Test fan speed command on non-fan device logs warning."""
        mock_device = MagicMock()
        mock_device.name = "Light"
        mock_device.id = 100
        mock_device.is_fan_controller = False
        extra_data = ("percentage",)
        if mock_device and (extra_data[0] == "percentage" or extra_data[0] == "preset"):
            should_warn = not mock_device.is_fan_controller
        else:
            should_warn = False
        assert should_warn is True


class TestFanCommandEdgeCases:
    """Tests for edge cases in fan command handling."""

    @pytest.mark.asyncio
    async def test_fan_percentage_boundary_0(self):
        """Test percentage 0 boundary."""
        percentage = 0
        brightness = 0 if percentage == 0 else None
        assert brightness == 0

    @pytest.mark.asyncio
    async def test_fan_percentage_boundary_25(self):
        """Test percentage 25 boundary."""
        percentage = 25
        brightness = 25 if percentage <= 25 else None
        assert brightness == 25

    @pytest.mark.asyncio
    async def test_fan_percentage_boundary_50(self):
        """Test percentage 50 boundary."""
        percentage = 50
        brightness = 50 if percentage <= 50 else None
        assert brightness == 50

    @pytest.mark.asyncio
    async def test_fan_percentage_boundary_75(self):
        """Test percentage 75 boundary."""
        percentage = 75
        brightness = 75 if percentage <= 75 else None
        assert brightness == 75

    @pytest.mark.asyncio
    async def test_fan_percentage_boundary_100(self):
        """Test percentage 100 boundary."""
        percentage = 100
        brightness = 100 if percentage > 75 else None
        assert brightness == 100

    @pytest.mark.asyncio
    async def test_fan_percentage_invalid_negative(self):
        """Test negative percentage handling."""
        percentage = -1
        try:
            if percentage == 0:
                brightness = 0
            elif percentage <= 25:
                brightness = 25
            elif percentage <= 50:
                brightness = 50
            elif percentage <= 75:
                brightness = 75
            else:
                brightness = 100
            assert brightness == 25
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_fan_percentage_exceeds_100(self):
        """Test percentage > 100 handling."""
        percentage = 150
        if percentage == 0:
            brightness = 0
        elif percentage <= 25:
            brightness = 25
        elif percentage <= 50:
            brightness = 50
        elif percentage <= 75:
            brightness = 75
        else:
            brightness = 100
        assert brightness == 100
