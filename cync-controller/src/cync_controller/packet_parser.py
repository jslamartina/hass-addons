"""Packet parsing utilities for Cync protocol analysis"""

from typing import Any


def _parse_0x73_packet(packet_bytes: bytes | bytearray, result: dict[str, Any]) -> None:
    """Parse 0x73 DATA_CHANNEL packet."""
    if len(packet_bytes) <= 12:
        return

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

        if data_end - data_start > 8:
            cmd_bytes: bytes | bytearray = packet_bytes[data_start + 5 : data_start + 8]
            cmd_hex: str = " ".join(f"{b:02x}" for b in cmd_bytes)

            cmd_names = {
                "f8 52 06": "QUERY_STATUS",
                "f8 8e 0c": "SET_MODE",
                "fa 8e 14": "MODE_RESPONSE",
                "f8 ea 00": "UNKNOWN_CMD",
            }
            result["command"] = cmd_names.get(cmd_hex, f"CMD_{cmd_hex}")

            device_ids: list[int] = []
            search_start = data_start + 10 if data_start + 10 < data_end else data_start + 8
            for i in range(search_start, data_end - 1):
                if 10 <= packet_bytes[i] <= 255 and packet_bytes[i + 1] == 0x00 and packet_bytes[i] not in device_ids:
                    device_ids.append(packet_bytes[i])
            if device_ids:
                result["contains_devices"] = [f"{d} ({hex(d)})" for d in device_ids]


def _parse_0x83_packet(packet_bytes: bytes | bytearray, result: dict[str, Any]) -> None:
    """Parse 0x83 STATUS_BROADCAST packet."""
    if len(packet_bytes) <= 12:
        return

    result["data_payload"] = " ".join(f"{b:02x}" for b in packet_bytes[12:])
    result["data_length"] = len(packet_bytes) - 12

    device_ids: list[int] = []
    for i in range(12, len(packet_bytes) - 1):
        if (
            10 <= packet_bytes[i] <= 255
            and packet_bytes[i + 1] == 0x00
            and i + 3 < len(packet_bytes)
            and packet_bytes[i + 2] == packet_bytes[i]
            and packet_bytes[i + 3] == 0x00
        ):
            device_ids.append(packet_bytes[i])
    if device_ids:
        result["contains_devices"] = [f"{d} ({hex(d)})" for d in device_ids[:5]]


def _parse_0x43_packet(packet_bytes: bytes | bytearray, result: dict[str, Any]) -> None:
    """Parse 0x43 DEVICE_INFO packet."""
    if len(packet_bytes) <= 12:
        return

    result["data_payload"] = " ".join(f"{b:02x}" for b in packet_bytes[12:])

    statuses: list[dict[str, Any]] = []
    offset: int = 12
    while offset + 19 <= len(packet_bytes):
        dev_id: int = packet_bytes[offset + 3]
        state: int = packet_bytes[offset + 4]
        brightness: int = packet_bytes[offset + 5]
        temp: int = packet_bytes[offset + 6]
        r: int = packet_bytes[offset + 7]
        g: int = packet_bytes[offset + 8]
        b: int = packet_bytes[offset + 9]
        online: int = packet_bytes[offset + 10]

        status: dict[str, Any] = {
            "device_id": dev_id,
            "state": "ON" if state else "OFF",
            "brightness": brightness,
        }

        if temp > 100:
            status["mode"] = "RGB"
            status["color"] = f"#{r:02x}{g:02x}{b:02x}"
        else:
            status["mode"] = "WHITE"
            status["temp"] = temp

        status["online"] = bool(online)
        statuses.append(status)
        offset += 19

    if statuses:
        result["device_statuses"] = statuses
        result["contains_devices"] = [f"{s['device_id']} ({hex(s['device_id'])})" for s in statuses]


def parse_cync_packet(packet_bytes: bytes | bytearray, direction: str = "UNKNOWN") -> dict[str, Any] | None:
    """Parse a Cync protocol packet and return structured information

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

    result: dict[str, Any] = {
        "raw_hex": " ".join(f"{b:02x}" for b in packet_bytes),
        "raw_len": len(packet_bytes),
        "direction": direction,
    }

    # Parse header
    packet_type: int = packet_bytes[0]
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
        multiplier: int = packet_bytes[3]
        base_len: int = packet_bytes[4]
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

    if packet_type == 0x73:
        _parse_0x73_packet(packet_bytes, result)
    elif packet_type == 0x83:
        _parse_0x83_packet(packet_bytes, result)
    elif packet_type == 0x43:
        _parse_0x43_packet(packet_bytes, result)

    return result


def _format_packet_header(parsed: dict[str, Any]) -> str:
    """Format packet header line."""
    header = f"[{parsed['direction']}] {parsed['packet_type']} {parsed['packet_type_name']}"
    if "endpoint" in parsed:
        header += f" | EP:{parsed['endpoint']}"
    if "counter" in parsed:
        header += f" | CTR:{parsed['counter']}"
    if "declared_length" in parsed:
        header += f" | LEN:{parsed['declared_length']}"
    return header


def _format_device_statuses(parsed: dict[str, Any]) -> list[str]:
    """Format device statuses section."""
    lines: list[str] = []
    if "device_statuses" in parsed:
        lines.append(f"  Device Statuses ({len(parsed['device_statuses'])} devices):")
        for status in parsed["device_statuses"][:10]:
            line = f"    [{status['device_id']:3d}] {status['state']:3s} "
            if status["mode"] == "RGB":
                line += f"Bri:{status['brightness']:3d} RGB:{status['color']}"
            else:
                line += f"Bri:{status['brightness']:3d} Temp:{status['temp']:3d}"
            line += f" Online:{status['online']}"
            lines.append(line)
    return lines


def _format_data_payload(parsed: dict[str, Any], verbose: bool) -> list[str]:
    """Format data payload section."""
    lines: list[str] = []
    if verbose and "data_payload" in parsed:
        data: str = parsed["data_payload"]
        if len(data) > 100:
            lines.append(f"  Data: {data[:100]}...")
            lines.append(f"        {data[100:200]}...")
            if len(data) > 200:
                lines.append(f"        ... ({len(data)} chars total)")
        else:
            lines.append(f"  Data: {data}")
    return lines


def format_packet_log(parsed: dict[str, Any] | None, verbose: bool = True) -> str:
    """Format parsed packet into readable log string"""
    if not parsed:
        return "Invalid packet"

    lines: list[str] = [_format_packet_header(parsed)]

    if "command" in parsed:
        lines.append(f"  Command: {parsed['command']}")

    if "contains_devices" in parsed:
        lines.append(f"  Devices: {', '.join(parsed['contains_devices'])}")

    if verbose:
        lines.extend(_format_device_statuses(parsed))
        lines.extend(_format_data_payload(parsed, verbose))

        if parsed["raw_len"] <= 100:
            lines.append(f"  Raw: {parsed['raw_hex']}")
        else:
            lines.append(f"  Raw: {parsed['raw_hex'][:200]}... ({parsed['raw_len']} bytes)")

    return "\n".join(lines)
