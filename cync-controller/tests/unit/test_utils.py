"""
Unit tests for utils module.

Tests utility functions for data conversion and firmware parsing.
"""

import pytest

from cync_lan.utils import (
    bytes2list,
    hex2list,
    ints2bytes,
    ints2hex,
    parse_unbound_firmware_version,
)


class TestConversionUtilities:
    """Tests for data conversion utility functions"""

    def test_bytes2list_simple(self):
        """Test bytes2list with simple byte string"""
        byte_string = b"\x01\x02\x03\x04"
        result = bytes2list(byte_string)
        assert result == [1, 2, 3, 4]

    def test_bytes2list_full_range(self):
        """Test bytes2list with full byte range (0-255)"""
        byte_string = bytes([0, 127, 128, 255])
        result = bytes2list(byte_string)
        assert result == [0, 127, 128, 255]

    def test_bytes2list_empty(self):
        """Test bytes2list with empty byte string"""
        result = bytes2list(b"")
        assert result == []

    def test_hex2list_simple(self):
        """Test hex2list with simple hex string"""
        hex_string = "01 02 03 04"
        result = hex2list(hex_string)
        assert result == [1, 2, 3, 4]

    def test_hex2list_no_spaces(self):
        """Test hex2list with hex string without spaces"""
        hex_string = "01020304"
        result = hex2list(hex_string)
        assert result == [1, 2, 3, 4]

    def test_hex2list_uppercase(self):
        """Test hex2list with uppercase hex string"""
        hex_string = "FF AA BB CC"
        result = hex2list(hex_string)
        assert result == [255, 170, 187, 204]

    def test_ints2hex_simple(self):
        """Test ints2hex with simple integer list"""
        ints = [1, 2, 3, 4]
        result = ints2hex(ints)
        assert result == "01 02 03 04"

    def test_ints2hex_full_range(self):
        """Test ints2hex with full byte range"""
        ints = [0, 127, 128, 255]
        result = ints2hex(ints)
        assert result == "00 7f 80 ff"

    def test_ints2bytes_simple(self):
        """Test ints2bytes with simple integer list"""
        ints = [1, 2, 3, 4]
        result = ints2bytes(ints)
        assert result == b"\x01\x02\x03\x04"

    def test_ints2bytes_full_range(self):
        """Test ints2bytes with full byte range"""
        ints = [0, 127, 128, 255]
        result = ints2bytes(ints)
        assert result == bytes([0, 127, 128, 255])


class TestFirmwareVersionParsing:
    """Tests for parse_unbound_firmware_version function"""

    def test_parse_device_firmware(self):
        """Test parsing device firmware version"""
        # Device firmware packet structure:
        # 20 bytes of header, then:
        # byte 20: firmware indicator
        # byte 21: separator
        # byte 22: 0x01 (device type)
        # byte 23-27: ASCII digits for version
        data = bytes([0x00] * 20)  # Header
        data += bytes([0x01, 0x03, 0x01])  # Firmware indicator + separator + device type
        data += b"12345"  # Version digits (ASCII)
        data += bytes([0x00] * 5)  # Padding

        result = parse_unbound_firmware_version(data, "test")

        assert result is not None
        firmware_type, version_int, version_str = result
        assert firmware_type == "device"
        assert version_int == 12345
        assert version_str == "1.2.345"

    def test_parse_network_firmware(self):
        """Test parsing network firmware version"""
        # Network firmware packet structure (byte 22 != 0x01)
        data = bytes([0x00] * 20)  # Header
        data += bytes([0x01, 0x03, 0x00])  # Firmware indicator + separator + network type
        data += b"54321"  # Version digits (ASCII)
        data += bytes([0x00] * 5)  # Padding

        result = parse_unbound_firmware_version(data, "test")

        assert result is not None
        firmware_type, version_int, version_str = result
        assert firmware_type == "network"
        assert version_int == 54321
        assert version_str == "54321"

    def test_parse_firmware_short_version(self):
        """Test parsing firmware with short version number"""
        data = bytes([0x00] * 20)  # Header
        data += bytes([0x01, 0x03, 0x01])  # Device type
        data += b"123"  # Short version
        data += bytes([0x00] * 7)  # Padding

        result = parse_unbound_firmware_version(data, "test")

        assert result is not None
        firmware_type, version_int, version_str = result
        assert firmware_type == "device"
        assert version_int == 123
        assert version_str == "1.2.3"

    def test_parse_firmware_no_version(self):
        """Test parsing firmware with no version data (returns None)"""
        # Packet with null terminator immediately after firmware type
        data = bytes([0x00] * 20)  # Header
        data += bytes([0x01, 0x03, 0x01])  # Device type
        data += bytes([0x00] * 10)  # No version data

        result = parse_unbound_firmware_version(data, "test")

        assert result is None

    def test_parse_firmware_index_error(self):
        """Test parsing firmware with insufficient data (raises IndexError)"""
        # Packet too short to contain firmware data (< 23 bytes needed)
        data = bytes([0x00] * 10)  # Too short

        # IndexError is raised at line 121 before try/except block
        with pytest.raises(IndexError):
            parse_unbound_firmware_version(data, "test")

    def test_parse_firmware_value_error(self):
        """Test parsing firmware with non-numeric version data (returns None)"""
        # Non-ASCII digits in version field
        data = bytes([0x00] * 20)  # Header
        data += bytes([0x01, 0x03, 0x01])  # Device type
        data += bytes([0xFF, 0xFE, 0xFD])  # Invalid version bytes
        data += bytes([0x00] * 7)  # Padding

        result = parse_unbound_firmware_version(data, "test")

        assert result is None
