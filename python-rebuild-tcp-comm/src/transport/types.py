"""Core dataclasses for Phase 1b reliable transport layer.

This module defines the data structures used throughout the reliable transport
layer for tracking messages, results, and packets.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from protocol.packet_types import CyncPacket


@dataclass
class SendResult:
    """Result of send_reliable() operation.

    Attributes:
        success: Whether the send operation succeeded
        correlation_id: UUID v7 for observability and event tracing
        reason: Error reason if success=False (empty string if success=True)
        retry_count: Number of retry attempts made
    """

    success: bool
    correlation_id: str  # UUID v7
    reason: str = ""  # Error reason if success=False
    retry_count: int = 0  # Number of retries attempted


@dataclass
class TrackedPacket:
    """Packet with Phase 1b tracking metadata.

    Attributes:
        packet: Decoded CyncPacket from Phase 1a codec
        correlation_id: UUID v7 for observability
        recv_time: Timestamp when packet was received (time.time())
        dedup_key: Key used for deduplication (Full Fingerprint format)
    """

    packet: CyncPacket  # From Phase 1a decode
    correlation_id: str  # UUID v7 for observability
    recv_time: float  # Timestamp for metrics
    dedup_key: str  # Key used for deduplication


@dataclass
class PendingMessage:
    """Tracks message awaiting ACK.

    Attributes:
        msg_id: 2-byte wire protocol identifier
        correlation_id: UUID v7 for observability and event tracing
        sent_at: Timestamp when message was sent (time.time())
        ack_event: asyncio.Event that is set when ACK received
        retry_count: Number of retry attempts made
    """

    msg_id: bytes  # 2-byte wire protocol identifier
    correlation_id: str  # UUID v7 for observability
    sent_at: float  # Timestamp for timeout calculation
    ack_event: asyncio.Event  # Set when ACK received
    retry_count: int = 0  # Number of retry attempts
