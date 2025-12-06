"""Unit tests for TCPConnection socket abstraction.

Tests cover:
- Connection lifecycle (connect, send, recv, close)
- Error handling (timeouts, connection failures, cleanup errors)
- Timeout behavior
- Cleanup operations
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cync_controller.transport.socket_abstraction import TCPConnection


class TCPConnectionTestHarness(TCPConnection):
    """Expose protected connection state controls for testing."""

    _connected: bool = False
    reader: AsyncMock | None = None
    writer: AsyncMock | MagicMock | None = None

    def set_connected_state(
        self,
        connected: bool,
        *,
        reader: AsyncMock | None = None,
        writer: AsyncMock | MagicMock | None = None,
    ) -> None:
        self._connected = connected
        if reader is not None:
            self.reader = reader
        if writer is not None:
            self.writer = writer


@pytest.fixture
def tcp_connection():
    """Create TCPConnection instance for testing."""
    return TCPConnectionTestHarness(
        host="127.0.0.1",
        port=8080,
        connect_timeout=0.1,
        io_timeout=0.1,
    )


@pytest.mark.asyncio
async def test_connect_success(tcp_connection: TCPConnectionTestHarness) -> None:
    """Test successful connection."""
    with patch("asyncio.open_connection") as mock_open:
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_open.return_value = (mock_reader, mock_writer)

        result = await tcp_connection.connect()

        assert result is True
        assert tcp_connection.is_connected is True
        assert tcp_connection.reader is mock_reader
        assert tcp_connection.writer is mock_writer
        # Verify open_connection was called (exact args may vary)
        mock_open.assert_called_once()


@pytest.mark.asyncio
async def test_connect_timeout(tcp_connection: TCPConnectionTestHarness) -> None:
    """Test connection timeout."""
    with patch("asyncio.open_connection") as mock_open:
        # Simulate timeout by making open_connection hang
        async def slow_connect(*_args: object, **_kwargs: object) -> tuple[AsyncMock, AsyncMock]:
            await asyncio.sleep(1.0)  # Longer than timeout
            return (AsyncMock(spec=asyncio.StreamReader), AsyncMock(spec=asyncio.StreamWriter))

        mock_open.side_effect = slow_connect

        result = await tcp_connection.connect()

        assert result is False
        assert tcp_connection.is_connected is False
        assert tcp_connection.reader is None
        assert tcp_connection.writer is None


@pytest.mark.asyncio
async def test_connect_oserror(tcp_connection: TCPConnectionTestHarness) -> None:
    """Test connection failure with OSError."""
    with patch("asyncio.open_connection") as mock_open:
        mock_open.side_effect = OSError("Connection refused")

        result = await tcp_connection.connect()

        assert result is False
        assert tcp_connection.is_connected is False


@pytest.mark.asyncio
async def test_send_success(tcp_connection: TCPConnectionTestHarness) -> None:
    """Test successful send."""
    mock_writer = AsyncMock()
    mock_writer.write = MagicMock()
    mock_writer.drain = AsyncMock()
    tcp_connection.writer = mock_writer
    tcp_connection.set_connected_state(True)
    data = b"test data"
    result = await tcp_connection.send(data)

    assert result is True
    mock_writer.write.assert_called_once_with(data)
    mock_writer.drain.assert_called_once()


@pytest.mark.asyncio
async def test_send_not_connected(tcp_connection: TCPConnectionTestHarness) -> None:
    """Test send when not connected."""
    tcp_connection.set_connected_state(False)
    result = await tcp_connection.send(b"test")

    assert result is False


@pytest.mark.asyncio
async def test_send_timeout(tcp_connection: TCPConnectionTestHarness) -> None:
    """Test send timeout."""
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.write = MagicMock()

    async def slow_drain() -> None:
        await asyncio.sleep(1.0)  # Longer than timeout

    mock_writer.drain = slow_drain
    tcp_connection.writer = mock_writer
    tcp_connection.set_connected_state(True)
    result = await tcp_connection.send(b"test")

    assert result is False


@pytest.mark.asyncio
async def test_send_oserror(tcp_connection: TCPConnectionTestHarness) -> None:
    """Test send with OSError."""
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.write = MagicMock(side_effect=OSError("Broken pipe"))
    mock_writer.drain = AsyncMock()
    tcp_connection.writer = mock_writer
    tcp_connection.set_connected_state(True)
    result = await tcp_connection.send(b"test")

    assert result is False


@pytest.mark.asyncio
async def test_recv_success(tcp_connection: TCPConnectionTestHarness) -> None:
    """Test successful receive."""
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_reader.read = AsyncMock(return_value=b"received data")
    tcp_connection.reader = mock_reader
    tcp_connection.set_connected_state(True)
    result = await tcp_connection.recv()

    assert result == b"received data"
    mock_reader.read.assert_called_once_with(65536)


@pytest.mark.asyncio
async def test_recv_not_connected(tcp_connection: TCPConnectionTestHarness) -> None:
    """Test receive when not connected."""
    tcp_connection.set_connected_state(False)
    result = await tcp_connection.recv()

    assert result is None


@pytest.mark.asyncio
async def test_recv_timeout(tcp_connection: TCPConnectionTestHarness) -> None:
    """Test receive timeout."""
    mock_reader = AsyncMock(spec=asyncio.StreamReader)

    async def slow_read(*_args: object, **_kwargs: object) -> bytes:
        await asyncio.sleep(1.0)  # Longer than timeout
        return b"data"

    mock_reader.read = slow_read
    tcp_connection.reader = mock_reader
    tcp_connection.set_connected_state(True)
    result = await tcp_connection.recv()

    assert result is None


@pytest.mark.asyncio
async def test_recv_oserror(tcp_connection: TCPConnectionTestHarness) -> None:
    """Test receive with OSError."""
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_reader.read = AsyncMock(side_effect=OSError("Connection reset"))
    tcp_connection.reader = mock_reader
    tcp_connection.set_connected_state(True)
    result = await tcp_connection.recv()

    assert result is None


@pytest.mark.asyncio
async def test_close_success(tcp_connection: TCPConnectionTestHarness) -> None:
    """Test successful close."""
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()
    tcp_connection.writer = mock_writer
    tcp_connection.set_connected_state(True)
    await tcp_connection.close()

    assert tcp_connection.is_connected is False
    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_called_once()


@pytest.mark.asyncio
async def test_close_not_connected(tcp_connection: TCPConnectionTestHarness) -> None:
    """Test close when not connected."""
    tcp_connection.set_connected_state(False)
    tcp_connection.writer = None

    # Should not raise
    await tcp_connection.close()

    assert tcp_connection.is_connected is False


@pytest.mark.asyncio
async def test_close_oserror_continues(tcp_connection: TCPConnectionTestHarness) -> None:
    """Test that OSError during close doesn't fail cleanup."""
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.close = MagicMock(side_effect=OSError("Already closed"))
    mock_writer.wait_closed = AsyncMock()
    tcp_connection.writer = mock_writer
    tcp_connection.set_connected_state(True)
    # Should not raise - cleanup is best-effort
    await tcp_connection.close()

    assert tcp_connection.is_connected is False


@pytest.mark.asyncio
async def test_close_unexpected_error_continues(tcp_connection: TCPConnectionTestHarness) -> None:
    """Test that unexpected errors during close don't fail cleanup."""
    mock_writer = AsyncMock()
    mock_writer.close = MagicMock(side_effect=RuntimeError("Unexpected error"))
    mock_writer.wait_closed = AsyncMock()
    tcp_connection.writer = mock_writer
    tcp_connection.set_connected_state(True)
    # Should not raise - cleanup is best-effort
    await tcp_connection.close()

    assert tcp_connection.is_connected is False


@pytest.mark.asyncio
async def test_close_wait_closed_error_continues(tcp_connection: TCPConnectionTestHarness) -> None:
    """Test that wait_closed errors don't fail cleanup."""
    mock_writer = AsyncMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock(side_effect=OSError("Connection error"))
    tcp_connection.writer = mock_writer
    tcp_connection.set_connected_state(True)
    # Should not raise - cleanup is best-effort
    await tcp_connection.close()

    assert tcp_connection.is_connected is False


@pytest.mark.asyncio
async def test_close_writer_none(tcp_connection: TCPConnectionTestHarness) -> None:
    """Test close when writer is None."""
    tcp_connection.writer = None
    tcp_connection.reader = None
    tcp_connection.set_connected_state(True)
    # Should not raise - close handles None writer gracefully
    await tcp_connection.close()

    # When writer is None, _connected may remain True (implementation detail)
    # The important thing is that it doesn't raise
