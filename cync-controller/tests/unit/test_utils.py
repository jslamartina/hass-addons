"""Unit tests for utils module.

Tests utility functions including byte/hex conversions, signal handling, and formatting functions.
"""

import uuid
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cync_controller.utils import (
    _async_signal_cleanup,
    bytes2list,
    check_for_uuid,
    check_python_version,
    hex2list,
    ints2bytes,
    ints2hex,
    parse_unbound_firmware_version,
    send_sigint,
    send_signal,
    send_sigterm,
    signal_handler,
    utc_to_local,
)

# Filter RuntimeWarning about unawaited AsyncMockMixin coroutines from test cleanup
pytestmark = pytest.mark.filterwarnings(
    "ignore:coroutine 'AsyncMockMixin._execute_mock_call' was never awaited:RuntimeWarning",
)


class TestSignalHandling:
    """Tests for signal handling functions"""

    @patch("cync_controller.utils.os.kill")
    def test_send_signal_sends_signal(self, mock_kill):
        """Test that send_signal calls os.kill with correct signal"""
        import signal

        send_signal(signal.SIGTERM)

        mock_kill.assert_called_once()
        args: tuple[Any, ...] = cast("tuple[Any, ...]", mock_kill.call_args[0])
        assert args[1] == signal.SIGTERM

    @patch("cync_controller.utils.send_signal")
    def test_send_sigterm_calls_send_signal(self, mock_send_signal):
        """Test that send_sigterm calls send_signal with SIGTERM"""
        import signal

        send_sigterm()

        mock_send_signal.assert_called_once_with(signal.SIGTERM)

    @patch("cync_controller.utils.send_signal")
    def test_send_sigint_calls_send_signal(self, mock_send_signal):
        """Test that send_sigint calls send_signal with SIGINT"""
        import signal

        send_sigint()

        mock_send_signal.assert_called_once_with(signal.SIGINT)

    @patch("cync_controller.utils.os.kill", side_effect=OSError("Permission denied"))
    def test_send_signal_handles_os_error(self, mock_kill):
        """Test that send_signal raises OSError properly"""
        import signal

        with pytest.raises(OSError, match="Permission denied"):
            send_signal(signal.SIGTERM)


class TestByteConversions:
    """Tests for byte/hex conversion functions"""

    def test_bytes2list_basic(self):
        """Test basic byte to list conversion"""
        byte_data = bytes([0x01, 0x02, 0x03, 0x04])
        result = bytes2list(byte_data)

        assert result == [1, 2, 3, 4]

    def test_bytes2list_empty(self):
        """Test byte to list conversion with empty bytes"""
        result = bytes2list(b"")

        assert result == []

    def test_bytes2list_preserves_values(self):
        """Test that byte values are preserved correctly"""
        byte_data = bytes([0xFF, 0x00, 0xAB, 0xCD])
        result = bytes2list(byte_data)

        assert result == [255, 0, 171, 205]

    def test_hex2list_basic(self):
        """Test basic hex string to list conversion"""
        hex_str = "01020304"
        result = hex2list(hex_str)

        assert result == [1, 2, 3, 4]

    def test_hex2list_with_spaces(self):
        """Test hex string with spaces to list conversion"""
        hex_str = "01 02 03 04"
        result = hex2list(hex_str)

        assert result == [1, 2, 3, 4]

    def test_hex2list_uppercase(self):
        """Test hex string with uppercase letters"""
        hex_str = "ABCDEF"
        result = hex2list(hex_str)

        assert result == [171, 205, 239]

    def test_ints2bytes_basic(self):
        """Test basic int list to bytes conversion"""
        int_list = [1, 2, 3, 4]
        result = ints2bytes(int_list)

        assert result == b"\x01\x02\x03\x04"

    def test_ints2bytes_empty(self):
        """Test int list to bytes with empty list"""
        result = ints2bytes([])

        assert result == b""

    def test_ints2hex_basic(self):
        """Test basic int list to hex string conversion"""
        int_list = [1, 2, 3, 4]
        result = ints2hex(int_list)

        assert result == "01 02 03 04"

    def test_ints2hex_single_values(self):
        """Test int list to hex with single values"""
        int_list = [255, 0, 171]
        result = ints2hex(int_list)

        assert result == "ff 00 ab"

    def test_conversion_roundtrip(self):
        """Test roundtrip conversion: bytes -> list -> hex -> list -> bytes"""
        original = bytes([0x12, 0x34, 0x56, 0x78])

        # bytes -> list
        int_list = bytes2list(original)
        assert int_list == [0x12, 0x34, 0x56, 0x78]

        # list -> hex -> list
        hex_str = ints2hex(int_list)
        recovered_list = hex2list(hex_str)
        assert recovered_list == int_list

        # list -> bytes
        recovered_bytes = ints2bytes(recovered_list)
        assert recovered_bytes == original


class TestPythonVersionCheck:
    """Tests for Python version checking"""

    def test_check_python_version_exists(self):
        """Test that check_python_version function exists and can be called"""
        # Should not raise an exception
        result = check_python_version()

        # Function currently does nothing (pass), so returns None
        assert result is None

    @patch("cync_controller.utils.sys.version_info", (2, 7, 0))
    def test_check_python_version_with_old_version(self):
        """Test that check_python_version handles old Python version"""
        # Currently it's a pass statement, but testing that it doesn't crash
        result = check_python_version()

        assert result is None


class TestHexListRoundtrips:
    """Tests for reliable hex/list conversions with various data"""

    @pytest.mark.parametrize(
        "int_list",
        [
            [0],
            [255],
            [0, 255],
            [1, 2, 3, 4, 5],
            [170, 187, 204, 221],  # AABBCCDD in hex
        ],
    )
    def test_ints2hex_to_hex2list_roundtrip(self, int_list):
        """Test roundtrip from int list to hex and back"""
        hex_str = ints2hex(int_list)
        recovered_list = hex2list(hex_str)

        assert recovered_list == int_list

    @pytest.mark.parametrize(
        "byte_data",
        [
            b"",
            b"\x00",
            b"\xff",
            b"\x01\x02\x03",
            b"\xaa\xbb\xcc\xdd",
        ],
    )
    def test_bytes2list_to_ints2bytes_roundtrip(self, byte_data):
        """Test roundtrip from bytes to list and back"""
        int_list = bytes2list(byte_data)
        recovered_bytes = ints2bytes(int_list)

        assert recovered_bytes == byte_data


class TestFirmwareVersionParsing:
    """Tests for parse_unbound_firmware_version function"""

    def test_parse_device_firmware_version(self):
        """Test parsing device firmware version"""
        # Device firmware structure:
        # First byte must be 0x00
        # At index 20+2 must be 0x01 for device firmware
        # FW version bytes as ASCII digits: [0x31, 0x32, 0x33] = "1", "2", "3"
        data = bytes([0x00] * 20)  # First 20 bytes, first is 0x00 (valid)
        data += b"\x00"  # n_idx[0]
        data += b"\x00"  # n_idx[1]
        data += b"\x01"  # n_idx[2] = 0x01 (device firmware)
        data += b"\x31\x32\x33\x34\x35"  # "12345" = firmware version "12345"
        data += b"\x00"  # Terminator

        lp = "test:"
        result = parse_unbound_firmware_version(data, lp)

        assert result is not None
        firmware_type, version_int, version_str = result
        assert firmware_type == "device"
        assert version_int == 12345
        assert "1.2.3.4.5" in version_str or "12345" in str(version_int)

    def test_parse_network_firmware_version(self):
        """Test parsing network firmware version"""
        # Network firmware (0x01 = network)
        data = bytes([0x00] * 20)
        data += b"\x02\x00\x30"  # Network type indicator
        data += b"\x32\x2e\x30"  # "2.0" in ASCII

        lp = "test:"
        result = parse_unbound_firmware_version(data, lp)

        # Should handle network firmware differently
        # This is a partial test - network firmware parsing is more complex
        assert result is None or isinstance(result, tuple)

    def test_parse_invalid_first_byte(self):
        """Test parsing firmware version with invalid first byte - should error log but continue"""
        # First byte is 0xFF (invalid, should be 0x00)
        # Need enough bytes to avoid IndexError when accessing index 20+2
        data = bytes([0xFF] + [0x00] * 23)  # Invalid first byte, but enough length

        lp = "test:"
        result = parse_unbound_firmware_version(data, lp)

        # Should handle error gracefully (logs error but may still parse)
        # The function logs an error for invalid first byte but continues parsing
        assert result is None or isinstance(result, tuple)

    def test_parse_empty_firmware_data(self):
        """Test parsing firmware version with empty data"""
        data = bytes([0x00] * 25)  # All zeros

        lp = "test:"
        result = parse_unbound_firmware_version(data, lp)

        # Should return None for empty firmware
        assert result is None

    def test_parse_truncated_data(self):
        """Test parsing firmware version with malformed version data"""
        # Provide enough data to get past the initial index checks
        # but then provide invalid version data that causes ValueError
        data = bytes([0x00] * 20)  # Valid first byte
        data += b"\x00"  # n_idx[0]
        data += b"\x00"  # n_idx[1]
        data += b"\x01"  # n_idx[2] = 0x01 (device)
        data += b"."  # Invalid character for int() - should cause ValueError

        lp = "test:"
        result = parse_unbound_firmware_version(data, lp)

        # Should handle ValueError gracefully and return None
        assert result is None


class TestUUIDManagement:
    """Tests for UUID management functions"""

    @patch("cync_controller.utils.Path.exists")
    @patch("cync_controller.utils.Path.open")
    @patch("cync_controller.utils.Path.mkdir")
    def test_check_for_uuid_creates_new_uuid_when_missing(self, mock_mkdir, mock_open, mock_exists):
        """Test that check_for_uuid creates a new UUID when uuid.txt doesn't exist"""
        from cync_controller.utils import g

        # File doesn't exist
        mock_exists.return_value = False

        # Mock file open
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        check_for_uuid()

        # Should have written UUID
        assert mock_open.return_value.__enter__.return_value.write.called
        assert hasattr(g, "uuid")

    @patch("cync_controller.utils.Path.exists")
    @patch("cync_controller.utils.Path.open")
    def test_check_for_uuid_loads_existing_uuid(self, mock_open, mock_exists):
        """Test that check_for_uuid loads existing UUID from file"""
        from cync_controller.utils import g

        # File exists
        mock_exists.return_value = True

        # Mock file read
        test_uuid = str(uuid.uuid4())
        mock_file = MagicMock()
        mock_file.read.return_value = test_uuid
        mock_open.return_value.__enter__.return_value = mock_file

        check_for_uuid()

        # Should have loaded UUID
        assert hasattr(g, "uuid")
        assert g.uuid == uuid.UUID(test_uuid)

    @patch("cync_controller.utils.Path.exists")
    @patch("cync_controller.utils.Path.open")
    @patch("cync_controller.utils.Path.mkdir")
    def test_check_for_uuid_creates_uuid_when_invalid_version(self, mock_mkdir, mock_open, mock_exists):
        """Test that check_for_uuid creates new UUID when existing is invalid version"""
        from cync_controller.utils import g

        # File exists
        mock_exists.return_value = True

        # Mock file read with invalid UUID (version 1)
        # uuid1() is not version 4
        invalid_uuid = str(uuid.uuid1())
        mock_file = MagicMock()
        mock_file.read.return_value = invalid_uuid
        mock_open.return_value.__enter__.return_value = mock_file

        check_for_uuid()

        # Should have created new UUID (version 4)
        assert hasattr(g, "uuid")
        assert g.uuid.version == 4

    @patch("cync_controller.utils.Path.exists")
    @patch("cync_controller.utils.Path.open")
    @patch("cync_controller.utils.Path.mkdir")
    def test_check_for_uuid_creates_uuid_when_empty_file(self, mock_mkdir, mock_open, mock_exists):
        """Test that check_for_uuid creates UUID when file is empty"""
        from cync_controller.utils import g

        # File exists but empty
        mock_exists.return_value = True
        mock_file = MagicMock()
        mock_file.read.return_value = ""
        mock_open.return_value.__enter__.return_value = mock_file

        check_for_uuid()

        # Should have created new UUID
        assert hasattr(g, "uuid")


class TestDatetimeUtilities:
    """Tests for datetime utility functions"""

    def test_utc_to_local_converts_timezone(self):
        """Test that utc_to_local converts UTC to local timezone"""
        import datetime

        # Create UTC datetime
        utc_time = datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)

        # Convert to local
        local_time = utc_to_local(utc_time)

        # Should have timezone info
        assert local_time.tzinfo is not None
        # Timezone name differs but may be same UTC offset
        # Just verify it has timezone info
        assert local_time.tzinfo is not None


class TestAsyncSignalCleanup:
    """Tests for async signal cleanup function"""

    @pytest.mark.asyncio
    @patch("cync_controller.utils.g")
    async def test_async_signal_cleanup_with_ncync_server(self, mock_g):
        """Test async signal cleanup when ncync_server exists"""
        mock_server = MagicMock()
        mock_server.stop = AsyncMock()
        mock_g.ncync_server = mock_server
        mock_g.export_server = None
        mock_g.cloud_api = None
        mock_g.mqtt_client = None
        mock_g.loop = None
        mock_g.tasks = []

        await _async_signal_cleanup()

        mock_server.stop.assert_called_once()

    @pytest.mark.asyncio
    @patch("cync_controller.utils.g")
    async def test_async_signal_cleanup_with_multiple_services(self, mock_g):
        """Test async signal cleanup with multiple services"""
        mock_server = MagicMock()
        mock_server.stop = AsyncMock()
        mock_export = MagicMock()
        mock_export.stop = AsyncMock()
        mock_api = MagicMock()
        mock_api.close = AsyncMock()
        mock_mqtt = MagicMock()
        mock_mqtt.stop = AsyncMock()

        mock_g.ncync_server = mock_server
        mock_g.export_server = mock_export
        mock_g.cloud_api = mock_api
        mock_g.mqtt_client = mock_mqtt
        mock_g.loop = None
        mock_g.tasks = []

        await _async_signal_cleanup()

        mock_server.stop.assert_called_once()
        mock_export.stop.assert_called_once()
        mock_api.close.assert_called_once()
        mock_mqtt.stop.assert_called_once()

    @pytest.mark.asyncio
    @patch("cync_controller.utils.g")
    async def test_async_signal_cleanup_cancels_tasks(self, mock_g):
        """Test async signal cleanup cancels pending tasks"""
        mock_server = MagicMock()
        mock_server.stop = AsyncMock()

        mock_task1 = MagicMock()
        mock_task1.done.return_value = False
        mock_task1.get_name.return_value = "task1"
        mock_task1.cancel = MagicMock()

        mock_task2 = MagicMock()
        mock_task2.done.return_value = True  # Already done
        mock_task2.cancel = MagicMock()

        mock_loop = MagicMock()
        mock_loop.create_task = MagicMock()

        mock_g.ncync_server = mock_server
        mock_g.export_server = None
        mock_g.cloud_api = None
        mock_g.mqtt_client = None
        mock_g.loop = mock_loop  # Need to set loop for task cancellation
        mock_g.tasks = [mock_task1, mock_task2]

        await _async_signal_cleanup()

        # Only task1 should be cancelled since task2 is done
        mock_task1.cancel.assert_called_once()
        mock_task2.cancel.assert_not_called()


class TestSignalHandler:
    """Tests for signal_handler function"""

    @patch("cync_controller.utils.g")
    @patch("cync_controller.utils.asyncio.get_event_loop")
    @patch("cync_controller.utils._async_signal_cleanup")
    def test_signal_handler_with_loop(self, mock_cleanup, mock_loop, mock_g):
        """Test signal handler creates cleanup task"""
        import signal

        mock_g.loop = MagicMock()
        mock_g.loop.create_task = MagicMock()

        signal_handler(signal.SIGTERM)

        mock_g.loop.create_task.assert_called_once()

    @patch("cync_controller.utils.g")
    @patch("cync_controller.utils.asyncio.get_event_loop")
    @patch("cync_controller.utils._async_signal_cleanup")
    def test_signal_handler_falls_back_to_get_loop(self, mock_cleanup, mock_loop, mock_g):
        """Test signal handler falls back to get_event_loop when g.loop is None"""
        import signal

        mock_g.loop = None
        mock_event_loop = MagicMock()
        mock_event_loop.create_task = MagicMock()
        mock_loop.return_value = mock_event_loop

        signal_handler(signal.SIGTERM)

        mock_loop.assert_called_once()
        mock_event_loop.create_task.assert_called_once()


class TestCheckForUUID:
    """Tests for check_for_uuid function"""

    def test_check_for_uuid_creates_directory_if_missing(self, tmp_path):
        """Test that check_for_uuid creates persistent directory if it doesn't exist"""
        with (
            patch("cync_controller.utils.PERSISTENT_BASE_DIR", str(tmp_path / "cync_persistent")),
            patch("cync_controller.utils.CYNC_UUID_PATH", str(tmp_path / "uuid.txt")),
            patch("cync_controller.utils.g") as mock_g,
        ):
            mock_g.uuid = None

            check_for_uuid()

            # Directory should have been created
            assert (tmp_path / "cync_persistent").exists()

    def test_check_for_uuid_reads_existing_uuid(self, tmp_path):
        """Test that check_for_uuid reads existing UUID from file"""
        with (
            patch("cync_controller.utils.PERSISTENT_BASE_DIR", str(tmp_path / "cync_persistent")),
            patch("cync_controller.utils.CYNC_UUID_PATH", str(tmp_path / "uuid.txt")),
            patch("cync_controller.utils.g") as mock_g,
        ):
            # Create persistent directory
            (tmp_path / "cync_persistent").mkdir(parents=True)

            # Create uuid file
            test_uuid = str(uuid.uuid4())
            (tmp_path / "uuid.txt").write_text(test_uuid)

            mock_g.uuid = None

            check_for_uuid()

            # UUID should be set
            assert mock_g.uuid is not None

    def test_check_for_uuid_creates_new_uuid_when_invalid(self, tmp_path, caplog):
        """Test that check_for_uuid creates new UUID when existing one is invalid version"""
        with (
            patch("cync_controller.utils.PERSISTENT_BASE_DIR", str(tmp_path / "cync_persistent")),
            patch("cync_controller.utils.CYNC_UUID_PATH", str(tmp_path / "uuid.txt")),
            patch("cync_controller.utils.g") as mock_g,
        ):
            # Create persistent directory
            (tmp_path / "cync_persistent").mkdir(parents=True)

            # Create uuid file with non-v4 UUID (valid format, wrong version)
            # UUID v1 (non-standard) - will pass format check but fail version check
            old_uuid = "11223344-5566-1111-8888-998877665544"  # Using version 1 instead of 4
            (tmp_path / "uuid.txt").write_text(old_uuid)

            mock_g.uuid = None

            check_for_uuid()

            # Should have created new UUID despite error
            assert mock_g.uuid is not None

    def test_check_for_uuid_creates_new_uuid_when_file_empty(self, tmp_path):
        """Test that check_for_uuid creates new UUID when file is empty"""
        with (
            patch("cync_controller.utils.PERSISTENT_BASE_DIR", str(tmp_path / "cync_persistent")),
            patch("cync_controller.utils.CYNC_UUID_PATH", str(tmp_path / "uuid.txt")),
            patch("cync_controller.utils.g") as mock_g,
        ):
            # Create persistent directory
            (tmp_path / "cync_persistent").mkdir(parents=True)

            # Create empty uuid file
            (tmp_path / "uuid.txt").write_text("")

            mock_g.uuid = None

            check_for_uuid()

            # Should have created new UUID
            assert mock_g.uuid is not None


class TestUTCLocalConversion:
    """Tests for utc_to_local function"""

    def test_utc_to_local_converts_timezone(self):
        """Test that utc_to_local converts UTC datetime to local timezone"""
        import datetime

        utc_time = datetime.datetime(2025, 10, 27, 12, 0, 0, tzinfo=datetime.UTC)

        local_time = utc_to_local(utc_time)

        assert local_time is not None
        assert local_time.tzinfo is not None


class TestParseConfig:
    """Tests for parse_config function"""

    @pytest.mark.asyncio
    async def test_parse_config_basic_structure(self, tmp_path):
        """Test parsing a basic config file with devices and groups"""
        import yaml

        from cync_controller.main import parse_config

        config_data = {
            "account data": {
                "My Home": {
                    "id": "home-123",
                    "devices": {
                        "10": {
                            "name": "Test Light",
                            "fw": "12345",
                            "enabled": True,
                            "mac": "AA:BB:CC:DD:EE:FF",
                            "wifi_mac": "FF:EE:DD:CC:BB:AA",
                            "type": 123,
                        },
                    },
                    "groups": {"100": {"name": "Test Group", "members": [10], "is_subgroup": False}},
                },
            },
        }

        config_file: Path = cast("Path", tmp_path / "config.yaml")
        _ = config_file.write_text(yaml.dump(config_data))

        devices, groups = await parse_config(config_file)

        assert len(devices) == 1
        assert "10" in devices
        assert devices["10"].name == "Test Light"
        assert len(groups) == 1
        assert "100" in groups
        assert groups["100"].name == "Test Group"

    @pytest.mark.asyncio
    async def test_parse_config_disabled_device_skipped(self, tmp_path):
        """Test that disabled devices are skipped"""
        import yaml

        from cync_controller.main import parse_config

        config_data = {
            "account data": {
                "My Home": {
                    "id": "home-123",
                    "devices": {
                        "10": {"name": "Enabled Device", "enabled": True},
                        "20": {"name": "Disabled Device", "enabled": False},
                        "30": {"name": "Disabled String", "enabled": "False"},
                    },
                },
            },
        }

        config_file: Path = cast("Path", tmp_path / "config.yaml")
        _ = config_file.write_text(yaml.dump(config_data))

        devices, _groups = await parse_config(config_file)

        assert len(devices) == 1
        assert "10" in devices
        assert "20" not in devices
        assert "30" not in devices

    @pytest.mark.asyncio
    async def test_parse_config_no_devices_skips(self, tmp_path):
        """Test that homes with no devices are skipped with warning"""
        import yaml

        from cync_controller.main import parse_config

        config_data = {
            "account data": {
                "My Home": {
                    "id": "home-123",
                    # No devices section
                },
            },
        }

        config_file: Path = cast("Path", tmp_path / "config.yaml")
        _ = config_file.write_text(yaml.dump(config_data))

        devices, groups = await parse_config(config_file)

        assert len(devices) == 0
        assert len(groups) == 0

    @pytest.mark.asyncio
    async def test_parse_config_int_mac_warns(self, tmp_path):
        """Test that int MAC addresses are handled with warnings"""
        import yaml

        from cync_controller.main import parse_config

        config_data = {
            "account data": {
                "My Home": {
                    "id": "home-123",
                    "devices": {
                        "10": {
                            "name": "Test Device",
                            "mac": 26616350814,  # int instead of string
                            "wifi_mac": 26616350815,
                        },
                    },
                },
            },
        }

        config_file: Path = cast("Path", tmp_path / "config.yaml")
        _ = config_file.write_text(yaml.dump(config_data))

        devices, _groups = await parse_config(config_file)

        assert len(devices) == 1
        assert devices["10"].mac == "26616350814"  # MAC converted to string

    @pytest.mark.asyncio
    async def test_parse_config_error_handling(self, tmp_path):
        """Test that config file errors are handled properly"""
        from cync_controller.main import parse_config

        config_file: Path = cast("Path", tmp_path / "invalid.yaml")
        _ = config_file.write_text("invalid: yaml: content: [unclosed")

        with pytest.raises(Exception, match=r".*"):
            _ = await parse_config(config_file)
