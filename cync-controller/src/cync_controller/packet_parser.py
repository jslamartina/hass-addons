"""
Packet parsing utilities for Cync protocol analysis
"""

from typing import Callable, Dict, List, Optional


def parse_cync_packet(packet_bytes, direction="UNKNOWN"):
    """
    Parse a Cync protocol packet and return structured information

    Returns dict with:
        - packet_type: hex value (0x73, 0x83, etc.)
        - packet_type_name: human readable name
        - direction: DEV->CLOUD or CLOUD->DEV
        - length: packet length from header
        - endpoint: 4-byte endpoint ID
        - counter: sequence counter
        - data: parsed data payload
        - raw_hex: full packet as hex string
    """
    if not packet_bytes or len(packet_bytes) < 5:
        return None

    result = {
        "raw_hex": " ".join(f"{b:02x}" for b in packet_bytes),
        "raw_len": len(packet_bytes),
        "direction": direction,
    }

    # Parse header
    packet_type = packet_bytes[0]
    result["packet_type"] = f"0x{packet_type:02x}"

    # Packet type names
    type_names = {
        0x23: "HANDSHAKE",
        0x28: "HELLO_ACK",
        0x43: "DEVICE_INFO",
        0x48: "INFO_ACK",
        0x73: "DATA_CHANNEL",
        0x78: "KEEPALIVE",
        0x7B: "DATA_ACK",
        0x83: "STATUS_BROADCAST",
        0x88: "STATUS_ACK",
        0xD3: "HEARTBEAT_DEV",
        0xD8: "HEARTBEAT_CLOUD",
    }
    result["packet_type_name"] = type_names.get(packet_type, "UNKNOWN")

    # Parse length (bytes 1-4)
    # Byte 3 is multiplier (value * 256), byte 4 is base length
    # Total length = (byte[3] * 256) + byte[4]
    if len(packet_bytes) >= 5:
        multiplier = packet_bytes[3]
        base_len = packet_bytes[4]
        result["declared_length"] = (multiplier * 256) + base_len
        if multiplier > 0:
            result["length_calc"] = f"({multiplier} * 256) + {base_len}"

    # Parse endpoint and counter based on packet type
    if packet_type in [0x23, 0x73, 0x7B, 0x83, 0x88] and len(packet_bytes) >= 12:
        result["endpoint"] = " ".join(f"{b:02x}" for b in packet_bytes[5:9])
        result["endpoint_int"] = int.from_bytes(packet_bytes[5:9], "little")

        # Counter/sequence at different positions for different packets
        if packet_type == 0x23:
            result["counter"] = f"0x{packet_bytes[9]:02x}"
        elif packet_type in [0x73, 0x83]:
            result["counter"] = f"0x{packet_bytes[10]:02x}"

    # Use dispatch table to parse data payload
    parser_func = _get_packet_parser(packet_type)
    if parser_func:
        parser_func(packet_bytes, result)

    return result


def _get_packet_parser(packet_type: int) -> Optional[Callable]:
    """Get the appropriate parser function for a packet type."""
    parsers: Dict[int, Callable] = {
        0x73: _parse_data_channel_packet,
        0x83: _parse_status_broadcast_packet,
        0x43: _parse_device_info_packet,
    }
    return parsers.get(packet_type)


def _parse_data_channel_packet(packet_bytes: bytes, result: dict):
    """Parse 0x73 DATA_CHANNEL packet."""
    if len(packet_bytes) <= 12:
        return

    # Data starts at byte 12, look for 0x7e markers
    data_start = None
    data_end = None
    for i in range(12, len(packet_bytes)):
        if packet_bytes[i] == 0x7E:
            if data_start is None:
                data_start = i
            else:
                data_end = i
                break

    if data_start and data_end:
        result["data_payload"] = " ".join(f"{b:02x}" for b in packet_bytes[data_start : data_end + 1])
        result["data_length"] = data_end - data_start + 1

        # Parse command type for 0x73 packets
        if data_end - data_start > 8:
            cmd_bytes = packet_bytes[data_start + 5 : data_start + 8]
            cmd_hex = " ".join(f"{b:02x}" for b in cmd_bytes)

            cmd_names = {
                "f8 52 06": "QUERY_STATUS",
                "f8 8e 0c": "SET_MODE",
                "fa 8e 14": "MODE_RESPONSE",
                "f8 ea 00": "UNKNOWN_CMD",
            }
            result["command"] = cmd_names.get(cmd_hex, f"CMD_{cmd_hex}")

            # Parse device IDs in payload (skip command header bytes)
            device_ids = []
            # Command header is at offsets 5-7, device ID typically at offset 14+
            # Skip at least 10 bytes from data_start to avoid command header bytes
            search_start = data_start + 10 if data_start + 10 < data_end else data_start + 8
            for i in range(search_start, data_end - 1):
                # Look for device ID pattern (2 bytes forming valid ID)
                # Device IDs are typically followed by 0x00 and not part of command header
                # Avoid duplicates
                if (
                    10 <= packet_bytes[i] <= 255
                    and packet_bytes[i + 1] == 0x00
                    and packet_bytes[i] not in device_ids
                ):
                    device_ids.append(packet_bytes[i])
            if device_ids:
                result["contains_devices"] = [f"{d} ({hex(d)})" for d in device_ids]


def _parse_status_broadcast_packet(packet_bytes: bytes, result: dict):
    """Parse 0x83 STATUS_BROADCAST packet."""
    if len(packet_bytes) <= 12:
        return

    # Status broadcast - data after header
    result["data_payload"] = " ".join(f"{b:02x}" for b in packet_bytes[12:])
    result["data_length"] = len(packet_bytes) - 12

    # Parse device IDs in status
    device_ids = []
    for i in range(12, len(packet_bytes) - 1):
        # Check if followed by another copy (common pattern)
        if (
            10 <= packet_bytes[i] <= 255
            and packet_bytes[i + 1] == 0x00
            and i + 3 < len(packet_bytes)
            and packet_bytes[i + 2] == packet_bytes[i]
            and packet_bytes[i + 3] == 0x00
        ):
            device_ids.append(packet_bytes[i])
    if device_ids:
        result["contains_devices"] = [f"{d} ({hex(d)})" for d in device_ids[:5]]  # Limit to first 5


def _parse_device_info_packet(packet_bytes: bytes, result: dict):
    """Parse 0x43 DEVICE_INFO packet."""
    if len(packet_bytes) <= 12:
        return

    # Device info packet - contains 19-byte status structures for each device
    result["data_payload"] = " ".join(f"{b:02x}" for b in packet_bytes[12:])

    # Parse device statuses (19 bytes each)
    # Format: item(1) ?(1) ?(1) device_id(1) state(1) brightness(1) temp(1) R(1) G(1) B(1) online(1) ?(8)
    statuses = []
    offset = 12
    while offset + 19 <= len(packet_bytes):
        dev_id = packet_bytes[offset + 3]
        state = packet_bytes[offset + 4]
        brightness = packet_bytes[offset + 5]
        temp = packet_bytes[offset + 6]
        r = packet_bytes[offset + 7]
        g = packet_bytes[offset + 8]
        b = packet_bytes[offset + 9]
        online = packet_bytes[offset + 10]

        # Determine mode based on temperature value
        if temp > 100:
            mode = "RGB"
            color = f"#{r:02x}{g:02x}{b:02x}"
        else:
            mode = "WHITE"
            color = f"K{temp}"

        status = {
            "device_id": dev_id,
            "state": "ON" if state else "OFF",
            "brightness": brightness,
            "mode": mode,
            "color": color,
            "online": bool(online),
        }
        statuses.append(status)
        offset += 19

    if statuses:
        result["device_statuses"] = statuses


def format_packet_log(packet_info: dict) -> str:
    """
    Format packet information for logging

    Args:
        packet_info: Dictionary returned by parse_cync_packet()

    Returns:
        Formatted string for logging
    """
    if not packet_info:
        return "Invalid packet"

    lines = []
    lines.append(f"Packet: {packet_info['packet_type_name']} ({packet_info['packet_type']})")
    lines.append(f"Direction: {packet_info['direction']}")
    lines.append(f"Length: {packet_info['raw_len']} bytes")

    if "declared_length" in packet_info:
        lines.append(f"Declared: {packet_info['declared_length']} bytes")

    if "endpoint" in packet_info:
        lines.append(f"Endpoint: {packet_info['endpoint']}")

    if "counter" in packet_info:
        lines.append(f"Counter: {packet_info['counter']}")

    if "command" in packet_info:
        lines.append(f"Command: {packet_info['command']}")

    if "contains_devices" in packet_info:
        lines.append(f"Devices: {', '.join(packet_info['contains_devices'])}")

    if "device_statuses" in packet_info:
        lines.append("Device Statuses:")
        for status in packet_info["device_statuses"]:
            line = f"  ID {status['device_id']}: {status['state']}"
            if status["online"]:
                if status["mode"] == "RGB":
                    line += f" Bri:{status['brightness']:3d} RGB:{status['color']}"
                else:
                    line += f" Bri:{status['brightness']:3d} {status['color']}"
            else:
                line += " (offline)"
            lines.append(line)

    if "data_payload" in packet_info:
        lines.append(f"Data: {packet_info['data_payload']}")

    return "\n".join(lines)