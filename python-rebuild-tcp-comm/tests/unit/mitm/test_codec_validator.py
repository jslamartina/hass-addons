"""
Unit tests for codec validator plugin.

Tests the CodecValidatorPlugin stub implementation.
"""

from unittest.mock import MagicMock, patch

import pytest

from mitm.interfaces.packet_observer import PacketDirection
from mitm.validation.codec_validator import CodecValidatorPlugin


@pytest.fixture
def plugin() -> CodecValidatorPlugin:
    """Create plugin instance for testing."""
    return CodecValidatorPlugin()


def test_plugin_initialization(plugin: CodecValidatorPlugin) -> None:
    """Test plugin initialization creates empty framers dict."""
    assert hasattr(plugin, "framers")
    assert isinstance(plugin.framers, dict)
    assert len(plugin.framers) == 0


@patch("mitm.validation.codec_validator.logger")
def test_plugin_initialization_logs(mock_logger: MagicMock) -> None:
    """Test plugin logs initialization message."""
    _ = CodecValidatorPlugin()
    mock_logger.info.assert_called_once_with("CodecValidatorPlugin initialized (stub)")


@patch("mitm.validation.codec_validator.logger")
def test_on_packet_received_device_to_cloud(
    mock_logger: MagicMock, plugin: CodecValidatorPlugin
) -> None:
    """Test packet received handler logs DEVICE_TO_CLOUD packets."""
    data = b"\x73\x00\x00\x00\x1e"
    connection_id = 1

    plugin.on_packet_received(PacketDirection.DEVICE_TO_CLOUD, data, connection_id)

    # Verify logging call (skip initialization log)
    calls = [call for call in mock_logger.info.call_args_list if "Packet received" in str(call)]
    assert len(calls) == 1
    log_message = calls[0][0][0]
    assert "Packet received" in log_message
    assert "device_to_cloud" in log_message
    assert "5 bytes" in log_message
    assert "conn 1" in log_message


@patch("mitm.validation.codec_validator.logger")
def test_on_packet_received_cloud_to_device(
    mock_logger: MagicMock, plugin: CodecValidatorPlugin
) -> None:
    """Test packet received handler logs CLOUD_TO_DEVICE packets."""
    data = b"\x7b\x00\x00\x00\x0a"
    connection_id = 2

    plugin.on_packet_received(PacketDirection.CLOUD_TO_DEVICE, data, connection_id)

    # Verify logging call (skip initialization log)
    calls = [call for call in mock_logger.info.call_args_list if "Packet received" in str(call)]
    assert len(calls) == 1
    log_message = calls[0][0][0]
    assert "Packet received" in log_message
    assert "cloud_to_device" in log_message
    assert "5 bytes" in log_message
    assert "conn 2" in log_message


@patch("mitm.validation.codec_validator.logger")
def test_on_connection_established(mock_logger: MagicMock, plugin: CodecValidatorPlugin) -> None:
    """Test connection established handler logs event."""
    connection_id = 42

    plugin.on_connection_established(connection_id)

    # Verify logging call (skip initialization log)
    calls = [
        call for call in mock_logger.info.call_args_list if "Connection established" in str(call)
    ]
    assert len(calls) == 1
    log_message = calls[0][0][0]
    assert "Connection established: 42" in log_message


def test_on_connection_closed_cleans_up_framers(plugin: CodecValidatorPlugin) -> None:
    """Test connection closed handler removes framer from dict."""
    # Set up initial state with framer
    connection_id = 1
    plugin.framers[connection_id] = MagicMock()
    assert connection_id in plugin.framers

    # Close connection
    plugin.on_connection_closed(connection_id)

    # Verify framer removed
    assert connection_id not in plugin.framers


@patch("mitm.validation.codec_validator.logger")
def test_on_connection_closed_logs(mock_logger: MagicMock, plugin: CodecValidatorPlugin) -> None:
    """Test connection closed handler logs event."""
    connection_id = 42
    plugin.framers[connection_id] = MagicMock()

    plugin.on_connection_closed(connection_id)

    # Verify logging call (skip initialization log)
    calls = [call for call in mock_logger.info.call_args_list if "Connection closed" in str(call)]
    assert len(calls) == 1
    log_message = calls[0][0][0]
    assert "Connection closed: 42" in log_message


def test_on_connection_closed_nonexistent_connection(plugin: CodecValidatorPlugin) -> None:
    """Test closing nonexistent connection doesn't raise error."""
    connection_id = 999
    assert connection_id not in plugin.framers

    # Should not raise error
    plugin.on_connection_closed(connection_id)

    # Dict should still be empty
    assert connection_id not in plugin.framers


def test_plugin_implements_packet_observer_protocol(plugin: CodecValidatorPlugin) -> None:
    """Test plugin implements all PacketObserver methods."""
    assert hasattr(plugin, "on_packet_received")
    assert hasattr(plugin, "on_connection_established")
    assert hasattr(plugin, "on_connection_closed")
    assert callable(plugin.on_packet_received)
    assert callable(plugin.on_connection_established)
    assert callable(plugin.on_connection_closed)


def test_multiple_connections(plugin: CodecValidatorPlugin) -> None:
    """Test plugin handles multiple concurrent connections."""
    # Simulate multiple connections
    plugin.framers[1] = MagicMock()
    plugin.framers[2] = MagicMock()
    plugin.framers[3] = MagicMock()
    assert len(plugin.framers) == 3

    # Close connection 2
    plugin.on_connection_closed(2)
    assert len(plugin.framers) == 2
    assert 1 in plugin.framers
    assert 2 not in plugin.framers
    assert 3 in plugin.framers

    # Close remaining connections
    plugin.on_connection_closed(1)
    plugin.on_connection_closed(3)
    assert len(plugin.framers) == 0


def test_import_structure() -> None:
    """Test that module has proper import structure.

    Verifies the module can be imported and has the expected structure.
    The try/except import block is marked with pragma: no cover since it's
    defensive code for alternative execution contexts (direct script execution).
    """
    # Verify the plugin works with normal imports
    plugin = CodecValidatorPlugin()
    assert hasattr(plugin, "framers")
    assert isinstance(plugin.framers, dict)
