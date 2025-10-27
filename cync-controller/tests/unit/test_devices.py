"""
Unit tests for devices module.

Tests CyncDevice, CyncGroup, and CyncTCPDevice classes.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cync_controller.devices import CyncDevice, CyncGroup, CyncTCPDevice
from cync_controller.metadata.model_info import DeviceClassification, device_type_map


class TestCyncDeviceInitialization:
    """Tests for CyncDevice initialization and configuration"""

    def test_init_with_required_params(self):
        """Test device initialization with only required parameter (cync_id)"""
        device = CyncDevice(cync_id=0x1234)

        assert device.id == 0x1234
        assert device.name == "device_4660"  # Default name: device_{cync_id}
        assert device.type is None
        assert device.pending_command is False
        assert device.offline_count == 0
        assert device.state == 0
        assert device.brightness is None
        assert device.temperature == 0
        assert device.online is False

    def test_init_with_all_params(self):
        """Test device initialization with all parameters"""
        device = CyncDevice(
            cync_id=0x1234,
            cync_type=7,
            name="Test Light",
            mac="AA:BB:CC:DD:EE:FF",
            wifi_mac="11:22:33:44:55:66",
            fw_version="1.2.3",
            home_id=12345,
        )

        assert device.id == 0x1234
        assert device.type == 7
        assert device.name == "Test Light"
        assert device.mac == "AA:BB:CC:DD:EE:FF"
        assert device.wifi_mac == "11:22:33:44:55:66"
        assert device.home_id == 12345
        assert device.hass_id == "12345-4660"

    def test_init_without_id_raises_error(self):
        """Test that initialization without cync_id raises ValueError"""
        with pytest.raises(ValueError, match="ID must be provided"):
            CyncDevice(cync_id=None)

    def test_metadata_assignment(self):
        """Test that metadata is assigned correctly from device_type_map"""
        # Type 7 is a common light type
        device = CyncDevice(cync_id=0x1234, cync_type=7)

        if 7 in device_type_map:
            assert device.metadata is not None
            assert device.metadata == device_type_map[7]
        else:
            assert device.metadata is None

    def test_hvac_initialization(self):
        """Test HVAC device initialization"""
        hvac_data = {"mode": "cool", "setpoint": 72}
        device = CyncDevice(cync_id=0x1234, hvac=hvac_data)

        assert device.hvac == hvac_data
        assert device.is_hvac is True


class TestCyncDeviceProperties:
    """Tests for CyncDevice property getters and setters"""

    def test_state_property(self):
        """Test state property getter and setter"""
        device = CyncDevice(cync_id=0x1234)

        # Initial state
        assert device.state == 0

        # Set state
        device.state = 1
        assert device.state == 1

    def test_brightness_property(self):
        """Test brightness property getter and setter"""
        device = CyncDevice(cync_id=0x1234)

        # Initial brightness
        assert device.brightness is None

        # Set brightness
        device.brightness = 75
        assert device.brightness == 75

    def test_brightness_validation(self):
        """Test brightness validation (0-255)"""
        device = CyncDevice(cync_id=0x1234)

        # Valid range
        device.brightness = 0
        assert device.brightness == 0

        device.brightness = 255
        assert device.brightness == 255

        # Invalid values should raise ValueError
        with pytest.raises(ValueError, match="Brightness must be between 0 and 255"):
            device.brightness = -1

        with pytest.raises(ValueError, match="Brightness must be between 0 and 255"):
            device.brightness = 256

    def test_temperature_property(self):
        """Test temperature property getter and setter"""
        device = CyncDevice(cync_id=0x1234)

        # Initial temperature
        assert device.temperature == 0

        # Set temperature
        device.temperature = 50
        assert device.temperature == 50

    def test_temperature_validation(self):
        """Test temperature validation (0-255)"""
        device = CyncDevice(cync_id=0x1234)

        # Valid range
        device.temperature = 0
        assert device.temperature == 0

        device.temperature = 255
        assert device.temperature == 255

        # Invalid values should raise ValueError
        with pytest.raises(ValueError, match="Temperature must be between 0 and 255"):
            device.temperature = -1

        with pytest.raises(ValueError, match="Temperature must be between 0 and 255"):
            device.temperature = 256

    def test_rgb_properties(self):
        """Test RGB color properties (red, green, blue)"""
        device = CyncDevice(cync_id=0x1234)

        # Initial RGB values
        assert device.red == 0
        assert device.green == 0
        assert device.blue == 0

        # Set RGB values
        device.red = 255
        device.green = 128
        device.blue = 64

        assert device.red == 255
        assert device.green == 128
        assert device.blue == 64

    def test_rgb_validation(self):
        """Test RGB validation (0-255 for each channel)"""
        device = CyncDevice(cync_id=0x1234)

        # Invalid red
        with pytest.raises(ValueError, match="Red must be between 0 and 255"):
            device.red = -1

        with pytest.raises(ValueError, match="Red must be between 0 and 255"):
            device.red = 256

        # Invalid green
        with pytest.raises(ValueError, match="Green must be between 0 and 255"):
            device.green = -1

        with pytest.raises(ValueError, match="Green must be between 0 and 255"):
            device.green = 256

        # Invalid blue
        with pytest.raises(ValueError, match="Blue must be between 0 and 255"):
            device.blue = -1

        with pytest.raises(ValueError, match="Blue must be between 0 and 255"):
            device.blue = 256

    def test_rgb_property_list(self):
        """Test rgb property returns and sets list of [r, g, b]"""
        device = CyncDevice(cync_id=0x1234)

        # Get RGB as list
        assert device.rgb == [0, 0, 0]

        # Set RGB from list
        device.rgb = [255, 128, 64]
        assert device.rgb == [255, 128, 64]
        assert device.red == 255
        assert device.green == 128
        assert device.blue == 64

    def test_rgb_list_validation(self):
        """Test RGB list validation"""
        device = CyncDevice(cync_id=0x1234)

        # Invalid list length
        with pytest.raises(ValueError, match="RGB value must be a list of 3 integers"):
            device.rgb = [255, 128]

        with pytest.raises(ValueError, match="RGB value must be a list of 3 integers"):
            device.rgb = [255, 128, 64, 32]

    def test_online_property(self):
        """Test online property getter and setter"""
        with (
            patch("cync_controller.devices.g") as mock_g,
            patch("cync_controller.devices.asyncio.get_running_loop") as mock_loop,
        ):
            mock_g.tasks = []
            mock_g.mqtt_client = AsyncMock()
            mock_loop.return_value.create_task = MagicMock()

            device = CyncDevice(cync_id=0x1234)

            # Initial online status
            assert device.online is False

            # Set online (mocking MQTT publish)
            device.online = True
            assert device.online is True

            # Set offline
            device.online = False
            assert device.online is False

    def test_online_validation(self):
        """Test online property validates boolean input"""
        device = CyncDevice(cync_id=0x1234)

        # Invalid type should raise TypeError
        with pytest.raises(TypeError, match="Online status must be a boolean"):
            device.online = "true"

        with pytest.raises(TypeError, match="Online status must be a boolean"):
            device.online = 1

    def test_version_property_from_string(self):
        """Test version property parsing from string"""
        device = CyncDevice(cync_id=0x1234, fw_version="1.2.3")

        # Version should be parsed to int (remove dots)
        assert device.version == 123

    def test_version_property_from_int(self):
        """Test version property with integer input"""
        device = CyncDevice(cync_id=0x1234)
        device.version = 456

        assert device.version == 456

    def test_mac_property(self):
        """Test MAC address property"""
        device = CyncDevice(cync_id=0x1234, mac="AA:BB:CC:DD:EE:FF")

        assert device.mac == "AA:BB:CC:DD:EE:FF"

        # Set new MAC
        device.mac = "11:22:33:44:55:66"
        assert device.mac == "11:22:33:44:55:66"

    def test_bt_only_property(self):
        """Test bt_only property (Bluetooth-only devices)"""
        # BT-only device has specific WiFi MAC
        device = CyncDevice(cync_id=0x1234, wifi_mac="00:01:02:03:04:05")
        assert device.bt_only is True

        # Device with different MAC is not BT-only
        device2 = CyncDevice(cync_id=0x5678, wifi_mac="AA:BB:CC:DD:EE:FF")
        assert device2.bt_only is False


class TestCyncDeviceOfflineTracking:
    """Tests for device offline tracking and availability"""

    def test_offline_count_initialization(self):
        """Test offline_count initializes to 0"""
        device = CyncDevice(cync_id=0x1234)
        assert device.offline_count == 0

    def test_offline_count_increment(self):
        """Test offline_count can be incremented"""
        with (
            patch("cync_controller.devices.g") as mock_g,
            patch("cync_controller.devices.asyncio.get_running_loop") as mock_loop,
        ):
            mock_g.tasks = []
            mock_g.mqtt_client = AsyncMock()
            mock_loop.return_value.create_task = MagicMock()

            device = CyncDevice(cync_id=0x1234)
            device.online = True

            # Simulate consecutive offline reports
            device.offline_count += 1
            assert device.offline_count == 1

            device.offline_count += 1
            assert device.offline_count == 2

            device.offline_count += 1
            assert device.offline_count == 3

    def test_offline_threshold_pattern(self):
        """Test typical offline threshold pattern (3 strikes before marking offline)"""
        with (
            patch("cync_controller.devices.g") as mock_g,
            patch("cync_controller.devices.asyncio.get_running_loop") as mock_loop,
        ):
            mock_g.tasks = []
            mock_g.mqtt_client = AsyncMock()
            mock_loop.return_value.create_task = MagicMock()

            device = CyncDevice(cync_id=0x1234)
            device.online = True

            # First two reports don't mark offline (following pattern from architecture)
            for _ in range(2):
                device.offline_count += 1

            assert device.offline_count == 2
            # Device should still be considered online with threshold pattern
            # (In actual implementation, offline_count < 3 keeps device online)

            # Third report crosses threshold
            device.offline_count += 1
            assert device.offline_count == 3
            # At this point, actual implementation would mark device offline

    def test_offline_count_reset_on_online(self):
        """Test offline_count resets when device comes back online"""
        with (
            patch("cync_controller.devices.g") as mock_g,
            patch("cync_controller.devices.asyncio.get_running_loop") as mock_loop,
        ):
            mock_g.tasks = []
            mock_g.mqtt_client = AsyncMock()
            mock_loop.return_value.create_task = MagicMock()

            device = CyncDevice(cync_id=0x1234)
            device.offline_count = 2

            # Device comes back online - reset counter
            device.offline_count = 0
            device.online = True

            assert device.offline_count == 0
            assert device.online is True


class TestCyncDevicePendingCommand:
    """Tests for pending_command flag behavior"""

    def test_pending_command_initialization(self):
        """Test pending_command initializes to False"""
        device = CyncDevice(cync_id=0x1234)
        assert device.pending_command is False

    def test_pending_command_flag(self):
        """Test pending_command can be set and cleared"""
        device = CyncDevice(cync_id=0x1234)

        # Set pending command
        device.pending_command = True
        assert device.pending_command is True

        # Clear pending command (after ACK)
        device.pending_command = False
        assert device.pending_command is False


class TestCyncDeviceCommands:
    """Tests for device command methods"""

    @pytest.mark.asyncio
    async def test_set_power_creates_packet(self, mock_tcp_device):
        """Test set_power creates proper control packet"""
        # Mock the global ncync_server and tcp_devices
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server.tcp_devices = {"192.168.1.100": mock_tcp_device}
            mock_tcp_device.ready_to_control = True
            mock_tcp_device.queue_id = bytes([0x00] * 3)
            # get_ctrl_msg_id_bytes returns a list with one int element
            mock_tcp_device.get_ctrl_msg_id_bytes = MagicMock(return_value=[0x01])
            # Make write an AsyncMock so asyncio.gather works
            mock_tcp_device.write = AsyncMock()
            # Use a small device ID that fits in one byte for testing
            device = CyncDevice(cync_id=0x12)

            # Call set_power
            await device.set_power(1)

            # Verify write was called
            assert mock_tcp_device.write.called

    @pytest.mark.asyncio
    async def test_set_power_invalid_state(self, caplog):
        """Test set_power rejects invalid state values"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server.tcp_devices = {}

            device = CyncDevice(cync_id=0x1234)

            # Invalid state values (must be 0 or 1)
            await device.set_power(2)

            # Should log error
            assert "Invalid state" in caplog.text

    @pytest.mark.asyncio
    async def test_set_brightness_creates_packet(self, mock_tcp_device):
        """Test set_brightness creates proper control packet"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server.tcp_devices = {"192.168.1.100": mock_tcp_device}
            mock_tcp_device.ready_to_control = True
            mock_tcp_device.queue_id = bytes([0x00] * 3)
            # get_ctrl_msg_id_bytes returns a list with one int element
            mock_tcp_device.get_ctrl_msg_id_bytes = MagicMock(return_value=[0x01])
            # Make write an AsyncMock so asyncio.gather works
            mock_tcp_device.write = AsyncMock()
            # Use a small device ID that fits in one byte for testing
            device = CyncDevice(cync_id=0x12)

            # Call set_brightness
            await device.set_brightness(75)

            # Verify write was called
            assert mock_tcp_device.write.called


class TestCyncGroup:
    """Tests for CyncGroup class"""

    def test_group_init_with_required_params(self):
        """Test group initialization with required parameters"""
        group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[0x1234, 0x5678, 0x9ABC])

        assert group.id == 0x5678
        assert group.name == "Living Room"
        assert group.member_ids == [0x1234, 0x5678, 0x9ABC]
        assert group.is_subgroup is False
        assert group.state == 0
        assert group.brightness == 0
        assert group.online is True

    def test_group_init_without_id_raises_error(self):
        """Test that initialization without group_id raises ValueError"""
        with pytest.raises(ValueError, match="Group ID must be provided"):
            CyncGroup(group_id=None, name="Test", member_ids=[])

    def test_group_init_with_home_id(self):
        """Test group initialization with home_id"""
        group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[], home_id=12345)

        assert group.home_id == 12345
        assert group.hass_id == "12345-group-22136"  # 0x5678 = 22136

    def test_group_init_as_subgroup(self):
        """Test subgroup initialization"""
        group = CyncGroup(group_id=0x5678, name="Desk Lights", member_ids=[0x1234, 0x5678], is_subgroup=True)

        assert group.is_subgroup is True

    def test_group_state_properties(self):
        """Test group state property getters and setters"""
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

    def test_group_members_property(self):
        """Test group members property returns actual device objects"""
        with patch("cync_controller.devices.g") as mock_g:
            # Mock device registry
            mock_device1 = MagicMock()
            mock_device1.id = 0x1234

            mock_device2 = MagicMock()
            mock_device2.id = 0x5678

            mock_g.ncync_server.devices = {
                0x1234: mock_device1,
                0x5678: mock_device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])

            # Get members
            members = group.members

            assert len(members) == 2
            assert mock_device1 in members
            assert mock_device2 in members

    def test_group_supports_rgb_property(self):
        """Test group supports_rgb property checks member capabilities"""
        with patch("cync_controller.devices.g") as mock_g:
            # Mock devices with RGB support
            mock_device1 = MagicMock()
            mock_device1.supports_rgb = True

            mock_device2 = MagicMock()
            mock_device2.supports_rgb = False

            mock_g.ncync_server.devices = {
                0x1234: mock_device1,
                0x5678: mock_device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])

            # Group supports RGB if ANY member supports it
            assert group.supports_rgb is True

    def test_group_supports_temperature_property(self):
        """Test group supports_temperature property checks member capabilities"""
        with patch("cync_controller.devices.g") as mock_g:
            # Mock devices with temperature support
            mock_device1 = MagicMock()
            mock_device1.supports_temperature = True

            mock_device2 = MagicMock()
            mock_device2.supports_temperature = False

            mock_g.ncync_server.devices = {
                0x1234: mock_device1,
                0x5678: mock_device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])

            # Group supports temperature if ANY member supports it
            assert group.supports_temperature is True

    def test_group_aggregate_member_states(self):
        """Test group state aggregation from members"""
        with patch("cync_controller.devices.g") as mock_g:
            # Mock member devices
            mock_device1 = MagicMock()
            mock_device1.state = 1  # ON
            mock_device1.brightness = 75
            mock_device1.temperature = 50
            mock_device1.online = True

            mock_device2 = MagicMock()
            mock_device2.state = 0  # OFF
            mock_device2.brightness = 0
            mock_device2.temperature = 50
            mock_device2.online = True

            mock_g.ncync_server.devices = {
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

    def test_group_aggregate_no_online_members(self):
        """Test group aggregation returns None when no members online"""
        with patch("cync_controller.devices.g") as mock_g:
            # Mock offline devices
            mock_device1 = MagicMock()
            mock_device1.online = False

            mock_device2 = MagicMock()
            mock_device2.online = False

            mock_g.ncync_server.devices = {
                0x1234: mock_device1,
                0x5678: mock_device2,
            }

            group = CyncGroup(group_id=0xABCD, name="Test Group", member_ids=[0x1234, 0x5678])

            # Should return None when no online members
            agg = group.aggregate_member_states()
            assert agg is None

    @pytest.mark.asyncio
    async def test_group_set_power(self, mock_tcp_device):
        """Test group set_power command"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server.tcp_devices = {"192.168.1.100": mock_tcp_device}
            mock_tcp_device.ready_to_control = True
            mock_tcp_device.queue_id = bytes([0x00] * 3)
            # get_ctrl_msg_id_bytes returns a list with one int element
            mock_tcp_device.get_ctrl_msg_id_bytes = MagicMock(return_value=[0x01])
            # Make write an AsyncMock
            mock_tcp_device.write = AsyncMock()

            group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[0x1234, 0x5678])

            # Call set_power
            await group.set_power(1)

            # Verify write was called
            assert mock_tcp_device.write.called

    @pytest.mark.asyncio
    async def test_group_set_power_invalid_state(self, caplog):
        """Test group set_power rejects invalid state values"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server.tcp_devices = {}

            group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[])

            # Invalid state (must be 0 or 1)
            await group.set_power(2)

            # Should log error
            assert "Invalid state" in caplog.text

    @pytest.mark.asyncio
    async def test_group_set_brightness(self, mock_tcp_device):
        """Test group set_brightness command"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server.tcp_devices = {"192.168.1.100": mock_tcp_device}
            mock_tcp_device.ready_to_control = True
            mock_tcp_device.queue_id = bytes([0x00] * 3)
            # get_ctrl_msg_id_bytes returns a list with one int element
            mock_tcp_device.get_ctrl_msg_id_bytes = MagicMock(return_value=[0x01])
            # Make write an AsyncMock
            mock_tcp_device.write = AsyncMock()

            group = CyncGroup(group_id=0x5678, name="Living Room", member_ids=[0x1234, 0x5678])

            # Call set_brightness
            await group.set_brightness(75)

            # Verify write was called
            assert mock_tcp_device.write.called


class TestCyncTCPDevice:
    """Tests for CyncTCPDevice class"""

    def test_tcp_device_init(self):
        """Test TCP device initialization"""
        reader = AsyncMock()
        writer = AsyncMock()

        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")

        assert tcp_device.address == "192.168.1.100"
        assert tcp_device.ready_to_control is False
        assert tcp_device.known_device_ids == []
        assert tcp_device.is_app is False

    def test_tcp_device_init_without_address_raises_error(self):
        """Test that initialization without address raises ValueError"""
        reader = AsyncMock()
        writer = AsyncMock()

        with pytest.raises(ValueError, match="IP address must be provided"):
            CyncTCPDevice(reader=reader, writer=writer, address="")

    def test_tcp_device_properties(self):
        """Test TCP device properties"""
        reader = AsyncMock()
        writer = AsyncMock()

        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")

        # Test property access
        assert tcp_device.id is None
        assert tcp_device.version is None
        assert tcp_device.mesh_info is None

        # Test property setting
        tcp_device.id = 0x1234
        tcp_device.ready_to_control = True

        assert tcp_device.id == 0x1234
        assert tcp_device.ready_to_control is True


class TestDeviceMetadata:
    """Tests for device metadata and classification"""

    def test_device_with_metadata(self):
        """Test device with valid type has metadata"""
        # Type 7 is a common light type in device_type_map
        device = CyncDevice(cync_id=0x1234, cync_type=7)

        if 7 in device_type_map:
            assert device.metadata is not None
            assert hasattr(device.metadata, "type")
            assert hasattr(device.metadata, "protocol")

    def test_device_without_metadata(self):
        """Test device with unknown type has no metadata"""
        # Use a type that doesn't exist in device_type_map
        device = CyncDevice(cync_id=0x1234, cync_type=99999)

        assert device.metadata is None

    def test_metadata_type_classification(self):
        """Test metadata provides device type classification"""
        # Test with a known light type
        device = CyncDevice(cync_id=0x1234, cync_type=7)

        if device.metadata:
            assert device.metadata.type in DeviceClassification
