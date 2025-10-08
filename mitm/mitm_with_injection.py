#!/usr/bin/env python3
"""
⚠️⚠️⚠️ SECURITY WARNING ⚠️⚠️⚠️
This is a Man-in-the-Middle proxy for debugging Cync protocol.
- Disables ALL SSL security
- For LOCAL DEBUGGING ONLY
- DO NOT use on untrusted networks
- DO NOT use in production
⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️

MITM proxy that forwards traffic to Cync cloud AND can inject test packets
Run this instead of socat when you want to test mode changes
"""
import socket
import ssl
import threading
import time
import sys
import os
from packet_parser import parse_cync_packet, format_packet_log
from datetime import datetime

# Cync cloud server
CLOUD_SERVER = "35.196.85.236"
CLOUD_PORT = 23779

# Mode values (for the command byte at the end of the query packet)
MODE_TRADITIONAL = 0x01
MODE_SMART = 0x02

# Global flag to inject packet on next connection
inject_mode = None
inject_lock = threading.Lock()

# Global counter holder (shared across all connections for the same endpoint)
global_counter_holder = {}
counter_lock = threading.Lock()

# Track device 160 status
device_160_status = {
    "state": "UNKNOWN",
    "brightness": 0,
    "temp": 0,
    "online": False,
    "last_updated": None,
}
device_160_lock = threading.Lock()


def update_device_160_status(status):
    """Update device 160 status from parsed packet"""
    with device_160_lock:
        device_160_status.update(status)
        device_160_status["last_updated"] = datetime.now()


def status_logger_thread():
    """Global thread to log device 160 status every 5 seconds"""
    while True:
        try:
            time.sleep(5)
            with device_160_lock:
                if device_160_status["last_updated"]:
                    log(
                        f"[DEV 160] {device_160_status['state']:3s} Bri:{device_160_status['brightness']:3d} Temp:{device_160_status['temp']:3d} Online:{device_160_status['online']}"
                    )
        except Exception as e:
            log(f"[STATUS LOGGER] Error: {e}")
            break


def log(msg):
    """Log with timestamp to both console and file"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_msg = f"[{timestamp}] {msg}"
    print(log_msg, flush=True)

    # Also write to mitm.log
    try:
        with open("mitm.log", "a") as f:
            f.write(log_msg + "\n")
    except IOError as e:
        print(f"WARNING: Failed to write to mitm.log: {e}", file=sys.stderr)
    except Exception as e:
        print(f"ERROR: Unexpected logging failure: {e}", file=sys.stderr)


def calculate_checksum(data):
    """Calculate checksum: sum of data bytes between the 0x7e markers"""
    # Find the 0x7e markers
    start = data.index(0x7E)
    end = len(data) - 1  # Last byte is the closing 0x7E
    # Sum bytes between markers, excluding the markers themselves and the checksum byte
    return sum(data[start + 1 : end - 1]) % 256


def craft_mode_packet(endpoint, counter, mode_byte):
    """Craft a 0x73 mode query/command packet (CLOUD->DEV direction)"""
    # Based on captured packets (EXACT format):
    # Traditional: 73 00 00 00 1e 1b dc da 3e 00 13 00 | 7e 0d 01 00 00 f8 8e 0c 00 0e 01 00 00 00 a0 00 f7 11 02 01 01 | 55 7e
    # Smart:       73 00 00 00 1e 1b dc da 3e 00 15 00 | 7e 10 01 00 00 f8 8e 0c 00 11 01 00 00 00 a0 00 f7 11 02 01 02 | 59 7e

    inner_counter = 0x0D + counter
    inner_counter2 = 0x0E + counter

    packet = bytearray(
        [
            # Header (12 bytes total)
            0x73,
            0x00,
            0x00,
            0x00,
            0x1E,  # Packet type and length
            endpoint[0],
            endpoint[1],
            endpoint[2],
            endpoint[3],  # User/home endpoint
            0x00,
            counter,
            0x00,  # Sequence
            # Data wrapped in 0x7e markers (21 bytes)
            0x7E,  # Start marker
            inner_counter,
            0x01,
            0x00,
            0x00,  # Inner header
            0xF8,
            0x8E,
            0x0C,  # Command type
            0x00,
            inner_counter2,
            0x01,
            0x00,
            0x00,
            0x00,  # Sub-header
            0xA0,
            0x00,  # Device ID?
            0xF7,
            0x11,
            0x02,
            0x01,  # Unknown
            mode_byte,  # MODE: 0x01=Traditional, 0x02=Smart
            0x00,  # Checksum placeholder
            0x7E,  # End marker
        ]
    )

    # Calculate checksum: sum of bytes from position 18 to 33 (excluding checksum itself)
    # This is the inner command data after the 0x7e marker, excluding the marker itself
    checksum_data = packet[18:33]
    checksum = sum(checksum_data) % 256
    packet[33] = checksum

    return bytes(packet)


def forward_data(
    source,
    destination,
    direction,
    device_addr=None,
    switch_endpoint_holder=None,
    counter_holder=None,
):
    """Forward data from source to destination, with optional packet injection"""
    global inject_mode

    try:
        while True:
            data = source.recv(4096)
            if not data:
                break

            # Track packet counters (byte at position 10 for 0x73 packets)
            if counter_holder is not None and len(data) >= 12 and data[0] == 0x73:
                counter = data[10]
                if direction == "CLOUD->DEV":
                    counter_holder["cloud_to_dev"] = counter
                    # Initialize if first time seeing cloud->dev traffic
                    if "initialized" not in counter_holder:
                        counter_holder["initialized"] = True
                        log(
                            f"[COUNTER] Initialized Cloud->Dev counter at 0x{counter:02x}"
                        )
                elif direction == "DEV->CLOUD":
                    counter_holder["dev_to_cloud"] = counter
                    # If we haven't seen cloud traffic yet, initialize cloud counter from current state
                    if (
                        counter_holder.get("cloud_to_dev") is None
                        and counter_holder.get("initialized") is None
                    ):
                        # Start cloud counter at a reasonable value (current + 1)
                        counter_holder["cloud_to_dev"] = (counter + 1) % 256
                        counter_holder["initialized"] = True
                        log(
                            f"[COUNTER] Initialized from Dev->Cloud, starting at 0x{counter_holder['cloud_to_dev']:02x}"
                        )

            # Check for switch endpoint in 0x73/0x83 packets
            if switch_endpoint_holder is not None and len(data) >= 35:
                if data[0] in [0x73, 0x83]:  # Configuration/status packets
                    packet_endpoint = data[
                        5:9
                    ]  # User/home endpoint (e.g., 1b dc da 3e)

                    # Look for mode configuration packets (fa 8e 14 pattern) or mode status (a0 81 pattern)
                    # This indicates a switch with smart bulb mode capability
                    for i in range(len(data) - 3):
                        if data[i : i + 3] == bytes([0xFA, 0x8E, 0x14]) or data[
                            i : i + 2
                        ] == bytes([0xA0, 0x81]):
                            # Found mode packet! Extract device IDs
                            # Device IDs are at positions 24-25 and 26-27 (little-endian)
                            if i >= 8 and len(data) >= i + 20:
                                # Look for device ID bytes near the mode pattern
                                # Pattern: a0 00 4c 00 ... a0 81 [MODE]
                                # The device IDs are encoded as little-endian shorts before the mode bytes
                                device_id_offset = (
                                    i - 8
                                )  # Approximate offset to device IDs
                                if (
                                    device_id_offset >= 0
                                    and device_id_offset + 4 <= len(data)
                                ):
                                    # Try to extract device ID (looking for 0xa0 0x00 = 160)
                                    for j in range(
                                        max(0, i - 15), min(i, len(data) - 1)
                                    ):
                                        if data[j] == 0xA0 and data[j + 1] == 0x00:
                                            device_id = int.from_bytes(
                                                data[j : j + 2], "little"
                                            )
                                            if device_id == 160:
                                                if (
                                                    switch_endpoint_holder.get(
                                                        "device_id"
                                                    )
                                                    is None
                                                ):
                                                    switch_endpoint_holder[
                                                        "endpoint"
                                                    ] = packet_endpoint
                                                    switch_endpoint_holder[
                                                        "device_id"
                                                    ] = device_id
                                                    switch_endpoint_holder[
                                                        "device_addr"
                                                    ] = device_addr
                                                    log(
                                                        f"🎯 FOUND TARGET SWITCH! Device ID: {device_id} (Hallway 4way Switch)"
                                                    )
                                                    log(
                                                        f"   Home/User Endpoint: {' '.join(f'{b:02x}' for b in packet_endpoint)}"
                                                    )

                                                # Also log the mode if we see a0 81 pattern
                                                if data[i : i + 2] == bytes(
                                                    [0xA0, 0x81]
                                                ) and i + 2 < len(data):
                                                    mode_byte = data[i + 2]
                                                    mode_name = (
                                                        "SMART (Dimmable)"
                                                        if mode_byte == 0xB0
                                                        else (
                                                            "TRADITIONAL"
                                                            if mode_byte == 0x50
                                                            else f"UNKNOWN(0x{mode_byte:02x})"
                                                        )
                                                    )
                                                    log(
                                                        f"[MODE STATUS] Device 160: {mode_name}"
                                                    )
                                            break
                            break

            # Parse and log packet with structure
            parsed = parse_cync_packet(data, direction)
            if parsed:
                # Extract device 160 status if present
                if "device_statuses" in parsed:
                    for status in parsed["device_statuses"]:
                        if status["device_id"] == 160:
                            update_device_160_status(status)

                log(format_packet_log(parsed, verbose=True))
            else:
                # Fallback for unparseable packets
                log(f"{direction}: {' '.join(f'{b:02x}' for b in data[:100])}")

            # Check for mode information in device responses
            if direction == "DEV->CLOUD" and len(data) > 0 and data[0] == 0x73:
                parse_mode_from_response(data)

            # Forward the actual packet
            destination.sendall(data)

    except Exception as e:
        log(f"Forward error ({direction}): {e}")


def parse_mode_from_response(packet_bytes):
    """Parse mode information from device's 0x73 response (fa 8e 14 command)"""
    try:
        # Look for fa 8e 14 pattern (mode configuration response)
        packet_hex = " ".join(f"{b:02x}" for b in packet_bytes)
        if "fa 8e 14" in packet_hex:
            # Find device 160 (a0 00) pattern followed by mode info
            for i in range(len(packet_bytes) - 5):
                # Look for pattern: XX XX XX 11 02 a0 81 [MODE]
                if (
                    packet_bytes[i + 2] == 0x11
                    and packet_bytes[i + 3] == 0x02
                    and packet_bytes[i + 4] == 0xA0
                    and packet_bytes[i + 5] == 0x81
                ):
                    mode_byte = packet_bytes[i + 6]
                    if mode_byte == 0x50:
                        log(f"[MODE DETECTED] Device 160: TRADITIONAL (0x50)")
                        return "traditional"
                    elif mode_byte == 0xB0:
                        log(f"[MODE DETECTED] Device 160: SMART/DIMMABLE (0xb0)")
                        return "smart"
                    else:
                        log(
                            f"[MODE DETECTED] Device 160: UNKNOWN mode byte 0x{mode_byte:02x}"
                        )
                        return f"unknown_0x{mode_byte:02x}"
    except Exception as e:
        log(f"[MODE PARSE] Error: {e}")
    return None


def send_mode_query(cloud_ssl, counter_holder):
    """Send a mode query packet through the cloud SSL connection"""
    with counter_lock:
        if counter_holder.get("cloud_to_dev") is None:
            counter_holder["cloud_to_dev"] = 0x10

        counter = counter_holder["cloud_to_dev"]
        counter_holder["cloud_to_dev"] = (counter + 1) % 256

    endpoint = bytes([0x1B, 0xDC, 0xDA, 0x3E])

    inner_counter = 0x0D + counter
    inner_counter2 = 0x0E + counter

    packet = bytearray(
        [
            0x73,
            0x00,
            0x00,
            0x00,
            0x1E,
            endpoint[0],
            endpoint[1],
            endpoint[2],
            endpoint[3],
            0x00,
            counter,
            0x00,
            0x7E,
            inner_counter,
            0x01,
            0x00,
            0x00,
            0xF8,
            0x8E,
            0x0C,
            0x00,
            inner_counter2,
            0x01,
            0x00,
            0x00,
            0x00,
            0xA0,
            0x00,  # Device ID 160
            0xF7,
            0x11,
            0x02,
            0x01,
            0x01,  # Traditional mode byte
            0x00,  # Checksum placeholder
            0x7E,
        ]
    )

    checksum_data = packet[18:33]
    checksum = sum(checksum_data) % 256
    packet[33] = checksum

    cloud_ssl.sendall(bytes(packet))


def check_injection_periodically(
    device_ssl, cloud_ssl, counter_holder, device_endpoint
):
    """Periodically check for injection command and send packet directly"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    inject_file = os.path.join(script_dir, "inject_command.txt")

    # Only process injections on the connection for device 64 57 e7 f2 (the one that talks to device 160)
    # This is the endpoint we've seen device 160 communicate through
    target_endpoint = bytes([0x64, 0x57, 0xE7, 0xF2])
    is_target_connection = device_endpoint == target_endpoint

    if is_target_connection:
        log(
            f"[INJECT] This connection (EP:{' '.join(f'{b:02x}' for b in device_endpoint)}) handles device 160 - injection enabled"
        )
    else:
        log(
            f"[INJECT] This connection (EP:{' '.join(f'{b:02x}' for b in device_endpoint)}) is not for device 160 - injection disabled"
        )

    # Wait for connection to stabilize and counters to be detected
    time.sleep(3)

    query_counter = 0
    status_log_counter = 0

    while True:
        try:
            time.sleep(1)  # Check every second

            # Send mode query every 5 seconds
            query_counter += 1
            if query_counter >= 5:
                query_counter = 0
                try:
                    send_mode_query(cloud_ssl, counter_holder)
                except Exception as e:
                    log(f"[MODE QUERY] Error: {e}")

            # Only process injections on the target connection
            if not is_target_connection:
                continue

            # Check for raw bytes injection file
            raw_inject_file = os.path.join(script_dir, "inject_raw_bytes.txt")
            if os.path.exists(raw_inject_file):
                try:
                    with open(raw_inject_file, "r") as f:
                        raw_hex = f.read().strip()
                    os.remove(raw_inject_file)

                    # Parse hex bytes (space-separated)
                    hex_bytes = raw_hex.replace(" ", "").replace("\n", "")
                    packet = bytes.fromhex(hex_bytes)

                    log(f"*** INJECTING RAW PACKET ({len(packet)} bytes) ***")
                    log(f"    Hex: {' '.join(f'{b:02x}' for b in packet)}")
                    device_ssl.sendall(packet)
                    log("*** RAW INJECTION COMPLETE ***")
                except Exception as e:
                    log(f"[INJECT] Error with raw bytes: {e}")

            # Check for mode injection file
            if os.path.exists(inject_file):
                try:
                    with open(inject_file, "r") as f:
                        mode = f.read().strip().lower()
                    os.remove(inject_file)

                    if mode in ["smart", "traditional"]:
                        # Get counter with lock
                        with counter_lock:
                            # Initialize counter if not set (use a reasonable starting value)
                            if counter_holder.get("cloud_to_dev") is None:
                                # Start from 0x10 (arbitrary but safe)
                                counter_holder["cloud_to_dev"] = 0x10
                                log("[INJECT] Initialized counter at 0x10")

                            counter = counter_holder["cloud_to_dev"]
                            counter_holder["cloud_to_dev"] = (counter + 1) % 256

                        endpoint = bytes([0x1B, 0xDC, 0xDA, 0x3E])

                        log(
                            f"*** INJECTING {mode.upper()} MODE PACKET TO DEVICE 160 ***"
                        )
                        log(f"    Using counter: 0x{counter:02x}")
                        mode_byte = MODE_SMART if mode == "smart" else MODE_TRADITIONAL
                        packet = craft_mode_packet(endpoint, counter, mode_byte)
                        log(f"INJECT: {' '.join(f'{b:02x}' for b in packet)}")
                        device_ssl.sendall(packet)
                        log("*** INJECTION COMPLETE ***")
                        log("Watching for device response...")
                except Exception as e:
                    log(f"[INJECT] Error reading command: {e}")
        except Exception as e:
            log(f"[INJECT] Thread error: {e}")
            break


def handle_device_connection(device_socket, device_addr):
    """Handle a single device connection"""
    log(f"Device connected from {device_addr}")

    try:
        # Wrap device socket with SSL (server side)
        device_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        device_context.load_cert_chain("certs/server.pem")
        device_context.check_hostname = False
        device_context.verify_mode = ssl.CERT_NONE
        device_context.set_ciphers("AES256-SHA256:AES256-CCM:@SECLEVEL=0")

        device_ssl = device_context.wrap_socket(device_socket, server_side=True)
        log(f"SSL handshake complete with device")

        # Connect to real cloud server
        cloud_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cloud_socket.connect((CLOUD_SERVER, CLOUD_PORT))

        # Wrap cloud socket with SSL (client side)
        cloud_context = ssl.create_default_context()
        cloud_context.check_hostname = False
        cloud_context.verify_mode = ssl.CERT_NONE

        cloud_ssl = cloud_context.wrap_socket(
            cloud_socket, server_hostname=CLOUD_SERVER
        )
        log(f"Connected to cloud server {CLOUD_SERVER}:{CLOUD_PORT}")

        # Get device endpoint from first packet
        first_packet = device_ssl.recv(1024)
        endpoint = None
        if len(first_packet) >= 31 and first_packet[0] == 0x23:
            # This is a 0x23 handshake packet with endpoint
            endpoint = first_packet[6:10]  # This is the device's personal endpoint
            log(f"Device endpoint: {' '.join(f'{b:02x}' for b in endpoint)}")

        # Forward first packet
        cloud_ssl.sendall(first_packet)

        # Create a shared dict to track switch endpoint discovery
        switch_endpoint_holder = {}

        # User/home endpoint is always the same (user ID: 467458622 = 0x1bdcda3e)
        user_endpoint = bytes([0x1B, 0xDC, 0xDA, 0x3E])

        # Use global counter holder (shared across all connections)
        counter_holder = global_counter_holder

        # Mode queries disabled - they're being sent on wrong connection
        # TODO: Implement queries through the proper forward_data flow instead

        # Start injection checker thread (passes both SSL connections)
        injection_thread = threading.Thread(
            target=check_injection_periodically,
            args=(
                device_ssl,  # Send TO device (CLOUD->DEV direction)
                cloud_ssl,  # For queries that go to cloud
                counter_holder,
                endpoint if endpoint else b"\x00\x00\x00\x00",
            ),
            daemon=True,
        )
        injection_thread.start()

        # Start bidirectional forwarding
        device_to_cloud = threading.Thread(
            target=forward_data,
            args=(
                device_ssl,
                cloud_ssl,
                "DEV->CLOUD",
                device_addr,
                switch_endpoint_holder,
                counter_holder,
            ),
            daemon=True,
        )
        cloud_to_device = threading.Thread(
            target=forward_data,
            args=(
                cloud_ssl,
                device_ssl,
                "CLOUD->DEV",
                device_addr,
                switch_endpoint_holder,
                counter_holder,
            ),
            daemon=True,
        )

        device_to_cloud.start()
        cloud_to_device.start()

        # Wait for threads to finish
        device_to_cloud.join()
        cloud_to_device.join()

    except Exception as e:
        log(f"Connection error: {e}")
    finally:
        try:
            device_socket.close()
        except OSError as e:
            print(f"WARNING: Failed to close device socket: {e}", file=sys.stderr)
        except Exception as e:
            print(f"ERROR: Unexpected error closing device socket: {e}", file=sys.stderr)
        try:
            cloud_socket.close()
        except OSError as e:
            print(f"WARNING: Failed to close cloud socket: {e}", file=sys.stderr)
        except Exception as e:
            print(f"ERROR: Unexpected error closing cloud socket: {e}", file=sys.stderr)
        log(f"Connection closed for {device_addr}")


def command_listener():
    """Listen for commands on stdin to inject packets"""
    global inject_mode

    log("Command listener started. Type 'smart' or 'traditional' to inject packet")

    while True:
        try:
            cmd = input().strip().lower()
            if cmd in ["smart", "traditional"]:
                with inject_lock:
                    inject_mode = cmd
                log(f"*** INJECTION QUEUED: {cmd.upper()} mode ***")
            elif cmd == "help":
                print("Commands:")
                print("  smart       - Inject smart mode packet")
                print("  traditional - Inject traditional mode packet")
                print("  help        - Show this help")
            elif cmd:
                log(f"Unknown command: {cmd}")
        except EOFError:
            break
        except Exception as e:
            log(f"Command error: {e}")


def main():
    """Main MITM proxy server"""
    log("=" * 60)
    log("Cync MITM Proxy with Packet Injection")
    log("=" * 60)
    log("")

    # Create server socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("0.0.0.0", 23779))
    server_socket.listen(5)

    log(f"Listening on port 23779...")
    log(f"Forwarding to {CLOUD_SERVER}:{CLOUD_PORT}")
    log("")
    log("Type 'smart' or 'traditional' and press Enter to inject mode packet")
    log("=" * 60)
    log("")

    # Start global status logger thread (one instance for all connections)
    status_thread = threading.Thread(target=status_logger_thread, daemon=True)
    status_thread.start()

    # Start command listener thread
    cmd_thread = threading.Thread(target=command_listener, daemon=True)
    cmd_thread.start()

    try:
        while True:
            device_socket, device_addr = server_socket.accept()

            # Handle each connection in a separate thread
            handler = threading.Thread(
                target=handle_device_connection,
                args=(device_socket, device_addr),
                daemon=True,
            )
            handler.start()

    except KeyboardInterrupt:
        log("\nShutting down...")
    finally:
        server_socket.close()


if __name__ == "__main__":
    main()
