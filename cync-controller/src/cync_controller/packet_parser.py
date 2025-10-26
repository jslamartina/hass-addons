"""
Packet parsing utilities for Cync protocol analysis
"""


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

    # Parse data payload for 0x73 and 0x83
    if packet_type == 0x73 and len(packet_bytes) > 12:
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

    elif packet_type == 0x83 and len(packet_bytes) > 12:
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

    elif packet_type == 0x43 and len(packet_bytes) > 12:
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

            status = {
                "device_id": dev_id,
                "state": "ON" if state else "OFF",
                "brightness": brightness,
            }

            if temp > 100:
                # RGB mode
                status["mode"] = "RGB"
                status["color"] = f"#{r:02x}{g:02x}{b:02x}"
            else:
                # White/temp mode
                status["mode"] = "WHITE"
                status["temp"] = temp

            status["online"] = bool(online)
            statuses.append(status)
            offset += 19

        if statuses:
            result["device_statuses"] = statuses
            result["contains_devices"] = [f"{s['device_id']} ({hex(s['device_id'])})" for s in statuses]

    return result


def format_packet_log(parsed, verbose=True):
    """Format parsed packet into readable log string"""
    if not parsed:
        return "Invalid packet"

    lines = []

    # Header line with type and direction
    header = f"[{parsed['direction']}] {parsed['packet_type']} {parsed['packet_type_name']}"
    if "endpoint" in parsed:
        header += f" | EP:{parsed['endpoint']}"
    if "counter" in parsed:
        header += f" | CTR:{parsed['counter']}"
    if "declared_length" in parsed:
        header += f" | LEN:{parsed['declared_length']}"
    lines.append(header)

    # Command info for data packets
    if "command" in parsed:
        lines.append(f"  Command: {parsed['command']}")

    # Device IDs if present
    if "contains_devices" in parsed:
        lines.append(f"  Devices: {', '.join(parsed['contains_devices'])}")

    # Device statuses for 0x43 packets
    if "device_statuses" in parsed and verbose:
        lines.append(f"  Device Statuses ({len(parsed['device_statuses'])} devices):")
        for status in parsed["device_statuses"][:10]:  # Limit to 10
            line = f"    [{status['device_id']:3d}] {status['state']:3s} "
            if status["mode"] == "RGB":
                line += f"Bri:{status['brightness']:3d} RGB:{status['color']}"
            else:
                line += f"Bri:{status['brightness']:3d} Temp:{status['temp']:3d}"
            line += f" Online:{status['online']}"
            lines.append(line)

    # Data payload if verbose
    if verbose and "data_payload" in parsed:
        # Split long payloads into multiple lines
        data = parsed["data_payload"]
        if len(data) > 100:
            lines.append(f"  Data: {data[:100]}...")
            lines.append(f"        {data[100:200]}...")
            if len(data) > 200:
                lines.append(f"        ... ({len(data)} chars total)")
        else:
            lines.append(f"  Data: {data}")

    # Raw hex if very verbose
    if verbose and parsed["raw_len"] <= 100:
        lines.append(f"  Raw: {parsed['raw_hex']}")
    elif verbose:
        lines.append(f"  Raw: {parsed['raw_hex'][:200]}... ({parsed['raw_len']} bytes)")

    return "\n".join(lines)
