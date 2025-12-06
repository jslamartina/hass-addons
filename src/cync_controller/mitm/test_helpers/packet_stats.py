#!/usr/bin/env python3
"""Packet statistics calculator for Phase 1a manual testing.

Provides detailed packet classification and analysis functions.
"""

# Validation thresholds
MIN_PACKETS_FOR_VALIDATION = 100
MAX_ERROR_RATE_PERCENT = 1.0


def classify_packet_type(packet_type_hex: str) -> str:
    """Classify packet type by hex value.

    Args:
        packet_type_hex: Packet type as hex string (e.g., "0x23")

    Returns:
        Human-readable packet classification

    """
    packet_map = {
        "0x23": "Handshake (DEV→CLOUD)",
        "0x28": "Hello ACK (CLOUD→DEV)",
        "0x43": "Device Info (DEV→CLOUD)",
        "0x48": "Info ACK (CLOUD→DEV)",
        "0x73": "Data Channel (CLOUD→DEV)",
        "0x7b": "Data ACK (DEV→CLOUD)",
        "0x83": "Status Broadcast (DEV→CLOUD)",
        "0x88": "Status ACK (CLOUD→DEV)",
        "0xd3": "Heartbeat Device (DEV→CLOUD)",
        "0xd8": "Heartbeat Cloud (CLOUD→DEV)",
    }
    return packet_map.get(packet_type_hex.lower(), f"Unknown ({packet_type_hex})")


def calculate_packet_distribution(packet_types: dict[str, int]) -> dict[str, float]:
    """Calculate percentage distribution of packet types.

    Args:
        packet_types: Dictionary of {packet_type: count}

    Returns:
        Dictionary of {packet_type: percentage}

    """
    total = sum(packet_types.values())
    if total == 0:
        return {}

    return {ptype: (count / total * 100) for ptype, count in packet_types.items()}


def generate_statistics_table(packet_types: dict[str, int], direction_counts: dict[str, int]) -> str:
    """Generate formatted statistics table.

    Args:
        packet_types: Dictionary of {packet_type: count}
        direction_counts: Dictionary of {direction: count}

    Returns:
        Markdown-formatted table

    """
    lines: list[str] = []
    lines.append("## Packet Type Distribution\n")
    lines.append("| Packet Type | Classification | Count | Percentage |")
    lines.append("|-------------|----------------|-------|------------|")

    distribution = calculate_packet_distribution(packet_types)

    for ptype in sorted(packet_types):
        count = packet_types[ptype]
        pct = distribution.get(ptype, 0.0)
        classification = classify_packet_type(ptype)
        lines.append(f"| {ptype} | {classification} | {count} | {pct:.1f}% |")

    lines.append("")
    lines.append("## Traffic Direction\n")
    lines.append("| Direction | Count |")
    lines.append("|-----------|-------|")

    for direction, count in sorted(direction_counts.items()):
        lines.append(f"| {direction} | {count} |")

    return "\n".join(lines)


def identify_missing_packet_types(observed_types: list[str]) -> list[str]:
    """Identify which major packet types were not observed.

    Args:
        observed_types: List of observed packet type hex strings

    Returns:
        List of missing packet type hex strings

    """
    expected_major_types = {"0x23", "0x73", "0x83", "0xd3"}
    observed_normalized = {ptype.lower() for ptype in observed_types}
    missing = expected_major_types - observed_normalized
    return sorted(missing)


def assess_validation_quality(total_validated: int, total_failed: int, packet_types: dict[str, int]) -> dict[str, bool]:
    """Assess validation quality against acceptance criteria.

    Args:
        total_validated: Number of successfully validated packets
        total_failed: Number of failed validations
        packet_types: Dictionary of observed packet types

    Returns:
        Dictionary of {criterion: passed}

    """
    error_rate = (total_failed / total_validated * 100) if total_validated > 0 else 100.0

    observed_types = list(packet_types)
    missing_types = identify_missing_packet_types(observed_types)

    return {
        "sufficient_packets": total_validated >= MIN_PACKETS_FOR_VALIDATION,
        "low_error_rate": error_rate < MAX_ERROR_RATE_PERCENT,
        "all_major_types": len(missing_types) == 0,
        "has_handshake": any("0x23" in t.lower() for t in observed_types),
        "has_data_channel": any("0x73" in t.lower() for t in observed_types),
        "has_status_broadcast": any("0x83" in t.lower() for t in observed_types),
        "has_heartbeat": any("0xd3" in t.lower() for t in observed_types),
    }


def format_quality_assessment(assessment: dict[str, bool]) -> str:
    """Format quality assessment as checklist.

    Args:
        assessment: Quality assessment dictionary

    Returns:
        Formatted checklist string

    """
    lines: list[str] = []
    lines.append("## Validation Quality Assessment\n")

    criteria_labels = {
        "sufficient_packets": "≥100 packets decoded",
        "low_error_rate": "Error rate <1%",
        "all_major_types": "All major packet types observed",
        "has_handshake": "Handshake packets (0x23) present",
        "has_data_channel": "Data channel packets (0x73) present",
        "has_status_broadcast": "Status broadcast packets (0x83) present",
        "has_heartbeat": "Heartbeat packets (0xD3) present",
    }

    for criterion, passed in assessment.items():
        label = criteria_labels.get(criterion, criterion)
        status = "✅ PASS" if passed else "❌ FAIL"
        lines.append(f"- {status}: {label}")

    overall_pass = all(assessment.values())
    lines.append("")
    lines.append(
        f"**Overall**: {'✅ PASS' if overall_pass else '❌ FAIL'} "
        f"({sum(assessment.values())}/{len(assessment)} criteria met)"
    )

    return "\n".join(lines)
