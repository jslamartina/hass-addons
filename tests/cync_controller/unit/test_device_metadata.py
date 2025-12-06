"""Unit tests for device metadata and classification.

Tests device metadata access and property classification.
"""

from cync_controller.devices.base_device import CyncDevice
from cync_controller.metadata.model_info import DeviceClassification, device_type_map


class TestDeviceMetadata:
    """Tests for device metadata and classification."""

    def test_device_with_metadata(self):
        """Test device with valid type has metadata."""
        # Type 7 is a common light type in device_type_map
        device = CyncDevice(cync_id=0x1234, cync_type=7)

        if 7 in device_type_map:
            assert device.metadata is not None
            assert hasattr(device.metadata, "type")
            assert hasattr(device.metadata, "protocol")

    def test_device_without_metadata(self):
        """Test device with unknown type has no metadata."""
        # Use a type that doesn't exist in device_type_map
        device = CyncDevice(cync_id=0x1234, cync_type=99999)

        assert device.metadata is None

    def test_metadata_type_classification(self):
        """Test metadata provides device type classification."""
        # Test with a known light type
        device = CyncDevice(cync_id=0x1234, cync_type=7)

        if device.metadata:
            assert device.metadata.type in DeviceClassification


class TestCyncDevicePropertyClassification:
    """Tests for device classification properties."""

    def test_is_hvac_property(self):
        """Test is_hvac property getter and setter."""
        device = CyncDevice(cync_id=0x1234)

        # Initially should be False or None
        assert device.is_hvac in [False, None]

        # Set HVAC
        device.is_hvac = True
        assert device.is_hvac is True

        # Unset HVAC
        device.is_hvac = False
        assert device.is_hvac is False

    def test_is_light_property(self):
        """Test is_light property getter and setter."""
        device = CyncDevice(cync_id=0x1234)

        # Initially should check metadata or return False

        # Set light
        device.is_light = True
        assert device.is_light is True

        device.is_light = False
        assert device.is_light is False

    def test_is_switch_property(self):
        """Test is_switch property getter and setter."""
        device = CyncDevice(cync_id=0x1234)

        # Initially should check metadata or return False

        # Set switch
        device.is_switch = True
        assert device.is_switch is True

        device.is_switch = False
        assert device.is_switch is False

    def test_is_plug_property(self):
        """Test is_plug property getter and setter."""
        device = CyncDevice(cync_id=0x1234)

        # Initially should check metadata or return False

        # Set plug
        device.is_plug = True
        assert device.is_plug is True

        device.is_plug = False
        assert device.is_plug is False

    def test_is_fan_controller_property(self):
        """Test is_fan_controller property getter and setter."""
        device = CyncDevice(cync_id=0x1234)

        # Initially should check metadata or return False

        # Set fan controller
        device.is_fan_controller = True
        assert device.is_fan_controller is True

        device.is_fan_controller = False
        assert device.is_fan_controller is False

    def test_has_wifi_property(self):
        """Test has_wifi property."""
        device = CyncDevice(cync_id=0x1234)

        # Check has_wifi
        has_wifi = device.has_wifi
        assert isinstance(has_wifi, bool)

    def test_bt_only_property_with_specific_mac(self):
        """Test bt_only property with specific MAC address."""
        device = CyncDevice(cync_id=0x1234, wifi_mac="00:01:02:03:04:05")

        # Should be bt_only due to specific MAC
        assert device.bt_only is True

    def test_bt_only_property_with_other_mac(self):
        """Test bt_only property with other MAC address."""
        device = CyncDevice(cync_id=0x1234, wifi_mac="AA:BB:CC:DD:EE:FF")

        # Should not be bt_only with different MAC
        assert device.bt_only is False

    def test_mac_property_getter_and_setter(self):
        """Test mac property getter and setter."""
        device = CyncDevice(cync_id=0x1234, mac="AA:BB:CC:DD:EE:FF")

        # Get MAC
        assert device.mac == "AA:BB:CC:DD:EE:FF"

        # Set new MAC
        device.mac = "11:22:33:44:55:66"
        assert device.mac == "11:22:33:44:55:66"
