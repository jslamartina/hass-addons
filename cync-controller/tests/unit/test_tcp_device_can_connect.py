"""Unit tests for CyncTCPDevice.can_connect method.

Tests connection acceptance logic including:
- Max connections enforcement
- TCP whitelist checking
- Server shutdown handling
"""

from __future__ import annotations

from asyncio import StreamReader, StreamWriter
from dataclasses import dataclass, field
from typing import cast
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest

from cync_controller.const import CYNC_MAX_TCP_CONN
from cync_controller.devices.tcp_device import CyncTCPDevice


def _create_stream_reader() -> StreamReader:
    return cast(StreamReader, create_autospec(StreamReader, instance=True))


def _create_stream_writer() -> StreamWriter:
    return cast(StreamWriter, create_autospec(StreamWriter, instance=True))


@dataclass
class ServerStub:
    shutting_down: bool = False
    tcp_devices: dict[str, object] = field(default_factory=dict)
    tcp_conn_attempts: dict[str, int] = field(default_factory=dict)

    async def remove_tcp_device(self, _device: object) -> bool:
        """Stub async remover to satisfy device cleanup during tests."""
        return True


def _create_server_mock(shutting_down: bool = False) -> ServerStub:
    return ServerStub(shutting_down=shutting_down)


@pytest.fixture
def mock_reader() -> StreamReader:
    """Mock asyncio StreamReader."""
    reader = _create_stream_reader()
    reader.at_eof = MagicMock(return_value=False)  # type: ignore[assignment]
    reader.feed_eof = MagicMock()  # type: ignore[assignment]
    return reader


@pytest.fixture
def mock_writer() -> StreamWriter:
    """Mock asyncio StreamWriter."""
    writer = _create_stream_writer()
    writer.is_closing = MagicMock(return_value=False)  # type: ignore[assignment]
    writer.close = MagicMock()  # type: ignore[assignment]
    writer.wait_closed = AsyncMock(return_value=None)  # type: ignore[assignment]
    writer.drain = AsyncMock()  # type: ignore[assignment]
    writer.write = MagicMock()  # type: ignore[assignment]
    return writer


class TestCyncTCPDeviceCanConnect:
    """Tests for CyncTCPDevice.can_connect static method."""

    @pytest.mark.asyncio
    async def test_can_connect_accepts_when_under_limit(
        self, mock_reader: StreamReader, mock_writer: StreamWriter
    ) -> None:
        """Test can_connect accepts connection when under max connections."""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = _create_server_mock()

            device = CyncTCPDevice(mock_reader, mock_writer, address="192.168.1.100")

            # Mock task creation
            mock_g.ncync_server.tcp_conn_attempts["192.168.1.100"] = 0

            try:
                # Should return True when under limit
                result = await device.can_connect()

                assert result is True
                assert device.reader is not None
                assert device.writer is not None
            finally:
                await device.close()

    @pytest.mark.asyncio
    async def test_can_connect_rejects_when_max_connections_reached(
        self, mock_reader: StreamReader, mock_writer: StreamWriter
    ) -> None:
        """Test can_connect rejects when max connections reached."""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = _create_server_mock()
            mock_g.ncync_server.tcp_devices = cast(
                dict[str, object],
                {f"192.168.1.{i}": MagicMock() for i in range(CYNC_MAX_TCP_CONN)},
            )

            device = CyncTCPDevice(mock_reader, mock_writer, address="192.168.1.200")

            mock_g.ncync_server.tcp_conn_attempts["192.168.1.200"] = 1

            result = await device.can_connect()

            assert result is False
            assert device.reader is None
            assert device.writer is None

    @pytest.mark.asyncio
    async def test_can_connect_rejects_when_not_in_whitelist(
        self, mock_reader: StreamReader, mock_writer: StreamWriter
    ) -> None:
        """Test can_connect rejects when IP not in whitelist."""
        with (
            patch("cync_controller.devices.tcp_device.CYNC_TCP_WHITELIST", ["192.168.1.100", "192.168.1.200"]),
            patch("cync_controller.devices.tcp_device._get_global_object") as mock_get_g,
        ):
            mock_g = MagicMock()
            mock_get_g.return_value = mock_g
            mock_g.ncync_server = _create_server_mock()

            # Try to connect from IP not in whitelist
            device = CyncTCPDevice(mock_reader, mock_writer, address="192.168.1.300")

            mock_g.ncync_server.tcp_conn_attempts["192.168.1.300"] = 1

            result = await device.can_connect()

            assert result is False
            assert device.reader is None
            assert device.writer is None

    @pytest.mark.asyncio
    async def test_can_connect_accepts_when_in_whitelist(
        self, mock_reader: StreamReader, mock_writer: StreamWriter
    ) -> None:
        """Test can_connect accepts when IP in whitelist."""
        with (
            patch("cync_controller.devices.tcp_device.CYNC_TCP_WHITELIST", ["192.168.1.100", "192.168.1.200"]),
            patch("cync_controller.devices.tcp_device._get_global_object") as mock_get_g,
        ):
            mock_g = MagicMock()
            mock_get_g.return_value = mock_g
            mock_g.ncync_server = _create_server_mock()

            # Connect from IP in whitelist
            device = CyncTCPDevice(mock_reader, mock_writer, address="192.168.1.100")

            mock_g.ncync_server.tcp_conn_attempts["192.168.1.100"] = 0

            try:
                result = await device.can_connect()

                assert result is True
            finally:
                await device.close()

    @pytest.mark.asyncio
    async def test_can_connect_rejects_when_server_shutting_down(
        self, mock_reader: StreamReader, mock_writer: StreamWriter
    ) -> None:
        """Test can_connect rejects when server is shutting down."""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = _create_server_mock(shutting_down=True)

            device = CyncTCPDevice(mock_reader, mock_writer, address="192.168.1.100")

            mock_g.ncync_server.tcp_conn_attempts["192.168.1.100"] = 1

            result = await device.can_connect()

            assert result is False
            assert device.reader is None
            assert device.writer is None

    @pytest.mark.asyncio
    async def test_can_connect_creates_receive_task(self, mock_reader: StreamReader, mock_writer: StreamWriter) -> None:
        """Test can_connect creates receive_task when accepting."""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = _create_server_mock()

            device = CyncTCPDevice(mock_reader, mock_writer, address="192.168.1.100")

            mock_g.ncync_server.tcp_conn_attempts["192.168.1.100"] = 0

            try:
                result = await device.can_connect()

                assert result is True
                # Verify task was created (it will be in tasks.receive)
                assert hasattr(device.tasks, "receive")
            finally:
                await device.close()

    @pytest.mark.asyncio
    async def test_can_connect_creates_callback_cleanup_task(
        self, mock_reader: StreamReader, mock_writer: StreamWriter
    ) -> None:
        """Test can_connect creates callback_cleanup_task when accepting."""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = _create_server_mock()

            device = CyncTCPDevice(mock_reader, mock_writer, address="192.168.1.100")

            mock_g.ncync_server.tcp_conn_attempts["192.168.1.100"] = 0

            try:
                result = await device.can_connect()

                assert result is True
                # Verify task was created
                assert hasattr(device.tasks, "callback_cleanup")
            finally:
                await device.close()
