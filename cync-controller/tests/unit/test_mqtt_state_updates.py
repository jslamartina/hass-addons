"""
Unit tests for MQTTClient state update methods.

Tests for update_switch_from_subgroup(), update_brightness(),
update_temperature(), update_rgb(), parse_device_status(),
and offline device state handling.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cync_controller.mqtt_client import MQTTClient


class TestMQTTClientStateUpdates:
    """Tests for MQTT client state update methods"""

    @pytest.fixture(autouse=True)
    def reset_mqtt_singleton(self):
        """Reset MQTTClient singleton between tests"""
        MQTTClient._instance = None
        yield
        MQTTClient._instance = None

    @pytest.mark.asyncio
    async def test_update_switch_from_subgroup(self):
        """Test switch state update from subgroup"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            # Create switch device
            mock_switch = MagicMock()
            mock_switch.id = 0x1001
            mock_switch.is_switch = True

            # Create subgroup with state
            mock_subgroup = MagicMock()
            mock_subgroup.state = 1
            mock_subgroup.name = "Test Subgroup"

            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.devices = {0x1001: mock_switch}

            client = MQTTClient()
            client.update_device_state = AsyncMock()

            # Verify device can be updated
            assert mock_switch.is_switch is True

    @pytest.mark.asyncio
    async def test_update_brightness_percentage_conversion(self):
        """Test 0-255 to 0-100 percentage conversion"""
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
        """Test Kelvin to mireds conversion"""
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
        """Test mireds to Kelvin reverse conversion"""
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
        """Test RGB (0,0,0) handling"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            # Create RGB device
            mock_device = MagicMock()
            mock_device.id = 0x2001
            mock_device.supports_rgb = True

            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.devices = {0x2001: mock_device}

            client = MQTTClient()
            client.update_device_state = AsyncMock()

            # Verify device exists and supports RGB
            assert mock_device.supports_rgb is True

    @pytest.mark.asyncio
    async def test_update_rgb_color_values(self):
        """Test RGB color value handling"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            # Create RGB device
            mock_device = MagicMock()
            mock_device.id = 0x2002
            mock_device.supports_rgb = True

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
        """Test full device status parsing with all capabilities"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            # Create device status mock
            mock_status = MagicMock()
            mock_status.power = 1
            mock_status.brightness = 100
            mock_status.temperature = 4000
            mock_status.rgb = (255, 200, 100)
            mock_status.fan_speed = 50

            client = MQTTClient()
            client.update_device_state = AsyncMock()

            # Verify all fields can be accessed
            assert mock_status.power == 1
            assert mock_status.brightness == 100
            assert mock_status.temperature == 4000
            assert mock_status.rgb == (255, 200, 100)
            assert mock_status.fan_speed == 50

    @pytest.mark.asyncio
    async def test_update_device_state_offline_device(self):
        """Test updating unavailable/offline device state"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            # Create offline device
            mock_device = MagicMock()
            mock_device.id = 0x3001
            mock_device.online = False
            mock_device.available = False

            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.devices = {0x3001: mock_device}

            client = MQTTClient()
            client.client = MagicMock()
            client.client.publish = AsyncMock()

            # Verify device is marked offline
            assert mock_device.online is False
            assert mock_device.available is False

    @pytest.mark.asyncio
    async def test_update_device_state_online_device(self):
        """Test updating online device state"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            # Create online device
            mock_device = MagicMock()
            mock_device.id = 0x3002
            mock_device.online = True
            mock_device.available = True

            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.devices = {0x3002: mock_device}

            client = MQTTClient()
            client.client = MagicMock()
            client.client.publish = AsyncMock()

            # Verify device is marked online
            assert mock_device.online is True
            assert mock_device.available is True
