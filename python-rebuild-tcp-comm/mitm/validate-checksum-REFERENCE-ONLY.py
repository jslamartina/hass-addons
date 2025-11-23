#!/usr/bin/env python3
"""
Validate Cync checksum algorithm against captured packets.

This script tests the checksum algorithm from the legacy codebase
against real packet fixtures captured during Phase 0.5.

Uses legacy code as reference - Phase 1a will copy the validated algorithm.

⚠️ CRITICAL ARCHITECTURE EXCEPTION: This validation script is the ONLY exception to
the "No Legacy Imports" principle (Phase 1 spec lines 21-27). This script imports legacy
code for verification purposes ONLY to validate the algorithm is correct.

FOR PHASE 1a IMPLEMENTERS: DO NOT import legacy code in production implementation!
Phase 1a MUST copy the validated algorithm into new codebase (see Phase 1a Step 2).
Importing legacy code in Phase 1a violates architecture principles and will be rejected.
"""

import sys
from pathlib import Path

# Add legacy codebase to path for validation purposes ONLY
legacy_path = Path(__file__).parent.parent.parent / "cync-controller" / "src"
sys.path.insert(0, str(legacy_path))

# Import from legacy codebase (reference only - for validation)
from cync_controller.packet_checksum import calculate_checksum_between_markers  # noqa: E402

# Legacy test fixtures from cync-controller (known-good checksums)
LEGACY_FIXTURES = {
    "SIMPLE_PACKET": bytes(
        [
            0x00,
            0x00,
            0x00,  # Prefix
            0x7E,  # Start marker (index 3)
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,  # Offset bytes (6 bytes)
            0x01,
            0x02,
            0x03,  # Data to sum (1 + 2 + 3 = 6)
            0x06,  # Checksum byte
            0x7E,  # End marker
        ]
    ),
    "MODULO_256_PACKET": bytes(
        [
            0x7E,  # Start marker (index 0)
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,  # Offset (6 bytes)
            0xFF,
            0xFF,
            0xFF,  # Data: 255 + 255 + 255 = 765
            0xFD,  # Checksum: 765 % 256 = 253
            0x7E,  # End marker
        ]
    ),
}

# Real packet fixtures from Phase 0.5 captures (populated from MITM proxy capture)
REAL_FIXTURES = {
    "STATUS_BROADCAST_0x83_FRAMED_1": bytes.fromhex(
        "83 00 00 00 25 45 88 0f 3a 00 09 00 7e 1f 00 00 00 fa db 13 00 72 25 11 50 00 50 00 db 11 02 01 01 0a 0a ff ff ff 00 00 37 7e"
    ),
    "STATUS_BROADCAST_0x83_FRAMED_2": bytes.fromhex(
        "83 00 00 00 26 60 b1 7c 4a 00 0c 00 7e 1f 00 00 00 fa db 14 00 22 22 33 1a 00 ff ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 43 7e"
    ),
    "STATUS_BROADCAST_0x83_FRAMED_3": bytes.fromhex(
        "83 00 00 00 26 3d 54 86 1c 00 0b 00 7e 1f 00 00 00 fa db 14 00 f0 2b 00 1a 00 ff ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 e7 7e"
    ),
    # Additional diverse STATUS_BROADCAST packets for comprehensive validation
    "STATUS_BROADCAST_0x83_FRAMED_4": bytes.fromhex(
        "83 00 00 00 26 3d 54 6d e6 00 09 00 7e 1f 00 00 00 fa db 14 00 95 2b 00 1a 00 ff ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 8c 7e"
    ),
    "STATUS_BROADCAST_0x83_FRAMED_5": bytes.fromhex(
        "83 00 00 00 26 32 5d 3e ad 00 0d 00 7e 1f 00 00 00 fa db 14 00 51 2c 00 1a 00 ff ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 49 7e"
    ),
    "STATUS_BROADCAST_0x83_FRAMED_6": bytes.fromhex(
        "83 00 00 00 26 60 b1 74 37 00 0d 00 7e 1f 00 00 00 fa db 14 00 4a 2e 00 1a 00 ff ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 44 7e"
    ),
    "STATUS_BROADCAST_0x83_FRAMED_7": bytes.fromhex(
        "83 00 00 00 26 60 b1 7a 37 00 0a 00 7e 1f 00 00 00 fa db 14 00 15 2e 00 1a 00 ff ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 0f 7e"
    ),
    "STATUS_BROADCAST_0x83_FRAMED_8": bytes.fromhex(
        "83 00 00 00 26 60 b1 7c b4 00 0d 00 7e 1f 00 00 00 fa db 14 00 01 2e 00 1a 00 ff ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 fb 7e"
    ),
    "STATUS_BROADCAST_0x83_FRAMED_9": bytes.fromhex(
        "83 00 00 00 26 60 b1 8e 42 00 10 00 7e 24 00 00 00 fa db 14 00 f6 2d 00 1a 00 ff ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 ef 7e"
    ),
    "STATUS_BROADCAST_0x83_FRAMED_10": bytes.fromhex(
        "83 00 00 00 26 38 e8 ee 97 00 0d 00 7e 1f 00 00 00 fa db 14 00 05 2c 00 1a 00 ff ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 fd 7e"
    ),
    "STATUS_BROADCAST_0x83_FRAMED_11": bytes.fromhex(
        "83 00 00 00 26 38 e8 dd 4d 00 14 00 7e 1f 00 00 00 fa db 14 00 aa 2b 00 1a 00 ff ff ea 11 02 1a a1 01 0b 01 00 00 00 00 00 a1 7e"
    ),
}


def extract_checksum_from_packet(packet: bytes) -> int:
    """Extract the checksum byte from packet (second-to-last byte before 0x7E)."""
    end_marker_pos = packet.rfind(0x7E)
    if end_marker_pos < 2:
        error_msg = "No trailing 0x7E marker found"
        raise ValueError(error_msg)
    return packet[end_marker_pos - 1]


def validate_fixtures(fixtures: dict, fixture_type: str) -> list:
    """Validate checksum algorithm matches legacy code against all fixtures."""
    results = []
    print(f"\n{'=' * 60}")
    print(f"Validating {fixture_type} Fixtures")
    print(f"{'=' * 60}\n")

    for packet_name, packet_bytes in fixtures.items():
        expected = extract_checksum_from_packet(packet_bytes)
        calculated = calculate_checksum_between_markers(packet_bytes)
        match = expected == calculated

        results.append(
            {
                "packet": packet_name,
                "expected": expected,
                "calculated": calculated,
                "match": match,
            }
        )

        if not match:
            print(f"❌ MISMATCH: {packet_name}")
            print(f"   Expected: 0x{expected:02x}, Calculated: 0x{calculated:02x}")
            print(f"   Packet: {packet_bytes.hex(' ')}\n")
        else:
            print(f"✅ MATCH: {packet_name} (checksum: 0x{expected:02x})")

    return results


def main() -> None:
    """Main validation entry point."""
    print("\nCync Protocol Checksum Validation")
    print("=" * 60)
    print("This script validates the legacy checksum algorithm against test fixtures.")
    print("⚠️  FOR VALIDATION ONLY - Phase 1a must copy algorithm, not import legacy code")

    all_results = []

    # Validate against legacy test fixtures
    legacy_results = validate_fixtures(LEGACY_FIXTURES, "Legacy Test")
    all_results.extend(legacy_results)

    # Validate against real captured packets (if any)
    if REAL_FIXTURES:
        real_results = validate_fixtures(REAL_FIXTURES, "Real Captured")
        all_results.extend(real_results)
    else:
        print("\n" + "=" * 60)
        print("Note: No real packet fixtures loaded yet")
        print("Run MITM proxy to capture real packets, then add to REAL_FIXTURES")
        print("=" * 60)

    # Summary
    print("\n" + "=" * 60)
    print("Validation Summary")
    print("=" * 60)
    mismatches = [r for r in all_results if not r["match"]]

    if mismatches:
        print(f"\n❌ VALIDATION FAILED: {len(mismatches)} checksum mismatches found!")
        print("\nMismatched packets:")
        for r in mismatches:
            print(f"  - {r['packet']}: expected 0x{r['expected']:02x}, got 0x{r['calculated']:02x}")
        sys.exit(1)
    else:
        print(f"\n✅ All {len(all_results)} packets validated successfully")
        print("\nChecksum algorithm confirmed correct:")
        print("  1. Locate first and last 0x7E markers")
        print("  2. Sum bytes from (start + 6) to (end - 1)")
        print("  3. Return sum % 256")
        print("\n📋 Phase 1a can proceed with copying this algorithm")


if __name__ == "__main__":
    main()
