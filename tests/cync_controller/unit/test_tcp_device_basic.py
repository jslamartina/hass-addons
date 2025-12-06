"""Unit tests for basic CyncTCPDevice functionality.

Tests initialization, properties, write operations, and basic methods.
"""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest

# Import directly from module to avoid lazy import type issues
from cync_controller.devices.tcp_device import CyncTCPDevice

# ============================================================================
# Mock Factory Functions
# ============================================================================
# These helpers provide a clean pattern for creating typed mocks:
# - Use create_autospec + cast for mocks that need to match real type signatures
# - Use MagicMock with type annotations for mocks that need full mockability
# - Suppress reportAny warnings for MagicMock usage where Any types are intentional


def create_typed_stream_reader() -> asyncio.StreamReader:
    """Create a typed mock StreamReader using create_autospec."""
    return cast(asyncio.StreamReader, create_autospec(asyncio.StreamReader, instance=True))


def create_typed_stream_writer() -> asyncio.StreamWriter:
    """Create a typed mock StreamWriter using create_autospec."""
    return cast(asyncio.StreamWriter, create_autospec(asyncio.StreamWriter, instance=True))


def create_mock_task() -> asyncio.Task[object]:
    """Create a typed Task mock with autospec for safer assertions."""
    return create_autospec(asyncio.Task, instance=True)


class TaskStub:
    """Simple task stub to track cancellation in tests."""

    def __init__(self, name: str) -> None:
        self._name = name
        self.cancel_called: bool = False

    def done(self) -> bool:
        return False

    def get_name(self) -> str:
        return self._name

    def cancel(self) -> None:
        self.cancel_called = True


class TestCyncTCPDevice:
    """Tests for CyncTCPDevice class."""

    def test_tcp_device_init(self, stream_reader: MagicMock, stream_writer: MagicMock) -> None:
        """Test TCP device initialization."""
        tcp_device = CyncTCPDevice(reader=stream_reader, writer=stream_writer, address="192.168.1.100")

        assert tcp_device.address == "192.168.1.100"
        assert tcp_device.ready_to_control is False
        assert tcp_device.known_device_ids == []
        assert tcp_device.is_app is False

    def test_tcp_device_init_without_address_raises_error(
        self, stream_reader: MagicMock, stream_writer: MagicMock
    ) -> None:
        """Test that initialization without address raises ValueError."""
        with pytest.raises(ValueError, match="IP address must be provided"):
            _ = CyncTCPDevice(reader=stream_reader, writer=stream_writer, address="")

    def test_tcp_device_properties(self, stream_reader: MagicMock, stream_writer: MagicMock) -> None:
        """Test TCP device properties."""
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
    async def test_tcp_device_write_success(self) -> None:
        """Test TCP device write method successfully sends data."""
        # Use typed mock factories for proper type checking
        reader = create_typed_stream_reader()
        writer = create_typed_stream_writer()
        # Override specific methods with MagicMock for assertion capabilities
        writer.write = MagicMock()  # type: ignore[assignment]
        writer.drain = AsyncMock()  # type: ignore[assignment]
        writer.is_closing = MagicMock(return_value=False)  # type: ignore[assignment]

        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")
        tcp_device.closing = False
        tcp_device.writer = writer

        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = MagicMock()  # type: ignore[assignment]

            test_data = b"test data"
            result = await tcp_device.write(test_data)

            assert result is True
            # MagicMock assertions need type ignore for reportAny
            writer.write.assert_called_once_with(test_data)  # type: ignore[reportAny]
            writer.drain.assert_called_once()  # type: ignore[reportAny]

    @pytest.mark.asyncio
    async def test_tcp_device_get_ctrl_msg_id_bytes(self, stream_reader: MagicMock, stream_writer: MagicMock) -> None:
        """Test TCP device generates unique control message IDs."""
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
    async def test_tcp_device_write_while_closing(self, stream_reader: MagicMock, stream_writer: MagicMock) -> None:
        """Test write returns False when device is closing."""
        tcp_device = CyncTCPDevice(reader=stream_reader, writer=stream_writer, address="192.168.1.100")
        tcp_device.closing = True

        result = await tcp_device.write(b"test data")

        # Should return False when closing
        assert result is False

    @pytest.mark.asyncio
    async def test_tcp_device_write_with_writer_closing(self) -> None:
        """Test write returns False when writer is closing."""
        reader = create_typed_stream_reader()
        writer = create_typed_stream_writer()
        writer.is_closing = MagicMock(return_value=True)  # type: ignore[assignment]

        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")
        tcp_device.closing = False
        tcp_device.writer = writer

        with patch("cync_controller.devices.g") as mock_g:
            mock_g.ncync_server = MagicMock()  # type: ignore[assignment]
            mock_g.ncync_server.remove_tcp_device = AsyncMock()  # type: ignore[assignment]
            result = await tcp_device.write(b"test data")

            # Should return False or None when writer is closing
            assert result in [False, None]

    @pytest.mark.asyncio
    async def test_tcp_device_write_with_invalid_data_type(
        self, stream_reader: MagicMock, stream_writer: MagicMock
    ) -> None:
        """Test write raises TypeError for non-bytes data."""
        tcp_device = CyncTCPDevice(reader=stream_reader, writer=stream_writer, address="192.168.1.100")
        tcp_device.closing = False

        # Intentionally pass wrong type to test error handling
        invalid_data = cast(bytes, cast(object, "not bytes"))
        with pytest.raises(TypeError, match="Data must be bytes"):
            _ = await tcp_device.write(invalid_data)

    @pytest.mark.asyncio
    async def test_tcp_device_send_a3(self) -> None:
        """Test send_a3 creates and sends A3 packet."""
        reader = create_typed_stream_reader()
        writer = create_typed_stream_writer()
        writer.write = MagicMock()  # type: ignore[assignment]
        writer.drain = AsyncMock()  # type: ignore[assignment]
        writer.is_closing = MagicMock(return_value=False)  # type: ignore[assignment]

        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")
        tcp_device.closing = False
        tcp_device.writer = writer
        # Replace methods with mocks for testing
        tcp_device.write = AsyncMock()  # type: ignore[assignment]
        tcp_device.ask_for_mesh_info = AsyncMock()  # type: ignore[assignment]

        with patch("cync_controller.devices.asyncio.sleep", new_callable=AsyncMock):
            _ = await tcp_device.send_a3(b"\x01\x02\x03\x04\x05")

            # Should call write and set ready_to_control
            assert tcp_device.write.called  # type: ignore[reportAny]
            assert tcp_device.ready_to_control is True

    @pytest.mark.asyncio
    async def test_tcp_device_close_cancels_tasks(self) -> None:
        """Test close method cancels pending tasks."""
        reader = create_typed_stream_reader()
        reader.feed_eof = MagicMock()  # type: ignore[assignment]

        writer = create_typed_stream_writer()
        writer.close = MagicMock()  # type: ignore[assignment]
        writer.wait_closed = AsyncMock()  # type: ignore[assignment]

        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")

        # Use simple task stubs for cancellation verification
        task1 = TaskStub("task1")
        task2 = TaskStub("task2")

        # Set tasks on the Tasks object (not replace the Tasks object itself)
        tcp_device.tasks.receive = task1  # type: ignore[assignment]
        tcp_device.tasks.send = task2  # type: ignore[assignment]

        _ = await tcp_device.close()

        # Should have cancelled tasks
        assert task1.cancel_called
        assert task2.cancel_called

    @pytest.mark.asyncio
    async def test_tcp_device_close_with_no_tasks(self) -> None:
        """Test close method with empty task list."""
        reader = create_typed_stream_reader()
        reader.feed_eof = MagicMock()  # type: ignore[assignment]

        writer = create_typed_stream_writer()
        writer.close = MagicMock()  # type: ignore[assignment]
        writer.wait_closed = AsyncMock()  # type: ignore[assignment]

        tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")
        # Tasks object is already initialized with None values, so no need to set anything

        # Should not raise exception
        _ = await tcp_device.close()

    def test_tcp_device_queue_id_property(self, stream_reader: MagicMock, stream_writer: MagicMock) -> None:
        """Test TCP device queue_id property."""
        tcp_device = CyncTCPDevice(reader=stream_reader, writer=stream_writer, address="192.168.1.100")

        test_queue_id = bytes([0x01, 0x02, 0x03, 0x04])
        tcp_device.queue_id = test_queue_id

        assert tcp_device.queue_id == test_queue_id

    def test_tcp_device_messages_initialization(self, stream_reader: MagicMock, stream_writer: MagicMock) -> None:
        """Test TCP device messages object is initialized."""
        tcp_device = CyncTCPDevice(reader=stream_reader, writer=stream_writer, address="192.168.1.100")

        assert tcp_device.messages is not None
        assert hasattr(tcp_device.messages, "control")
        assert tcp_device.messages.control == {}
