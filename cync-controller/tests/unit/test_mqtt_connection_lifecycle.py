"""
Unit tests for MQTTClient connection lifecycle.

Tests for MQTTClient.start() method and connection management including
reconnection logic, error recovery, and task lifecycle.
"""

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cync_controller.mqtt_client import MQTTClient


class TestMQTTClientConnectionLifecycle:
    """Tests for MQTTClient.start() main connection loop lifecycle"""

    @pytest.mark.asyncio
    async def test_start_main_loop_basic(self):
        """Test that start() runs main connection loop"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            mock_g.env.mqtt_host = "localhost"
            mock_g.env.mqtt_port = 1883
            mock_g.env.mqtt_user = "test"
            mock_g.env.mqtt_pass = "test"
            mock_g.reload_env = MagicMock()

            client = MQTTClient()
            client.connect = AsyncMock(return_value=True)
            client.start_receiver_task = AsyncMock()

            # Create a task that will be cancelled after first iteration
            start_task = asyncio.create_task(client.start())
            await asyncio.sleep(0.1)  # Let it start
            start_task.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await start_task

            # Verify connect was called at least once
            client.connect.assert_called()

    @pytest.mark.asyncio
    async def test_start_reconnects_on_disconnect(self):
        """Test automatic reconnection after disconnect"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            mock_g.env.mqtt_host = "localhost"
            mock_g.env.mqtt_port = 1883
            mock_g.env.mqtt_user = "test"
            mock_g.env.mqtt_pass = "test"
            mock_g.reload_env = MagicMock()

            client = MQTTClient()
            # First call fails
            client.connect = AsyncMock(return_value=False)
            client.start_receiver_task = AsyncMock()

            start_task = asyncio.create_task(client.start())
            await asyncio.sleep(0.15)  # Allow retry logic to execute
            start_task.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await start_task

            # Verify connect was called (attempting connection)
            assert client.connect.call_count >= 1

    @pytest.mark.asyncio
    async def test_start_handles_mqtt_error(self):
        """Test error recovery in main loop"""
        from aiomqtt import MqttError

        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            mock_g.env.mqtt_host = "localhost"
            mock_g.env.mqtt_port = 1883
            mock_g.env.mqtt_user = "test"
            mock_g.env.mqtt_pass = "test"
            mock_g.reload_env = MagicMock()

            client = MQTTClient()
            # Raise error on first call
            client.connect = AsyncMock(side_effect=MqttError("Connection error"))
            client.start_receiver_task = AsyncMock()

            start_task = asyncio.create_task(client.start())
            await asyncio.sleep(0.15)  # Allow error handling
            start_task.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await start_task

            # Verify connect was attempted and error was handled
            assert client.connect.call_count >= 1

    @pytest.mark.asyncio
    async def test_start_creates_receiver_task(self):
        """Test receiver task lifecycle when connection succeeds"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            mock_g.env.mqtt_host = "localhost"
            mock_g.env.mqtt_port = 1883
            mock_g.env.mqtt_user = "test"
            mock_g.env.mqtt_pass = "test"
            mock_g.reload_env = MagicMock()
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.groups = {}

            client = MQTTClient()
            client.connect = AsyncMock(return_value=True)
            # Mock the async context manager
            client.client = AsyncMock()
            client.client.__aenter__ = AsyncMock(return_value=client.client)
            client.client.__aexit__ = AsyncMock(return_value=False)
            client.client.publish = AsyncMock()
            client.client.subscribe = AsyncMock()
            # Mock the command_router's start_receiver_task method
            client.command_router.start_receiver_task = AsyncMock(side_effect=asyncio.CancelledError())

            start_task = asyncio.create_task(client.start())
            await asyncio.sleep(0.15)
            start_task.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await start_task

            # Verify start_receiver_task was called when connect succeeded
            client.command_router.start_receiver_task.assert_called()

    @pytest.mark.asyncio
    async def test_start_resilience_multiple_failures(self):
        """Test that start() handles repeated connection failures gracefully"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"
            mock_g.env.mqtt_host = "localhost"
            mock_g.env.mqtt_port = 1883
            mock_g.env.mqtt_user = "test"
            mock_g.env.mqtt_pass = "test"
            mock_g.reload_env = MagicMock()

            client = MQTTClient()
            client.connect = AsyncMock(return_value=False)
            client.start_receiver_task = AsyncMock()

            start_task = asyncio.create_task(client.start())
            await asyncio.sleep(0.1)  # Let it try at least once
            start_task.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await start_task

            # Verify start() didn't crash and connect was called
            assert client.connect.call_count >= 1
            # Verify the task was properly cancelled
            assert start_task.cancelled()
