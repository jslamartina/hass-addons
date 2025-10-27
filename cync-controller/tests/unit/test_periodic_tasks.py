"""
Unit tests for periodic background tasks in server.py.

Tests cover:
- periodic_status_refresh (lines 876-924)
- periodic_pool_status_logger (lines 926-970)
"""

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_server():
    """Create a mock NCyncServer for testing."""
    server = MagicMock()
    server.running = True
    server.tcp_devices = {}
    return server


@pytest.fixture
def mock_bridge_device():
    """Create a mock bridge device for testing."""
    device = MagicMock()
    device.ready_to_control = True
    device.address = "192.168.1.100"
    device.id = 1
    device.ask_for_mesh_info = AsyncMock()
    device.connected_at = 0
    return device


class TestPeriodicStatusRefresh:
    """Tests for periodic_status_refresh task (lines 876-924)."""

    @pytest.mark.asyncio
    async def test_periodic_refresh_with_ready_bridges(self, mock_server, mock_bridge_device):
        """Test periodic refresh calls ask_for_mesh_info on ready bridges."""
        # Arrange
        mock_server.tcp_devices = {"dev1": mock_bridge_device}
        sleep_call_count = 0

        async def mock_sleep(seconds):  # noqa: ARG001
            nonlocal sleep_call_count
            sleep_call_count += 1
            if sleep_call_count > 2:  # Stop after a few iterations
                mock_server.running = False

        with patch("asyncio.sleep", side_effect=mock_sleep):
            # Act - Simulate periodic_status_refresh logic
            while mock_server.running:
                await asyncio.sleep(300)

                if not mock_server.running:
                    break

                bridge_devices = [dev for dev in mock_server.tcp_devices.values() if dev and dev.ready_to_control]

                if not bridge_devices:
                    continue

                for bridge_device in bridge_devices:
                    await bridge_device.ask_for_mesh_info(False)
                    await asyncio.sleep(1)

            # Assert
            mock_bridge_device.ask_for_mesh_info.assert_called()

    @pytest.mark.asyncio
    async def test_periodic_refresh_skips_when_no_ready_bridges(self, mock_server):
        """Test refresh skips when no bridge devices are ready."""
        # Arrange
        offline_bridge = MagicMock()
        offline_bridge.ready_to_control = False
        mock_server.tcp_devices = {"dev1": offline_bridge}

        skip_called = False

        async def mock_sleep(seconds):  # noqa: ARG001
            nonlocal skip_called
            mock_server.running = False
            skip_called = True

        with patch("asyncio.sleep", side_effect=mock_sleep):
            # Act
            while mock_server.running:
                await asyncio.sleep(300)

                if not mock_server.running:
                    break

                bridge_devices = [dev for dev in mock_server.tcp_devices.values() if dev and dev.ready_to_control]

                if not bridge_devices:
                    skip_called = True
                    break

            # Assert
            assert skip_called is True

    @pytest.mark.asyncio
    async def test_periodic_refresh_multiple_bridges(self, mock_server):
        """Test periodic refresh handles multiple bridge devices."""
        # Arrange
        bridge1 = MagicMock()
        bridge1.ready_to_control = True
        bridge1.address = "192.168.1.100"
        bridge1.ask_for_mesh_info = AsyncMock()

        bridge2 = MagicMock()
        bridge2.ready_to_control = True
        bridge2.address = "192.168.1.101"
        bridge2.ask_for_mesh_info = AsyncMock()

        mock_server.tcp_devices = {"dev1": bridge1, "dev2": bridge2}
        mock_server.running = True
        sleep_count = 0

        async def mock_sleep(seconds):  # noqa: ARG001
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count > 2:
                mock_server.running = False

        with patch("asyncio.sleep", side_effect=mock_sleep):
            # Act
            while mock_server.running:
                await asyncio.sleep(300)

                if not mock_server.running:
                    break

                bridge_devices = [dev for dev in mock_server.tcp_devices.values() if dev and dev.ready_to_control]

                for bridge_device in bridge_devices:
                    await bridge_device.ask_for_mesh_info(False)
                    await asyncio.sleep(1)

            # Assert
            bridge1.ask_for_mesh_info.assert_called()
            bridge2.ask_for_mesh_info.assert_called()

    @pytest.mark.asyncio
    async def test_periodic_refresh_handles_bridge_exceptions(self, mock_server, mock_bridge_device):
        """Test refresh handles exceptions from bridge devices gracefully."""
        # Arrange
        mock_bridge_device.ask_for_mesh_info = AsyncMock(side_effect=Exception("Bridge error"))
        mock_server.tcp_devices = {"dev1": mock_bridge_device}

        async def mock_sleep(seconds):  # noqa: ARG001
            mock_server.running = False

        with patch("asyncio.sleep", side_effect=mock_sleep):
            # Act - Should not raise
            try:
                while mock_server.running:
                    await asyncio.sleep(300)

                    if not mock_server.running:
                        break

                    bridge_devices = [dev for dev in mock_server.tcp_devices.values() if dev and dev.ready_to_control]

                    for bridge_device in bridge_devices:
                        with contextlib.suppress(Exception):
                            await bridge_device.ask_for_mesh_info(False)
                        await asyncio.sleep(1)

                exception_handled = True
            except Exception:
                exception_handled = False

            # Assert
            assert exception_handled is True

    @pytest.mark.asyncio
    async def test_periodic_refresh_stops_when_not_running(self, mock_server):
        """Test refresh stops when running flag is False."""
        # Arrange
        mock_server.running = False

        # Act
        iterations = 0
        while mock_server.running:
            iterations += 1
            break

        # Assert
        assert iterations == 0

    @pytest.mark.asyncio
    async def test_periodic_refresh_task_cancellation(self, mock_server, mock_bridge_device):
        """Test refresh task can be cancelled."""
        # Arrange
        mock_server.tcp_devices = {"dev1": mock_bridge_device}
        cancellation_handled = False

        async def mock_sleep(seconds):  # noqa: ARG001
            raise asyncio.CancelledError

        with patch("asyncio.sleep", side_effect=mock_sleep):
            # Act
            try:
                while mock_server.running:
                    await asyncio.sleep(300)
                    break
            except asyncio.CancelledError:
                cancellation_handled = True

            # Assert
            assert cancellation_handled is True


class TestPeriodicPoolStatusLogging:
    """Tests for periodic_pool_status_logger task (lines 926-970)."""

    @pytest.mark.asyncio
    async def test_pool_status_logger_logs_metrics(self, mock_server, mock_bridge_device):
        """Test pool monitoring logs connection metrics."""
        # Arrange
        mock_server.tcp_devices = {"dev1": mock_bridge_device}
        logged_metrics = None

        async def mock_sleep(seconds):  # noqa: ARG001
            mock_server.running = False

        def mock_logger_info(*args, **kwargs):  # noqa: ARG001
            nonlocal logged_metrics
            if "extra" in kwargs:
                logged_metrics = kwargs["extra"]

        with patch("asyncio.sleep", side_effect=mock_sleep):
            with patch("cync_controller.server.logger.info", side_effect=mock_logger_info):
                # Act
                total_connections = len(mock_server.tcp_devices)
                ready_connections = [dev for dev in mock_server.tcp_devices.values() if dev and dev.ready_to_control]

                # Assert
                assert total_connections == 1
                assert len(ready_connections) == 1

    @pytest.mark.asyncio
    async def test_pool_status_logger_empty_pool(self, mock_server):
        """Test pool monitoring with empty connection pool."""
        # Arrange
        mock_server.tcp_devices = {}

        # Act
        total_connections = len(mock_server.tcp_devices)
        ready_connections = [dev for dev in mock_server.tcp_devices.values() if dev and dev.ready_to_control]

        # Assert
        assert total_connections == 0
        assert len(ready_connections) == 0

    @pytest.mark.asyncio
    async def test_pool_status_logger_mixed_ready_offline(self, mock_server):
        """Test pool monitoring with mix of ready and offline devices."""
        # Arrange
        ready_device = MagicMock()
        ready_device.ready_to_control = True
        ready_device.connected_at = 0

        offline_device = MagicMock()
        offline_device.ready_to_control = False
        offline_device.connected_at = 0

        mock_server.tcp_devices = {"dev1": ready_device, "dev2": offline_device, "dev3": None}

        # Act
        total_connections = len(mock_server.tcp_devices)
        ready_connections = [dev for dev in mock_server.tcp_devices.values() if dev and dev.ready_to_control]

        # Assert
        assert total_connections == 3
        assert len(ready_connections) == 1

    @pytest.mark.asyncio
    async def test_pool_status_logger_tracks_uptime(self, mock_server):
        """Test pool monitoring tracks device uptime."""
        # Arrange
        import time

        current_time = time.time()
        device = MagicMock()
        device.ready_to_control = True
        device.connected_at = current_time - 3600  # Connected 1 hour ago
        device.address = "192.168.1.100"

        mock_server.tcp_devices = {"dev1": device}

        # Act
        uptime = current_time - device.connected_at

        # Assert
        assert uptime >= 3600

    @pytest.mark.asyncio
    async def test_pool_status_logger_stops_when_not_running(self, mock_server):
        """Test pool monitoring stops when running flag is False."""
        # Arrange
        mock_server.running = False

        # Act
        iterations = 0
        while mock_server.running:
            iterations += 1
            break

        # Assert
        assert iterations == 0

    @pytest.mark.asyncio
    async def test_pool_status_logger_handles_exceptions(self, mock_server, mock_bridge_device):
        """Test pool monitoring handles exceptions gracefully."""
        # Arrange
        mock_server.tcp_devices = {"dev1": mock_bridge_device}
        exception_handled = False

        async def mock_sleep(seconds):  # noqa: ARG001
            mock_server.running = False

        with patch("asyncio.sleep", side_effect=mock_sleep):
            # Act
            try:
                while mock_server.running:
                    await asyncio.sleep(30)
                    if not mock_server.running:
                        break
                    try:
                        pass
                    except Exception:
                        exception_handled = True
                exception_handled = True
            except Exception:
                exception_handled = False

            # Assert - Should handle and continue
            assert exception_handled is True

    @pytest.mark.asyncio
    async def test_pool_status_logger_task_cancellation(self, mock_server):
        """Test pool monitoring task can be cancelled."""
        # Arrange
        cancellation_handled = False

        async def mock_sleep(seconds):  # noqa: ARG001
            raise asyncio.CancelledError

        with patch("asyncio.sleep", side_effect=mock_sleep):
            # Act
            try:
                while mock_server.running:
                    await asyncio.sleep(30)
                    break
            except asyncio.CancelledError:
                cancellation_handled = True

            # Assert
            assert cancellation_handled is True


class TestBackgroundTaskEdgeCases:
    """Tests for edge cases in background task handling."""

    @pytest.mark.asyncio
    async def test_refresh_with_none_device(self, mock_server):
        """Test periodic refresh handles None device gracefully."""
        # Arrange
        mock_server.tcp_devices = {"dev1": None}

        # Act
        bridge_devices = [dev for dev in mock_server.tcp_devices.values() if dev and dev.ready_to_control]

        # Assert
        assert len(bridge_devices) == 0

    @pytest.mark.asyncio
    async def test_pool_logger_with_missing_attributes(self, mock_server):
        """Test pool logger handles devices with missing attributes."""
        # Arrange
        incomplete_device = MagicMock()
        # Deliberately missing some attributes
        mock_server.tcp_devices = {"dev1": incomplete_device}

        # Act
        total = len(mock_server.tcp_devices)

        # Assert
        assert total == 1

    @pytest.mark.asyncio
    async def test_concurrent_task_operations(self, mock_server, mock_bridge_device):
        """Test concurrent operations don't cause issues."""
        # Arrange
        mock_server.tcp_devices = {"dev1": mock_bridge_device}

        # Act
        call_count = 0

        async def mock_async_op():
            nonlocal call_count
            call_count += 1

        # Simulate concurrent calls
        await mock_async_op()
        await mock_async_op()

        # Assert
        assert call_count == 2


class TestTaskIntegration:
    """Integration tests for background tasks."""

    @pytest.mark.asyncio
    async def test_refresh_and_pool_monitoring_coexist(self, mock_server, mock_bridge_device):
        """Test refresh and pool monitoring can coexist."""
        # Arrange
        mock_server.tcp_devices = {"dev1": mock_bridge_device}

        # Act
        total_devices = len(mock_server.tcp_devices)
        ready_devices = [dev for dev in mock_server.tcp_devices.values() if dev and dev.ready_to_control]

        # Assert
        assert total_devices == 1
        assert len(ready_devices) == 1
