#!/usr/bin/env python3

"""
⚠️⚠️⚠️ SECURITY WARNING ⚠️⚠️⚠️
This script disables SSL verification for MITM debugging.
- Disables ALL SSL security
- For LOCAL DEBUGGING ONLY
- DO NOT use on untrusted networks
- DO NOT use in production
⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️

Send a mode query to device 160 and parse the response
"""

import socket
import ssl
import time

# Based on captured query: 73 00 00 00 1e 1b dc da 3e 00 13 00 7e 0d 01 00 00 f8 8e 0c 00 0e 01 00 00 00 a0 00 f7 11 02 01 01 55 7e
# The device responds with: 73 00 00 00 26 ... fa 8e 14 ... a0 81 [MODE]

def query_mode():
    # Connect to MITM (which forwards to device)
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)

    # This will connect through our MITM
    print("Connecting to MITM proxy...")
    sock.connect(("172.17.0.2", 23779))

    # Just read whatever comes back from existing traffic
    print("Listening for device status packets...")
    for i in range(30):
        try:
            data = sock.recv(4096)
            if data:
                hex_str = ' '.join(f'{b:02x}' for b in data)
                print(f"Received: {hex_str}")

                # Look for mode pattern: fa 8e 14 ... a0 81 [MODE]
                if b'\xfa\x8e\x14' in data and b'\xa0\x81' in data:
                    idx = data.index(b'\xa0\x81')
                    if idx + 2 < len(data):
                        mode_byte = data[idx + 2]
                        mode_name = {
                            0x50: "TRADITIONAL",
                            0xb0: "SMART (Dimmable)",
                            0x90: "SMART (Dimmable)",
                        }.get(mode_byte, f"UNKNOWN (0x{mode_byte:02x})")
                        print(f"\n*** MODE DETECTED: {mode_name} ***\n")
        except socket.timeout:
            print("Timeout waiting for data")
            break
        time.sleep(0.5)

    sock.close()

if __name__ == "__main__":
    query_mode()
