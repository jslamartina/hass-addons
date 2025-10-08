#!/usr/bin/env python3
"""
Send mode change packet through active MITM connection
We'll monitor the MITM capture file and inject our packet
"""
import socket
import ssl
import time
import sys

# Mode values
MODE_TRADITIONAL = 0x50  # Relay enabled
MODE_SMART = 0xB0  # Relay disabled


def calculate_checksum(data):
    """Calculate checksum: sum(data[18:41]) % 256"""
    return sum(data[18:41]) % 256


def craft_mode_packet(endpoint, counter, mode_byte):
    """Craft a 0x73 mode change packet"""
    packet = bytearray(
        [
            # Header (5 bytes)
            0x73,
            0x00,
            0x00,
            0x00,
            0x26,
            # Endpoint (7 bytes)
            endpoint[0],
            endpoint[1],
            endpoint[2],
            endpoint[3],
            0x01,
            counter,
            0x00,
            # Start marker + command header (5 bytes)
            0x7E,
            counter + 0x23,
            0x01,
            0x00,
            0x00,
            # Subcommand (3 bytes)
            0xFA,
            0x8E,
            0x14,
            # Unknown (2 bytes)
            0x00,
            0x73 + counter,
            # Unknown (2 bytes)
            0x04,
            0x00,
            # Device/Group IDs (4 bytes)
            0xA0,
            0x00,
            0x4C,
            0x00,
            # Unknown (3 bytes)
            0xEA,
            0x11,
            0x02,
            # Mode control bytes (3 bytes)
            0xA0,
            0x81,
            mode_byte,
            # Padding (6 bytes)
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            # Unknown (1 byte)
            0x14,
            # Checksum (placeholder)
            0x00,
            # End marker
            0x7E,
        ]
    )

    # Calculate and insert checksum
    checksum = calculate_checksum(packet)
    packet[41] = checksum

    return bytes(packet)


def send_packet_to_device():
    """
    Act as a simple SSL server that accepts device connections
    and sends the mode change packet
    """
    # Load certificates
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain("certs/server.pem")
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    # Set ciphers to match what socat uses (AES256-SHA256 for devices)
    context.set_ciphers("AES256-SHA256:AES256-CCM:@SECLEVEL=0")

    # Create socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("0.0.0.0", 23779))
    server_socket.listen(5)

    print("Listening on port 23779...")
    print("Waiting for device connection...")

    client_socket, addr = server_socket.accept()
    print(f"Connection from {addr}")

    # Wrap with SSL
    ssl_socket = context.wrap_socket(client_socket, server_side=True)

    # Receive handshake
    data = ssl_socket.recv(1024)
    print(f"Received handshake: {' '.join(f'{b:02x}' for b in data)}")

    # Send ACK
    ack = bytes([0x28, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00])
    ssl_socket.sendall(ack)
    print("Sent ACK")

    # Wait a bit
    time.sleep(1)

    # Craft and send mode packet
    endpoint = bytes([0x1B, 0xDC, 0xDA, 0x3E])
    mode_byte = (
        MODE_SMART if len(sys.argv) > 1 and sys.argv[1] == "smart" else MODE_TRADITIONAL
    )
    packet = craft_mode_packet(endpoint, 0x00, mode_byte)

    print(f"Sending mode change packet: {' '.join(f'{b:02x}' for b in packet)}")
    ssl_socket.sendall(packet)

    # Wait for response
    response = ssl_socket.recv(1024)
    print(f"Response: {' '.join(f'{b:02x}' for b in response)}")

    ssl_socket.close()
    server_socket.close()


if __name__ == "__main__":
    print("Starting test server on port 23779...")
    print()
    send_packet_to_device()
