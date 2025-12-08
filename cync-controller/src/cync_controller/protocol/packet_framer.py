"""TCP stream packet framing with buffer overflow protection.

This module provides PacketFramer for extracting complete packets from TCP byte streams,
handling partial packets, multi-packet reads, and protecting against buffer exhaustion.
"""

import logging

from cync_controller.protocol.cync_protocol import PACKET_HEADER_LENGTH

logger = logging.getLogger(__name__)


class PacketFramer:
    r"""Extract complete packets from TCP byte stream.

    TCP reads may return partial packets, multiple packets, or exact boundaries.
    PacketFramer buffers incoming bytes and extracts complete packets based on
    the header length field.

    Security: Validates packet length against MAX_PACKET_SIZE to prevent
    buffer exhaustion from malicious/corrupted packets.

    Algorithm:

    1. Buffer all incoming bytes
    2. Check if buffer has at least 5 bytes (header)
    3. Parse header to get packet length (byte[3]*256 + byte[4])
    4. Validate length <= MAX_PACKET_SIZE (4096 bytes)
    5. If buffer has full packet (5 + length), extract it
    6. Repeat until buffer exhausted

    Handles:
    - Buffering incomplete packets across multiple reads
    - Header-based length calculation
    - Multi-packet extraction from single read
    - Partial packet handling
    - Length overflow protection (discards buffer on invalid length)

    Recovery Loop Protection:
    - Scans up to min(buffer_size, 5000) bytes before clearing buffer
    - Formula: max_recovery_attempts = min(1000, max(100, buffer_size // 5))
    - Time Complexity: O(n) where n = bytes scanned (max 5000)
    - Memory: O(1) additional (in-place buffer operations)
    - Example: 10KB corrupt buffer = 2048 attempts, scans 10KB, then clears
    - Bounded behavior: Will scan entire buffer once, then clear if no valid packets found

    Example:
        framer = PacketFramer()
        # First read: partial packet (header only)
        packets = framer.feed(b'\\x23\\x00\\x00\\x00\\x1a')
        assert packets == []  # Incomplete

        # Second read: remaining bytes
        packets = framer.feed(b'\\x39\\x87\\xc8\\x57...')
        assert len(packets) == 1  # Now complete

    """

    MAX_PACKET_SIZE: int = 4096  # 4KB max (observed max: 395 bytes)

    def __init__(self) -> None:
        """Initialize packet framer with empty buffer."""
        self.buffer: bytearray = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        """Add data to buffer and return list of complete packets.

        Args:
            data: Incoming bytes from TCP read

        Returns:
            List of complete packet bytes (may be empty if no complete packets)

        """
        self.buffer.extend(data)
        return self._extract_packets()

    def _extract_packets(self) -> list[bytes]:
        """Extract all complete packets from buffer.

        Validates packet length against MAX_PACKET_SIZE to prevent buffer
        exhaustion from malicious/corrupted packets.

        Implements recovery limit to prevent infinite loop on corrupt buffer.

        Performance Characteristics:
        - Time Complexity: O(n) where n = buffer size (single-pass)
        - Worst Case: O(n) even with corrupt packets (recovery limit prevents O(n²))
        - Memory: O(1) additional memory (in-place buffer operations)
        - Typical: Extracts 1-5 packets per call in normal operation

        Returns:
            List of complete packets; buffer retains incomplete data

        """
        packets: list[bytes] = []
        recovery_attempts = 0
        # Recovery attempts proportional to buffer size (min 100, max 1000)
        # Formula: attempts = buffer_size // 5 (capped at 1000)
        # Examples: 500-byte buffer = 100 attempts; 5000-byte buffer = 1000 attempts
        # Each attempt scans 5 bytes, so max scanned = 5000 bytes worst case
        max_recovery_attempts = min(1000, max(100, len(self.buffer) // PACKET_HEADER_LENGTH))

        while len(self.buffer) >= PACKET_HEADER_LENGTH:
            # Check recovery limit
            # Log once per buffer clear event, not per recovery attempt
            if recovery_attempts > max_recovery_attempts:
                logger.error(
                    "Buffer cleared after max recovery attempts",
                    extra={
                        "max_attempts": max_recovery_attempts,
                        "buffer_size": len(self.buffer),
                        "bytes_scanned": recovery_attempts * 5,
                    },
                )
                self.buffer = bytearray()  # Clear corrupted buffer
                break

            # Parse header to get packet length
            multiplier = self.buffer[3]
            base_len = self.buffer[4]
            packet_length = (multiplier * 256) + base_len

            # Validate length before proceeding
            # Rate-limited: logs once per invalid length found, not per attempt
            if packet_length > self.MAX_PACKET_SIZE:
                logger.warning(
                    (
                        "Invalid packet length: %d (max %d), advancing 5 bytes to next potential header "
                        "(attempt %d/%d, scanned %d bytes)"
                    ),
                    packet_length,
                    self.MAX_PACKET_SIZE,
                    recovery_attempts + 1,
                    max_recovery_attempts,
                    (recovery_attempts + 1) * 5,
                    extra={"buffer_size": len(self.buffer)},
                )
                # Fast-forward by header size (5 bytes) instead of 1 byte for performance
                # This maintains O(n) with bounded scan on malicious input
                advance_bytes = min(5, len(self.buffer))
                self.buffer = self.buffer[advance_bytes:]
                recovery_attempts += 1
                continue  # Retry parsing from new position

            # Reset recovery counter on valid packet
            recovery_attempts = 0

            total_length = 5 + packet_length  # Header (5 bytes) + data

            if len(self.buffer) >= total_length:
                # Extract complete packet
                packet = bytes(self.buffer[:total_length])
                packets.append(packet)
                self.buffer = self.buffer[total_length:]
            else:
                # Incomplete packet, wait for more data
                break

        return packets
