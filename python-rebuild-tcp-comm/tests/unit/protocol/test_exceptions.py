"""Unit tests for protocol exception types."""

from __future__ import annotations

from _pytest.outcomes import fail

from protocol.exceptions import CyncProtocolError, PacketDecodeError, PacketFramingError

# Test constants
DATA_PREVIEW_TRUNCATE_LENGTH = 16  # Maximum bytes stored in error preview
SHORT_DATA_LENGTH = 3  # Short test data length
TEST_BUFFER_SIZE_LARGE = 5000  # Large buffer size for testing
TEST_BUFFER_SIZE_MEDIUM = 1000  # Medium buffer size for testing


def test_packet_decode_error_has_reason() -> None:
    """Test PacketDecodeError has reason attribute."""
    error = PacketDecodeError("too_short", b"\x23\x00")

    assert error.reason == "too_short"
    assert "too_short" in str(error)


def test_packet_decode_error_truncates_data() -> None:
    """Test PacketDecodeError truncates data preview to 16 bytes."""
    # Create 32 bytes of test data
    large_data = bytes(range(32))

    error = PacketDecodeError("invalid_checksum", large_data)

    # Should only store first 16 bytes
    assert len(error.data_preview) == DATA_PREVIEW_TRUNCATE_LENGTH
    assert error.data_preview == large_data[:DATA_PREVIEW_TRUNCATE_LENGTH]


def test_packet_decode_error_empty_data() -> None:
    """Test PacketDecodeError handles empty data."""
    error = PacketDecodeError("unknown_type")

    assert error.reason == "unknown_type"
    assert error.data_preview == b""


def test_packet_decode_error_short_data() -> None:
    """Test PacketDecodeError handles data shorter than 16 bytes."""
    short_data = b"\x23\x00\x00"

    error = PacketDecodeError("too_short", short_data)

    # Should store all available bytes (not pad to 16)
    assert error.data_preview == short_data
    assert len(error.data_preview) == SHORT_DATA_LENGTH


def test_packet_framing_error_has_buffer_size() -> None:
    """Test PacketFramingError has buffer_size attribute."""
    error = PacketFramingError("packet_too_large", buffer_size=TEST_BUFFER_SIZE_LARGE)

    assert error.reason == "packet_too_large"
    assert error.buffer_size == TEST_BUFFER_SIZE_LARGE
    assert "packet_too_large" in str(error)


def test_packet_framing_error_default_buffer_size() -> None:
    """Test PacketFramingError buffer_size defaults to 0."""
    error = PacketFramingError("buffer_overflow")

    assert error.reason == "buffer_overflow"
    assert error.buffer_size == 0


def test_exceptions_inherit_from_base() -> None:
    """Test exception hierarchy - all inherit from CyncProtocolError."""
    decode_error = PacketDecodeError("too_short")
    framing_error = PacketFramingError("invalid_length")

    assert isinstance(decode_error, CyncProtocolError)
    assert isinstance(framing_error, CyncProtocolError)
    assert isinstance(decode_error, Exception)
    assert isinstance(framing_error, Exception)


def test_cync_protocol_error_catch_all() -> None:
    """Test CyncProtocolError can catch all protocol exceptions."""
    error_reason = "test_reason"
    try:
        raise PacketDecodeError(error_reason)
    except CyncProtocolError as err:
        assert isinstance(err, PacketDecodeError)
        assert "test_reason" in str(err)
    else:  # pragma: no cover
        fail("Expected PacketDecodeError to be caught as CyncProtocolError")
    error_framing = "test_framing"
    try:
        raise PacketFramingError(error_framing)
    except CyncProtocolError as err:
        assert isinstance(err, PacketFramingError)
        assert "test_framing" in str(err)
    else:  # pragma: no cover
        fail("Expected PacketFramingError to be caught as CyncProtocolError")


def test_packet_decode_error_all_reasons() -> None:
    """Test all expected PacketDecodeError reasons."""
    reasons = [
        "too_short",
        "invalid_checksum",
        "unknown_type",
        "invalid_length",
        "missing_0x7e_markers",
    ]

    for reason in reasons:
        error = PacketDecodeError(reason, b"\x00\x01\x02")
        assert error.reason == reason
        assert reason in str(error)


def test_packet_framing_error_all_reasons() -> None:
    """Test all expected PacketFramingError reasons."""
    reasons = ["packet_too_large", "invalid_length", "buffer_overflow"]

    for reason in reasons:
        error = PacketFramingError(reason, buffer_size=TEST_BUFFER_SIZE_MEDIUM)
        assert error.reason == reason
        assert reason in str(error)
        assert error.buffer_size == TEST_BUFFER_SIZE_MEDIUM
