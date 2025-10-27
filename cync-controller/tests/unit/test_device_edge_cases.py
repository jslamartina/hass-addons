"""
Unit tests for device edge cases and error paths.

Tests error handling, edge value handling, and group aggregation with edge cases.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cync_controller.devices import CyncDevice, CyncGroup
from cync_controller.metadata.model_info import device_type_map


class TestCyncDeviceErrorPaths:
    """Tests for error paths and edge cases"""

    def test_device_state_setter_with_float(self):
        """Test state setter accepts float values"""
        device = CyncDevice(cync_id=0x1234)

        # Float 1.0 should become 1
        device.state = 1.0
        assert device.state == 1

        # Float 0.0 should become 0
        device.state = 0.0
        assert device.state == 0

    def test_device_brightness_edge_values(self):
        """Test brightness with edge values 0 and 255"""
        device = CyncDevice(cync_id=0x1234)

        # Edge case: minimum brightness
        device.brightness = 0
        assert device.brightness == 0

        # Edge case: maximum brightness
        device.brightness = 255
        assert device.brightness == 255

    def test_device_temperature_edge_values(self):
        """Test temperature with edge values"""
        device = CyncDevice(cync_id=0x1234)

        # Edge case: minimum temperature
        device.temperature = 0
        assert device.temperature == 0

        # Edge case: maximum temperature
        device.temperature = 255
        assert device.temperature == 255

    def test_device_rgb_edge_values(self):
        """Test RGB with edge values 0 and 255"""
        device = CyncDevice(cync_id=0x1234)

        # All channels at minimum
        device.rgb = [0, 0, 0]
        assert device.rgb == [0, 0, 0]

        # All channels at maximum
        device.rgb = [255, 255, 255]
        assert device.rgb == [255, 255, 255]

    def test_group_aggregate_with_none_brightness(self):
        """Test group aggregation when members have None brightness"""
        with patch("cync_controller.devices.g") as mock_g:
            device1 = MagicMock()
            device1.state = 1
            device1.brightness = None  # No brightness set
            device1.temperature = 50
            device1.online = True

            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.devices = {0x1234: device1}

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234])

            agg = group.aggregate_member_states()

            assert agg is not None
            assert agg["brightness"] == 0  # None brightnesses are skipped

    def test_group_aggregate_with_partial_member_data(self):
        """Test group aggregation when some members have None values"""
        with patch("cync_controller.devices.g") as mock_g:
            device1 = MagicMock()
            device1.state = 1
            device1.brightness = 100
            device1.temperature = None  # No temperature
            device1.online = True

            device2 = MagicMock()
            device2.state = 1
            device2.brightness = 50
            device2.temperature = 60
            device2.online = True

            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.devices = {0x1234: device1, 0x5678: device2}

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])

            agg = group.aggregate_member_states()

            assert agg is not None
            assert agg["brightness"] == 75  # (100 + 50) / 2
            assert agg["temperature"] == 60  # Only one device with temperature


class TestCyncDeviceEdgeCases:
    """Tests for device edge cases"""

    def test_device_with_metadata_and_type(self):
        """Test device with both metadata and explicit type"""
        device = CyncDevice(cync_id=0x1234, cync_type=7)

        # Device should have metadata
        if 7 in device_type_map:
            assert device.metadata is not None

    def test_device_hass_id_formatting(self):
        """Test device hass_id formatting"""
        device = CyncDevice(cync_id=0x1234, home_id=12345)

        assert device.hass_id == "12345-4660"  # home_id-cync_id (0x1234 = 4660)

    def test_device_version_parsing_with_dots(self):
        """Test version parsing handles dot-separated versions"""
        device = CyncDevice(cync_id=0x1234)

        device.version = "1.2.3.4"
        # Should parse to int
        assert device.version == 1234

    def test_device_version_parsing_with_nulls(self):
        """Test version parsing handles null bytes"""
        device = CyncDevice(cync_id=0x1234)

        device.version = "1.2.3\0"
        # Should strip null bytes
        assert device.version == 123

    def test_device_initialization_with_empty_name(self):
        """Test device initialization with empty string name"""
        device = CyncDevice(cync_id=0x1234, name="")

        # Empty string name is used as-is (device does not default if name="" is provided)
        assert device.name == ""

    @pytest.mark.asyncio
    async def test_set_power_pending_command_set(self, mock_tcp_device):
        """Test set_power sets pending_command flag"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server.tcp_devices = {"192.168.1.100": mock_tcp_device}
            mock_g.mqtt_client = AsyncMock()
            mock_tcp_device.ready_to_control = True
            mock_tcp_device.queue_id = bytes([0x00] * 3)
            mock_tcp_device.get_ctrl_msg_id_bytes = MagicMock(return_value=[0x01])
            mock_tcp_device.write = AsyncMock()
            mock_tcp_device.messages.control = {}

            device = CyncDevice(cync_id=0x12)

            await device.set_power(1)

            # pending_command should be set
            assert device.pending_command is True

    @pytest.mark.asyncio
    async def test_set_power_pending_command_reset(self, mock_tcp_device):
        """Test pending_command flag is properly reset"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server.tcp_devices = {"192.168.1.100": mock_tcp_device}
            mock_g.mqtt_client = AsyncMock()
            mock_tcp_device.ready_to_control = True
            mock_tcp_device.queue_id = bytes([0x00] * 3)
            mock_tcp_device.get_ctrl_msg_id_bytes = MagicMock(return_value=[0x01])
            mock_tcp_device.write = AsyncMock()
            mock_tcp_device.messages.control = {}

            device = CyncDevice(cync_id=0x12)

            # Send command - should set flag
            await device.set_power(1)
            assert device.pending_command is True

            # Reset flag
            device.pending_command = False
            assert device.pending_command is False
