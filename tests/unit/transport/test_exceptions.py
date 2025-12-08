"""Unit tests for transport layer exceptions."""

from __future__ import annotations

from cync_controller.protocol.exceptions import CyncProtocolError
from cync_controller.transport.exceptions import (
    ACKTimeoutError,
    CyncConnectionError,
    DuplicatePacketError,
    HandshakeError,
    PacketReceiveError,
)

# Test constants
EXPECTED_ATTEMPTS = 3
EXPECTED_RETRIES = 3


class TestExceptionHierarchy:
    """Tests for exception inheritance."""

    def test_all_exceptions_inherit_from_cync_protocol_error(self):
        """Test that all transport exceptions inherit from CyncProtocolError."""
        assert issubclass(CyncConnectionError, CyncProtocolError)
        assert issubclass(HandshakeError, CyncProtocolError)
        assert issubclass(PacketReceiveError, CyncProtocolError)
        assert issubclass(DuplicatePacketError, CyncProtocolError)
        assert issubclass(ACKTimeoutError, CyncProtocolError)


class TestCyncConnectionError:
    """Tests for CyncConnectionError."""

    def test_connection_error_with_reason(self):
        """Test CyncConnectionError with reason only."""
        error = CyncConnectionError(reason="not_connected")
        assert error.reason == "not_connected"
        assert error.state == "unknown"
        assert "not_connected" in str(error)

    def test_connection_error_with_state(self):
        """Test CyncConnectionError with reason and state."""
        error = CyncConnectionError(reason="handshake_failed", state="CONNECTING")
        assert error.reason == "handshake_failed"
        assert error.state == "CONNECTING"
        assert "handshake_failed" in str(error)
        assert "CONNECTING" in str(error)


class TestHandshakeError:
    """Tests for HandshakeError."""

    def test_handshake_error_with_reason(self):
        """Test HandshakeError with reason only."""
        error = HandshakeError(reason="timeout")
        assert error.reason == "timeout"
        assert error.attempts == 0
        assert "timeout" in str(error)

    def test_handshake_error_with_attempts(self):
        """Test HandshakeError with reason and attempts."""
        error = HandshakeError(reason="timeout", attempts=3)
        assert error.reason == "timeout"
        assert error.attempts == EXPECTED_ATTEMPTS
        assert "timeout" in str(error)
        assert "3" in str(error)


class TestPacketReceiveError:
    """Tests for PacketReceiveError."""

    def test_packet_receive_error(self):
        """Test PacketReceiveError creation."""
        error = PacketReceiveError(reason="connection_closed")
        assert error.reason == "connection_closed"
        assert "connection_closed" in str(error)


class TestDuplicatePacketError:
    """Tests for DuplicatePacketError."""

    def test_duplicate_packet_error(self):
        """Test DuplicatePacketError creation."""
        error = DuplicatePacketError(
            dedup_key="test-key",
            correlation_id="test-correlation-id",
        )
        assert error.dedup_key == "test-key"
        assert error.correlation_id == "test-correlation-id"
        assert "test-key" in str(error)


class TestACKTimeoutError:
    """Tests for ACKTimeoutError."""

    def test_ack_timeout_error_minimal(self):
        """Test ACKTimeoutError with minimal parameters."""
        error = ACKTimeoutError(
            msg_id=b"\x01\x02",
            timeout_seconds=1.0,
            retries=3,
        )
        assert error.msg_id == b"\x01\x02"
        assert error.timeout_seconds == 1.0
        assert error.retries == EXPECTED_RETRIES
        assert error.correlation_id == ""
        assert "1.0" in str(error)
        assert "3" in str(error)

    def test_ack_timeout_error_with_correlation_id(self):
        """Test ACKTimeoutError with correlation_id."""
        error = ACKTimeoutError(
            msg_id=b"\x01\x02",
            timeout_seconds=1.0,
            retries=3,
            correlation_id="test-correlation-id",
        )
        assert error.correlation_id == "test-correlation-id"
