#!/usr/bin/env python3
"""
Test script for toggle packet injection via MITM proxy REST API.

This script crafts toggle (0x73) and mesh info request packets, injects them
via the MITM proxy REST API, and analyzes the responses for ACK validation.

Usage:
    python mitm/test-toggle-injection.py --endpoint "45 88 0f 3a" --device-id 80 --iterations 10
    python mitm/test-toggle-injection.py --test mesh-info --endpoint "45 88 0f 3a"
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

# Import constants from transport module
try:
    from transport.device_info import DEVICE_ID_LENGTH_BYTES, DEVICE_TYPE_LENGTH_BYTES
except ImportError:
    # Fallback if import fails
    DEVICE_ID_LENGTH_BYTES = 4
    DEVICE_TYPE_LENGTH_BYTES = 24

DEVICE_ID_BYTES = 2

# Test constants
TIMEOUT_MS = 100
SLEEP_SHORT_SECONDS = 0.2
SLEEP_LONG_SECONDS = 2.0

# Packet parsing constants
MSG_ID_POSITION_CHECK = 10  # Expected position for msg_id in hex bytes
MIN_SAMPLES_FOR_P95 = 20  # Minimum samples needed for p95 percentile calculation
MIN_MESH_INFO_PACKET_LENGTH = 50  # Minimum packet length to consider as mesh info


def calculate_checksum_between_markers(packet: bytes, offset_after_start: int = 6) -> int:
    """
    Compute checksum for a packet with 0x7E-delimited inner structure.

    Algorithm (from legacy packet_checksum.py):
    - Find the first 0x7E and the last 0x7E
    - Sum bytes from (start_index + offset_after_start) up to the byte
      just before the checksum (i.e., excluding the last two bytes: checksum and 0x7E)
    - Return sum modulo 256

    Args:
        packet: Complete packet bytes
        offset_after_start: Number of bytes to skip after the first 0x7E (default 6)

    Returns:
        The checksum (0-255)
    """
    start = packet.index(0x7E)
    end = len(packet) - 1  # index of trailing 0x7E

    if end <= start + offset_after_start:
        error_msg = "Packet too short to compute checksum with given offset"
        raise ValueError(error_msg)

    # Exclude checksum byte at position end-1 and trailing 0x7E at position end
    data_to_sum = packet[start + offset_after_start : end - 1]
    return sum(data_to_sum) % 256


def craft_toggle_packet(endpoint: bytes, msg_id: int, device_id: int, state: bool) -> bytes:
    """
    Craft a toggle (0x73) packet for device control.

    Args:
        endpoint: 4-byte endpoint from handshake packet
        msg_id: Message ID (0x00-0xFF)
        device_id: DEVICE_ID_BYTES-byte device ID (0-65535)
        state: True=on, False=off

    Returns:
        Complete packet bytes
    """
    # Header: packet type + length
    header = bytes([0x73, 0x00, 0x00, 0x00, 0x1F])  # Length = 31 bytes (0x1F)

    # Queue ID: endpoint + 0x00 (5 bytes)
    queue_id = endpoint + bytes([0x00])

    # msg_id: 3 bytes (msg_id, 0x00, 0x00)
    msg_id_bytes = bytes([msg_id, 0x00, 0x00])

    # Device ID as 2-byte little-endian
    device_id_bytes = device_id.to_bytes(DEVICE_ID_BYTES, byteorder="little")

    # State byte
    state_byte = 0x01 if state else 0x00

    # Inner structure (without checksum yet)
    inner_struct = bytearray(
        [
            0x7E,  # Start marker
            msg_id,  # Control byte
            0x01,
            0x00,
            0x00,
            0xF8,
            0x8E,
            0x0C,
            0x00,
            msg_id,  # Control byte (repeated)
            0x01,
            0x00,
            0x00,
            0x00,
            device_id_bytes[0],
            device_id_bytes[1],  # Device ID (little-endian)
            0xF7,
            0x11,
            0x02,
            state_byte,  # State
            0x01,
            0x00,  # Checksum placeholder
            0x7E,  # End marker
        ]
    )

    # Calculate and insert checksum
    checksum = calculate_checksum_between_markers(bytes(inner_struct))
    inner_struct[-2] = checksum

    # Combine all parts
    return header + queue_id + msg_id_bytes + bytes(inner_struct)


def craft_mesh_info_request(endpoint: bytes) -> bytes:
    """
    Craft a mesh info request (0x73) packet.

    Args:
        endpoint: 4-byte endpoint from handshake packet

    Returns:
        Complete packet bytes
    """
    # Header: packet type + length
    header = bytes([0x73, 0x00, 0x00, 0x00, 0x18])  # Length = 24 bytes (0x18)

    # Queue ID: endpoint + 0x00 (5 bytes)
    queue_id = endpoint + bytes([0x00])

    # msg_id: Always 0x00 0x00 0x00 for mesh info
    msg_id_bytes = bytes([0x00, 0x00, 0x00])

    # Inner structure (without checksum yet)
    inner_struct = bytearray(
        [
            0x7E,  # Start marker
            0x1F,  # Control byte 1
            0x00,
            0x00,
            0x00,
            0xF8,  # Fixed
            0x52,  # Control byte 2 (identifies mesh info)
            0x06,  # Command type
            0x00,
            0x00,
            0x00,
            0xFF,
            0xFF,  # Broadcast to all devices
            0x00,
            0x00,
            0x00,  # Checksum placeholder
            0x7E,  # End marker
        ]
    )

    # Calculate and insert checksum
    checksum = calculate_checksum_between_markers(bytes(inner_struct))
    inner_struct[-2] = checksum

    # Combine all parts
    return header + queue_id + msg_id_bytes + bytes(inner_struct)


def inject_packet(api_url: str, packet: bytes, direction: str = "CLOUD→DEV") -> dict[str, Any]:
    """
    Inject packet via MITM proxy REST API.

    Args:
        api_url: REST API URL (e.g., http://localhost:8080/inject)
        packet: Packet bytes to inject
        direction: "CLOUD→DEV" or "DEV→CLOUD"

    Returns:
        API response as dict
    """
    hex_string = packet.hex(" ")

    response = requests.post(api_url, json={"direction": direction, "hex": hex_string}, timeout=5)

    response.raise_for_status()
    return response.json()


def parse_capture_logs(capture_file: Path, since_time: float | None = None) -> list[dict[str, Any]]:
    """
    Parse JSONL capture logs.

    Args:
        capture_file: Path to capture file (JSONL format)
        since_time: Only return packets after this Unix timestamp

    Returns:
        List of packet dicts
    """
    packets = []

    if not capture_file.exists():
        return packets

    capture_path = Path(capture_file)
    with capture_path.open() as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue

            try:
                packet = json.loads(line)

                # Filter by timestamp if requested
                if since_time is not None:
                    packet_time = datetime.fromisoformat(packet["timestamp"]).timestamp()
                    if packet_time < since_time:
                        continue

                packets.append(packet)
            except json.JSONDecodeError:
                continue

    return packets


def find_ack_for_msg_id(
    packets: list[dict[str, Any]], msg_id: int, ack_type: str = "7b"
) -> dict[str, Any] | None:
    """
    Find ACK packet matching msg_id.

    Args:
        packets: List of packet dicts from capture
        msg_id: Message ID to match (0x00-0xFF)
        ack_type: ACK packet type (default "7b" for DATA_ACK)

    Returns:
        Matching ACK packet dict or None
    """
    msg_id_hex = f"{msg_id:02x}"

    for packet in packets:
        hex_data = packet["hex"]

        # Check if packet type matches
        if not hex_data.startswith(ack_type):
            continue

        # Check for msg_id in expected positions (bytes 10-11 typically)
        hex_bytes = hex_data.split()
        if (
            len(hex_bytes) > MSG_ID_POSITION_CHECK
            and hex_bytes[MSG_ID_POSITION_CHECK] == msg_id_hex
        ):
            return packet

    return None


def parse_mesh_info_response(hex_string: str) -> list[dict[str, Any]]:
    """
    Parse mesh info response into device structures.

    Args:
        hex_string: Hex string of mesh info response packet

    Returns:
        List of device info dicts
    """
    packet = bytes.fromhex(hex_string.replace(" ", ""))

    # Find inner struct boundaries
    try:
        start = packet.index(0x7E)
    except ValueError:
        return []

    end = len(packet) - 1  # trailing 0x7E

    # Extract inner struct
    inner_struct = packet[start + 1 : end]

    # Find start of device data (14 or 15 bytes into inner struct)
    device_data_start = 14
    if len(inner_struct) > device_data_start and inner_struct[device_data_start] == 0x00:
        device_data_start = 15

    # Parse DEVICE_TYPE_LENGTH_BYTES-byte device structures
    devices = []
    for i in range(device_data_start, len(inner_struct) - 1, DEVICE_TYPE_LENGTH_BYTES):
        dev_struct = inner_struct[i : i + DEVICE_TYPE_LENGTH_BYTES]
        if len(dev_struct) < DEVICE_TYPE_LENGTH_BYTES:
            break

        devices.append(
            {
                "device_id": dev_struct[0],
                "type": dev_struct[2],
                "state": dev_struct[8],
                "brightness": dev_struct[12],
                "temperature": dev_struct[16],
                "rgb": (dev_struct[20], dev_struct[21], dev_struct[22]),
                "valid": dev_struct[23],
            }
        )

    return devices


async def run_toggle_test(
    api_url: str,
    endpoint: bytes,
    device_id: int,
    iterations: int,
    capture_file: Path | None = None,
) -> dict[str, Any]:
    """
    Run toggle packet injection test.

    Args:
        api_url: REST API URL
        endpoint: Device endpoint (4 bytes)
        device_id: Device ID (0-65535)
        iterations: Number of toggle cycles
        capture_file: Optional capture file to monitor for ACKs

    Returns:
        Test results dict
    """
    results = {
        "test": "toggle",
        "iterations": iterations,
        "successes": 0,
        "failures": 0,
        "acks_received": 0,
        "latencies_ms": [],
        "packets": [],
    }

    print("\n=== Toggle Packet Injection Test ===")
    print(f"Endpoint: {endpoint.hex(' ')}")
    print(f"Device ID: {device_id}")
    print(f"Iterations: {iterations}")
    print(f"API URL: {api_url}\n")

    for i in range(iterations):
        msg_id = 0x10 + i
        state = (i % 2) == 0  # Alternate ON/OFF

        print(
            f"[{i + 1}/{iterations}] Injecting {'ON' if state else 'OFF'} command "
            f"(msg_id=0x{msg_id:02x})..."
        )

        # Craft packet
        packet = craft_toggle_packet(endpoint, msg_id, device_id, state)

        # Record start time
        start_time = time.time()

        # Inject
        try:
            response = inject_packet(api_url, packet)
            results["successes"] += 1

            injection_result = {
                "msg_id": msg_id,
                "state": "on" if state else "off",
                "packet_hex": packet.hex(" "),
                "injection_response": response,
                "ack": None,
                "latency_ms": None,
            }

            # Wait for ACK in capture logs
            if capture_file:
                await asyncio.sleep(SLEEP_SHORT_SECONDS)  # Give time for ACK

                packets = parse_capture_logs(capture_file, since_time=start_time)
                ack = find_ack_for_msg_id(packets, msg_id)

                if ack:
                    ack_time = datetime.fromisoformat(ack["timestamp"]).timestamp()
                    latency_ms = (ack_time - start_time) * 1000

                    injection_result["ack"] = ack
                    injection_result["latency_ms"] = latency_ms
                    results["acks_received"] += 1
                    results["latencies_ms"].append(latency_ms)

                    print(f"  ✓ ACK received (latency: {latency_ms:.1f}ms)")
                else:
                    print("  ✗ No ACK received")
            else:
                print("  ✓ Injected successfully")

            results["packets"].append(injection_result)

        except Exception as e:
            results["failures"] += 1
            print(f"  ✗ Injection failed: {e}")

        # Wait between iterations
        if i < iterations - 1:
            await asyncio.sleep(0.5)

    # Calculate statistics
    if results["latencies_ms"]:
        latencies = sorted(results["latencies_ms"])
        results["latency_stats"] = {
            "min": min(latencies),
            "max": max(latencies),
            "p50": latencies[len(latencies) // 2],
            "p95": latencies[int(len(latencies) * 0.95)]
            if len(latencies) >= MIN_SAMPLES_FOR_P95
            else latencies[-1],
            "p99": latencies[int(len(latencies) * 0.99)]
            if len(latencies) >= TIMEOUT_MS
            else latencies[-1],
        }

    return results


async def run_mesh_info_test(
    api_url: str,
    endpoint: bytes,
    capture_file: Path | None = None,
) -> dict[str, Any]:
    """
    Run mesh info request test.

    Args:
        api_url: REST API URL
        endpoint: Device endpoint (4 bytes)
        capture_file: Optional capture file to monitor for response

    Returns:
        Test results dict
    """
    results = {
        "test": "mesh_info",
        "success": False,
        "ack_received": False,
        "devices_found": 0,
        "devices": [],
    }

    print("\n=== Mesh Info Request Test ===")
    print(f"Endpoint: {endpoint.hex(' ')}")
    print(f"API URL: {api_url}\n")

    # Craft packet
    packet = craft_mesh_info_request(endpoint)

    print("Injecting mesh info request...")
    print(f"Packet: {packet.hex(' ')}\n")

    # Record start time
    start_time = time.time()

    # Inject
    try:
        response = inject_packet(api_url, packet)
        results["success"] = True
        results["injection_response"] = response

        print("✓ Injection successful")
        print(f"  Response: {response}\n")

        # Wait for responses
        if capture_file:
            print("Waiting for mesh info responses...")
            await asyncio.sleep(SLEEP_LONG_SECONDS)  # Give more time for large responses

            packets = parse_capture_logs(capture_file, since_time=start_time)

            # Look for small ACK (f9 52 01...)
            for packet_data in packets:
                hex_data = packet_data["hex"]
                if "f9 52 01" in hex_data:
                    results["ack_received"] = True
                    results["ack_packet"] = packet_data
                    print("✓ Mesh info ACK received")
                    print(f"  Packet: {hex_data[:50]}...\n")
                    break

            # Look for large data responses
            for packet_data in packets:
                hex_data = packet_data["hex"]

                # Mesh info data packets are 0x73 from DEV→CLOUD with large payloads
                if (
                    packet_data["direction"] == "DEV→CLOUD"
                    and hex_data.startswith("73")
                    and packet_data["length"] > MIN_MESH_INFO_PACKET_LENGTH
                ):
                    # Try to parse devices
                    devices = parse_mesh_info_response(hex_data)
                    if devices:
                        results["devices"].extend(devices)
                        results["devices_found"] = len(results["devices"])

                        print(f"✓ Mesh info data received ({len(devices)} devices in this packet)")
                        for dev in devices:
                            print(
                                f"  Device {dev['device_id']:3d}: "
                                f"state={dev['state']}, brightness={dev['brightness']}"
                            )

            if results["devices_found"] > 0:
                print(f"\nTotal devices found: {results['devices_found']}")

    except Exception as e:
        print(f"✗ Injection failed: {e}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Test toggle packet injection via MITM proxy")
    parser.add_argument(
        "--endpoint",
        type=str,
        required=True,
        help="Device endpoint as hex string (e.g., '45 88 0f 3a')",
    )
    parser.add_argument(
        "--device-id",
        type=int,
        default=80,
        help="Device ID (0-65535, default: 80)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=10,
        help="Number of toggle iterations (default: 10)",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="http://localhost:8080/inject",
        help="MITM proxy REST API URL (default: http://localhost:8080/inject)",
    )
    parser.add_argument(
        "--capture-file",
        type=str,
        help="Path to capture JSONL file to monitor for ACKs",
    )
    parser.add_argument(
        "--test",
        type=str,
        choices=["toggle", "mesh-info"],
        default="toggle",
        help="Test type (default: toggle)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for results (JSON)",
    )

    args = parser.parse_args()

    # Parse endpoint
    endpoint = bytes.fromhex(args.endpoint.replace(" ", ""))
    if len(endpoint) != DEVICE_ID_LENGTH_BYTES:
        print(f"Error: Endpoint must be 4 bytes, got {len(endpoint)}", file=sys.stderr)
        sys.exit(1)

    # Resolve capture file
    capture_file = Path(args.capture_file) if args.capture_file else None

    # Run test
    if args.test == "toggle":
        results = asyncio.run(
            run_toggle_test(args.api_url, endpoint, args.device_id, args.iterations, capture_file)
        )
    else:
        results = asyncio.run(run_mesh_info_test(args.api_url, endpoint, capture_file))

    # Print summary
    print("\n=== Test Summary ===")
    print(json.dumps(results, indent=2))

    # Save to file if requested
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w") as f:
            json.dump(results, f, indent=2)

        print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
