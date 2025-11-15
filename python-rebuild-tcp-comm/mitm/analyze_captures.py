#!/usr/bin/env python3
"""Analyze captured packets and generate documentation."""

import json
import logging
import sys
import tempfile
from collections import Counter
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def analyze_jsonl_captures(jsonl_file: Path) -> dict:
    """Analyze JSONL packet capture file."""
    packets = []

    with jsonl_file.open() as f:
        for line in f:
            if line.strip():
                packets.append(json.loads(line))

    # Count packet types
    packet_types = Counter()
    for pkt in packets:
        hex_data = pkt["hex"]
        packet_type = hex_data.split()[0] if hex_data else "unknown"
        direction = pkt["direction"]
        packet_types[(packet_type, direction)] += 1

    return {
        "total_packets": len(packets),
        "packet_types": dict(packet_types),
        "packets": packets,
    }


def main():
    """Main analysis entry point."""
    # Use tempfile.gettempdir() for cross-platform compatibility
    temp_dir = Path(tempfile.gettempdir())
    jsonl_file = temp_dir / "mitm-packets.jsonl"

    if not jsonl_file.exists():
        logger.error("No capture file found at %s", jsonl_file)
        sys.exit(1)

    analysis = analyze_jsonl_captures(jsonl_file)

    logger.info("\n%s", "=" * 60)
    logger.info("MITM Proxy Capture Analysis")
    logger.info("%s\n", "=" * 60)

    logger.info("Total Packets: %d", analysis["total_packets"])
    logger.info("\nPacket Type Breakdown:")
    logger.info("%-6s %-12s %-8s", "Type", "Direction", "Count")
    logger.info("-" * 30)

    # Sort by packet type
    for (ptype, direction), count in sorted(analysis["packet_types"].items()):
        logger.info("0x%-4s %-12s %-8d", ptype, direction, count)

    # Check for key packet types
    logger.info("\n%s", "=" * 60)
    logger.info("Phase 0.5 Deliverable Status")
    logger.info("%s\n", "=" * 60)

    types_found = {t for t, _ in analysis["packet_types"]}

    flows = {
        "Handshake (0x23→0x28)": ("23" in types_found and "28" in types_found),
        "Toggle (0x73→0x7B→0x83→0x88)": all(t in types_found for t in ["73", "7b", "83", "88"]),
        "Status Broadcast (0x83→0x88)": ("83" in types_found and "88" in types_found),
        "Heartbeat (0xD3→0xD8)": ("d3" in types_found and "d8" in types_found),
        "Device Info (0x43→0x48)": ("43" in types_found and "48" in types_found),
    }

    for flow_name, captured in flows.items():
        status = "✅ Captured" if captured else "❌ Not captured"
        logger.info("%-15s %s", status, flow_name)

    # Find examples of each packet type
    logger.info("\n%s", "=" * 60)
    logger.info("Sample Packets")
    logger.info("%s\n", "=" * 60)

    for ptype in sorted(types_found):
        examples = [p for p in analysis["packets"] if p["hex"].startswith(ptype)]
        if examples:
            example = examples[0]
            logger.info(
                "\n0x%s %s (%d bytes)",
                ptype.upper(),
                example["direction"],
                example["length"],
            )
            logger.info("Hex: %s...", example["hex"][:60])


if __name__ == "__main__":
    main()
