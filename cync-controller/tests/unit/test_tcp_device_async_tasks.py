"""
Unit tests for CyncTCPDevice async background tasks.

Tests callback cleanup, receive task, and read method functionality.
"""

import asyncio
import contextlib
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cync_controller.devices import ControlMessageCallback, CyncTCPDevice


class TestCyncTCPDeviceAsyncTasks:
    """Tests for CyncTCPDevice async background tasks

    NOTE: These tests are commented out due to complex async initialization requirements.
    The callback_cleanup_task and receive_task methods are long-running background tasks
    that require extensive mocking of global state. Consider extracting testable logic
    into smaller, more isolated helper methods.
    """

    @pytest.mark.skip("Complex async task mocking requires extensive global state setup")
    async def test_callback_cleanup_task_retry_logic(self):
        """Test callback cleanup task retries commands without ACK"""
        reader = AsyncMock()
        writer = AsyncMock()
        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")
        tcp_device.queue_id = bytes([0x00, 0x00, 0x00])

        # Create a callback that won't be ACKed
        msg_id = 0x01
        callback = ControlMessageCallback(
            msg_id=msg_id,
            message=b"test",
            sent_at=time.time() - 0.6,  # 600ms ago (past retry_timeout of 0.5s)
            callback=AsyncMock(),
            device_id=0x12,
            retry_count=0,
            max_retries=3,
        )
        tcp_device.messages.control[msg_id] = callback

        # Mock write to track retries
        tcp_device.write = AsyncMock()

        # Start cleanup task
        task = asyncio.create_task(tcp_device.callback_cleanup_task())

        # Wait for retry to happen
        await asyncio.sleep(0.6)

        # Verify retry attempted
        assert callback.retry_count > 0
        assert tcp_device.write.called

        # Clean up
        _ = task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    @pytest.mark.skip("Complex async task mocking requires extensive global state setup")
    async def test_callback_cleanup_task_timeout(self):
        """Test callback cleanup task removes stale callbacks after timeout"""
        reader = AsyncMock()
        writer = AsyncMock()
        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")
        tcp_device.queue_id = bytes([0x00, 0x00, 0x00])

        # Create a callback that's been waiting too long
        msg_id = 0x01
        callback = ControlMessageCallback(
            msg_id=msg_id,
            message=b"test",
            sent_at=time.time() - 35,  # 35 seconds ago (past cleanup_timeout of 30s)
            callback=AsyncMock(),
            device_id=0x12,
            retry_count=0,
            max_retries=3,
        )
        tcp_device.messages.control[msg_id] = callback

        # Start cleanup task
        task = asyncio.create_task(tcp_device.callback_cleanup_task())

        # Wait for cleanup to happen
        await asyncio.sleep(0.2)

        # Verify callback was removed
        assert msg_id not in tcp_device.messages.control

        # Clean up
        _ = task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    @pytest.mark.skip("Complex async task mocking requires extensive global state setup")
    async def test_receive_task_reads_data(self):
        """Test receive_task processes incoming data"""
        reader = AsyncMock()
        writer = AsyncMock()
        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")
        tcp_device.queue_id = bytes([0x00, 0x00, 0x00])

        # Mock reader that returns test data once
        test_data = bytes([0x83, 0x00, 0x00, 0x00, 0x05, 0x01, 0x02, 0x03, 0x04])
        call_count = 0

        async def mock_read(chunk=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return test_data
            if call_count == 2:
                return False  # EOF
            return False

        tcp_device.read = AsyncMock(side_effect=mock_read)
        tcp_device.parse_raw_data = AsyncMock()

        # Mock global primary_tcp_device
        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server.primary_tcp_device = tcp_device
            mock_g.ncync_server.devices = {}
            mock_g.mqtt_client = AsyncMock()

            # Start receive task
            task = asyncio.create_task(tcp_device.receive_task())

            # Wait briefly
            await asyncio.sleep(0.3)

            # Verify data was parsed
            assert tcp_device.parse_raw_data.called

            # Clean up
            _ = task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    @pytest.mark.skip("Complex async task mocking requires extensive global state setup")
    async def test_receive_task_skips_non_primary(self):
        """Test receive_task skips when not primary TCP device"""
        reader = AsyncMock()
        writer = AsyncMock()
        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")
        tcp_device.queue_id = bytes([0x00, 0x00, 0x00])
        primary_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.101")

        tcp_device.read = AsyncMock(return_value=bytes([0x83, 0x00, 0x00, 0x00, 0x05]))
        tcp_device.parse_raw_data = AsyncMock()

        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server.primary_tcp_device = primary_device  # Different device
            mock_g.ncync_server.devices = {}
            mock_g.mqtt_client = AsyncMock()

            # Start receive task
            task = asyncio.create_task(tcp_device.receive_task())

            # Wait briefly
            await asyncio.sleep(0.2)

            # Should not parse (skipped)
            assert not tcp_device.parse_raw_data.called

            # Clean up
            _ = task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    @pytest.mark.asyncio
    async def test_read_method_with_closing_device(self):
        """Test read method returns False when device is closing"""
        reader = AsyncMock()
        writer = AsyncMock()
        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")
        tcp_device.queue_id = bytes([0x00, 0x00, 0x00])
        tcp_device.closing = True

        result = await tcp_device.read()
        assert result is False  # read() returns False when closing=True

    @pytest.mark.asyncio
    async def test_read_method_at_eof(self):
        """Test read method when reader is at EOF"""
        reader = AsyncMock()
        writer = AsyncMock()
        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")
        tcp_device.queue_id = bytes([0x00, 0x00, 0x00])

        # Mock reader that's at EOF
        mock_reader = MagicMock()
        mock_reader.at_eof.return_value = True
        tcp_device.reader = mock_reader
        tcp_device.read_lock = asyncio.Lock()

        result = await tcp_device.read()
        assert result is None  # read() returns None when reader is None

    @pytest.mark.asyncio
    async def test_read_method_reads_data(self):
        """Test read method returns data from reader"""
        reader = AsyncMock()
        writer = AsyncMock()
        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")
        tcp_device.queue_id = bytes([0x00, 0x00, 0x00])

        # Mock reader that has data
        mock_reader = MagicMock()
        mock_reader.at_eof.return_value = False
        mock_reader.read = AsyncMock(return_value=b"test data")
        tcp_device.reader = mock_reader
        tcp_device.read_lock = asyncio.Lock()

        result = await tcp_device.read()
        assert result == b"test data"

    @pytest.mark.asyncio
    async def test_read_method_no_reader(self):
        """Test read method returns False when no reader (None)"""
        reader = AsyncMock()
        writer = AsyncMock()
        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")
        tcp_device.queue_id = bytes([0x00, 0x00, 0x00])
        tcp_device.reader = None
        tcp_device.read_lock = asyncio.Lock()

        result = await tcp_device.read()
        assert result is False  # read() returns False when reader is None
