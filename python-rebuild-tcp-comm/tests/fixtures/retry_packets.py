"""Retry packet fixtures for Phase 1b deduplication testing.

Generated: 2025-11-07T00:38:02.243134
Source: Retry field verification analysis
"""

from dataclasses import dataclass


@dataclass
class RetryPacketPair:
    """Retry packet pair with original and retry response."""

    iteration: str
    packet_type: str
    original_hex: str
    retry_hex: str
    original_dedup_key: str
    retry_dedup_key: str
    fields_stable: bool


# Retry packet pairs for testing
RETRY_PAIRS = [
    RetryPacketPair(
        iteration="ITERATION_01",
        packet_type="0x73",
        original_hex=(
            "73 00 00 00 13 1b dc da 3e 00 00 00 7e 0d 01 00 00 "
            "f9 8e 01 00 00 8f 7e 7b 00 00 00 07 1b dc da 3e 00 13 00"
        ),
        retry_hex=(
            "73 00 00 00 13 1b dc da 3e 00 2c 00 7e 0d 01 00 00 "
            "f9 8e 01 00 00 8f 7e 7b 00 00 00 07 1b dc da 3e 00 13 00"
        ),
        original_dedup_key="0x73:unknown:00:00:7e:7afb54622026a487",
        retry_dedup_key="0x73:unknown:2c:00:7e:7afb54622026a487",
        fields_stable=False,
    ),
    RetryPacketPair(
        iteration="ITERATION_01",
        packet_type="0x73",
        original_hex=(
            "73 00 00 00 13 1b dc da 3e 00 00 00 7e 0d 01 00 00 "
            "f9 8e 01 00 00 8f 7e 7b 00 00 00 07 1b dc da 3e 00 13 00"
        ),
        retry_hex=(
            "73 00 00 00 13 1b dc da 3e 00 06 00 7e 0d 01 00 00 "
            "f9 8e 01 00 00 8f 7e 7b 00 00 00 07 1b dc da 3e 00 13 00"
        ),
        original_dedup_key="0x73:unknown:00:00:7e:7afb54622026a487",
        retry_dedup_key="0x73:unknown:06:00:7e:7afb54622026a487",
        fields_stable=False,
    ),
    RetryPacketPair(
        iteration="ITERATION_01",
        packet_type="0x73",
        original_hex=(
            "73 00 00 00 13 1b dc da 3e 00 00 00 7e 0d 01 00 00 "
            "f9 8e 01 00 00 8f 7e 7b 00 00 00 07 1b dc da 3e 00 13 00"
        ),
        retry_hex=(
            "73 00 00 00 13 1b dc da 3e 00 05 00 7e 0d 01 00 00 "
            "f9 8e 01 00 00 8f 7e 7b 00 00 00 07 1b dc da 3e 00 13 00"
        ),
        original_dedup_key="0x73:unknown:00:00:7e:7afb54622026a487",
        retry_dedup_key="0x73:unknown:05:00:7e:7afb54622026a487",
        fields_stable=False,
    ),
    RetryPacketPair(
        iteration="ITERATION_01",
        packet_type="0x73",
        original_hex=(
            "73 00 00 00 13 1b dc da 3e 00 00 00 7e 0d 01 00 00 "
            "f9 8e 01 00 00 8f 7e 7b 00 00 00 07 1b dc da 3e 00 13 00"
        ),
        retry_hex=(
            "73 00 00 00 13 1b dc da 3e 00 06 00 7e 0d 01 00 00 "
            "f9 8e 01 00 00 8f 7e 7b 00 00 00 07 1b dc da 3e 00 13 00"
        ),
        original_dedup_key="0x73:unknown:00:00:7e:7afb54622026a487",
        retry_dedup_key="0x73:unknown:06:00:7e:7afb54622026a487",
        fields_stable=False,
    ),
    RetryPacketPair(
        iteration="ITERATION_01",
        packet_type="0x73",
        original_hex=(
            "73 00 00 00 13 1b dc da 3e 00 00 00 7e 0d 01 00 00 "
            "f9 8e 01 00 00 8f 7e 7b 00 00 00 07 1b dc da 3e 00 13 00"
        ),
        retry_hex=(
            "73 00 00 00 13 1b dc da 3e 00 05 00 7e 0d 01 00 00 "
            "f9 8e 01 00 00 8f 7e 7b 00 00 00 07 1b dc da 3e 00 13 00"
        ),
        original_dedup_key="0x73:unknown:00:00:7e:7afb54622026a487",
        retry_dedup_key="0x73:unknown:05:00:7e:7afb54622026a487",
        fields_stable=False,
    ),
]

# Expected dedup behavior:
# - If fields_stable=True: original and retry should have SAME dedup_key
# - If fields_stable=False: dedup_keys may differ (document which fields vary)
