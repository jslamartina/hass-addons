#!/usr/bin/env python3
"""
Verify checksum algorithm found in cync-lan code
"""

# Smart → Traditional packet (checksum = 0x87)
packet1 = bytes([
    0x73, 0x00, 0x00, 0x00, 0x26,  # Header (0-4)
    0x1b, 0xdc, 0xda, 0x3e, 0x01, 0x00, 0x00,  # Endpoint (5-11)
    0x7e, 0x23, 0x01, 0x00, 0x00,  # Start marker + command header (12-16)
    0xfa, 0x8e, 0x14,  # Subcommand (17-19)
    0x00, 0x73,  # Unknown (20-21)
    0x04, 0x00,  # Unknown (22-23)
    0xa0, 0x00,  # Device ID 1 (24-25)
    0x4c, 0x00,  # Device ID 2 (26-27)
    0xea, 0x11, 0x02,  # Unknown (28-30)
    0xa0, 0x81, 0x50,  # Mode bytes (31-33)
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # Padding (34-39)
    0x14,  # Unknown (40)
    0x87,  # Checksum (41)
    0x7e   # End marker (42)
])

# Traditional → Smart packet (checksum = 0xf2)
packet2 = bytes([
    0x73, 0x00, 0x00, 0x00, 0x26,  # Header
    0x1b, 0xdc, 0xda, 0x3e, 0x01, 0x3a, 0x00,  # Endpoint
    0x7e, 0x36, 0x01, 0x00, 0x00,  # Start marker + command header
    0xfa, 0x8e, 0x14,  # Subcommand
    0x00, 0x7e,  # Unknown
    0x04, 0x00,  # Unknown
    0xa0, 0x00,  # Device ID 1
    0x4c, 0x00,  # Device ID 2
    0xea, 0x11, 0x02,  # Unknown
    0xa0, 0x81, 0xb0,  # Mode bytes (0xb0 = Smart)
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # Padding
    0x14,  # Unknown
    0xf2,  # Checksum
    0x7e   # End marker
])

print("=" * 60)
print("VERIFYING CHECKSUM ALGORITHM FROM CYNC-LAN")
print("=" * 60)
print()
print("Algorithm: checksum = sum(inner_struct[6:-2]) % 256")
print("  Where inner_struct starts at the 0x7e marker (byte 12)")
print()

def verify_packet(packet, name):
    # Find the 0x7e marker (should be at byte 12)
    marker_idx = packet.index(0x7e)
    
    # inner_struct starts at the marker
    # Sum from marker+6 (byte 18) to -2 (exclude checksum and end marker)
    inner_start = marker_idx + 6
    inner_end = len(packet) - 2  # Exclude checksum and 0x7e
    
    data_to_sum = packet[inner_start:inner_end]
    calculated = sum(data_to_sum) % 256
    expected = packet[-2]
    
    print(f"{name}:")
    print(f"  0x7e marker at byte {marker_idx}")
    print(f"  Summing bytes {inner_start} to {inner_end-1}")
    print(f"  Data: {' '.join(f'{b:02x}' for b in data_to_sum)}")
    print(f"  Sum: {sum(data_to_sum)} mod 256 = {calculated}")
    print(f"  Expected: 0x{expected:02x}")
    print(f"  Calculated: 0x{calculated:02x}")
    print(f"  Status: {'✓ MATCH!' if calculated == expected else '✗ MISMATCH'}")
    print()
    
    return calculated == expected

result1 = verify_packet(packet1, "Packet 1 (Smart → Traditional)")
result2 = verify_packet(packet2, "Packet 2 (Traditional → Smart)")

print("=" * 60)
if result1 and result2:
    print("SUCCESS! Checksum algorithm verified! ✓")
else:
    print("FAILED - Algorithm doesn't match")
print("=" * 60)

