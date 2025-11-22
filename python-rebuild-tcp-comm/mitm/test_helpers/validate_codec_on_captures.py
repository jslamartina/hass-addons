#!/usr/bin/env python3
"""Validate Phase 1a codec against existing MITM capture files.

This script parses raw packet hex from capture files and decodes them
using the Phase 1a codec to validate against real traffic.
"""

import re
import sys
from collections import Counter
from pathlib import Path
from typing import TypedDict

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from protocol.cync_protocol import CyncProtocol
from protocol.exceptions import PacketDecodeError

# Constants for validation criteria
MIN_DECODED_PACKETS_REQUIRED = 100
MIN_ARGS_REQUIRED = 2
MAX_ERROR_RATE = 1.0


class ValidationStats(TypedDict):
    """Statistics dictionary structure for validation results."""

    total_packets: int
    decoded_successfully: int
    decode_errors: int
    packet_types: Counter[str]
    error_reasons: Counter[str]
    direction_counts: dict[str, int]
    sample_packets: dict[str, dict[str, str | int]]
    error_rate: float


def parse_capture_packets(filepath: Path) -> list[tuple[str, str, bytes]]:
    """Parse capture file and extract raw packet hex.

    Args:
        filepath: Path to capture file

    Returns:
        List of (timestamp, direction, packet_bytes) tuples
    """
    with filepath.open() as f:
        lines = f.readlines()

    packets: list[tuple[str, str, bytes]] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Match packet header line (timestamp + direction + size)
        header_match = re.match(
            r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6})\s+(DEV→CLOUD|CLOUD→DEV)",
            line,
        )

        if header_match:
            timestamp = header_match.group(1)
            direction = header_match.group(2)

            # Next line should have hex data
            if i + 1 < len(lines):
                hex_line = lines[i + 1].strip()
                if hex_line and not hex_line.startswith("2025-"):  # Not a new header
                    try:
                        # Parse hex bytes
                        packet_bytes = bytes.fromhex(hex_line)
                        packets.append((timestamp, direction, packet_bytes))
                    except ValueError:
                        # Invalid hex, skip
                        pass

            i += 2  # Skip header line and hex line to next packet
        else:
            i += 1

    return packets


def validate_packets(
    packets: list[tuple[str, str, bytes]],
    limit: int | None = None,
) -> ValidationStats:
    """Decode packets using Phase 1a codec and collect statistics.

    Args:
        packets: List of (timestamp, direction, packet_bytes)
        limit: Optional limit on number of packets to process

    Returns:
        Statistics dictionary
    """
    protocol = CyncProtocol()
    stats: ValidationStats = {
        "total_packets": 0,
        "decoded_successfully": 0,
        "decode_errors": 0,
        "packet_types": Counter[str](),
        "error_reasons": Counter[str](),
        "direction_counts": {"DEV→CLOUD": 0, "CLOUD→DEV": 0},
        "sample_packets": {},
        "error_rate": 0.0,
    }

    packets_to_process = packets[:limit] if limit else packets

    for timestamp, direction, packet_bytes in packets_to_process:
        stats["total_packets"] += 1
        stats["direction_counts"][direction] += 1

        try:
            decoded = protocol.decode_packet(packet_bytes)
            stats["decoded_successfully"] += 1

            # Count packet type
            packet_type_hex = f"0x{decoded.packet_type:02x}"
            stats["packet_types"][packet_type_hex] += 1

            # Store sample packet (first of each type)
            if packet_type_hex not in stats["sample_packets"]:
                stats["sample_packets"][packet_type_hex] = {
                    "timestamp": timestamp,
                    "direction": direction,
                    "hex": packet_bytes.hex(" "),
                    "length": decoded.length,
                }

        except PacketDecodeError as e:
            stats["decode_errors"] += 1
            stats["error_reasons"][e.reason] += 1

    # Calculate error rate
    if stats["total_packets"] > 0:
        stats["error_rate"] = stats["decode_errors"] / stats["total_packets"] * 100
    else:
        stats["error_rate"] = 0.0

    return stats


def _format_overall_statistics(stats: ValidationStats) -> list[str]:
    """Format overall statistics section."""
    lines: list[str] = []
    lines.append("Overall Statistics:")
    lines.append(f"  Total Packets Processed: {stats['total_packets']:,}")
    lines.append(f"  Successfully Decoded: {stats['decoded_successfully']:,}")
    lines.append(f"  Decode Errors: {stats['decode_errors']:,}")
    lines.append(f"  Error Rate: {stats['error_rate']:.3f}%")
    lines.append("")
    return lines


def _format_traffic_direction(stats: ValidationStats) -> list[str]:
    """Format traffic direction section."""
    lines: list[str] = []
    lines.append("Traffic Direction:")
    for direction, count in stats["direction_counts"].items():
        lines.append(f"  {direction}: {count:,} packets")
    lines.append("")
    return lines


def _format_packet_types(stats: ValidationStats) -> list[str]:
    """Format packet types section."""
    lines: list[str] = []
    if stats["packet_types"]:
        lines.append("Packet Types Decoded:")
        for ptype, count in sorted(stats["packet_types"].items()):
            pct = (
                (count / stats["decoded_successfully"] * 100)
                if stats["decoded_successfully"] > 0
                else 0
            )
            lines.append(f"  {ptype}: {count:,} packets ({pct:.1f}%)")
        lines.append("")
    return lines


def _format_error_reasons(stats: ValidationStats) -> list[str]:
    """Format error reasons section."""
    lines: list[str] = []
    if stats["error_reasons"]:
        lines.append("Error Reasons:")
        for reason, count in stats["error_reasons"].most_common():
            lines.append(f"  {reason}: {count:,} occurrences")
        lines.append("")
    return lines


def _format_acceptance_criteria(stats: ValidationStats) -> tuple[list[str], bool]:
    """Format acceptance criteria section. Returns (lines, overall_pass)."""
    lines: list[str] = []
    lines.append("Phase 1a Acceptance Criteria:")

    decoded_pass = stats["decoded_successfully"] >= MIN_DECODED_PACKETS_REQUIRED
    if decoded_pass:
        lines.append(
            f"  ✅ PASS: Decoded {stats['decoded_successfully']:,} packets "
            f"(≥MIN_DECODED_PACKETS_REQUIRED required)"
        )
    else:
        lines.append(
            f"  ❌ FAIL: Only {stats['decoded_successfully']} packets "
            f"(need ≥MIN_DECODED_PACKETS_REQUIRED)"
        )

    error_rate_pass = stats["error_rate"] < MAX_ERROR_RATE
    if error_rate_pass:
        lines.append(f"  ✅ PASS: Error rate {stats['error_rate']:.3f}% (<1% required)")
    else:
        lines.append(f"  ❌ FAIL: Error rate {stats['error_rate']:.3f}% (≥1%)")

    # Check for all major packet types
    expected_types = ["0x23", "0x73", "0x83", "0xd3"]
    observed = [pt.lower() for pt in stats["packet_types"]]
    has_all = all(et in observed for et in expected_types)

    if has_all:
        lines.append("  ✅ PASS: All major packet types observed (0x23, 0x73, 0x83, 0xD3)")
    else:
        missing = [et for et in expected_types if et not in observed]
        lines.append(f"  ⚠️  WARNING: Missing types: {missing}")

    overall_pass = decoded_pass and error_rate_pass and has_all
    return lines, overall_pass


def format_validation_report(stats: ValidationStats, capture_file: str) -> str:
    """Format validation results as report.

    Args:
        stats: Statistics dictionary
        capture_file: Path to capture file

    Returns:
        Formatted report string
    """
    lines: list[str] = []
    lines.append("=" * 80)
    lines.append("Phase 1a Codec Validation - Decode Test Results")
    lines.append("=" * 80)
    lines.append(f"Capture File: {capture_file}")
    lines.append("")

    lines.extend(_format_overall_statistics(stats))
    lines.extend(_format_traffic_direction(stats))
    lines.extend(_format_packet_types(stats))
    lines.extend(_format_error_reasons(stats))

    criteria_lines, overall_pass = _format_acceptance_criteria(stats)
    lines.extend(criteria_lines)

    lines.append("")
    lines.append("=" * 80)

    # Overall result
    if overall_pass:
        lines.append("✅ VALIDATION PASSED - Phase 1a codec ready for production")
    else:
        lines.append("❌ VALIDATION FAILED - Review errors above")

    lines.append("=" * 80)

    return "\n".join(lines)


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = pass, 1 = fail)
    """
    if len(sys.argv) < MIN_ARGS_REQUIRED:
        print("Usage: python validate_codec_on_captures.py <capture_file> [packet_limit]")
        print("\nExample:")
        print(
            "  python validate_codec_on_captures.py mitm/captures/capture_20251108_221408.txt 1000"
        )
        print("  (Processes first 1000 packets)")
        return 1

    filepath = Path(sys.argv[1])
    limit = int(sys.argv[MIN_ARGS_REQUIRED]) if len(sys.argv) > MIN_ARGS_REQUIRED else None

    if not filepath.exists():
        print(f"Error: Capture file not found: {filepath}")
        return 1

    print(f"Parsing capture file: {filepath}")
    print(f"Packet limit: {limit if limit else 'None (all packets)'}")
    print("")

    # Parse packets
    packets = parse_capture_packets(filepath)
    print(f"Extracted {len(packets):,} packets from capture")
    print("")

    # Validate using Phase 1a codec
    print("Decoding packets with Phase 1a codec...")
    stats = validate_packets(packets, limit=limit)

    # Print report
    report = format_validation_report(stats, str(filepath))
    print(report)

    # Return 0 if passed, 1 if failed
    passed = (
        stats["decoded_successfully"] >= MIN_DECODED_PACKETS_REQUIRED
        and stats["error_rate"] < MAX_ERROR_RATE
        and all(
            ptype in [pt.lower() for pt in stats["packet_types"]]
            for ptype in ["0x23", "0x73", "0x83", "0xd3"]
        )
    )

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
