#!/usr/bin/env python3
"""
Parse and analyze MITM capture files.

Usage:
    # Show all packet types
    python mitm/parse-capture.py mitm/captures/capture_*.txt

    # Filter by packet type
    python mitm/parse-capture.py --filter 0x73 mitm/captures/capture_*.txt

    # Show statistics
    python mitm/parse-capture.py --stats mitm/captures/capture_*.txt

    # Extract ACK pairs
    python mitm/parse-capture.py --ack-pairs mitm/captures/capture_*.txt
"""

import argparse
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Display constants
FIRST_PACKETS_TO_SHOW = 10
LAST_PACKETS_TO_SHOW = 5


def parse_capture_file(filepath: str) -> list[dict]:
    """Parse MITM capture file and extract packets."""
    packets = []

    file_path = Path(filepath)
    with file_path.open() as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Parse header line
        if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", line):
            parts = line.split()
            timestamp_str = parts[0]
            direction = parts[1] if len(parts) > 1 else ""

            # Parse hex bytes on next line
            i += 1
            if i < len(lines):
                hex_bytes = lines[i].strip()
                packet_type = hex_bytes.split()[0] if hex_bytes else ""

                packets.append(
                    {
                        "timestamp": datetime.fromisoformat(timestamp_str),
                        "direction": direction,
                        "packet_type": packet_type.lower(),
                        "hex_bytes": hex_bytes,
                        "length": len(hex_bytes.split()) if hex_bytes else 0,
                    }
                )

        i += 1

    return packets


def filter_packets(packets: list[dict], packet_type: str) -> list[dict]:
    """Filter packets by type."""
    return [p for p in packets if p["packet_type"] == packet_type.lower().replace("0x", "")]


def show_statistics(packets: list[dict]):
    """Show packet statistics."""
    total = len(packets)
    type_counts = Counter(p["packet_type"] for p in packets)
    direction_counts = Counter(p["direction"] for p in packets)

    logger.info("=== Capture Statistics ===")
    logger.info("Total packets: %d", total)
    logger.info("")

    logger.info("Packet Types:")
    for ptype, count in sorted(type_counts.items()):
        pct = (count / total * 100) if total > 0 else 0
        logger.info("  0x%2s: %6d (%5.1f%%)", ptype.upper(), count, pct)
    logger.info("")

    logger.info("Directions:")
    for direction, count in direction_counts.items():
        pct = (count / total * 100) if total > 0 else 0
        logger.info("  %-10s: %6d (%5.1f%%)", direction, count, pct)


def extract_ack_pairs(packets: list[dict]) -> dict[str, list[tuple]]:
    """Extract request → ACK pairs."""
    pairs = defaultdict(list)

    pending = {
        "23": [],  # Handshake → 28
        "73": [],  # Data → 7b
        "83": [],  # Status → 88
        "d3": [],  # Heartbeat → d8
    }

    for packet in packets:
        ptype = packet["packet_type"]

        # Track requests
        if ptype in pending:
            pending[ptype].append(packet)

        # Match ACKs
        elif ptype == "28" and pending["23"]:
            req = pending["23"].pop(0)
            latency = (packet["timestamp"] - req["timestamp"]).total_seconds() * 1000
            pairs["0x28"].append((req, packet, latency))

        elif ptype == "7b" and pending["73"]:
            req = pending["73"].pop(0)
            latency = (packet["timestamp"] - req["timestamp"]).total_seconds() * 1000
            pairs["0x7B"].append((req, packet, latency))

        elif ptype == "88" and pending["83"]:
            req = pending["83"].pop(0)
            latency = (packet["timestamp"] - req["timestamp"]).total_seconds() * 1000
            pairs["0x88"].append((req, packet, latency))

        elif ptype == "d8" and pending["d3"]:
            req = pending["d3"].pop(0)
            latency = (packet["timestamp"] - req["timestamp"]).total_seconds() * 1000
            pairs["0xD8"].append((req, packet, latency))

    return pairs


def show_ack_pairs(pairs: dict[str, list[tuple]]):
    """Display ACK pair statistics."""
    logger.info("=== ACK Pair Statistics ===")

    for ack_type in ["0x28", "0x7B", "0x88", "0xD8"]:
        pair_list = pairs[ack_type]
        if pair_list:
            latencies = [lat for _, _, lat in pair_list]
            sorted_lats = sorted(latencies)
            n = len(sorted_lats)

            logger.info("\n%s ACK:", ack_type)
            logger.info("  Pairs: %d", n)
            logger.info("  Min latency: %.1fms", min(latencies))
            logger.info("  p50 latency: %.1fms", sorted_lats[n // 2])
            logger.info("  p95 latency: %.1fms", sorted_lats[int(n * 0.95)])
            logger.info("  p99 latency: %.1fms", sorted_lats[int(n * 0.99)])
            logger.info("  Max latency: %.1fms", max(latencies))


def main():
    parser = argparse.ArgumentParser(description="Parse and analyze MITM capture files")
    parser.add_argument("files", nargs="+", help="Capture files to analyze")
    parser.add_argument("--filter", metavar="TYPE", help="Filter by packet type (e.g., 0x73)")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    parser.add_argument("--ack-pairs", action="store_true", help="Extract and show ACK pairs")
    parser.add_argument("--limit", type=int, help="Limit output to N packets")

    args = parser.parse_args()

    # Parse all files
    all_packets = []
    for filepath in args.files:
        packets = parse_capture_file(filepath)
        all_packets.extend(packets)

    logger.info("Loaded %d packets from %d file(s)", len(all_packets), len(args.files))
    logger.info("")

    # Apply filter
    if args.filter:
        all_packets = filter_packets(all_packets, args.filter)
        logger.info("Filtered to %d packets of type %s", len(all_packets), args.filter)
        logger.info("")

    # Show statistics
    if args.stats:
        show_statistics(all_packets)
        return

    # Show ACK pairs
    if args.ack_pairs:
        pairs = extract_ack_pairs(all_packets)
        show_ack_pairs(pairs)
        return

    # Default: show packets
    limit = args.limit if args.limit else len(all_packets)
    for i, packet in enumerate(all_packets[:limit]):
        ts = packet["timestamp"].strftime("%H:%M:%S.%f")[:-3]
        logger.info(
            "%s %-10s 0x%2s (%3d bytes)",
            ts,
            packet["direction"],
            packet["packet_type"].upper(),
            packet["length"],
        )
        if (
            i < FIRST_PACKETS_TO_SHOW or i >= limit - LAST_PACKETS_TO_SHOW
        ):  # Show first N and last M
            logger.info("  %s", packet["hex_bytes"])
        elif i == FIRST_PACKETS_TO_SHOW:
            logger.info("  ...")


if __name__ == "__main__":
    main()
