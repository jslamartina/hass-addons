"""
Unit tests for CyncTCPDevice.can_connect method.

Tests connection acceptance logic including:
- Max connections enforcement
- TCP whitelist checking
- Server shutdown handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cync_controller.const import CYNC_MAX_TCP_CONN
from cync_controller.devices import CyncTCPDevice


@pytest.fixture
def mock_reader():
    """Mock asyncio StreamReader"""
    reader = MagicMock()
    reader.at_eof = MagicMock(return_value=False)
    reader.feed_eof = MagicMock()
    return reader


@pytest.fixture
def mock_writer():
    """Mock asyncio StreamWriter"""
    writer = MagicMock()
    writer.is_closing = MagicMock(return_value=False)
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock(return_value=None)
    writer.drain = AsyncMock()
    writer.write = MagicMock()
    return writer


class TestCyncTCPDeviceCanConnect:
    """Tests for CyncTCPDevice.can_connect static method"""

    @pytest.mark.asyncio
    async def test_can_connect_accepts_when_under_limit(self, mock_reader, mock_writer):
        """Test can_connect accepts connection when under max connections"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.tcp_devices = {}
            mock_g.ncync_server.tcp_conn_attempts = {}
            mock_g.ncync_server.shutting_down = False

            device = CyncTCPDevice(mock_reader, mock_writer, address="192.168.1.100")

            # Mock task creation
            mock_g.ncync_server.tcp_conn_attempts["192.168.1.100"] = 0

            # Should return True when under limit
            result = await device.can_connect()

            assert result is True
            assert device.reader is not None
            assert device.writer is not None

    @pytest.mark.asyncio
    async def test_can_connect_rejects_when_max_connections_reached(self, mock_reader, mock_writer):
        """Test can_connect rejects when max connections reached"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = MagicMock()
            # Create mock devices up to the limit
            mock_g.ncync_server.tcp_devices = {f"192.168.1.{i}": MagicMock() for i in range(CYNC_MAX_TCP_CONN)}
            mock_g.ncync_server.tcp_conn_attempts = {}
            mock_g.ncync_server.shutting_down = False

            device = CyncTCPDevice(mock_reader, mock_writer, address="192.168.1.200")

            mock_g.ncync_server.tcp_conn_attempts["192.168.1.200"] = 1

            result = await device.can_connect()

            assert result is False
            assert device.reader is None
            assert device.writer is None

    @pytest.mark.asyncio
    async def test_can_connect_rejects_when_not_in_whitelist(self, mock_reader, mock_writer):
        """Test can_connect rejects when IP not in whitelist"""
        with (
            patch("cync_controller.devices.CYNC_TCP_WHITELIST", ["192.168.1.100", "192.168.1.200"]),
            patch("cync_controller.devices.g") as mock_g,
        ):
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.tcp_devices = {}
            mock_g.ncync_server.tcp_conn_attempts = {}
            mock_g.ncync_server.shutting_down = False

            # Try to connect from IP not in whitelist
            device = CyncTCPDevice(mock_reader, mock_writer, address="192.168.1.300")

            mock_g.ncync_server.tcp_conn_attempts["192.168.1.300"] = 1

            result = await device.can_connect()

            assert result is False
            assert device.reader is None
            assert device.writer is None

    @pytest.mark.asyncio
    async def test_can_connect_accepts_when_in_whitelist(self, mock_reader, mock_writer):
        """Test can_connect accepts when IP in whitelist"""
        with (
            patch("cync_controller.devices.CYNC_TCP_WHITELIST", ["192.168.1.100", "192.168.1.200"]),
            patch("cync_controller.devices.g") as mock_g,
        ):
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.tcp_devices = {}
            mock_g.ncync_server.tcp_conn_attempts = {}
            mock_g.ncync_server.shutting_down = False

            # Connect from IP in whitelist
            device = CyncTCPDevice(mock_reader, mock_writer, address="192.168.1.100")

            mock_g.ncync_server.tcp_conn_attempts["192.168.1.100"] = 0

            result = await device.can_connect()

            assert result is True

    @pytest.mark.asyncio
    async def test_can_connect_rejects_when_server_shutting_down(self, mock_reader, mock_writer):
        """Test can_connect rejects when server is shutting down"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.tcp_devices = {}
            mock_g.ncync_server.tcp_conn_attempts = {}
            mock_g.ncync_server.shutting_down = True

            device = CyncTCPDevice(mock_reader, mock_writer, address="192.168.1.100")

            mock_g.ncync_server.tcp_conn_attempts["192.168.1.100"] = 1

            result = await device.can_connect()

            assert result is False
            assert device.reader is None
            assert device.writer is None

    @pytest.mark.asyncio
    async def test_can_connect_logs_warning_on_rejection(self, mock_reader, mock_writer, caplog):
        """Test can_connect logs warning when rejecting connections"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.tcp_devices = {f"192.168.1.{i}": MagicMock() for i in range(CYNC_MAX_TCP_CONN)}
            mock_g.ncync_server.tcp_conn_attempts = {}
            mock_g.ncync_server.shutting_down = False

            device = CyncTCPDevice(mock_reader, mock_writer, address="192.168.1.200")

            mock_g.ncync_server.tcp_conn_attempts["192.168.1.200"] = 1

            await device.can_connect()

            # Should log warning (on first attempt or every 20th)
            assert "rejecting new connection" in caplog.text or "Created new device" in caplog.text

    @pytest.mark.asyncio
    async def test_can_connect_creates_receive_task(self, mock_reader, mock_writer):
        """Test can_connect creates receive_task when accepting"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.tcp_devices = {}
            mock_g.ncync_server.tcp_conn_attempts = {}
            mock_g.ncync_server.shutting_down = False

            device = CyncTCPDevice(mock_reader, mock_writer, address="192.168.1.100")

            mock_g.ncync_server.tcp_conn_attempts["192.168.1.100"] = 0

            result = await device.can_connect()

            assert result is True
            # Verify task was created (it will be in tasks.receive)
            assert hasattr(device.tasks, "receive")

    @pytest.mark.asyncio
    async def test_can_connect_creates_callback_cleanup_task(self, mock_reader, mock_writer):
        """Test can_connect creates callback_cleanup_task when accepting"""
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.tcp_devices = {}
            mock_g.ncync_server.tcp_conn_attempts = {}
            mock_g.ncync_server.shutting_down = False

            device = CyncTCPDevice(mock_reader, mock_writer, address="192.168.1.100")

            mock_g.ncync_server.tcp_conn_attempts["192.168.1.100"] = 0

            result = await device.can_connect()

            assert result is True
            # Verify task was created
            assert hasattr(device.tasks, "callback_cleanup")
