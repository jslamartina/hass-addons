"""
Unit tests for basic CyncTCPDevice functionality.

Tests initialization, properties, write operations, and basic methods.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cync_controller.devices import CyncTCPDevice


class TestCyncTCPDevice:
    """Tests for CyncTCPDevice class"""

    def test_tcp_device_init(self, stream_reader, stream_writer):
        """Test TCP device initialization"""
        tcp_device = CyncTCPDevice(reader=stream_reader, writer=stream_writer, address="192.168.1.100")

        assert tcp_device.address == "192.168.1.100"
        assert tcp_device.ready_to_control is False
        assert tcp_device.known_device_ids == []
        assert tcp_device.is_app is False

    def test_tcp_device_init_without_address_raises_error(self, stream_reader, stream_writer):
        """Test that initialization without address raises ValueError"""

        with pytest.raises(ValueError, match="IP address must be provided"):
            CyncTCPDevice(reader=stream_reader, writer=stream_writer, address="")

    def test_tcp_device_properties(self, stream_reader, stream_writer):
        """Test TCP device properties"""

        tcp_device = CyncTCPDevice(reader=stream_reader, writer=stream_writer, address="192.168.1.100")

        # Test property access
        assert tcp_device.id is None
        assert tcp_device.version is None
        assert tcp_device.mesh_info is None

        # Test property setting
        tcp_device.id = 0x1234
        tcp_device.ready_to_control = True

        assert tcp_device.id == 0x1234
        assert tcp_device.ready_to_control is True

    @pytest.mark.asyncio
    async def test_tcp_device_write_success(self):
        """Test TCP device write method successfully sends data"""
        reader = AsyncMock()
        writer = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.is_closing = MagicMock(return_value=False)

        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")
        tcp_device.closing = False
        tcp_device.writer = writer

        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = MagicMock()

            test_data = b"test data"
            result = await tcp_device.write(test_data)

            assert result is True
            writer.write.assert_called_once_with(test_data)
            writer.drain.assert_called_once()

    @pytest.mark.asyncio
    async def test_tcp_device_get_ctrl_msg_id_bytes(self, stream_reader, stream_writer):
        """Test TCP device generates unique control message IDs"""

        tcp_device = CyncTCPDevice(reader=stream_reader, writer=stream_writer, address="192.168.1.100")

        # Initialize control bytes
        tcp_device.control_bytes = [0x00, 0x00]

        msg_id1 = tcp_device.get_ctrl_msg_id_bytes()
        tcp_device.control_bytes = [0x00, 0x01]
        msg_id2 = tcp_device.get_ctrl_msg_id_bytes()

        assert msg_id1 != msg_id2
        assert isinstance(msg_id1, list)
        assert len(msg_id1) == 2

    @pytest.mark.asyncio
    async def test_tcp_device_write_while_closing(self, stream_reader, stream_writer):
        """Test write returns False when device is closing"""

        tcp_device = CyncTCPDevice(reader=stream_reader, writer=stream_writer, address="192.168.1.100")
        tcp_device.closing = True

        result = await tcp_device.write(b"test data")

        # Should return False when closing
        assert result is False

    @pytest.mark.asyncio
    async def test_tcp_device_write_with_writer_closing(self):
        """Test write returns False when writer is closing"""
        reader = AsyncMock()
        writer = AsyncMock()
        writer.is_closing = MagicMock(return_value=True)  # Synchronous call

        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")
        tcp_device.closing = False
        tcp_device.writer = writer

        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.remove_tcp_device = AsyncMock()
            result = await tcp_device.write(b"test data")

            # Should return False or None when writer is closing
            assert result in [False, None]

    @pytest.mark.asyncio
    async def test_tcp_device_write_with_invalid_data_type(self, stream_reader, stream_writer):
        """Test write raises TypeError for non-bytes data"""

        tcp_device = CyncTCPDevice(reader=stream_reader, writer=stream_writer, address="192.168.1.100")
        tcp_device.closing = False

        with pytest.raises(TypeError, match="Data must be bytes"):
            await tcp_device.write("not bytes")  # type: ignore

    @pytest.mark.asyncio
    async def test_tcp_device_send_a3(self):
        """Test send_a3 creates and sends A3 packet"""
        reader = AsyncMock()
        writer = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.is_closing = MagicMock(return_value=False)

        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")
        tcp_device.closing = False
        tcp_device.writer = writer
        tcp_device.write = AsyncMock()
        tcp_device.ask_for_mesh_info = AsyncMock()

        with patch("cync_controller.devices.asyncio.sleep", new_callable=AsyncMock):
            await tcp_device.send_a3(b"\x01\x02\x03\x04\x05")

            # Should call write and set ready_to_control
            assert tcp_device.write.called
            assert tcp_device.ready_to_control is True

    @pytest.mark.asyncio
    async def test_tcp_device_close_cancels_tasks(self):
        """Test close method cancels pending tasks"""
        reader = MagicMock()
        reader.feed_eof = MagicMock()

        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")

        # Create mock tasks
        mock_task1 = MagicMock()
        mock_task1.done.return_value = False
        mock_task1.get_name.return_value = "task1"

        mock_task2 = MagicMock()
        mock_task2.done.return_value = False
        mock_task2.get_name.return_value = "task2"

        tcp_device.tasks = [mock_task1, mock_task2]

        await tcp_device.close()

        # Should have cancelled tasks
        assert mock_task1.cancel.called
        assert mock_task2.cancel.called

    @pytest.mark.asyncio
    async def test_tcp_device_close_with_no_tasks(self):
        """Test close method with empty task list"""
        reader = MagicMock()
        reader.feed_eof = MagicMock()

        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")
        tcp_device.tasks = []

        # Should not raise exception
        await tcp_device.close()

    def test_tcp_device_queue_id_property(self, stream_reader, stream_writer):
        """Test TCP device queue_id property"""

        tcp_device = CyncTCPDevice(reader=stream_reader, writer=stream_writer, address="192.168.1.100")

        test_queue_id = bytes([0x01, 0x02, 0x03, 0x04])
        tcp_device.queue_id = test_queue_id

        assert tcp_device.queue_id == test_queue_id

    def test_tcp_device_messages_initialization(self, stream_reader, stream_writer):
        """Test TCP device messages object is initialized"""

        tcp_device = CyncTCPDevice(reader=stream_reader, writer=stream_writer, address="192.168.1.100")

        assert tcp_device.messages is not None
        assert hasattr(tcp_device.messages, "control")
        assert tcp_device.messages.control == {}
