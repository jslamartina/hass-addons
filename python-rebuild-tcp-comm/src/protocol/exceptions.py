"""Custom exception types for Cync protocol errors.

This module defines the exception hierarchy for protocol-related errors,
following the "No Nullability" principle where errors raise exceptions
instead of returning None.
"""

from __future__ import annotations


class CyncProtocolError(Exception):
    """Base exception for all Cync protocol errors.

    All protocol-related exceptions inherit from this base class,
    enabling catch-all error handling when needed while maintaining
    specific exception types for detailed handling.
    """


class PacketDecodeError(CyncProtocolError):
    """Packet cannot be decoded.

    Raised when packet parsing fails due to malformed data, invalid checksum,
    unknown type, invalid length, or missing frame markers.

    Attributes:
        reason: Specific failure reason (e.g., "too_short", "invalid_checksum")
        data_preview: First 16 bytes of packet data (security: prevents credential leakage)
    """

    def __init__(self, reason: str, data: bytes = b""):
        self.reason = reason
        # Security: Only store first 16 bytes to prevent credential leakage in logs/tracebacks
        self.data_preview = data[:16] if data else b""
        super().__init__(f"Packet decode failed: {reason}")


class PacketFramingError(CyncProtocolError):
    """TCP stream framing error.

    Raised by PacketFramer when extracting packets from TCP stream fails
    due to invalid length, buffer overflow, or recovery failures.

    Attributes:
        reason: Specific failure reason (e.g., "packet_too_large", "buffer_overflow")
        buffer_size: Size of buffer when error occurred
    """

    def __init__(self, reason: str, buffer_size: int = 0):
        self.reason = reason
        self.buffer_size = buffer_size
        super().__init__(f"Packet framing failed: {reason}")
