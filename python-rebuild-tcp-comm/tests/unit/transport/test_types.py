"""Unit tests for transport layer dataclasses."""

from __future__ import annotations

import asyncio

from protocol.packet_types import CyncPacket
from transport.types import PendingMessage, SendResult, TrackedPacket

EXPECTED_RETRY_COUNT = 3

TEST_TIMESTAMP = 1234.567


class TestSendResult:
    """Tests for SendResult dataclass."""

    def test_success_result(self):
        """Test successful SendResult creation."""
        result = SendResult(
            success=True,
            correlation_id="test-correlation-id",
            retry_count=0,
        )
        assert result.success is True
        assert result.correlation_id == "test-correlation-id"
        assert result.reason == ""
        assert result.retry_count == 0

    def test_failure_result(self):
        """Test failed SendResult creation."""
        result = SendResult(
            success=False,
            correlation_id="test-correlation-id",
            reason="timeout",
            retry_count=3,
        )
        assert result.success is False
        assert result.correlation_id == "test-correlation-id"
        assert result.reason == "timeout"
        assert result.retry_count == EXPECTED_RETRY_COUNT

    def test_default_values(self):
        """Test SendResult with default values."""
        result = SendResult(success=True, correlation_id="test-id")
        assert result.reason == ""
        assert result.retry_count == 0


class TestTrackedPacket:
    """Tests for TrackedPacket dataclass."""

    def test_tracked_packet_creation(self):
        """Test TrackedPacket creation."""
        packet = CyncPacket(
            packet_type=0x73,
            length=10,
            payload=b"test",
            raw=b"\x73\x00\x00\x00\x0atest",
        )
        tracked = TrackedPacket(
            packet=packet,
            correlation_id="test-correlation-id",
            recv_time=TEST_TIMESTAMP,
            dedup_key="test-dedup-key",
        )
        assert tracked.packet == packet
        assert tracked.correlation_id == "test-correlation-id"
        assert tracked.recv_time == TEST_TIMESTAMP
        assert tracked.dedup_key == "test-dedup-key"


class TestPendingMessage:
    """Tests for PendingMessage dataclass."""

    def test_pending_message_creation(self):
        """Test PendingMessage creation."""
        event = asyncio.Event()
        pending = PendingMessage(
            msg_id=b"\x01\x02",
            correlation_id="test-correlation-id",
            sent_at=TEST_TIMESTAMP,
            ack_event=event,
            retry_count=0,
        )
        assert pending.msg_id == b"\x01\x02"
        assert pending.correlation_id == "test-correlation-id"
        assert pending.sent_at == TEST_TIMESTAMP
        assert pending.ack_event == event
        assert pending.retry_count == 0

    def test_pending_message_default_retry_count(self):
        """Test PendingMessage with default retry_count."""
        event = asyncio.Event()
        pending = PendingMessage(
            msg_id=b"\x01\x02",
            correlation_id="test-correlation-id",
            sent_at=TEST_TIMESTAMP,
            ack_event=event,
        )
        assert pending.retry_count == 0

    def test_pending_message_with_retries(self):
        """Test PendingMessage with retry count."""
        event = asyncio.Event()
        pending = PendingMessage(
            msg_id=b"\x01\x02",
            correlation_id="test-correlation-id",
            sent_at=TEST_TIMESTAMP,
            ack_event=event,
            retry_count=3,
        )
        assert pending.retry_count == EXPECTED_RETRY_COUNT
