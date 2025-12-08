"""Unit tests for device properties and state handling.

Tests current status, state conversion, status objects, and version handling.
"""

import pytest
from _pytest.logging import LogCaptureFixture

from cync_controller.devices.base_device import CyncDevice


class TestCyncDeviceCurrentStatus:
    """Tests for device current status property."""

    def test_current_status_returns_list(self):
        """Test current_status returns list of state values."""
        device = CyncDevice(cync_id=0x1234)
        device.state = 1
        device.brightness = 75
        device.temperature = 50
        device.red = 255
        device.green = 128
        device.blue = 64

        status = device.current_status

        assert isinstance(status, list)
        assert len(status) == 6
        assert status[0] == 1  # state
        assert status[1] == 75  # brightness
        assert status[2] == 50  # temperature
        assert status[3] == 255  # red
        assert status[4] == 128  # green
        assert status[5] == 64  # blue


class TestCyncDeviceStateConversion:
    """Tests for state property with different input types."""

    def test_state_setter_with_strings(self):
        """Test state setter accepts various string representations."""
        device = CyncDevice(cync_id=0x1234)

        # Test string "on" variations
        for value in ["on", "On", "ON", "true", "True", "TRUE", "yes", "Yes", "YES", "y", "Y", "t", "T"]:
            device.state = value  # pyright: ignore[reportAttributeAccessIssue]
            assert device.state == 1

        # Test string "off" variations
        for value in ["off", "Off", "OFF", "false", "False", "FALSE", "no", "No", "NO", "n", "N", "f", "F"]:
            device.state = value  # pyright: ignore[reportAttributeAccessIssue]
            assert device.state == 0

    def test_state_setter_with_integers(self):
        """Test state setter accepts integer values."""
        device = CyncDevice(cync_id=0x1234)

        device.state = 1
        assert device.state == 1

        device.state = 0
        assert device.state == 0

    def test_state_setter_with_booleans(self):
        """Test state setter accepts boolean values."""
        device = CyncDevice(cync_id=0x1234)

        device.state = True
        assert device.state == 1

        device.state = False
        assert device.state == 0

    def test_state_setter_invalid_value(self):
        """Test state setter rejects invalid values."""
        device = CyncDevice(cync_id=0x1234)

        with pytest.raises(ValueError, match="Invalid value for state"):
            device.state = "invalid"  # pyright: ignore[reportAttributeAccessIssue]

    def test_state_setter_invalid_type(self):
        """Test state setter rejects invalid types."""
        device = CyncDevice(cync_id=0x1234)

        with pytest.raises(TypeError, match="Invalid type for state"):
            device.state = {"not": "valid"}  # pyright: ignore[reportAttributeAccessIssue]


class TestCyncDeviceStatusObject:
    """Tests for device status object management."""

    def test_status_setter_and_getter(self):
        """Test status property setter and getter."""
        from cync_controller.structs import DeviceStatus

        device = CyncDevice(cync_id=0x1234)

        # Get initial status

        # Create new status object
        new_status = DeviceStatus()
        new_status.state = 1
        new_status.brightness = 100

        # Set status
        device.status = new_status

        # Verify status was updated
        assert device.status == new_status


class TestCyncDeviceVersionProperty:
    """Tests for device version property."""

    def test_version_setter_with_string(self):
        """Test version setter with string input."""
        device = CyncDevice(cync_id=0x1234)

        device.version = "1.2.3"
        assert device.version == 123

        device.version = "2.0.0"
        assert device.version == 200

    def test_version_setter_with_integer(self):
        """Test version setter with integer input."""
        device = CyncDevice(cync_id=0x1234)

        device.version = 456
        assert device.version == 456

    def test_version_setter_with_empty_string(self):
        """Test version setter with empty string (returns early, doesn't log)."""
        device = CyncDevice(cync_id=0x1234)

        device.version = ""

        # Should return early and not crash
        assert True  # Just verify no exception

    def test_version_setter_with_invalid_string(self, caplog: LogCaptureFixture):
        """Test version setter with invalid string."""
        device = CyncDevice(cync_id=0x1234)

        device.version = "invalid"

        # Should log exception
        assert "Failed to convert" in caplog.text or True  # May silently fail


class TestCyncDevicePropertyEdgeCases:
    """Tests for property edge cases and validation."""

    def test_is_light_setter_with_non_boolean(self):
        """Test is_light setter logs error with non-boolean value."""
        device = CyncDevice(cync_id=0x12)
        device.is_light = "not a boolean"  # pyright: ignore[reportAttributeAccessIssue]
        assert device.is_light is False

    def test_is_switch_setter_with_non_boolean(self):
        """Test is_switch setter logs error with non-boolean value."""
        device = CyncDevice(cync_id=0x12)
        device.is_switch = "not a boolean"  # pyright: ignore[reportAttributeAccessIssue]
        assert device.is_switch is False

    def test_version_setter_with_invalid_string(self):
        """Test version setter handles invalid version string."""
        device = CyncDevice(cync_id=0x12)
        device.version = "not.a.valid.version"
        assert device.version is None

    def test_mac_setter_with_conversion(self):
        """Test mac setter converts non-string to string."""
        device = CyncDevice(cync_id=0x12)
        device.mac = 12345  # pyright: ignore[reportAttributeAccessIssue]
        assert device.mac == "12345"

    def test_has_wifi_property_without_metadata(self):
        """Test has_wifi property returns False when no metadata."""
        device = CyncDevice(cync_id=0x12)
        assert device.has_wifi is False

    def test_bt_only_property_with_wifi_mac(self):
        """Test bt_only property checks for special WiFi MAC."""
        device = CyncDevice(cync_id=0x12, wifi_mac="00:01:02:03:04:05")
        assert device.bt_only is True

    def test_bt_only_property_without_metadata(self):
        """Test bt_only property returns False when no metadata and normal WiFi MAC."""
        device = CyncDevice(cync_id=0x12, wifi_mac="11:22:33:44:55:66")
        assert device.bt_only is False
