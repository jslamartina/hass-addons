#!/usr/bin/env python3
"""Analyze captured packets and generate documentation."""

import json
import sys
from collections import Counter
from pathlib import Path


def analyze_jsonl_captures(jsonl_file: Path) -> dict:
    """Analyze JSONL packet capture file."""
    packets = []

    with open(jsonl_file) as f:
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
    jsonl_file = Path("/tmp/mitm-packets.jsonl")

    if not jsonl_file.exists():
        print("No capture file found at /tmp/mitm-packets.jsonl")
        sys.exit(1)

    analysis = analyze_jsonl_captures(jsonl_file)

    print(f"\n{'=' * 60}")
    print("MITM Proxy Capture Analysis")
    print(f"{'=' * 60}\n")

    print(f"Total Packets: {analysis['total_packets']}")
    print("\nPacket Type Breakdown:")
    print(f"{'Type':<6} {'Direction':<12} {'Count':<8}")
    print("-" * 30)

    # Sort by packet type
    for (ptype, direction), count in sorted(analysis["packet_types"].items()):
        print(f"0x{ptype:<4} {direction:<12} {count:<8}")

    # Check for key packet types
    print(f"\n{'=' * 60}")
    print("Phase 0.5 Deliverable Status")
    print(f"{'=' * 60}\n")

    types_found = set(t for t, _ in analysis["packet_types"].keys())

    flows = {
        "Handshake (0x23→0x28)": ("23" in types_found and "28" in types_found),
        "Toggle (0x73→0x7B→0x83→0x88)": all(t in types_found for t in ["73", "7b", "83", "88"]),
        "Status Broadcast (0x83→0x88)": ("83" in types_found and "88" in types_found),
        "Heartbeat (0xD3→0xD8)": ("d3" in types_found and "d8" in types_found),
        "Device Info (0x43→0x48)": ("43" in types_found and "48" in types_found),
    }

    for flow_name, captured in flows.items():
        status = "✅ Captured" if captured else "❌ Not captured"
        print(f"{status:<15} {flow_name}")

    # Find examples of each packet type
    print(f"\n{'=' * 60}")
    print("Sample Packets")
    print(f"{'=' * 60}\n")

    for ptype in sorted(types_found):
        examples = [p for p in analysis["packets"] if p["hex"].startswith(ptype)]
        if examples:
            example = examples[0]
            print(f"\n0x{ptype.upper()} {example['direction']} ({example['length']} bytes)")
            print(f"Hex: {example['hex'][:60]}...")


if __name__ == "__main__":
    main()
