"""Custom exception types for Phase 1b transport layer errors.

This module defines the exception hierarchy for transport-related errors,
extending the Phase 1a protocol exceptions.
"""

from __future__ import annotations

from cync_controller.protocol.exceptions import CyncProtocolError


class CyncConnectionError(CyncProtocolError):
    """Connection state error (not connected, handshake failed, etc.).

    Raised when:
    - Attempting to send while disconnected
    - Connection lost during operation
    - Connection manager in invalid state

    Note: Named CyncConnectionError to avoid shadowing Python's built-in ConnectionError.

    Attributes:
        reason: Specific failure reason
        state: Connection state when error occurred

    """

    def __init__(self, reason: str, state: str = "unknown") -> None:
        """Initialize connection error with reason and state."""
        self.reason: str = reason
        self.state: str = state
        super().__init__(f"Connection error: {reason} (state: {state})")


class HandshakeError(CyncProtocolError):
    """Handshake failed (timeout, invalid response, authentication failed).

    Raised when:
    - 0x23 handshake timeout (no 0x28 ACK received)
    - Invalid handshake response packet
    - Max handshake retries exceeded

    Attributes:
        reason: Specific failure reason
        attempts: Number of handshake attempts made

    """

    def __init__(self, reason: str, attempts: int = 0) -> None:
        """Initialize handshake error with reason and attempt count."""
        self.reason: str = reason
        self.attempts: int = attempts
        super().__init__(f"Handshake failed: {reason} after {attempts} attempts")


class PacketReceiveError(CyncProtocolError):
    """Error receiving packet from connection (network failure, timeout, etc.).

    Raised when:
    - TCP connection closed unexpectedly
    - Network read timeout
    - Socket error during receive

    Attributes:
        reason: Specific failure reason

    """

    def __init__(self, reason: str) -> None:
        """Initialize packet receive error with reason."""
        self.reason: str = reason
        super().__init__(f"Packet receive failed: {reason}")


class DuplicatePacketError(CyncProtocolError):
    """Packet is a duplicate (caught by deduplication cache).

    This is a normal condition during retry scenarios, not necessarily
    an error. Caller may choose to log and continue.

    Attributes:
        dedup_key: Deduplication key that matched
        correlation_id: Correlation ID of the duplicate packet

    """

    def __init__(self, dedup_key: str, correlation_id: str) -> None:
        """Initialize duplicate packet error."""
        self.dedup_key: str = dedup_key
        self.correlation_id: str = correlation_id
        super().__init__(f"Duplicate packet: {dedup_key}")


class ACKTimeoutError(CyncProtocolError):
    """ACK not received within timeout period.

    Raised when:
    - Expected ACK not received within ack_timeout_seconds
    - Max retries exceeded waiting for ACK

    Attributes:
        msg_id: Message ID that timed out
        timeout_seconds: Timeout value that was exceeded
        retries: Number of retry attempts made
        correlation_id: Correlation ID for observability

    """

    def __init__(self, msg_id: bytes, timeout_seconds: float, retries: int, correlation_id: str = "") -> None:
        """Initialize ACK timeout error."""
        self.msg_id: bytes = msg_id
        self.timeout_seconds: float = timeout_seconds
        self.retries: int = retries
        self.correlation_id: str = correlation_id
        super().__init__(f"ACK timeout after {timeout_seconds}s ({retries} retries)")
