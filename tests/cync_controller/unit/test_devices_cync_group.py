"""Unit tests for devices module.

Tests CyncDevice, CyncGroup, and CyncTCPDevice classes.
"""

from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from _pytest.logging import LogCaptureFixture

# Import directly to avoid lazy import type checking issues
from cync_controller.devices.group import CyncGroup
from cync_controller.structs import CyncDeviceProtocol, CyncTCPDeviceProtocol, Messages, NCyncServerProtocol


def _configure_globals(mock_g: MagicMock) -> NCyncServerProtocol:
    """Initialize a typed ncync_server on the patched global."""
    server: NCyncServerProtocol = cast(NCyncServerProtocol, MagicMock(spec=NCyncServerProtocol))
    server.devices = {}
    server.groups = {}
    server.tcp_devices = {}
    server.running = True
    server.primary_tcp_device = None
    server.start_task = None
    mock_g.ncync_server = server
    mock_g.mqtt_client = AsyncMock()
    return server


def _make_device(**attrs: object) -> CyncDeviceProtocol:
    """Create a typed device mock with provided attributes."""
    device = cast(CyncDeviceProtocol, MagicMock(spec=CyncDeviceProtocol))
    for key, value in attrs.items():
        setattr(device, key, value)
    return device


def _prepare_tcp_bridge(tcp_device: CyncTCPDeviceProtocol, msg_id_bytes: list[int]) -> AsyncMock:
    """Configure common TCP bridge attributes for group command tests."""
    tcp_device.ready_to_control = True
    tcp_device.queue_id = bytes([0x00] * 3)
    tcp_device.get_ctrl_msg_id_bytes = MagicMock(return_value=msg_id_bytes)
    tcp_device.messages = Messages()
    write_mock: AsyncMock = AsyncMock()
    tcp_device.write = write_mock
    return write_mock


class TestCyncGroup:
    """Tests for CyncGroup class."""

    def test_group_init_with_required_params(self) -> None:
        """Test group initialization with required parameters."""
        group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[0x1234, 0x5678, 0x9ABC])

        assert group.id == 0x5678
        assert group.name == "Living Room"
        assert group.member_ids == [0x1234, 0x5678, 0x9ABC]
        assert group.is_subgroup is False
        assert group.state == 0
        assert group.brightness == 0
        assert group.online is True

    def test_group_init_without_id_raises_error(self) -> None:
        """Test that initialization without group_id raises ValueError."""
        with pytest.raises(ValueError, match="Group ID must be provided"):
            _ = CyncGroup(group_id=cast(int, cast(object, None)), name="Test", member_ids=[])

    def test_group_init_with_home_id(self) -> None:
        """Test group initialization with home_id."""
        group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[], home_id=12345)

        assert group.home_id == 12345
        assert group.hass_id == "12345-group-22136"  # 0x5678 = 22136

    def test_group_init_as_subgroup(self) -> None:
        """Test subgroup initialization."""
        group = CyncGroup(group_id=0x5678, name="Desk Lights", member_ids=[0x1234, 0x5678], is_subgroup=True)

        assert group.is_subgroup is True

    def test_group_state_properties(self) -> None:
        """Test group state property getters and setters."""
        group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[])

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
        """Test group members property returns actual device objects."""
        with patch("cync_controller.devices.g") as mock_g:
            # Mock device registry
            server = _configure_globals(mock_g)
            mock_device1 = _make_device(id=0x1234)
            mock_device2 = _make_device(id=0x5678)

            server.devices = {
                0x1234: mock_device1,
                0x5678: mock_device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])

            # Get members
            members = group.members

            assert len(members) == 2
            assert mock_device1 in members
            assert mock_device2 in members

    def test_group_members_when_server_uninitialized(self) -> None:
        """Members should return empty list when ncync_server is not ready."""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = None

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])

            assert group.members == []

    def test_group_supports_rgb_property(self) -> None:
        """Test group supports_rgb property checks member capabilities."""
        with patch("cync_controller.devices.g") as mock_g:
            # Mock devices with RGB support
            server = _configure_globals(mock_g)
            mock_device1 = _make_device(supports_rgb=True)
            mock_device2 = _make_device(supports_rgb=False)

            server.devices = {
                0x1234: mock_device1,
                0x5678: mock_device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])

            # Group supports RGB if ANY member supports it
            assert group.supports_rgb is True

    def test_group_supports_temperature_property(self) -> None:
        """Test group supports_temperature property checks member capabilities."""
        with patch("cync_controller.devices.g") as mock_g:
            # Mock devices with temperature support
            server = _configure_globals(mock_g)
            mock_device1 = _make_device(supports_temperature=True)
            mock_device2 = _make_device(supports_temperature=False)

            server.devices = {
                0x1234: mock_device1,
                0x5678: mock_device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])

            # Group supports temperature if ANY member supports it
            assert group.supports_temperature is True

    def test_group_aggregate_member_states(self) -> None:
        """Test group state aggregation from members."""
        with patch("cync_controller.devices.g") as mock_g:
            # Mock member devices
            server = _configure_globals(mock_g)
            mock_device1 = _make_device(state=1, brightness=75, temperature=50, online=True)
            mock_device2 = _make_device(state=0, brightness=0, temperature=50, online=True)

            server.devices = {
                0x1234: mock_device1,
                0x5678: mock_device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])

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
        """Aggregate should safely return None when ncync_server is missing."""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = None

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])

            assert group.aggregate_member_states() is None

    def test_group_aggregate_no_online_members(self) -> None:
        """Test group aggregation returns None when no members online."""
        with patch("cync_controller.devices.g") as mock_g:
            # Mock offline devices
            server = _configure_globals(mock_g)
            mock_device1 = _make_device(online=False)
            mock_device2 = _make_device(online=False)

            server.devices = {
                0x1234: mock_device1,
                0x5678: mock_device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])

            # Should return None when no online members
            agg = group.aggregate_member_states()
            assert agg is None

    @pytest.mark.asyncio
    async def test_group_set_power(self, mock_tcp_device: MagicMock) -> None:
        """Test group set_power command."""
        with (
            patch("cync_controller.devices.g") as mock_g,
            patch("cync_controller.devices.asyncio.sleep", new_callable=AsyncMock),
        ):
            server = _configure_globals(mock_g)
            tcp_device = cast(CyncTCPDeviceProtocol, mock_tcp_device)
            server.tcp_devices = {"192.168.1.100": tcp_device}
            server.devices = {}
            mqtt_client = cast(AsyncMock, mock_g.mqtt_client)
            mqtt_client.sync_group_devices = AsyncMock()

            tcp_device.mesh_info = None
            tcp_device.known_device_ids = []
            write_mock = _prepare_tcp_bridge(tcp_device, [0x01])

            group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[0x1234, 0x5678])

            # Call set_power
            _ = await group.set_power(1)

            # Verify write was called
            assert write_mock.called

    @pytest.mark.asyncio
    async def test_group_set_power_invalid_state(self, caplog: LogCaptureFixture) -> None:
        """Test group set_power rejects invalid state values."""
        with patch("cync_controller.devices.g") as mock_g:
            server = _configure_globals(mock_g)
            server.tcp_devices = {}

            group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[])

            # Invalid state (must be 0 or 1)
            _ = await group.set_power(2)

            # Should log error
            assert "Invalid state" in caplog.text

    @pytest.mark.asyncio
    async def test_group_set_brightness(self, mock_tcp_device: MagicMock) -> None:
        """Test group set_brightness command."""
        with patch("cync_controller.devices.g") as mock_g:
            server = _configure_globals(mock_g)
            tcp_device = cast(CyncTCPDeviceProtocol, mock_tcp_device)
            server.tcp_devices = {"192.168.1.100": tcp_device}
            write_mock = _prepare_tcp_bridge(tcp_device, [0x01])

            group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[0x1234, 0x5678])

            # Call set_brightness
            _ = await group.set_brightness(75)

            # Verify write was called
            assert write_mock.called

    @pytest.mark.asyncio
    async def test_group_set_temperature_valid_execution(self, mock_tcp_device: MagicMock) -> None:
        """Test group set_temperature successfully sends command."""
        with patch("cync_controller.devices.g") as mock_g:
            server = _configure_globals(mock_g)
            tcp_device = cast(CyncTCPDeviceProtocol, mock_tcp_device)
            server.tcp_devices = {"192.168.1.100": tcp_device}
            server.devices = {}
            write_mock = _prepare_tcp_bridge(tcp_device, [0x07])

            group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[0x1234, 0x5678])

            _ = await group.set_temperature(75)

            assert write_mock.called

    @pytest.mark.asyncio
    async def test_group_set_temperature_invalid_value(self, caplog: LogCaptureFixture) -> None:
        """Test group set_temperature rejects invalid temperature values."""
        with patch("cync_controller.devices.g") as mock_g:
            server = _configure_globals(mock_g)
            server.tcp_devices = {}

            group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[])

            _ = await group.set_temperature(-1)
            assert "Invalid temperature" in caplog.text

            _ = await group.set_temperature(101)
            assert "Invalid temperature" in caplog.text

    @pytest.mark.asyncio
    async def test_group_set_temperature_no_tcp_bridges(self, caplog: LogCaptureFixture) -> None:
        """Test group set_temperature logs error when no TCP bridges available."""
        with patch("cync_controller.devices.g") as mock_g:
            server = _configure_globals(mock_g)
            server.tcp_devices = {}

            group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[])

            _ = await group.set_temperature(50)

            assert "No TCP bridges available" in caplog.text


class TestCyncGroupAdvancedCommands:
    """Tests for advanced CyncGroup commands and features."""

    @pytest.mark.asyncio
    async def test_group_aggregate_with_mixed_states(self) -> None:
        """Test group aggregation with mixed member states."""
        with patch("cync_controller.devices.g") as mock_g:
            # Create group with mixed-state devices
            server = _configure_globals(mock_g)
            device1 = _make_device(state=1, brightness=100, temperature=50, online=True)
            device2 = _make_device(state=0, brightness=0, temperature=50, online=True)

            server.devices = {
                0x1234: device1,
                0x5678: device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Mixed Group", member_ids=[0x1234, 0x5678])

            agg = group.aggregate_member_states()

            assert agg is not None
            # State should be ON (any member is ON)
            assert agg["state"] == 1
            # Brightness should be average
            assert agg["brightness"] == 50  # (100 + 0) / 2

    @pytest.mark.asyncio
    async def test_group_aggregate_with_one_online_member(self) -> None:
        """Test group aggregation when only one member is online."""
        with patch("cync_controller.devices.g") as mock_g:
            server = _configure_globals(mock_g)
            device1 = _make_device(state=1, brightness=75, temperature=60, online=True)
            device2 = _make_device(online=False)

            server.devices = {
                0x1234: device1,
                0x5678: device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])

            agg = group.aggregate_member_states()

            assert agg is not None
            assert agg["state"] == 1
            assert agg["brightness"] == 75  # Only online member

    def test_group_supports_rgb_when_no_members(self) -> None:
        """Test group supports_rgb when group has no members."""
        group = CyncGroup(group_id=0xABCD, name="Empty Group", member_ids=[])

        # Should not support RGB if no members
        assert group.supports_rgb is False

    def test_group_supports_temperature_when_no_members(self) -> None:
        """Test group supports_temperature when group has no members."""
        group = CyncGroup(group_id=0xABCD, name="Empty Group", member_ids=[])

        # Should not support temperature if no members
        assert group.supports_temperature is False

    def test_group_aggregate_returns_none_when_all_offline(self) -> None:
        """Test group aggregation returns None when all members are offline."""
        with patch("cync_controller.devices.g") as mock_g:
            server = _configure_globals(mock_g)
            device1 = _make_device(online=False)
            device2 = _make_device(online=False)

            server.devices = {
                0x1234: device1,
                0x5678: device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Offline Group", member_ids=[0x1234, 0x5678])

            agg = group.aggregate_member_states()

            # Should return None when no online members
            assert agg is None

    def test_group_aggregate_filters_invalid_temperatures(self) -> None:
        """Test group aggregation filters out invalid temperature values."""
        with patch("cync_controller.devices.g") as mock_g:
            server = _configure_globals(mock_g)
            device1 = _make_device(state=1, brightness=50, temperature=129, online=True)
            device2 = _make_device(state=1, brightness=50, temperature=50, online=True)

            server.devices = {
                0x1234: device1,
                0x5678: device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])

            agg = group.aggregate_member_states()

            assert agg is not None
            # Should only include valid temperatures (<= 100)
            assert agg["temperature"] == 50  # Should not be 90 (average of 129 and 50)

    def test_group_aggregate_averages_multiple_devices(self) -> None:
        """Test group aggregation correctly averages multiple devices."""
        with patch("cync_controller.devices.g") as mock_g:
            # Create 4 devices with different states
            server = _configure_globals(mock_g)
            server.devices = {}

            for i, dev_id in enumerate([0x1234, 0x5678, 0x9ABC, 0xDEF0]):
                device = _make_device(
                    state=1 if i % 2 == 0 else 0,
                    brightness=(i + 1) * 25,
                    temperature=60,
                    online=True,
                )
                server.devices[dev_id] = device

            group = CyncGroup(group_id=0xABCD, name="Average Group", member_ids=[0x1234, 0x5678, 0x9ABC, 0xDEF0])

            agg = group.aggregate_member_states()

            assert agg is not None
            assert agg["state"] == 1  # Any member ON
            assert agg["brightness"] == 62  # (25 + 50 + 75 + 100) / 4 = 62.5 -> 62
            assert agg["temperature"] == 60  # All same

    # REMOVED: pending_command test - flag no longer exists (command queue handles throttling)

    def test_group_str_representation(self) -> None:
        """Test group __str__ and __repr__ methods."""
        group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[0x1234, 0x5678])

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
    """Tests for error handling paths in group methods."""

    @pytest.mark.asyncio
    async def test_group_set_brightness_error_no_tcp_bridges(self, caplog: LogCaptureFixture) -> None:
        """Test group set_brightness logs error when no TCP bridges available."""
        with patch("cync_controller.devices.g") as mock_g:
            server = _configure_globals(mock_g)
            server.tcp_devices = {}
            server.devices = {}

            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[0x1234, 0x5678])

            _ = await group.set_brightness(75)

            assert "No TCP bridges available" in caplog.text

    @pytest.mark.asyncio
    async def test_group_set_temperature_error_no_tcp_bridges(self, caplog: LogCaptureFixture) -> None:
        """Test group set_temperature logs error when no TCP bridges available."""
        with patch("cync_controller.devices.g") as mock_g:
            server = _configure_globals(mock_g)
            server.tcp_devices = {}
            server.devices = {}

            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[0x1234, 0x5678])

            # Use a valid temperature value (0-100 range, not 0-255)
            _ = await group.set_temperature(50)

            assert "No TCP bridges available" in caplog.text

    @pytest.mark.asyncio
    async def test_group_set_temperature_invalid_value(self, caplog: LogCaptureFixture) -> None:
        """Test group set_temperature handles invalid temperature values."""
        with patch("cync_controller.devices.g") as mock_g:
            server = _configure_globals(mock_g)
            server.tcp_devices = {}
            server.devices = {}

            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[0x1234])

            # Test negative temperature
            _ = await group.set_temperature(-1)
            assert "Temperature must be between 0 and 255" in caplog.text or "Invalid temperature" in caplog.text

            # Reset logs
            caplog.clear()

            # Test temperature > 255
            _ = await group.set_temperature(256)
            assert "Temperature must be between 0 and 255" in caplog.text or "Invalid temperature" in caplog.text


class TestCyncGroupOperations:
    """Tests for group operation methods."""

    @pytest.mark.asyncio
    async def test_group_set_brightness_success(self) -> None:
        """Test successful group brightness command."""
        with patch("cync_controller.devices.g") as mock_g:
            server = _configure_globals(mock_g)
            bridge = cast(CyncTCPDeviceProtocol, AsyncMock())
            bridge.address = "192.168.1.100"
            write_mock = _prepare_tcp_bridge(bridge, [0x45])
            server.tcp_devices = {"192.168.1.100": bridge}

            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[0x1234, 0x5678])

            _ = await group.set_brightness(75)

            # Should have called bridge.write
            write_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_group_set_brightness_bridge_not_ready(self, caplog: LogCaptureFixture) -> None:
        """Test group brightness when bridge not ready."""
        with patch("cync_controller.devices.g") as mock_g:
            server = _configure_globals(mock_g)
            bridge = cast(CyncTCPDeviceProtocol, MagicMock(spec=CyncTCPDeviceProtocol))
            bridge.ready_to_control = False
            bridge.address = "192.168.1.100"

            server.tcp_devices = {"192.168.1.100": bridge}

            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[0x1234])

            _ = await group.set_brightness(50)

            assert "not ready to control" in caplog.text or "No TCP bridges" in caplog.text

    @pytest.mark.asyncio
    async def test_group_set_brightness_invalid_range(self, caplog: LogCaptureFixture) -> None:
        """Test group brightness with out-of-range values."""
        with patch("cync_controller.devices.g") as mock_g:
            server = _configure_globals(mock_g)
            server.tcp_devices = {}

            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[0x1234])

            # Test negative brightness
            _ = await group.set_brightness(-1)
            assert "Invalid brightness" in caplog.text

            caplog.clear()

            # Test brightness > 100
            _ = await group.set_brightness(101)
            assert "Invalid brightness" in caplog.text

    @pytest.mark.asyncio
    async def test_group_set_power_all_members(self) -> None:
        """Test group power command affects all member devices."""
        with patch("cync_controller.devices.g") as mock_g:
            server = _configure_globals(mock_g)
            bridge = cast(CyncTCPDeviceProtocol, AsyncMock())
            bridge.address = "192.168.1.100"
            write_mock = _prepare_tcp_bridge(bridge, [0x45])
            server.tcp_devices = {"192.168.1.100": bridge}
            mqtt_client = cast(AsyncMock, mock_g.mqtt_client)
            mqtt_client.sync_group_devices = AsyncMock()

            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[0x1234, 0x5678, 0x9ABC])

            _ = await group.set_power(1)

            # Should have called bridge.write to send group command
            write_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_group_aggregate_member_states_all_on(self) -> None:
        """Test group aggregation when all members are ON."""
        with patch("cync_controller.devices.g") as mock_g:
            # Create group with member devices
            server = _configure_globals(mock_g)
            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[1, 2, 3])

            device1 = _make_device(state=1, brightness=80, temperature=50)
            device2 = _make_device(state=1, brightness=90, temperature=60)
            device3 = _make_device(state=1, brightness=100, temperature=70)

            server.devices = {1: device1, 2: device2, 3: device3}

            result = group.aggregate_member_states()

            assert result is not None
            assert result["state"] == 1
            assert result["online"] is True
            # Brightness should be average
            assert result["brightness"] == 90

    @pytest.mark.asyncio
    async def test_group_aggregate_member_states_all_off(self) -> None:
        """Test group aggregation when all members are OFF."""
        with patch("cync_controller.devices.g") as mock_g:
            server = _configure_globals(mock_g)
            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[1, 2])

            device1 = _make_device(state=0, brightness=0, temperature=0)
            device2 = _make_device(state=0, brightness=0, temperature=0)

            server.devices = {1: device1, 2: device2}

            result = group.aggregate_member_states()

            assert result is not None
            assert result["state"] == 0

    @pytest.mark.asyncio
    async def test_group_aggregate_member_states_mixed(self) -> None:
        """Test group aggregation when members have mixed states."""
        with patch("cync_controller.devices.g") as mock_g:
            server = _configure_globals(mock_g)
            group = CyncGroup(group_id=0x5678, name="Test Group", member_ids=[1, 2, 3])

            device1 = _make_device(state=1, brightness=80, temperature=50)
            device2 = _make_device(state=0, brightness=0, temperature=0)
            device3 = _make_device(state=1, brightness=90, temperature=60)

            server.devices = {1: device1, 2: device2, 3: device3}

            result = group.aggregate_member_states()

            assert result is not None
            # Should aggregate based on majority or all
            assert result["brightness"] > 0  # Some devices are on
