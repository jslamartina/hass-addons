#!/usr/bin/env python3
"""
Analyze checksum algorithm for 0x73 packets
"""

# Smart → Traditional packet (checksum = 0x87)
packet1 = bytes([
    0x73, 0x00, 0x00, 0x00, 0x26,  # Header
    0x1b, 0xdc, 0xda, 0x3e, 0x01, 0x00, 0x00,  # Endpoint
    0x7e, 0x23, 0x01, 0x00, 0x00,  # Start marker + command header
    0xfa, 0x8e, 0x14,  # Subcommand
    0x00, 0x73,  # Unknown
    0x04, 0x00,  # Unknown
    0xa0, 0x00,  # Device ID 1
    0x4c, 0x00,  # Device ID 2
    0xea, 0x11, 0x02,  # Unknown
    0xa0, 0x81, 0x50,  # Mode bytes (0x50 = Traditional)
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # Padding
    0x14,  # Unknown
    0x87,  # Checksum
    0x7e   # End marker
])

# Traditional → Smart packet (checksum = 0xf2)
packet2 = bytes([
    0x73, 0x00, 0x00, 0x00, 0x26,  # Header
    0x1b, 0xdc, 0xda, 0x3e, 0x01, 0x3a, 0x00,  # Endpoint (different counter)
    0x7e, 0x36, 0x01, 0x00, 0x00,  # Start marker + command header
    0xfa, 0x8e, 0x14,  # Subcommand
    0x00, 0x7e,  # Unknown (different!)
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
print("CHECKSUM ANALYSIS FOR 0x73 PACKETS")
print("=" * 60)
print()

print("Packet 1 (Smart → Traditional, checksum = 0x87):")
print(" ".join(f"{b:02x}" for b in packet1))
print()

print("Packet 2 (Traditional → Smart, checksum = 0xf2):")
print(" ".join(f"{b:02x}" for b in packet2))
print()

print("=" * 60)
print("BYTE DIFFERENCES:")
print("=" * 60)
for i, (b1, b2) in enumerate(zip(packet1, packet2)):
    if b1 != b2:
        print(f"Byte {i:2d}: 0x{b1:02x} vs 0x{b2:02x}  (diff: {b2-b1:+4d} / 0x{(b2-b1)&0xff:02x})")
print()

# Test common checksum algorithms
print("=" * 60)
print("TESTING CHECKSUM ALGORITHMS:")
print("=" * 60)
print()

# The checksum is at byte 41, end marker at 42
# We need to figure out what bytes are included in the checksum

def test_checksum(packet, name, start_idx, end_idx):
    """Test various checksum algorithms on a range of bytes"""
    data = packet[start_idx:end_idx]
    checksum_byte = packet[41]
    
    # Simple sum mod 256
    sum_mod256 = sum(data) & 0xff
    
    # XOR all bytes
    xor_result = 0
    for b in data:
        xor_result ^= b
    
    # Two's complement
    twos_comp = (~sum(data) + 1) & 0xff
    
    # One's complement
    ones_comp = (~sum(data)) & 0xff
    
    print(f"{name} (bytes {start_idx}-{end_idx}):")
    print(f"  Expected:        0x{checksum_byte:02x}")
    print(f"  Sum mod 256:     0x{sum_mod256:02x} {'✓' if sum_mod256 == checksum_byte else '✗'}")
    print(f"  XOR:             0x{xor_result:02x} {'✓' if xor_result == checksum_byte else '✗'}")
    print(f"  Two's comp:      0x{twos_comp:02x} {'✓' if twos_comp == checksum_byte else '✗'}")
    print(f"  One's comp:      0x{ones_comp:02x} {'✓' if ones_comp == checksum_byte else '✗'}")
    print()

# Test different ranges
print("\nPacket 1 tests:")
test_checksum(packet1, "Full packet (0-40)", 0, 41)
test_checksum(packet1, "After 0x7e marker (12-40)", 12, 41)
test_checksum(packet1, "Data only (13-40)", 13, 41)
test_checksum(packet1, "Data without 0x14 (13-39)", 13, 40)

print("\nPacket 2 tests:")
test_checksum(packet2, "Full packet (0-40)", 0, 41)
test_checksum(packet2, "After 0x7e marker (12-40)", 12, 41)
test_checksum(packet2, "Data only (13-40)", 13, 41)
test_checksum(packet2, "Data without 0x14 (13-39)", 13, 40)

# Manual analysis
print("=" * 60)
print("MANUAL CHECKSUM CALCULATION:")
print("=" * 60)
print()

# Try to find the pattern
print("Looking for patterns...")
print(f"Checksum 1: 0x87 = {0x87:08b} (binary) = {0x87} (decimal)")
print(f"Checksum 2: 0xf2 = {0xf2:08b} (binary) = {0xf2} (decimal)")
print(f"Difference: 0x{(0xf2 - 0x87):02x} = {0xf2 - 0x87} (decimal)")
print()

# The mode byte difference
print(f"Mode byte 1: 0x50 = {0x50} (decimal)")
print(f"Mode byte 2: 0xb0 = {0xb0} (decimal)")
print(f"Difference:  0x{(0xb0 - 0x50):02x} = {0xb0 - 0x50} (decimal)")
print()

# Counter difference
print(f"Counter byte 1: 0x00")
print(f"Counter byte 2: 0x3a = {0x3a} (decimal)")
print()

# Command header difference
print(f"Command header 1: 0x23")
print(f"Command header 2: 0x36")
print(f"Difference:       0x{(0x36 - 0x23):02x} = {0x36 - 0x23} (decimal)")
print()

print("Trying to find correlation...")
print(f"Mode diff (0x60) + Counter (0x3a) + Command diff (0x13) = 0x{(0x60 + 0x3a + 0x13):02x}")
print(f"Checksum diff = 0x{(0xf2 - 0x87):02x}")

