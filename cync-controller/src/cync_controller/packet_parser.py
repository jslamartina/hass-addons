"""Packet parsing utilities for Cync protocol analysis."""

from typing import cast

PacketDict = dict[str, object]

MIN_PACKET_HEADER_BYTES = 12
SYNC_DELIMITER = 0x7E
MIN_CMD_WINDOW_BYTES = 8
MIN_DEVICE_ID_VALUE = 10
MAX_DEVICE_ID_VALUE = 0xFF
STATUS_PREVIEW_LIMIT = 10
DEVICE_PREVIEW_LIMIT = 5
RGB_TEMP_THRESHOLD = 100
DATA_PREVIEW_SHORT = 100
DATA_PREVIEW_LONG = 200
MIN_PACKET_LENGTH = 5
PACKET_TYPE_HANDSHAKE = 0x23
PACKET_TYPE_DATA_CHANNEL = 0x73
PACKET_TYPE_STATUS_BROADCAST = 0x83
PACKET_TYPE_DEVICE_INFO = 0x43
COUNTER_PACKET_TYPES = (
    PACKET_TYPE_HANDSHAKE,
    PACKET_TYPE_DATA_CHANNEL,
    0x7B,
    PACKET_TYPE_STATUS_BROADCAST,
    0x88,
)


def _format_device_reference(device_id: int) -> str:
    return f"{device_id} ({hex(device_id)})"


def _parse_0x73_packet(packet_bytes: bytes | bytearray, result: PacketDict) -> None:
    """Parse 0x73 DATA_CHANNEL packet."""
    if len(packet_bytes) <= MIN_PACKET_HEADER_BYTES:
        return

    data_start = None
    data_end = None
    for i in range(MIN_PACKET_HEADER_BYTES, len(packet_bytes)):
        if packet_bytes[i] == SYNC_DELIMITER:
            if data_start is None:
                data_start = i
            else:
                data_end = i
                break

    if data_start and data_end:
        result["data_payload"] = " ".join(f"{b:02x}" for b in packet_bytes[data_start : data_end + 1])
        result["data_length"] = data_end - data_start + 1

        if data_end - data_start > MIN_CMD_WINDOW_BYTES:
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
            preferred_offset = data_start + MIN_DEVICE_ID_VALUE
            fallback_offset = data_start + MIN_CMD_WINDOW_BYTES
            search_start = preferred_offset if preferred_offset < data_end else fallback_offset
            for i in range(search_start, data_end - 1):
                if (
                    MIN_DEVICE_ID_VALUE <= packet_bytes[i] <= MAX_DEVICE_ID_VALUE
                    and packet_bytes[i + 1] == 0x00
                    and packet_bytes[i] not in device_ids
                ):
                    device_ids.append(packet_bytes[i])
            if device_ids:
                result["contains_devices"] = [_format_device_reference(d) for d in device_ids]


def _parse_0x83_packet(packet_bytes: bytes | bytearray, result: PacketDict) -> None:
    """Parse 0x83 STATUS_BROADCAST packet."""
    if len(packet_bytes) <= MIN_PACKET_HEADER_BYTES:
        return

    result["data_payload"] = " ".join(f"{b:02x}" for b in packet_bytes[MIN_PACKET_HEADER_BYTES:])
    result["data_length"] = len(packet_bytes) - MIN_PACKET_HEADER_BYTES

    device_ids: list[int] = []
    for i in range(MIN_PACKET_HEADER_BYTES, len(packet_bytes) - 1):
        if (
            MIN_DEVICE_ID_VALUE <= packet_bytes[i] <= MAX_DEVICE_ID_VALUE
            and packet_bytes[i + 1] == 0x00
            and i + 3 < len(packet_bytes)
            and packet_bytes[i + 2] == packet_bytes[i]
            and packet_bytes[i + 3] == 0x00
        ):
            device_ids.append(packet_bytes[i])
    if device_ids:
        result["contains_devices"] = [_format_device_reference(d) for d in device_ids[:DEVICE_PREVIEW_LIMIT]]


def _parse_0x43_packet(packet_bytes: bytes | bytearray, result: PacketDict) -> None:
    """Parse 0x43 DEVICE_INFO packet."""
    if len(packet_bytes) <= MIN_PACKET_HEADER_BYTES:
        return

    result["data_payload"] = " ".join(f"{b:02x}" for b in packet_bytes[MIN_PACKET_HEADER_BYTES:])

    statuses: list[PacketDict] = []
    offset: int = MIN_PACKET_HEADER_BYTES
    while offset + 19 <= len(packet_bytes):
        dev_id: int = packet_bytes[offset + 3]
        state: int = packet_bytes[offset + 4]
        brightness: int = packet_bytes[offset + 5]
        temp: int = packet_bytes[offset + 6]
        r: int = packet_bytes[offset + 7]
        g: int = packet_bytes[offset + 8]
        b: int = packet_bytes[offset + 9]
        online: int = packet_bytes[offset + 10]

        status: PacketDict = {
            "device_id": dev_id,
            "state": "ON" if state else "OFF",
            "brightness": brightness,
        }

        if temp > RGB_TEMP_THRESHOLD:
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
        formatted_devices: list[str] = []
        for status in statuses:
            device_id = status.get("device_id")
            if isinstance(device_id, int):
                formatted_devices.append(_format_device_reference(device_id))
        if formatted_devices:
            result["contains_devices"] = formatted_devices


def parse_cync_packet(packet_bytes: bytes | bytearray, direction: str = "UNKNOWN") -> PacketDict | None:
    """Parse a Cync protocol packet and return structured information.

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
    if not packet_bytes or len(packet_bytes) < MIN_PACKET_LENGTH:
        return None

    result: PacketDict = {
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
    if len(packet_bytes) >= MIN_PACKET_LENGTH:
        multiplier: int = packet_bytes[3]
        base_len: int = packet_bytes[4]
        result["declared_length"] = (multiplier * 256) + base_len
        if multiplier > 0:
            result["length_calc"] = f"({multiplier} * 256) + {base_len}"

    # Parse endpoint and counter based on packet type
    if packet_type in COUNTER_PACKET_TYPES and len(packet_bytes) >= MIN_PACKET_HEADER_BYTES:
        result["endpoint"] = " ".join(f"{b:02x}" for b in packet_bytes[5:9])
        result["endpoint_int"] = int.from_bytes(packet_bytes[5:9], "little")

        # Counter/sequence at different positions for different packets
        if packet_type == PACKET_TYPE_HANDSHAKE:
            result["counter"] = f"0x{packet_bytes[9]:02x}"
        elif packet_type in (PACKET_TYPE_DATA_CHANNEL, PACKET_TYPE_STATUS_BROADCAST):
            result["counter"] = f"0x{packet_bytes[10]:02x}"

    if packet_type == PACKET_TYPE_DATA_CHANNEL:
        _parse_0x73_packet(packet_bytes, result)
    elif packet_type == PACKET_TYPE_STATUS_BROADCAST:
        _parse_0x83_packet(packet_bytes, result)
    elif packet_type == PACKET_TYPE_DEVICE_INFO:
        _parse_0x43_packet(packet_bytes, result)

    return result


def _format_packet_header(parsed: PacketDict) -> str:
    """Format packet header line."""
    direction = str(parsed.get("direction", ""))
    packet_type = str(parsed.get("packet_type", ""))
    packet_type_name = str(parsed.get("packet_type_name", ""))
    header = f"[{direction}] {packet_type} {packet_type_name}"
    endpoint = parsed.get("endpoint")
    if endpoint is not None:
        header += f" | EP:{endpoint}"
    counter = parsed.get("counter")
    if counter is not None:
        header += f" | CTR:{counter}"
    declared_length = parsed.get("declared_length")
    if declared_length is not None:
        header += f" | LEN:{declared_length}"
    return header


def _format_device_statuses(parsed: PacketDict) -> list[str]:
    """Format device statuses section."""
    lines: list[str] = []
    if "device_statuses" in parsed:
        raw_statuses = parsed["device_statuses"]
        if isinstance(raw_statuses, list):
            typed_statuses: list[PacketDict] = []
            for status in raw_statuses:
                if isinstance(status, dict):
                    typed_statuses.append(cast("PacketDict", status))
            if not typed_statuses:
                return lines
            lines.append(f"  Device Statuses ({len(typed_statuses)} devices):")
            for status_dict in typed_statuses[:STATUS_PREVIEW_LIMIT]:
                device_id_obj = status_dict.get("device_id")
                if not isinstance(device_id_obj, int):
                    continue
                brightness_obj = status_dict.get("brightness", 0)
                state_value = status_dict.get("state", "")
                state_display = str(state_value)
                brightness_value = int(brightness_obj) if isinstance(brightness_obj, int) else 0
                line = f"    [{device_id_obj:3d}] {state_display:3s} "
                mode = status_dict.get("mode")
                if mode == "RGB":
                    color = status_dict.get("color", "")
                    line += f"Bri:{brightness_value:3d} RGB:{color}"
                else:
                    temp_value = status_dict.get("temp")
                    temp_display = int(temp_value) if isinstance(temp_value, int) else 0
                    line += f"Bri:{brightness_value:3d} Temp:{temp_display:3d}"
                line += f" Online:{bool(status_dict.get('online'))}"
                lines.append(line)
    return lines


def _format_data_payload(parsed: PacketDict, verbose: bool) -> list[str]:
    """Format data payload section."""
    lines: list[str] = []
    if verbose and "data_payload" in parsed:
        data = parsed["data_payload"]
        if not isinstance(data, str):
            return lines
        if len(data) > DATA_PREVIEW_SHORT:
            lines.append(f"  Data: {data[:DATA_PREVIEW_SHORT]}...")
            lines.append(f"        {data[DATA_PREVIEW_SHORT:DATA_PREVIEW_LONG]}...")
            if len(data) > DATA_PREVIEW_LONG:
                lines.append(f"        ... ({len(data)} chars total)")
        else:
            lines.append(f"  Data: {data}")
    return lines


def format_packet_log(parsed: PacketDict | None, verbose: bool = True) -> str:
    """Format parsed packet into readable log string."""
    if not parsed:
        return "Invalid packet"

    lines: list[str] = [_format_packet_header(parsed)]

    command = parsed.get("command")
    if command is not None:
        lines.append(f"  Command: {command}")

    devices = parsed.get("contains_devices")
    if isinstance(devices, list):
        device_list: list[str] = []
        for device in devices:
            if isinstance(device, str):
                device_list.append(device)
        if device_list:
            lines.append(f"  Devices: {', '.join(device_list)}")

    if verbose:
        lines.extend(_format_device_statuses(parsed))
        lines.extend(_format_data_payload(parsed, verbose))

        raw_len = parsed.get("raw_len")
        raw_hex = parsed.get("raw_hex")
        if isinstance(raw_len, int) and isinstance(raw_hex, str):
            if raw_len <= DATA_PREVIEW_SHORT:
                lines.append(f"  Raw: {raw_hex}")
            else:
                lines.append(f"  Raw: {raw_hex[:DATA_PREVIEW_LONG]}... ({raw_len} bytes)")

    return "\n".join(lines)
