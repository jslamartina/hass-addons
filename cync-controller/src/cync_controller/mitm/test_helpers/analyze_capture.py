#!/usr/bin/env python3
"""Analyze MITM capture logs for Phase 1a codec validation.

This script parses MITM capture files to extract packet statistics,
validate codec performance, and identify any decode errors.
"""

import logging
import re
import sys
from collections import Counter
from pathlib import Path
from typing import TypedDict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

MIN_ARGS_REQUIRED = 2
MIN_DECODED_PACKETS_REQUIRED = 100


class RawPacketCounts(TypedDict):
    """Raw packet direction counts."""

    dev_to_cloud: int
    cloud_to_dev: int


class CaptureStats(TypedDict):
    """Structured statistics extracted from capture logs."""

    total_validated: int
    total_failed: int
    error_rate: float
    packet_types: dict[str, int]
    direction_counts: dict[str, int]
    raw_packet_counts: RawPacketCounts
    capture_file: str


def parse_capture_file(filepath: Path) -> CaptureStats:
    """Parse MITM capture file and extract packet statistics.

    Args:
        filepath: Path to capture file

    Returns:
        Dictionary with packet statistics and validation results

    """
    with filepath.open() as f:
        content = f.read()

    # Extract codec validation successes
    validated_pattern = r"Phase 1a codec validated.*type[=:].*?(0x[0-9a-fA-F]{2})"
    validated_matches = re.findall(validated_pattern, content)

    # Extract validation failures
    failed_pattern = r"Phase 1a validation failed"
    failed_matches = re.findall(failed_pattern, content)

    # Count packet types
    packet_types = Counter(validated_matches)

    # Extract packet direction if available
    direction_pattern = r"direction[=:].*?(device_to_cloud|cloud_to_device)"
    direction_matches = re.findall(direction_pattern, content)
    direction_counts = Counter(direction_matches)

    # Count total packets (dev→cloud and cloud→dev from raw capture)
    dev_to_cloud = len(re.findall(r"DEV→CLOUD|Device → Cloud", content, re.IGNORECASE))
    cloud_to_dev = len(re.findall(r"CLOUD→DEV|Cloud → Device", content, re.IGNORECASE))

    return CaptureStats(
        total_validated=len(validated_matches),
        total_failed=len(failed_matches),
        error_rate=((len(failed_matches) / len(validated_matches) * 100) if validated_matches else 0.0),
        packet_types=dict(packet_types),
        direction_counts=dict(direction_counts),
        raw_packet_counts=RawPacketCounts(
            dev_to_cloud=dev_to_cloud,
            cloud_to_dev=cloud_to_dev,
        ),
        capture_file=str(filepath),
    )


def format_statistics_report(stats: CaptureStats) -> str:
    """Format statistics as human-readable report.

    Args:
        stats: Statistics dictionary from parse_capture_file

    Returns:
        Formatted report string

    """
    report: list[str] = []
    report.append("=" * 70)
    report.append("Phase 1a Codec Validation - Capture Analysis")
    report.append("=" * 70)
    report.append(f"Capture File: {stats['capture_file']}")
    report.append("")

    report.append("Packet Decode Statistics:")
    report.append(f"  Total Validated: {stats['total_validated']}")
    report.append(f"  Total Failed: {stats['total_failed']}")
    report.append(f"  Error Rate: {stats['error_rate']:.2f}%")
    report.append("")

    if stats["packet_types"]:
        report.append("Packet Types Decoded:")
        for ptype, count in sorted(stats["packet_types"].items()):
            report.append(f"  {ptype}: {count} packets")
        report.append("")

    if stats["direction_counts"]:
        report.append("Traffic Direction:")
        for direction, count in stats["direction_counts"].items():
            report.append(f"  {direction}: {count} packets")
        report.append("")

    report.append("Raw Packet Counts (from capture):")
    report.append(f"  DEV→CLOUD: {stats['raw_packet_counts']['dev_to_cloud']}")
    report.append(f"  CLOUD→DEV: {stats['raw_packet_counts']['cloud_to_dev']}")
    report.append("")

    # Validation status
    report.append("Validation Status:")
    if stats["total_validated"] >= MIN_DECODED_PACKETS_REQUIRED:
        report.append(f"  ✅ PASS: ≥{MIN_DECODED_PACKETS_REQUIRED} packets decoded")
    else:
        report.append(
            f"  ❌ FAIL: Only {stats['total_validated']} packets (need ≥{MIN_DECODED_PACKETS_REQUIRED})",
        )

    if stats["error_rate"] < 1.0:
        report.append(f"  ✅ PASS: Error rate {stats['error_rate']:.2f}% (<1%)")
    else:
        report.append(f"  ❌ FAIL: Error rate {stats['error_rate']:.2f}% (≥1%)")

    # Check for all major packet types
    expected_types = {"0x23", "0x73", "0x83", "0xd3"}
    observed_types = {ptype.lower() for ptype in stats["packet_types"]}
    if expected_types.issubset(observed_types):
        report.append("  ✅ PASS: All major packet types observed")
    else:
        missing = expected_types - observed_types
        report.append(f"  ⚠️  WARNING: Missing packet types: {missing}")

    report.append("=" * 70)

    return "\n".join(report)


def main() -> int:
    """Run capture analysis script.

    Returns:
        Exit code (0 = success, 1 = error)

    """
    if len(sys.argv) < MIN_ARGS_REQUIRED:
        logger.error("Usage: python analyze_capture.py <capture_file>")
        logger.error("\nExample:")
        logger.error("  python analyze_capture.py mitm/captures/capture_20251110_1234.txt")
        return 1

    filepath = Path(sys.argv[1])

    if not filepath.exists():
        logger.error("Error: Capture file not found: %s", filepath)
        return 1

    # Parse and analyze
    stats = parse_capture_file(filepath)

    # Print report
    report = format_statistics_report(stats)
    logger.info("%s", report)

    # Return 0 if validation passes, 1 if fails
    passed = stats["total_validated"] >= MIN_DECODED_PACKETS_REQUIRED and stats["error_rate"] < 1.0
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
