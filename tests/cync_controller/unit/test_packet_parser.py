"""Unit tests for packet_parser module.

Tests packet parsing functionality for Cync protocol packets.
"""

from __future__ import annotations

from typing import cast

from cync_controller.packet_parser import PacketDict, format_packet_log, parse_cync_packet


def _require_packet(packet: PacketDict | None) -> PacketDict:
    """Assert that a parsed packet is present and return it."""
    assert packet is not None
    return packet


def _get_device_statuses(result: PacketDict) -> list[PacketDict]:
    """Return typed device status list from a parsed packet."""
    statuses = result.get("device_statuses")
    assert isinstance(statuses, list)
    return cast(list[PacketDict], statuses)


class TestParseCyncPacket:
    """Tests for parse_cync_packet function."""

    def test_parse_returns_none_for_empty_packet(self):
        """Test that empty packet returns None."""
        result = parse_cync_packet(b"")
        assert result is None

    def test_parse_returns_none_for_too_short_packet(self):
        """Test that packet shorter than 5 bytes returns None."""
        result = parse_cync_packet(b"\x73\x00\x00")
        assert result is None

    def test_parse_returns_none_for_none_input(self):
        """Test that None input returns None."""
        result = parse_cync_packet(None)  # pyright: ignore[reportArgumentType]
        assert result is None

    def test_parse_minimal_valid_packet(self):
        """Test parsing minimal valid packet (5 bytes)."""
        # Minimal packet: type + 4 padding bytes
        packet = bytes([0x73, 0x00, 0x00, 0x00, 0x00])
        result = _require_packet(parse_cync_packet(packet))
        assert result["packet_type"] == "0x73"
        assert result["packet_type_name"] == "DATA_CHANNEL"
        assert result["raw_len"] == 5
        assert "raw_hex" in result

    def test_parse_handshake_packet(self):
        """Test parsing 0x23 HANDSHAKE packet."""
        packet = bytes([0x23, 0x00, 0x00, 0x00, 0x10] + [0x00] * 16)
        result = _require_packet(parse_cync_packet(packet))

        assert result["packet_type"] == "0x23"
        assert result["packet_type_name"] == "HANDSHAKE"
        assert result["declared_length"] == 16

    def test_parse_data_channel_packet(self):
        """Test parsing 0x73 DATA_CHANNEL packet."""
        # Create packet with endpoint and counter
        packet = bytes(
            [
                0x73,  # Type
                0x00,
                0x00,  # Padding
                0x00,
                0x20,  # Length (32 bytes)
                0xAA,
                0xBB,
                0xCC,
                0xDD,  # Endpoint (4 bytes)
                0x00,  # Unknown
                0x05,  # Counter
                0x00,
            ]
            + [0x00] * 20  # Rest of packet
        )
        result = _require_packet(parse_cync_packet(packet))

        assert result["packet_type"] == "0x73"
        assert result["packet_type_name"] == "DATA_CHANNEL"
        assert result["declared_length"] == 32
        assert "endpoint" in result
        assert result["endpoint_int"] == 0xDDCCBBAA  # Little endian
        assert result["counter"] == "0x05"

    def test_parse_status_broadcast_packet(self):
        """Test parsing 0x83 STATUS_BROADCAST packet."""
        packet = bytes(
            [
                0x83,  # Type
                0x00,
                0x00,
                0x00,
                0x18,  # Length (24 bytes)
                0x11,
                0x22,
                0x33,
                0x44,  # Endpoint
                0x00,
                0x03,  # Counter
                0x00,
            ]
            + [0xFF] * 12  # Data payload
        )
        result = _require_packet(parse_cync_packet(packet))

        assert result["packet_type"] == "0x83"
        assert result["packet_type_name"] == "STATUS_BROADCAST"
        assert "endpoint" in result
        assert result["counter"] == "0x03"
        assert "data_payload" in result
        assert result["data_length"] == 12

    def test_parse_device_info_packet(self):
        """Test parsing 0x43 DEVICE_INFO packet with device status."""
        # Create packet with one 19-byte device status
        packet = bytes(
            [
                0x43,  # Type
                0x00,
                0x00,
                0x00,
                0x1F,  # Length (31 bytes: 12 header + 19 status)
                0x00,
                0x00,
                0x00,
                0x00,  # Endpoint
                0x00,
                0x00,
                0x00,  # Padding
                # Device status (19 bytes):
                0x01,  # item
                0x00,  # ?
                0x00,  # ?
                0x15,  # device_id = 21
                0x01,  # state = ON
                0x64,  # brightness = 100
                0x50,  # temp = 80 (WHITE mode)
                0x00,  # R
                0x00,  # G
                0x00,  # B
                0x01,  # online = true
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,  # padding (8 bytes)
            ]
        )
        result = _require_packet(parse_cync_packet(packet))

        assert result["packet_type"] == "0x43"
        assert result["packet_type_name"] == "DEVICE_INFO"
        statuses = _get_device_statuses(result)
        assert len(statuses) == 1

        status = statuses[0]
        assert status["device_id"] == 21
        assert status["state"] == "ON"
        assert status["brightness"] == 100
        assert status["mode"] == "WHITE"
        assert status["temp"] == 80
        assert status["online"] is True

    def test_parse_device_info_rgb_mode(self):
        """Test parsing device status in RGB mode."""
        # Device status with temp > 100 indicates RGB mode
        packet = bytes(
            [
                0x43,  # Type
                0x00,
                0x00,
                0x00,
                0x1F,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                # Device status (RGB mode):
                0x01,
                0x00,
                0x00,
                0x20,  # device_id = 32
                0x01,  # state = ON
                0x80,  # brightness = 128
                0xFF,  # temp = 255 (>100, so RGB mode)
                0xFF,  # R = 255
                0x80,  # G = 128
                0x00,  # B = 0
                0x01,  # online = true
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
            ]
        )
        result = _require_packet(parse_cync_packet(packet))

        status = _get_device_statuses(result)[0]
        assert status["mode"] == "RGB"
        assert status["color"] == "#ff8000"
        assert "temp" not in status

    def test_parse_packet_with_large_length(self):
        """Test parsing packet with length multiplier."""
        # Length = (2 * 256) + 50 = 562 bytes
        packet = bytes([0x73, 0x00, 0x00, 0x02, 0x32]) + bytes(557)
        result = _require_packet(parse_cync_packet(packet))

        assert result["declared_length"] == 562
        assert "length_calc" in result
        assert result["length_calc"] == "(2 * 256) + 50"

    def test_parse_keepalive_packet(self):
        """Test parsing 0x78 KEEPALIVE packet."""
        packet = bytes([0x78, 0x00, 0x00, 0x00, 0x08] + [0x00] * 3)
        result = _require_packet(parse_cync_packet(packet))

        assert result["packet_type"] == "0x78"
        assert result["packet_type_name"] == "KEEPALIVE"

    def test_parse_heartbeat_dev_packet(self):
        """Test parsing 0xD3 HEARTBEAT_DEV packet."""
        packet = bytes([0xD3, 0x00, 0x00, 0x00, 0x08] + [0x00] * 3)
        result = _require_packet(parse_cync_packet(packet))

        assert result["packet_type"] == "0xd3"
        assert result["packet_type_name"] == "HEARTBEAT_DEV"

    def test_parse_heartbeat_cloud_packet(self):
        """Test parsing 0xD8 HEARTBEAT_CLOUD packet."""
        packet = bytes([0xD8, 0x00, 0x00, 0x00, 0x08] + [0x00] * 3)
        result = _require_packet(parse_cync_packet(packet))

        assert result["packet_type"] == "0xd8"
        assert result["packet_type_name"] == "HEARTBEAT_CLOUD"

    def test_parse_unknown_packet_type(self):
        """Test parsing packet with unknown type."""
        packet = bytes([0xFF, 0x00, 0x00, 0x00, 0x08] + [0x00] * 3)
        result = _require_packet(parse_cync_packet(packet))

        assert result["packet_type"] == "0xff"
        assert result["packet_type_name"] == "UNKNOWN"

    def test_parse_direction_parameter(self):
        """Test that direction parameter is included in result."""
        packet = bytes([0x73, 0x00, 0x00, 0x00, 0x08])

        result_dev = _require_packet(parse_cync_packet(packet, direction="DEV->CLOUD"))
        assert result_dev["direction"] == "DEV->CLOUD"

        result_cloud = _require_packet(parse_cync_packet(packet, direction="CLOUD->DEV"))
        assert result_cloud["direction"] == "CLOUD->DEV"

    def test_parse_data_channel_with_7e_markers(self):
        """Test parsing 0x73 packet with 0x7e data markers."""
        packet = bytes(
            [
                0x73,
                0x00,
                0x00,
                0x00,
                0x20,
                0xAA,
                0xBB,
                0xCC,
                0xDD,
                0x00,
                0x05,
                0x00,
                0x7E,  # Start marker (byte 12)
                0xF8,
                0x52,
                0x06,  # Command bytes
                0x00,
                0x00,
                0x00,
                0x01,
                0x02,
                0x03,
                0x7E,  # End marker
            ]
            + [0x00] * 8
        )
        result = _require_packet(parse_cync_packet(packet))

        assert "data_payload" in result
        assert result["data_length"] == 11  # From 0x7E to 0x7E inclusive

    def test_parse_query_status_command(self):
        """Test parsing QUERY_STATUS command in 0x73 packet."""
        packet = bytes(
            [
                0x73,
                0x00,
                0x00,
                0x00,
                0x20,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x7E,  # Start
                0x00,
                0x00,
                0x00,
                0x00,
                0xF8,
                0x52,
                0x06,  # QUERY_STATUS command
            ]
            + [0x00] * 3
            + [0x7E]
            + [0x00] * 7  # End marker
        )
        result = _require_packet(parse_cync_packet(packet))

        assert "command" in result
        assert result["command"] == "QUERY_STATUS"

    def test_parse_multiple_device_statuses(self):
        """Test parsing multiple device statuses in 0x43 packet."""
        # Create packet with two 19-byte device statuses
        status1 = bytes([0x01, 0x00, 0x00, 0x10, 0x01, 0x64, 0x50, 0x00, 0x00, 0x00, 0x01] + [0x00] * 8)
        status2 = bytes([0x02, 0x00, 0x00, 0x20, 0x00, 0x32, 0x40, 0x00, 0x00, 0x00, 0x00] + [0x00] * 8)

        packet = bytes([0x43, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]) + status1 + status2

        result = _require_packet(parse_cync_packet(packet))

        statuses = _get_device_statuses(result)
        assert len(statuses) == 2
        assert statuses[0]["device_id"] == 16
        assert statuses[1]["device_id"] == 32

    def test_parse_all_known_packet_types(self) -> None:
        """Test parsing all known packet types."""
        cases = [
            (0x23, "HANDSHAKE"),
            (0x28, "HELLO_ACK"),
            (0x43, "DEVICE_INFO"),
            (0x48, "INFO_ACK"),
            (0x73, "DATA_CHANNEL"),
            (0x78, "KEEPALIVE"),
            (0x7B, "DATA_ACK"),
            (0x83, "STATUS_BROADCAST"),
            (0x88, "STATUS_ACK"),
            (0xD3, "HEARTBEAT_DEV"),
            (0xD8, "HEARTBEAT_CLOUD"),
        ]
        for packet_type, expected_name in cases:
            packet = bytes([packet_type, 0x00, 0x00, 0x00, 0x08] + [0x00] * 3)
            result = _require_packet(parse_cync_packet(packet))
            assert result["packet_type_name"] == expected_name


class TestFormatPacketLog:
    """Tests for format_packet_log function."""

    def test_format_none_input(self):
        """Test formatting None input."""
        result = format_packet_log(None)
        assert result == "Invalid packet"

    def test_format_empty_dict(self):
        """Test formatting empty dict."""
        result = format_packet_log({})
        # Should return "Invalid packet" since required keys are missing
        assert result == "Invalid packet"

    def test_format_minimal_packet(self):
        """Test formatting minimal valid parsed packet."""
        parsed: PacketDict = {
            "direction": "DEV->CLOUD",
            "packet_type": "0x73",
            "packet_type_name": "DATA_CHANNEL",
            "raw_len": 10,
            "raw_hex": "73 00 00 00 08 aa bb cc dd ee",
        }
        result = format_packet_log(parsed)

        assert "[DEV->CLOUD]" in result
        assert "0x73" in result
        assert "DATA_CHANNEL" in result

    def test_format_with_endpoint_and_counter(self):
        """Test formatting packet with endpoint and counter."""
        parsed: PacketDict = {
            "direction": "CLOUD->DEV",
            "packet_type": "0x83",
            "packet_type_name": "STATUS_BROADCAST",
            "endpoint": "aa bb cc dd",
            "counter": "0x05",
            "declared_length": 32,
            "raw_len": 32,
            "raw_hex": "83 00 00 00 20 " + " ".join(["00"] * 27),
        }
        result = format_packet_log(parsed, verbose=True)

        assert "EP:aa bb cc dd" in result
        assert "CTR:0x05" in result
        assert "LEN:32" in result

    def test_format_with_command(self):
        """Test formatting packet with command."""
        parsed: PacketDict = {
            "direction": "DEV->CLOUD",
            "packet_type": "0x73",
            "packet_type_name": "DATA_CHANNEL",
            "command": "QUERY_STATUS",
            "raw_len": 20,
            "raw_hex": "73 " + " ".join(["00"] * 19),
        }
        result = format_packet_log(parsed)

        assert "Command: QUERY_STATUS" in result

    def test_format_with_devices(self):
        """Test formatting packet with device IDs."""
        parsed: PacketDict = {
            "direction": "DEV->CLOUD",
            "packet_type": "0x43",
            "packet_type_name": "DEVICE_INFO",
            "contains_devices": ["16 (0x10)", "32 (0x20)"],
            "raw_len": 40,
            "raw_hex": "43 " + " ".join(["00"] * 39),
        }
        result = format_packet_log(parsed)

        assert "Devices: 16 (0x10), 32 (0x20)" in result

    def test_format_with_device_statuses_verbose(self):
        """Test formatting packet with device statuses in verbose mode."""
        parsed: PacketDict = {
            "direction": "DEV->CLOUD",
            "packet_type": "0x43",
            "packet_type_name": "DEVICE_INFO",
            "device_statuses": [
                {"device_id": 16, "state": "ON", "brightness": 100, "mode": "WHITE", "temp": 80, "online": True},
                {"device_id": 32, "state": "OFF", "brightness": 0, "mode": "RGB", "color": "#ff0000", "online": False},
            ],
            "raw_len": 50,
            "raw_hex": "43 " + " ".join(["00"] * 49),
        }
        result = format_packet_log(parsed, verbose=True)

        assert "Device Statuses (2 devices):" in result
        assert "[ 16]" in result or "[16]" in result  # Allow spacing variations
        assert "ON" in result
        assert "Bri:100" in result
        assert "Temp: 80" in result or "Temp:80" in result  # Allow spacing variations
        assert "[ 32]" in result or "[32]" in result  # Allow spacing variations
        assert "OFF" in result

    def test_format_with_device_statuses_non_verbose(self):
        """Test formatting packet with device statuses in non-verbose mode."""
        parsed: PacketDict = {
            "direction": "DEV->CLOUD",
            "packet_type": "0x43",
            "packet_type_name": "DEVICE_INFO",
            "device_statuses": [
                {"device_id": 16, "state": "ON", "brightness": 100, "mode": "WHITE", "temp": 80, "online": True}
            ],
            "raw_len": 30,
            "raw_hex": "43 " + " ".join(["00"] * 29),
        }
        result = format_packet_log(parsed, verbose=False)

        # Non-verbose should not show device details
        assert "Device Statuses" not in result or "[16]" not in result

    def test_format_with_short_data_payload(self):
        """Test formatting packet with short data payload."""
        parsed: PacketDict = {
            "direction": "DEV->CLOUD",
            "packet_type": "0x73",
            "packet_type_name": "DATA_CHANNEL",
            "data_payload": "7e f8 52 06 00 7e",
            "raw_len": 20,
            "raw_hex": "73 00 00 00 14 " + " ".join(["00"] * 15),
        }
        result = format_packet_log(parsed, verbose=True)

        assert "Data: 7e f8 52 06 00 7e" in result

    def test_format_with_long_data_payload(self):
        """Test formatting packet with long data payload (>100 chars)."""
        long_payload = " ".join(["aa"] * 60)  # Creates 179 char string
        parsed: PacketDict = {
            "direction": "DEV->CLOUD",
            "packet_type": "0x73",
            "packet_type_name": "DATA_CHANNEL",
            "data_payload": long_payload,
            "raw_len": 70,
            "raw_hex": "73 " + long_payload,
        }
        result = format_packet_log(parsed, verbose=True)

        # Should truncate and show "..."
        assert "Data: " in result
        assert "..." in result

    def test_format_with_very_long_raw_hex(self):
        """Test formatting packet with very long raw hex."""
        long_hex = " ".join(["ff"] * 150)  # Creates 449 char string
        parsed: PacketDict = {
            "direction": "DEV->CLOUD",
            "packet_type": "0x83",
            "packet_type_name": "STATUS_BROADCAST",
            "raw_len": 150,
            "raw_hex": long_hex,
        }
        result = format_packet_log(parsed, verbose=True)

        # Should truncate raw hex
        assert "Raw: " in result
        assert "... (150 bytes)" in result

    def test_format_non_verbose_mode(self):
        """Test formatting in non-verbose mode excludes details."""
        parsed: PacketDict = {
            "direction": "DEV->CLOUD",
            "packet_type": "0x73",
            "packet_type_name": "DATA_CHANNEL",
            "data_payload": "7e f8 52 06 00 7e",
            "raw_len": 20,
            "raw_hex": "73 00 00 00 14 " + " ".join(["00"] * 15),
        }
        result = format_packet_log(parsed, verbose=False)

        # Non-verbose should not show data payload or raw hex
        assert "Data:" not in result
        assert "Raw:" not in result
