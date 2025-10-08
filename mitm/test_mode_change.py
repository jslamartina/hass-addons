#!/usr/bin/env python3
"""
Test script to send smart bulb mode change command to Cync switch
"""
import socket
import sys
import time
import os
from checksum import calculate_checksum_between_markers

# Device configuration
DEVICE_IP = os.getenv("DEVICE_IP", "172.64.66.1")  # Override via env or CLI arg
DEVICE_PORT = 23779
DEVICE_ENDPOINT = bytes([0x1b, 0xdc, 0xda, 0x3e])

# Mode values
MODE_TRADITIONAL = 0x50  # Relay enabled
MODE_SMART = 0xb0        # Relay disabled

def calculate_checksum(data):
    """Calculate checksum based on inner 0x7E-bounded structure"""
    return calculate_checksum_between_markers(bytes(data))

def craft_mode_packet(endpoint, counter, mode_byte):
    """
    Craft a 0x73 mode change packet
    
    Args:
        endpoint: 4-byte endpoint (device ID)
        counter: 1-byte counter value  
        mode_byte: 0x50 for Traditional, 0xb0 for Smart
    
    Returns:
        bytes: Complete packet ready to send
    """
    # Build packet structure
    packet = bytearray([
        # Header (5 bytes)
        0x73, 0x00, 0x00, 0x00, 0x26,
        
        # Endpoint (7 bytes)
        endpoint[0], endpoint[1], endpoint[2], endpoint[3],
        0x01, counter, 0x00,
        
        # Start marker + command header (5 bytes)
        0x7e, counter + 0x23, 0x01, 0x00, 0x00,
        
        # Subcommand (3 bytes)
        0xfa, 0x8e, 0x14,
        
        # Unknown (2 bytes) - seems to vary
        0x00, 0x73 + counter,  # This byte changes with counter
        
        # Unknown (2 bytes)
        0x04, 0x00,
        
        # Device/Group IDs (4 bytes)
        0xa0, 0x00, 0x4c, 0x00,
        
        # Unknown (3 bytes)
        0xea, 0x11, 0x02,
        
        # Mode control bytes (3 bytes)
        0xa0, 0x81, mode_byte,
        
        # Padding (6 bytes)
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        
        # Unknown (1 byte)
        0x14,
        
        # Checksum (placeholder)
        0x00,
        
        # End marker
        0x7e
    ])
    
    # Calculate and insert checksum
    checksum = calculate_checksum(packet)
    packet[41] = checksum
    
    return bytes(packet)

def send_mode_command(device_ip, device_port, endpoint, counter, mode_byte):
    """Send mode change command to device"""
    packet = craft_mode_packet(endpoint, counter, mode_byte)
    
    mode_name = "TRADITIONAL" if mode_byte == MODE_TRADITIONAL else "SMART"
    
    print("=" * 60)
    print(f"SENDING MODE CHANGE COMMAND: {mode_name}")
    print("=" * 60)
    print()
    print(f"Target: {device_ip}:{device_port}")
    print(f"Endpoint: {' '.join(f'{b:02x}' for b in endpoint)}")
    print(f"Counter: 0x{counter:02x}")
    print(f"Mode byte: 0x{mode_byte:02x}")
    print()
    print("Packet:")
    print(" ".join(f"{b:02x}" for b in packet))
    print()
    
    try:
        # Connect to device
        print(f"Connecting to {device_ip}:{device_port}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((device_ip, device_port))
        print("✓ Connected!")
        
        # Send packet
        print(f"Sending {len(packet)} bytes...")
        sock.sendall(packet)
        print("✓ Packet sent!")
        
        # Wait for response
        print("Waiting for response...")
        sock.settimeout(2)
        response = sock.recv(1024)
        
        if response:
            print(f"✓ Received response ({len(response)} bytes):")
            print(" ".join(f"{b:02x}" for b in response))
            
            # Check for 0x7b ACK
            if len(response) >= 5 and response[0] == 0x7b:
                print("✓ Got 0x7b ACK packet!")
            else:
                print(f"? Unexpected response type: 0x{response[0]:02x}")
        else:
            print("✗ No response received")
        
        sock.close()
        
    except socket.timeout:
        print("✗ Connection timed out")
        return False
    except ConnectionRefusedError:
        print("✗ Connection refused - is the device online?")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print()
    print("Cync Smart Bulb Mode Control Test")
    print()
    
    if len(sys.argv) < 2:
        print("Usage: python3 test_mode_change.py <mode>")
        print("  mode: 'traditional' or 'smart'")
        print()
        print("Example:")
        print("  python3 test_mode_change.py smart")
        sys.exit(1)
    
    mode_arg = sys.argv[1].lower()
    # Optional CLI override for device IP
    if len(sys.argv) >= 3:
        DEVICE_IP = sys.argv[2]
    
    if mode_arg == "traditional":
        mode_byte = MODE_TRADITIONAL
    elif mode_arg == "smart":
        mode_byte = MODE_SMART
    else:
        print(f"Invalid mode: {mode_arg}")
        print("Must be 'traditional' or 'smart'")
        sys.exit(1)
    
    # Use counter value from recent captures
    # In practice, this should be incremented based on device state
    counter = 0x00  # Start with 0, increment for each command
    
    result = send_mode_command(
        DEVICE_IP,
        DEVICE_PORT,
        DEVICE_ENDPOINT,
        counter,
        mode_byte
    )
    
    if result:
        print()
        print("=" * 60)
        print("Command sent successfully!")
        print("Check the switch to see if the mode changed.")
        print("=" * 60)
    else:
        print()
        print("=" * 60)
        print("Command failed!")
        print("=" * 60)
        sys.exit(1)

