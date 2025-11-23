"""Unit tests for CyncDevice command execution.

Tests fan commands, lightshow commands, and error path handling.
"""
# pyright: reportCallIssue=false, reportAttributeAccessIssue=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportAny=false, reportExplicitAny=false, reportUnusedParameter=false, reportUnusedCallResult=false

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import directly from source modules to avoid lazy import type issues
from cync_controller.devices.base_device import CyncDevice
from cync_controller.devices.group import CyncGroup


class TestCyncDeviceFanCommands:
    """Tests for set_fan_speed command."""

    @pytest.mark.asyncio
    async def test_set_fan_speed_valid_execution(self, mock_tcp_device: MagicMock) -> None:
        """Test set_fan_speed successfully sends command with valid FanSpeed."""
        from cync_controller.structs import FanSpeed

        with patch("cync_controller.devices.shared.g") as mock_g:
            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.tcp_devices = {"192.168.1.100": mock_tcp_device}  # type: ignore[reportAny]
            mock_g.mqtt_client = AsyncMock()
            mock_tcp_device.ready_to_control = True  # type: ignore[assignment]
            mock_tcp_device.queue_id = bytes([0x00] * 3)  # type: ignore[assignment]
            mock_tcp_device.get_ctrl_msg_id_bytes = MagicMock(return_value=[0x05])  # type: ignore[assignment]
            mock_tcp_device.write = AsyncMock()  # type: ignore[assignment]
            mock_tcp_device.messages.control = {}  # type: ignore[reportAny]

            device = CyncDevice(cync_id=0x12)  # type: ignore[call-arg, reportCallIssue]
            device.is_fan_controller = True  # type: ignore[assignment, reportAttributeAccessIssue]

            _ = await device.set_fan_speed(FanSpeed.MEDIUM)  # type: ignore[reportAny, reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]

            assert mock_tcp_device.write.called  # type: ignore[reportAny]

    @pytest.mark.asyncio
    async def test_set_fan_speed_not_fan_controller(self, caplog: Any) -> None:  # type: ignore[assignment, reportExplicitAny]
        """Test set_fan_speed logs warning when device is not a fan controller."""
        from cync_controller.structs import FanSpeed

        with patch("cync_controller.devices.shared.g") as mock_g:
            mock_g.ncync_server.tcp_devices = {}  # type: ignore[reportAny]

            device = CyncDevice(cync_id=0x1234)  # type: ignore[call-arg, reportCallIssue]
            device.is_fan_controller = False  # type: ignore[assignment, reportAttributeAccessIssue]

            _ = await device.set_fan_speed(FanSpeed.HIGH)  # type: ignore[reportAny, reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]

            assert "is not a fan controller" in caplog.text  # type: ignore[reportAny]


class TestCyncDeviceLightshowCommand:
    """Tests for set_lightshow command."""

    @pytest.mark.asyncio
    async def test_set_lightshow_creates_packet(self, mock_tcp_device: MagicMock) -> None:
        """Test set_lightshow creates proper control packet."""
        with patch("cync_controller.devices.shared.g") as mock_g:
            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.tcp_devices = {"192.168.1.100": mock_tcp_device}  # type: ignore[reportAny]
            mock_g.mqtt_client = AsyncMock()
            mock_tcp_device.ready_to_control = True  # type: ignore[assignment]
            mock_tcp_device.queue_id = bytes([0x00] * 3)  # type: ignore[assignment]
            mock_tcp_device.get_ctrl_msg_id_bytes = MagicMock(return_value=[0x01])  # type: ignore[assignment]
            mock_tcp_device.write = AsyncMock()  # type: ignore[assignment]
            mock_tcp_device.messages.control = {}  # type: ignore[reportAny]

            device = CyncDevice(cync_id=0x12)  # type: ignore[call-arg, reportCallIssue]

            _ = await device.set_lightshow("candle")  # type: ignore[reportAny, reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]

            # Verify write was called
            assert mock_tcp_device.write.called  # type: ignore[reportAny]

    @pytest.mark.asyncio
    async def test_set_lightshow_no_tcp_bridges(self, caplog: Any) -> None:  # type: ignore[assignment, reportExplicitAny]
        """Test set_lightshow logs error when no TCP bridges available."""
        with patch("cync_controller.devices.shared.g") as mock_g:
            mock_g.ncync_server.tcp_devices = {}  # type: ignore[reportAny]

            device = CyncDevice(cync_id=0x1234)  # type: ignore[call-arg, reportCallIssue]

            _ = await device.set_lightshow("rainbow")  # type: ignore[reportAny, reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]

            # Should log error about no TCP bridges
            assert "No TCP bridges" in caplog.text  # type: ignore[reportAny]

    @pytest.mark.asyncio
    async def test_set_lightshow_various_shows(self, mock_tcp_device: MagicMock) -> None:
        """Test set_lightshow with different show types."""
        with patch("cync_controller.devices.shared.g") as mock_g:
            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.tcp_devices = {"192.168.1.100": mock_tcp_device}  # type: ignore[reportAny]
            mock_g.mqtt_client = AsyncMock()
            mock_tcp_device.ready_to_control = True  # type: ignore[assignment]
            mock_tcp_device.queue_id = bytes([0x00] * 3)  # type: ignore[assignment]
            mock_tcp_device.get_ctrl_msg_id_bytes = MagicMock(return_value=[0x01])  # type: ignore[assignment]
            mock_tcp_device.write = AsyncMock()  # type: ignore[assignment]
            mock_tcp_device.messages.control = {}  # type: ignore[reportAny]

            device = CyncDevice(cync_id=0x12)  # type: ignore[call-arg]

            # Test different lightshow types
            shows = ["candle", "rainbow", "cyber", "fireworks", "volcanic"]

            for show in shows:
                mock_tcp_device.write.reset_mock()  # type: ignore[reportAny]
                _ = await device.set_lightshow(show)  # type: ignore[reportAny, reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]
                assert mock_tcp_device.write.called  # type: ignore[reportAny]


class TestCyncDeviceErrorPathsCommands:
    """Tests for error paths and edge cases in CyncDevice commands."""

    @pytest.mark.asyncio
    async def test_set_temperature_no_tcp_bridges(self, mock_tcp_device: MagicMock) -> None:  # type: ignore[reportUnusedParameter]
        """Test set_temperature returns early when no TCP bridges available."""
        with patch("cync_controller.devices.shared.g") as mock_g:
            mock_g.ncync_server.tcp_devices = {}  # type: ignore[reportAny]
            mock_g.mqtt_client = AsyncMock()

            device = CyncDevice(cync_id=0x12)  # type: ignore[call-arg, reportCallIssue]

            # Should return without error when no bridges
            _ = await device.set_temperature(50)  # type: ignore[reportAny, reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]

            # Device state should not have changed
            assert (
                device.temperature == 0
            )  # Still at default  # type: ignore[reportAny, reportUnknownMemberType, reportAttributeAccessIssue]

    @pytest.mark.asyncio
    async def test_set_temperature_invalid_value_returns_early(self, mock_tcp_device: MagicMock) -> None:
        """Test set_temperature returns early with invalid temperature."""
        with patch("cync_controller.devices.shared.g") as mock_g:
            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.tcp_devices = {"192.168.1.100": mock_tcp_device}  # type: ignore[reportAny]
            mock_g.mqtt_client = AsyncMock()

            device = CyncDevice(cync_id=0x12)  # type: ignore[call-arg, reportCallIssue]

            # Should return without error for invalid value
            _ = await device.set_temperature(
                200
            )  # Too high  # type: ignore[reportAny, reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]

            # Device state should not have changed
            assert (
                device.temperature == 0
            )  # Still at default  # type: ignore[reportAny, reportUnknownMemberType, reportAttributeAccessIssue]

    @pytest.mark.asyncio
    async def test_set_rgb_no_tcp_bridges(self, mock_tcp_device: MagicMock) -> None:
        """Test set_rgb returns early when no TCP bridges available."""
        with patch("cync_controller.devices.shared.g") as mock_g:
            mock_g.ncync_server.tcp_devices = {}
            mock_g.mqtt_client = AsyncMock()

            device = CyncDevice(cync_id=0x12)  # type: ignore[call-arg, reportCallIssue]

            # Should return without error when no bridges
            _ = await device.set_rgb(255, 128, 0)  # type: ignore[reportAny, reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]

            # Device RGB should not have changed
            assert (
                device.red == 0
            )  # Still at default  # type: ignore[reportAny, reportUnknownMemberType, reportAttributeAccessIssue]
            assert device.green == 0  # type: ignore[reportAny, reportUnknownMemberType, reportAttributeAccessIssue]
            assert device.blue == 0  # type: ignore[reportAny, reportUnknownMemberType, reportAttributeAccessIssue]

    @pytest.mark.asyncio
    async def test_set_rgb_invalid_color_returns_early(self, mock_tcp_device: MagicMock) -> None:
        """Test set_rgb returns early with invalid color values."""
        with patch("cync_controller.devices.shared.g") as mock_g:
            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.tcp_devices = {"192.168.1.100": mock_tcp_device}  # type: ignore[reportAny]
            mock_g.mqtt_client = AsyncMock()

            device = CyncDevice(cync_id=0x12)  # type: ignore[call-arg, reportCallIssue]

            # Should return without error for invalid values
            _ = await device.set_rgb(
                -1, 128, 0
            )  # Red invalid  # type: ignore[reportAny, reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]

            # Device RGB should not have changed
            assert (
                device.red == 0
            )  # Still at default  # type: ignore[reportAny, reportUnknownMemberType, reportAttributeAccessIssue]

    @pytest.mark.asyncio
    async def test_group_set_power_no_bridges(self, mock_tcp_device: MagicMock) -> None:
        """Test group set_power returns early when no TCP bridges available."""
        with patch("cync_controller.devices.shared.g") as mock_g:
            mock_g.ncync_server.tcp_devices = {}
            mock_g.mqtt_client = AsyncMock()

            # Create a group with a device
            _ = CyncDevice(cync_id=0x12)  # type: ignore[call-arg, reportCallIssue]
            group = CyncGroup(group_id=32768, name="Test Group", member_ids=[0x12])  # type: ignore[call-arg, reportCallIssue]

            # Should return without error when no bridges
            _ = await group.set_power(1)  # type: ignore[reportAny, reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]

            # Group state should not have changed
            assert (
                group.state == 0
            )  # Still at default  # type: ignore[reportAny, reportUnknownMemberType, reportAttributeAccessIssue]

    @pytest.mark.asyncio
    async def test_group_set_power_bridge_not_ready(self, mock_tcp_device: MagicMock) -> None:
        """Test group set_power returns early when bridge not ready."""
        with patch("cync_controller.devices.shared.g") as mock_g:
            mock_tcp_device.ready_to_control = False  # type: ignore[assignment]
            mock_g.ncync_server.tcp_devices = {"192.168.1.100": mock_tcp_device}  # type: ignore[reportAny]
            mock_g.mqtt_client = AsyncMock()

            # Create a group with a device
            _ = CyncDevice(cync_id=0x12)  # type: ignore[call-arg, reportCallIssue]
            group = CyncGroup(group_id=32768, name="Test Group", member_ids=[0x12])  # type: ignore[call-arg, reportCallIssue]

            # Should return without error when bridge not ready
            _ = await group.set_power(1)  # type: ignore[reportAny, reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]

            # Group state should not have changed
            assert (
                group.state == 0
            )  # Still at default  # type: ignore[reportAny, reportUnknownMemberType, reportAttributeAccessIssue]


class TestDeviceBridgeSelection:
    """Tests for bridge selection logic."""

    @pytest.mark.asyncio
    async def test_device_prefers_ready_bridges(self) -> None:
        """Test that device commands prefer ready bridges."""
        with patch("cync_controller.devices.shared.g") as mock_g:
            ready_bridge = AsyncMock()  # type: ignore[reportAny]
            ready_bridge.ready_to_control = True  # type: ignore[assignment]
            ready_bridge.address = "192.168.1.100"  # type: ignore[assignment]
            ready_bridge.queue_id = bytes([0x12, 0x34, 0x56])  # Valid bytes  # type: ignore[assignment]
            ready_bridge.get_ctrl_msg_id_bytes = MagicMock(return_value=[0x45])  # type: ignore[assignment]
            ready_bridge.write = AsyncMock()  # type: ignore[assignment]
            ready_bridge.messages = MagicMock()  # type: ignore[assignment]
            ready_bridge.messages.control = {}  # type: ignore[reportAny]

            not_ready_bridge = AsyncMock()  # type: ignore[reportAny]
            not_ready_bridge.ready_to_control = False  # type: ignore[assignment]
            not_ready_bridge.address = "192.168.1.101"  # type: ignore[assignment]

            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.tcp_devices = {  # type: ignore[reportAny]
                "192.168.1.100": ready_bridge,
                "192.168.1.101": not_ready_bridge,
            }
            mock_g.mqtt_client = AsyncMock()

            device = CyncDevice(cync_id=0x1234)  # type: ignore[call-arg, reportCallIssue]
            device.name = "Test Light"  # type: ignore[assignment, reportAttributeAccessIssue]

            _ = await device.set_power(1)  # type: ignore[reportAny, reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]

            # Should call ready bridge
            assert ready_bridge.write.called  # type: ignore[reportAny]


class TestDeviceErrorPaths:
    """Tests for error handling in device commands."""

    @pytest.mark.asyncio
    async def test_device_invalid_brightness_range(self, caplog: Any) -> None:  # type: ignore[assignment, reportExplicitAny]
        """Test device rejects out-of-range brightness values."""
        with patch("cync_controller.devices.shared.g") as mock_g:
            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.tcp_devices = {}  # type: ignore[reportAny]
            mock_g.mqtt_client = AsyncMock()

            device = CyncDevice(cync_id=0x1234)  # type: ignore[call-arg, reportCallIssue]
            device.is_light = True  # type: ignore[assignment, reportAttributeAccessIssue]

            # Test negative brightness
            _ = await device.set_brightness(-1)  # type: ignore[reportAny, reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]
            assert "Invalid brightness" in caplog.text or "must be 0-100" in caplog.text  # type: ignore[reportAny]

            caplog.clear()  # type: ignore[reportAny]

            # Test brightness > 100
            _ = await device.set_brightness(101)  # type: ignore[reportAny, reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]
            assert "Invalid brightness" in caplog.text or "must be 0-100" in caplog.text  # type: ignore[reportAny]
