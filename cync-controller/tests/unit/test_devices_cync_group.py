"""
Unit tests for devices module.

Tests CyncDevice, CyncGroup, and CyncTCPDevice classes.
"""

from typing import Any

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import directly to avoid lazy import type checking issues
from cync_controller.devices.group import CyncGroup


class TestCyncGroup:
    """Tests for CyncGroup class"""

    def test_group_init_with_required_params(self) -> None:
        """Test group initialization with required parameters"""
        group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[0x1234, 0x5678, 0x9ABC])  # type: ignore[misc]

        assert group.id == 0x5678
        assert group.name == "Living Room"
        assert group.member_ids == [0x1234, 0x5678, 0x9ABC]
        assert group.is_subgroup is False
        assert group.state == 0
        assert group.brightness == 0
        assert group.online is True

    def test_group_init_without_id_raises_error(self) -> None:
        """Test that initialization without group_id raises ValueError"""
        with pytest.raises(ValueError, match="Group ID must be provided"):
            _ = CyncGroup(group_id=None, name="Test", member_ids=[])  # pyright: ignore[reportArgumentType]

    def test_group_init_with_home_id(self) -> None:
        """Test group initialization with home_id"""
        group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[], home_id=12345)  # type: ignore

        assert group.home_id == 12345
        assert group.hass_id == "12345-group-22136"  # 0x5678 = 22136

    def test_group_init_as_subgroup(self) -> None:
        """Test subgroup initialization"""
        group = CyncGroup(group_id=0x5678, name="Desk Lights", member_ids=[0x1234, 0x5678], is_subgroup=True)  # type: ignore

        assert group.is_subgroup is True

    def test_group_state_properties(self) -> None:
        """Test group state property getters and setters"""
        group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[])  # type: ignore

        # Initial state
        assert group.state == 0
        assert group.brightness == 0
        assert group.temperature == 0

        # Set state
        group.state = 1
        group.brightness = 75
        group.temperature = 50

        assert group.state == 1
        assert group.brightness == 75
        assert group.temperature == 50

    def test_group_members_property(self) -> None:
        """Test group members property returns actual device objects"""
        with patch("cync_controller.devices.g") as mock_g:
            # Mock device registry
            mock_device1: Any = MagicMock()  # type: ignore[reportExplicitAny]
            mock_device1.id = 0x1234  # type: ignore[reportAny]

            mock_device2: Any = MagicMock()  # type: ignore[reportExplicitAny]
            mock_device2.id = 0x5678  # type: ignore[reportAny]

            mock_g.ncync_server.devices = {  # type: ignore[reportAny, reportUnknownMemberType]
                0x1234: mock_device1,
                0x5678: mock_device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])  # type: ignore

            # Get members
            members = group.members

            assert len(members) == 2
            assert mock_device1 in members
            assert mock_device2 in members

    def test_group_members_when_server_uninitialized(self) -> None:
        """members should return empty list when ncync_server is not ready"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = None  # type: ignore[reportAny]

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])  # type: ignore

            assert group.members == []

    def test_group_supports_rgb_property(self) -> None:
        """Test group supports_rgb property checks member capabilities"""
        with patch("cync_controller.devices.g") as mock_g:
            # Mock devices with RGB support
            mock_device1: Any = MagicMock()  # type: ignore[reportExplicitAny]
            mock_device1.supports_rgb = True  # type: ignore[reportAny]

            mock_device2: Any = MagicMock()  # type: ignore[reportExplicitAny]
            mock_device2.supports_rgb = False  # type: ignore[reportAny]

            mock_g.ncync_server.devices = {  # type: ignore[reportAny, reportUnknownMemberType]
                0x1234: mock_device1,
                0x5678: mock_device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])  # type: ignore

            # Group supports RGB if ANY member supports it
            assert group.supports_rgb is True

    def test_group_supports_temperature_property(self) -> None:
        """Test group supports_temperature property checks member capabilities"""
        with patch("cync_controller.devices.g") as mock_g:
            # Mock devices with temperature support
            mock_device1: Any = MagicMock()  # type: ignore[reportExplicitAny]
            mock_device1.supports_temperature = True  # type: ignore[reportAny]

            mock_device2: Any = MagicMock()  # type: ignore[reportExplicitAny]
            mock_device2.supports_temperature = False  # type: ignore[reportAny]

            mock_g.ncync_server.devices = {  # type: ignore[reportAny, reportUnknownMemberType]
                0x1234: mock_device1,
                0x5678: mock_device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])  # type: ignore

            # Group supports temperature if ANY member supports it
            assert group.supports_temperature is True

    def test_group_aggregate_member_states(self) -> None:
        """Test group state aggregation from members"""
        with patch("cync_controller.devices.g") as mock_g:
            # Mock member devices
            mock_device1: Any = MagicMock()  # type: ignore[reportExplicitAny]
            mock_device1.state = 1  # type: ignore[reportAny]  # ON
            mock_device1.brightness = 75  # type: ignore[reportAny]
            mock_device1.temperature = 50  # type: ignore[reportAny]
            mock_device1.online = True  # type: ignore[reportAny]

            mock_device2: Any = MagicMock()  # type: ignore[reportExplicitAny]
            mock_device2.state = 0  # type: ignore[reportAny]  # OFF
            mock_device2.brightness = 0  # type: ignore[reportAny]
            mock_device2.temperature = 50  # type: ignore[reportAny]
            mock_device2.online = True  # type: ignore[reportAny]

            mock_g.ncync_server.devices = {  # type: ignore[reportAny, reportUnknownMemberType]
                0x1234: mock_device1,
                0x5678: mock_device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])  # type: ignore

            # Aggregate states
            agg = group.aggregate_member_states()

            assert agg is not None
            # State: ON if ANY member is ON
            assert agg["state"] == 1
            # Brightness: average of members
            assert agg["brightness"] == 37  # (75 + 0) / 2
            # Temperature: average of members
            assert agg["temperature"] == 50
            # Online if ANY member online
            assert agg["online"] is True

    def test_group_aggregate_when_server_uninitialized(self) -> None:
        """Aggregate should safely return None when ncync_server is missing"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = None  # type: ignore[reportAny]

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])  # type: ignore

            assert group.aggregate_member_states() is None

    def test_group_aggregate_no_online_members(self) -> None:
        """Test group aggregation returns None when no members online"""
        with patch("cync_controller.devices.g") as mock_g:
            # Mock offline devices
            mock_device1: Any = MagicMock()  # type: ignore[reportExplicitAny]
            mock_device1.online = False  # type: ignore[reportAny]

            mock_device2: Any = MagicMock()  # type: ignore[reportExplicitAny]
            mock_device2.online = False  # type: ignore[reportAny]

            mock_g.ncync_server.devices = {  # type: ignore[reportAny, reportUnknownMemberType]
                0x1234: mock_device1,
                0x5678: mock_device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])  # type: ignore

            # Should return None when no online members
            agg = group.aggregate_member_states()
            assert agg is None

    @pytest.mark.asyncio
    async def test_group_set_power(self, mock_tcp_device: Any) -> None:  # type: ignore[reportExplicitAny]
        """Test group set_power command"""
        with (
            patch("cync_controller.devices.g") as mock_g,
            patch("cync_controller.devices.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_g.ncync_server.tcp_devices = {"192.168.1.100": mock_tcp_device}  # type: ignore[reportAny]
            mock_g.ncync_server.devices = {}  # type: ignore[reportAny]
            mock_g.mqtt_client = MagicMock()  # type: ignore[reportAny]
            mock_g.mqtt_client.sync_group_devices = AsyncMock()  # type: ignore[reportAny]

            mock_tcp_device.ready_to_control = True  # type: ignore[reportAny]
            mock_tcp_device.queue_id = bytes([0x00] * 3)  # type: ignore[reportAny]
            # get_ctrl_msg_id_bytes returns a list with one int element
            mock_tcp_device.get_ctrl_msg_id_bytes = MagicMock(return_value=[0x01])  # type: ignore[reportAny]
            mock_tcp_device.mesh_info = {}  # type: ignore[reportAny]
            mock_tcp_device.known_device_ids = []  # type: ignore[reportAny]
            # Make write an AsyncMock so it can be awaited
            mock_tcp_device.write = AsyncMock(return_value=True)  # type: ignore[reportAny]
            mock_tcp_device.messages = MagicMock()  # type: ignore[reportAny]
            mock_tcp_device.messages.control = {}  # type: ignore[reportAny]

            group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[0x1234, 0x5678])  # type: ignore

            # Call set_power
            _ = await group.set_power(1)

            # Verify write was called
            assert mock_tcp_device.write.called  # type: ignore[reportAny]

    @pytest.mark.asyncio
    async def test_group_set_power_invalid_state(self, caplog: Any) -> None:  # type: ignore[reportExplicitAny]
        """Test group set_power rejects invalid state values"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server.tcp_devices = {}  # type: ignore[reportAny]

            group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[])  # type: ignore

            # Invalid state (must be 0 or 1)
            _ = await group.set_power(2)

            # Should log error
            assert "Invalid state" in caplog.text

    @pytest.mark.asyncio
    async def test_group_set_brightness(self, mock_tcp_device: Any) -> None:  # type: ignore[reportExplicitAny]
        """Test group set_brightness command"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server.tcp_devices = {"192.168.1.100": mock_tcp_device}  # type: ignore[reportAny]
            mock_tcp_device.ready_to_control = True  # type: ignore[reportAny]
            mock_tcp_device.queue_id = bytes([0x00] * 3)  # type: ignore[reportAny]
            # get_ctrl_msg_id_bytes returns a list with one int element
            mock_tcp_device.get_ctrl_msg_id_bytes = MagicMock(return_value=[0x01])  # type: ignore[reportAny]
            # Make write an AsyncMock
            mock_tcp_device.write = AsyncMock()  # type: ignore[reportAny]

            group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[0x1234, 0x5678])  # type: ignore

            # Call set_brightness
            _ = await group.set_brightness(75)

            # Verify write was called
            assert mock_tcp_device.write.called  # type: ignore[reportAny]

    @pytest.mark.asyncio
    async def test_group_set_temperature_valid_execution(self, mock_tcp_device: Any) -> None:  # type: ignore[reportExplicitAny]
        """Test group set_temperature successfully sends command"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server.tcp_devices = {"192.168.1.100": mock_tcp_device}  # type: ignore[reportAny]
            mock_g.ncync_server.devices = {}  # type: ignore[reportAny]
            mock_tcp_device.ready_to_control = True  # type: ignore[reportAny]
            mock_tcp_device.queue_id = bytes([0x00] * 3)  # type: ignore[reportAny]
            mock_tcp_device.get_ctrl_msg_id_bytes = MagicMock(return_value=[0x07])  # type: ignore[reportAny]
            mock_tcp_device.write = AsyncMock(return_value=True)  # type: ignore[reportAny]
            mock_tcp_device.messages = MagicMock()  # type: ignore[reportAny]
            mock_tcp_device.messages.control = {}  # type: ignore[reportAny]

            group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[0x1234, 0x5678])  # type: ignore

            _ = await group.set_temperature(75)

            assert mock_tcp_device.write.called  # type: ignore[reportAny]

    @pytest.mark.asyncio
    async def test_group_set_temperature_invalid_value(self, caplog: Any) -> None:
        """Test group set_temperature rejects invalid temperature values"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server.tcp_devices = {}  # type: ignore[reportAny]

            group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[])  # type: ignore

            _ = await group.set_temperature(-1)
            assert "Invalid temperature" in caplog.text

            _ = await group.set_temperature(101)
            assert "Invalid temperature" in caplog.text

    @pytest.mark.asyncio
    async def test_group_set_temperature_no_tcp_bridges(self, caplog: Any) -> None:  # type: ignore[reportExplicitAny]
        """Test group set_temperature logs error when no TCP bridges available"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server.tcp_devices = {}  # type: ignore[reportAny]

            group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[])  # type: ignore

            _ = await group.set_temperature(50)

            assert "No TCP bridges available" in caplog.text


class TestCyncGroupAdvancedCommands:
    """Tests for advanced CyncGroup commands and features"""

    @pytest.mark.asyncio
    async def test_group_aggregate_with_mixed_states(self) -> None:
        """Test group aggregation with mixed member states"""
        with patch("cync_controller.devices.g") as mock_g:
            # Create group with mixed-state devices
            device1: Any = MagicMock()  # type: ignore[reportExplicitAny]
            device1.state = 1  # type: ignore[reportAny]  # ON
            device1.brightness = 100  # type: ignore[reportAny]
            device1.temperature = 50  # type: ignore[reportAny]
            device1.online = True  # type: ignore[reportAny]

            device2: Any = MagicMock()  # type: ignore[reportExplicitAny]
            device2.state = 0  # type: ignore[reportAny]  # OFF
            device2.brightness = 0  # type: ignore[reportAny]
            device2.temperature = 50  # type: ignore[reportAny]
            device2.online = True  # type: ignore[reportAny]

            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.devices = {  # type: ignore[reportAny, reportUnknownMemberType]
                0x1234: device1,
                0x5678: device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Mixed Group", member_ids=[0x1234, 0x5678])  # type: ignore

            agg = group.aggregate_member_states()

            assert agg is not None
            # State should be ON (any member is ON)
            assert agg["state"] == 1
            # Brightness should be average
            assert agg["brightness"] == 50  # (100 + 0) / 2

    @pytest.mark.asyncio
    async def test_group_aggregate_with_one_online_member(self) -> None:
        """Test group aggregation when only one member is online"""
        with patch("cync_controller.devices.g") as mock_g:
            device1: Any = MagicMock()  # type: ignore[reportExplicitAny]
            device1.state = 1  # type: ignore[reportAny]
            device1.brightness = 75  # type: ignore[reportAny]
            device1.temperature = 60  # type: ignore[reportAny]
            device1.online = True  # type: ignore[reportAny]

            device2: Any = MagicMock()  # type: ignore[reportExplicitAny]
            device2.online = False  # type: ignore[reportAny]  # Offline

            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.devices = {  # type: ignore[reportAny, reportUnknownMemberType]
                0x1234: device1,
                0x5678: device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])  # type: ignore

            agg = group.aggregate_member_states()

            assert agg is not None
            assert agg["state"] == 1
            assert agg["brightness"] == 75  # Only online member

    def test_group_supports_rgb_when_no_members(self) -> None:
        """Test group supports_rgb when group has no members"""
        group = CyncGroup(group_id=0xABCD, name="Empty Group", member_ids=[])  # type: ignore

        # Should not support RGB if no members
        assert group.supports_rgb is False

    def test_group_supports_temperature_when_no_members(self) -> None:
        """Test group supports_temperature when group has no members"""
        group = CyncGroup(group_id=0xABCD, name="Empty Group", member_ids=[])  # type: ignore

        # Should not support temperature if no members
        assert group.supports_temperature is False

    def test_group_aggregate_returns_none_when_all_offline(self) -> None:
        """Test group aggregation returns None when all members are offline"""
        with patch("cync_controller.devices.g") as mock_g:
            device1: Any = MagicMock()  # type: ignore[reportExplicitAny]
            device1.online = False  # type: ignore[reportAny]

            device2: Any = MagicMock()  # type: ignore[reportExplicitAny]
            device2.online = False  # type: ignore[reportAny]

            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.devices = {  # type: ignore[reportAny, reportUnknownMemberType]
                0x1234: device1,
                0x5678: device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Offline Group", member_ids=[0x1234, 0x5678])  # type: ignore

            agg = group.aggregate_member_states()

            # Should return None when no online members
            assert agg is None

    def test_group_aggregate_filters_invalid_temperatures(self) -> None:
        """Test group aggregation filters out invalid temperature values"""
        with patch("cync_controller.devices.g") as mock_g:
            device1: Any = MagicMock()  # type: ignore[reportExplicitAny]
            device1.state = 1  # type: ignore[reportAny]
            device1.brightness = 50  # type: ignore[reportAny]
            device1.temperature = 129  # type: ignore[reportAny]  # Special value > 100 (effect mode)
            device1.online = True  # type: ignore[reportAny]

            device2: Any = MagicMock()  # type: ignore[reportExplicitAny]
            device2.state = 1  # type: ignore[reportAny]
            device2.brightness = 50  # type: ignore[reportAny]
            device2.temperature = 50  # type: ignore[reportAny]  # Valid temperature
            device2.online = True  # type: ignore[reportAny]

            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.devices = {  # type: ignore[reportAny, reportUnknownMemberType]
                0x1234: device1,
                0x5678: device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])  # type: ignore

            agg = group.aggregate_member_states()

            assert agg is not None
            # Should only include valid temperatures (<= 100)
            assert agg["temperature"] == 50  # Should not be 90 (average of 129 and 50)

    def test_group_aggregate_averages_multiple_devices(self) -> None:
        """Test group aggregation correctly averages multiple devices"""
        with patch("cync_controller.devices.g") as mock_g:
            # Create 4 devices with different states
            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.devices = {}  # type: ignore[reportAny]

            for i, dev_id in enumerate([0x1234, 0x5678, 0x9ABC, 0xDEF0]):
                device: Any = MagicMock()  # type: ignore[reportExplicitAny]
                device.state = 1 if i % 2 == 0 else 0  # type: ignore[reportAny]  # Alternating ON/OFF
                device.brightness = (i + 1) * 25  # type: ignore[reportAny]  # 25, 50, 75, 100
                device.temperature = 60  # type: ignore[reportAny]
                device.online = True  # type: ignore[reportAny]
                mock_g.ncync_server.devices[dev_id] = device  # type: ignore[reportAny]

            group = CyncGroup(group_id=0xABCD, name="Average Group", member_ids=[0x1234, 0x5678, 0x9ABC, 0xDEF0])  # type: ignore

            agg = group.aggregate_member_states()

            assert agg is not None
            assert agg["state"] == 1  # Any member ON
            assert agg["brightness"] == 62  # (25 + 50 + 75 + 100) / 4 = 62.5 -> 62
            assert agg["temperature"] == 60  # All same

    # REMOVED: pending_command test - flag no longer exists (command queue handles throttling)

    def test_group_str_representation(self) -> None:
        """Test group __str__ and __repr__ methods"""
        group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[0x1234, 0x5678])  # type: ignore

        # Test __str__ (shows decimal ID)
        str_repr = str(group)
        assert "CyncGroup" in str_repr
        assert "22136" in str_repr  # 0x5678 = 22136 in decimal
        assert "Living Room" in str_repr

        # Test __repr__
        repr_str = repr(group)
        assert "CyncGroup" in repr_str
        assert "22136" in repr_str  # Decimal representation
        assert str(len(group.member_ids)) in repr_str


class TestCyncGroupErrorHandling:
    """Tests for error handling paths in group methods"""

    @pytest.mark.asyncio
    async def test_group_set_brightness_error_no_tcp_bridges(self, caplog: Any) -> None:  # type: ignore[reportExplicitAny]
        """Test group set_brightness logs error when no TCP bridges available"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.tcp_devices = {}  # type: ignore[reportAny]
            mock_g.ncync_server.devices = {}  # type: ignore[reportAny]
            mock_g.mqtt_client = MagicMock()  # type: ignore[reportAny]

            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[0x1234, 0x5678])  # type: ignore

            _ = await group.set_brightness(75)

            assert "No TCP bridges available" in caplog.text

    @pytest.mark.asyncio
    async def test_group_set_temperature_error_no_tcp_bridges(self, caplog: Any) -> None:  # type: ignore[reportExplicitAny]
        """Test group set_temperature logs error when no TCP bridges available"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.tcp_devices = {}  # type: ignore[reportAny]
            mock_g.ncync_server.devices = {}  # type: ignore[reportAny]
            mock_g.mqtt_client = MagicMock()  # type: ignore[reportAny]

            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[0x1234, 0x5678])  # type: ignore

            # Use a valid temperature value (0-100 range, not 0-255)
            _ = await group.set_temperature(50)

            assert "No TCP bridges available" in caplog.text

    @pytest.mark.asyncio
    async def test_group_set_temperature_invalid_value(self, caplog: Any) -> None:
        """Test group set_temperature handles invalid temperature values"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.tcp_devices = {}  # type: ignore[reportAny]
            mock_g.ncync_server.devices = {}  # type: ignore[reportAny]
            mock_g.mqtt_client = MagicMock()  # type: ignore[reportAny]

            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[0x1234])  # type: ignore

            # Test negative temperature
            _ = await group.set_temperature(-1)
            assert "Temperature must be between 0 and 255" in caplog.text or "Invalid temperature" in caplog.text

            # Reset logs
            caplog.clear()

            # Test temperature > 255
            _ = await group.set_temperature(256)
            assert "Temperature must be between 0 and 255" in caplog.text or "Invalid temperature" in caplog.text


class TestCyncGroupOperations:
    """Tests for group operation methods"""

    @pytest.mark.asyncio
    async def test_group_set_brightness_success(self) -> None:
        """Test successful group brightness command"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_bridge: Any = AsyncMock()  # type: ignore[reportExplicitAny]
            mock_bridge.ready_to_control = True  # type: ignore[reportAny]
            mock_bridge.address = "192.168.1.100"  # type: ignore[reportAny]
            mock_bridge.queue_id = b"\x12\x34\x56"  # type: ignore[reportAny]
            mock_bridge.get_ctrl_msg_id_bytes = MagicMock(return_value=[0x45])  # type: ignore[reportAny]
            mock_bridge.write = AsyncMock()  # type: ignore[reportAny]

            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.tcp_devices = {"192.168.1.100": mock_bridge}  # type: ignore[reportAny]
            mock_g.mqtt_client = MagicMock()  # type: ignore[reportAny]

            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[0x1234, 0x5678])  # type: ignore

            _ = await group.set_brightness(75)

            # Should have called bridge.write
            mock_bridge.write.assert_called_once()  # type: ignore[reportAny]

    @pytest.mark.asyncio
    async def test_group_set_brightness_bridge_not_ready(self, caplog: Any) -> None:  # type: ignore[reportExplicitAny]
        """Test group brightness when bridge not ready"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_bridge: Any = MagicMock()  # type: ignore[reportExplicitAny]
            mock_bridge.ready_to_control = False  # type: ignore[reportAny]
            mock_bridge.address = "192.168.1.100"  # type: ignore[reportAny]

            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.tcp_devices = {"192.168.1.100": mock_bridge}  # type: ignore[reportAny]
            mock_g.mqtt_client = MagicMock()  # type: ignore[reportAny]

            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[0x1234])  # type: ignore

            _ = await group.set_brightness(50)

            assert "not ready to control" in caplog.text or "No TCP bridges" in caplog.text

    @pytest.mark.asyncio
    async def test_group_set_brightness_invalid_range(self, caplog: Any) -> None:  # type: ignore[reportExplicitAny]
        """Test group brightness with out-of-range values"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.tcp_devices = {}  # type: ignore[reportAny]
            mock_g.mqtt_client = MagicMock()  # type: ignore[reportAny]

            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[0x1234])  # type: ignore

            # Test negative brightness
            _ = await group.set_brightness(-1)
            assert "Invalid brightness" in caplog.text

            caplog.clear()

            # Test brightness > 100
            _ = await group.set_brightness(101)
            assert "Invalid brightness" in caplog.text

    @pytest.mark.asyncio
    async def test_group_set_power_all_members(self) -> None:
        """Test group power command affects all member devices"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_bridge: Any = AsyncMock()  # type: ignore[reportExplicitAny]
            mock_bridge.ready_to_control = True  # type: ignore[reportAny]
            mock_bridge.address = "192.168.1.100"  # type: ignore[reportAny]
            mock_bridge.queue_id = b"\x12\x34\x56"  # type: ignore[reportAny]
            mock_bridge.get_ctrl_msg_id_bytes = MagicMock(return_value=[0x45])  # type: ignore[reportAny]
            mock_bridge.write = AsyncMock()  # type: ignore[reportAny]

            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.tcp_devices = {"192.168.1.100": mock_bridge}  # type: ignore[reportAny]
            mock_g.mqtt_client = MagicMock()  # type: ignore[reportAny]
            mock_g.mqtt_client.sync_group_devices = AsyncMock()  # type: ignore[reportAny]

            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[0x1234, 0x5678, 0x9ABC])  # type: ignore

            _ = await group.set_power(1)

            # Should have called bridge.write to send group command
            mock_bridge.write.assert_called_once()  # type: ignore[reportAny]

    @pytest.mark.asyncio
    async def test_group_aggregate_member_states_all_on(self) -> None:
        """Test group aggregation when all members are ON"""
        with patch("cync_controller.devices.g") as mock_g:
            # Create group with member devices
            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[1, 2, 3])  # type: ignore

            device1: Any = MagicMock()  # type: ignore[reportExplicitAny]
            device1.state = 1  # type: ignore[reportAny]
            device1.brightness = 80  # type: ignore[reportAny]
            device1.temperature = 50  # type: ignore[reportAny]

            device2: Any = MagicMock()  # type: ignore[reportExplicitAny]
            device2.state = 1  # type: ignore[reportAny]
            device2.brightness = 90  # type: ignore[reportAny]
            device2.temperature = 60  # type: ignore[reportAny]

            device3: Any = MagicMock()  # type: ignore[reportExplicitAny]
            device3.state = 1  # type: ignore[reportAny]
            device3.brightness = 100  # type: ignore[reportAny]
            device3.temperature = 70  # type: ignore[reportAny]

            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.devices = {1: device1, 2: device2, 3: device3}  # type: ignore[reportAny]

            result = group.aggregate_member_states()

            assert result is not None
            assert result["state"] == 1
            assert result["online"] is True
            # Brightness should be average
            assert result["brightness"] == 90

    @pytest.mark.asyncio
    async def test_group_aggregate_member_states_all_off(self) -> None:
        """Test group aggregation when all members are OFF"""
        with patch("cync_controller.devices.g") as mock_g:
            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[1, 2])  # type: ignore

            device1: Any = MagicMock()  # type: ignore[reportExplicitAny]
            device1.state = 0  # type: ignore[reportAny]
            device1.brightness = 0  # type: ignore[reportAny]
            device1.temperature = 0  # type: ignore[reportAny]

            device2: Any = MagicMock()  # type: ignore[reportExplicitAny]
            device2.state = 0  # type: ignore[reportAny]
            device2.brightness = 0  # type: ignore[reportAny]
            device2.temperature = 0  # type: ignore[reportAny]

            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.devices = {1: device1, 2: device2}  # type: ignore[reportAny]

            result = group.aggregate_member_states()

            assert result is not None
            assert result["state"] == 0

    @pytest.mark.asyncio
    async def test_group_aggregate_member_states_mixed(self) -> None:
        """Test group aggregation when members have mixed states"""
        with patch("cync_controller.devices.g") as mock_g:
            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[1, 2, 3])  # type: ignore

            device1: Any = MagicMock()  # type: ignore[reportExplicitAny]
            device1.state = 1  # type: ignore[reportAny]
            device1.brightness = 80  # type: ignore[reportAny]
            device1.temperature = 50  # type: ignore[reportAny]

            device2: Any = MagicMock()  # type: ignore[reportExplicitAny]
            device2.state = 0  # type: ignore[reportAny]
            device2.brightness = 0  # type: ignore[reportAny]
            device2.temperature = 0  # type: ignore[reportAny]

            device3: Any = MagicMock()  # type: ignore[reportExplicitAny]
            device3.state = 1  # type: ignore[reportAny]
            device3.brightness = 90  # type: ignore[reportAny]
            device3.temperature = 60  # type: ignore[reportAny]

            mock_g.ncync_server = MagicMock()  # type: ignore[reportAny]
            mock_g.ncync_server.devices = {1: device1, 2: device2, 3: device3}  # type: ignore[reportAny]

            result = group.aggregate_member_states()

            assert result is not None
            # Should aggregate based on majority or all
            assert result["brightness"] > 0  # Some devices are on
