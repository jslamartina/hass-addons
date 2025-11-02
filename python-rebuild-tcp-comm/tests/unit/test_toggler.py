"""Tests for toggle harness."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rebuild_tcp_comm.harness.toggler import send_toggle_packet, toggle_device_with_retry
from rebuild_tcp_comm.transport import TCPConnection


@pytest.mark.asyncio
async def test_tcp_connection_success() -> None:
    """Test successful TCP connection."""
    conn = TCPConnection("127.0.0.1", 9999, connect_timeout=0.5)

    # Mock the connection
    with patch("asyncio.open_connection") as mock_open:
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_open.return_value = (mock_reader, mock_writer)

        result = await conn.connect()

        assert result is True
        assert conn.is_connected
        mock_open.assert_called_once_with("127.0.0.1", 9999)


@pytest.mark.asyncio
async def test_tcp_connection_timeout() -> None:
    """Test TCP connection timeout."""
    conn = TCPConnection("192.0.2.1", 9999, connect_timeout=0.1)

    # Mock timeout
    with patch("asyncio.open_connection") as mock_open:
        mock_open.side_effect = asyncio.TimeoutError()

        result = await conn.connect()

        assert result is False
        assert not conn.is_connected


@pytest.mark.asyncio
async def test_send_toggle_packet_success() -> None:
    """Test successful toggle packet send and receive."""
    conn = TCPConnection("127.0.0.1", 9999)

    # Mock connection state
    conn._connected = True
    conn.reader = AsyncMock()
    conn.writer = MagicMock()

    # Mock successful send/recv
    with (
        patch.object(conn, "send", return_value=True) as mock_send,
        patch.object(conn, "recv", return_value=b"ACK") as mock_recv,
    ):
        response = await send_toggle_packet(
            conn=conn,
            device_id="TEST123",
            msg_id="abc123",
            state=True,
        )

        assert response == b"ACK"
        mock_send.assert_called_once()
        mock_recv.assert_called_once()


@pytest.mark.asyncio
async def test_send_toggle_packet_send_failure() -> None:
    """Test toggle packet send failure."""
    conn = TCPConnection("127.0.0.1", 9999)
    conn._connected = True

    # Mock send failure
    with patch.object(conn, "send", return_value=False):
        response = await send_toggle_packet(
            conn=conn,
            device_id="TEST123",
            msg_id="abc123",
            state=True,
        )

        assert response is None


@pytest.mark.asyncio
async def test_send_toggle_packet_recv_timeout() -> None:
    """Test toggle packet receive timeout."""
    conn = TCPConnection("127.0.0.1", 9999)
    conn._connected = True

    # Mock send success, recv timeout
    with (
        patch.object(conn, "send", return_value=True),
        patch.object(conn, "recv", return_value=None),
    ):
        response = await send_toggle_packet(
            conn=conn,
            device_id="TEST123",
            msg_id="abc123",
            state=True,
        )

        assert response is None


@pytest.mark.asyncio
async def test_toggle_device_with_retry_success() -> None:
    """Test toggle with successful first attempt."""
    with patch("rebuild_tcp_comm.harness.toggler.TCPConnection") as mock_conn_class:
        mock_conn = AsyncMock()
        mock_conn.connect.return_value = True
        mock_conn.close = AsyncMock()
        mock_conn_class.return_value = mock_conn

        with patch("rebuild_tcp_comm.harness.toggler.send_toggle_packet", return_value=b"ACK"):
            result = await toggle_device_with_retry(
                device_id="TEST123",
                device_host="127.0.0.1",
                device_port=9999,
                state=True,
                max_attempts=2,
            )

            assert result is True
            assert mock_conn.connect.call_count == 1
            assert mock_conn.close.call_count == 1


@pytest.mark.asyncio
async def test_toggle_device_with_retry_failure_then_success() -> None:
    """Test toggle with retry - first fails, second succeeds."""
    with patch("rebuild_tcp_comm.harness.toggler.TCPConnection") as mock_conn_class:
        mock_conn = AsyncMock()
        # First attempt fails connection, second succeeds
        mock_conn.connect.side_effect = [False, True]
        mock_conn.close = AsyncMock()
        mock_conn_class.return_value = mock_conn

        with (
            patch("rebuild_tcp_comm.harness.toggler.send_toggle_packet", return_value=b"ACK"),
            patch("asyncio.sleep"),
        ):  # Speed up test by mocking sleep
            result = await toggle_device_with_retry(
                device_id="TEST123",
                device_host="127.0.0.1",
                device_port=9999,
                state=True,
                max_attempts=2,
            )

            assert result is True
            assert mock_conn.connect.call_count == 2


@pytest.mark.asyncio
async def test_toggle_device_with_retry_all_attempts_fail() -> None:
    """Test toggle with all retry attempts failing."""
    with patch("rebuild_tcp_comm.harness.toggler.TCPConnection") as mock_conn_class:
        mock_conn = AsyncMock()
        mock_conn.connect.return_value = False
        mock_conn.close = AsyncMock()
        mock_conn_class.return_value = mock_conn

        with patch("asyncio.sleep"):  # Speed up test
            result = await toggle_device_with_retry(
                device_id="TEST123",
                device_host="127.0.0.1",
                device_port=9999,
                state=True,
                max_attempts=2,
            )

            assert result is False
            assert mock_conn.connect.call_count == 2


@pytest.mark.asyncio
async def test_tcp_send_success() -> None:
    """Test successful TCP send operation."""
    conn = TCPConnection("127.0.0.1", 9999, io_timeout=0.5)

    # Mock connected state
    conn._connected = True
    mock_writer = MagicMock()
    mock_drain = AsyncMock()
    mock_writer.drain = mock_drain
    conn.writer = mock_writer

    result = await conn.send(b"test data")

    assert result is True
    mock_writer.write.assert_called_once_with(b"test data")
    mock_drain.assert_called_once()


@pytest.mark.asyncio
async def test_tcp_recv_success() -> None:
    """Test successful TCP receive operation."""
    conn = TCPConnection("127.0.0.1", 9999, io_timeout=0.5)

    # Mock connected state
    conn._connected = True
    mock_reader = AsyncMock()
    mock_reader.read.return_value = b"response data"
    conn.reader = mock_reader

    result = await conn.recv(1024)

    assert result == b"response data"
    mock_reader.read.assert_called_once_with(1024)


@pytest.mark.asyncio
async def test_tcp_recv_connection_closed() -> None:
    """Test TCP receive when connection is closed by peer."""
    conn = TCPConnection("127.0.0.1", 9999, io_timeout=0.5)

    # Mock connected state
    conn._connected = True
    mock_reader = AsyncMock()
    mock_reader.read.return_value = b""  # Empty bytes = connection closed
    conn.reader = mock_reader

    result = await conn.recv(1024)

    assert result is None
    assert not conn.is_connected  # Should mark as disconnected
