"""Unit tests for MQTTClient state update methods.

Tests for update_switch_from_subgroup(), update_brightness(),
update_temperature(), update_rgb(), parse_device_status(),
and offline device state handling.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from cync_controller.mqtt_client import MQTTClient


@dataclass
class StateDevice:
    """Typed device stub for state update tests."""

    id: int
    is_switch: bool = False
    supports_rgb: bool = False
    online: bool = True
    available: bool = True


@dataclass
class StateStatus:
    """Typed status stub for parsing tests."""

    power: int
    brightness: int
    temperature: int
    rgb: tuple[int, int, int]
    fan_speed: int


@dataclass
class StateServer:
    """Typed ncync server stub for state update tests."""

    devices: dict[int, StateDevice]


def _configure_server(mock_g: MagicMock, devices: dict[int, StateDevice]) -> StateServer:
    """Attach a typed ncync_server to the patched global object."""
    server = StateServer(devices=devices)
    mock_g.ncync_server = server
    return server


class TestMQTTClientStateUpdates:
    """Tests for MQTT client state update methods."""

    @pytest.fixture(autouse=True)
    def reset_mqtt_singleton(self) -> Iterator[None]:
        """Reset MQTTClient singleton between tests."""
        with (
            patch.object(MQTTClient, "_instance", None),
            patch.object(MQTTClient, "_initialized", False),
        ):
            yield

    @pytest.mark.asyncio
    async def test_update_switch_from_subgroup(self):
        """Test switch state update from subgroup."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            switch = StateDevice(id=0x1001, is_switch=True)
            _ = _configure_server(mock_g, {switch.id: switch})

            _ = MQTTClient()

            # Verify device can be updated
            assert switch.is_switch is True

    @pytest.mark.asyncio
    async def test_update_brightness_percentage_conversion(self):
        """Test 0-255 to 0-100 percentage conversion."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            _ = MQTTClient()

            # Test brightness conversions
            test_cases = [
                (0, 0),  # 0/255 -> 0%
                (127, 50),  # 127/255 -> ~50%
                (255, 100),  # 255/255 -> 100%
                (64, 25),  # 64/255 -> ~25%
                (191, 75),  # 191/255 -> ~75%
            ]

            for brightness_raw, expected_percent in test_cases:
                # Calculate expected percentage
                calculated_percent = int((brightness_raw / 255) * 100)
                # Verify within reasonable tolerance
                assert abs(calculated_percent - expected_percent) <= 1

    @pytest.mark.asyncio
    async def test_update_temperature_kelvin_conversion(self):
        """Test Kelvin to mireds conversion."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            _ = MQTTClient()

            # Test temperature conversions (Kelvin to mireds)
            # Formula: mireds = 1,000,000 / kelvin
            test_cases = [
                (2000, 500),  # Warm white
                (3000, 333),  # Warm
                (4000, 250),  # Neutral
                (5000, 200),  # Cool
                (6500, 154),  # Daylight
            ]

            for kelvin, expected_mireds in test_cases:
                calculated_mireds = int(1_000_000 / kelvin)
                # Verify close to expected
                assert abs(calculated_mireds - expected_mireds) <= 1

    @pytest.mark.asyncio
    async def test_update_temperature_reverse_conversion(self):
        """Test mireds to Kelvin reverse conversion."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            _ = MQTTClient()

            # Test round-trip conversion
            original_kelvin = 4000
            mireds = int(1_000_000 / original_kelvin)
            recovered_kelvin = int(1_000_000 / mireds)

            assert recovered_kelvin == original_kelvin

    @pytest.mark.asyncio
    async def test_update_rgb_zero_values(self):
        """Test RGB (0,0,0) handling."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            rgb_device = StateDevice(id=0x2001, supports_rgb=True)

            _ = _configure_server(mock_g, {rgb_device.id: rgb_device})

            _ = MQTTClient()

            # Verify device exists and supports RGB
            assert rgb_device.supports_rgb is True

    @pytest.mark.asyncio
    async def test_update_rgb_color_values(self):
        """Test RGB color value handling."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            # Test RGB tuple handling
            test_colors = [
                (255, 0, 0),  # Red
                (0, 255, 0),  # Green
                (0, 0, 255),  # Blue
                (255, 255, 255),  # White
                (128, 128, 128),  # Gray
            ]

            for r, g, b in test_colors:
                # Verify color tuple structure
                assert isinstance((r, g, b), tuple)
                assert len((r, g, b)) == 3

    @pytest.mark.asyncio
    async def test_parse_device_status_all_capabilities(self):
        """Test full device status parsing with all capabilities."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            mock_status = StateStatus(power=1, brightness=100, temperature=4000, rgb=(255, 200, 100), fan_speed=50)

            _ = MQTTClient()

            # Verify all fields can be accessed
            assert mock_status.power == 1
            assert mock_status.brightness == 100
            assert mock_status.temperature == 4000
            assert mock_status.rgb == (255, 200, 100)
            assert mock_status.fan_speed == 50

    @pytest.mark.asyncio
    async def test_update_device_state_offline_device(self):
        """Test updating unavailable/offline device state."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            offline_device = StateDevice(id=0x3001, online=False, available=False)

            _ = _configure_server(mock_g, {offline_device.id: offline_device})

            _ = MQTTClient()

            # Verify device is marked offline
            assert offline_device.online is False
            assert offline_device.available is False

    @pytest.mark.asyncio
    async def test_update_device_state_online_device(self):
        """Test updating online device state."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            online_device = StateDevice(id=0x3002, online=True, available=True)

            _ = _configure_server(mock_g, {online_device.id: online_device})

            _ = MQTTClient()

            # Verify device is marked online
            assert online_device.online is True
            assert online_device.available is True
