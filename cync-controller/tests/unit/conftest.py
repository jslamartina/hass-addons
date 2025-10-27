"""
Shared fixtures for unit tests.

This module provides reusable fixtures for testing Cync LAN components.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_tcp_device():
    """
    Mock CyncTCPDevice for testing.

    Returns a MagicMock configured with common CyncTCPDevice attributes and methods.
    """
    device = MagicMock()
    device.device_id = 0x1234
    device.address = "192.168.1.100"
    device.write_message = AsyncMock()
    device.register_callback = MagicMock()
    device.messages = MagicMock()
    device.messages.control = {}

    # Use MagicMock for reader/writer with proper sync/async methods
    device.reader = MagicMock()
    device.reader.at_eof = MagicMock(return_value=False)
    device.reader.feed_eof = MagicMock()

    device.writer = MagicMock()
    device.writer.is_closing = MagicMock(return_value=False)
    device.writer.close = MagicMock()
    device.writer.wait_closed = AsyncMock()
    device.writer.drain = AsyncMock()
    device.writer.write = MagicMock()

    return device


@pytest.fixture
def mock_mqtt_client():
    """
    Mock MQTT client for testing.

    Returns an AsyncMock configured with common MQTT client methods.
    """
    client = AsyncMock()
    client.publish = AsyncMock()
    client.subscribe = AsyncMock()
    client.connect = AsyncMock(return_value=True)
    client.disconnect = AsyncMock()
    client._connected = True
    return client


@pytest.fixture
def sample_control_packet():
    """
    Sample 0x73 control packet for testing.

    This is a representative control packet (turn on command).
    """
    # 0x73 packet: Control command
    # Structure: header(1) + padding(3) + length(4) + device_id(2) + payload + checksum(2)
    return bytes.fromhex("73 00 00 00 1e 00 00 00 6e fc b9 57 0f 01 00 00 00 64 00 00 00 00 00 00 00 00 00 ab cd")


@pytest.fixture
def sample_mesh_info_packet():
    """
    Sample 0x83 mesh info packet for testing.

    This is a representative mesh info response packet.
    """
    # 0x83 packet: Mesh info response
    # Structure: header(1) + padding(3) + length(4) + device_id(2) + mesh data + checksum(2)
    return bytes.fromhex(
        "83 00 00 00 2c 00 00 00 6e fc b9 57 0f 01 00 00 00 "
        "00 00 00 00 01 02 03 04 05 06 07 08 09 0a 0b 0c 0d 0e 0f "
        "ab cd"
    )


@pytest.fixture
def sample_broadcast_packet():
    """
    Sample 0x43 broadcast packet for testing.

    This is a representative broadcast state update packet.
    """
    # 0x43 packet: Broadcast state update
    # Structure: header(1) + padding(3) + length(4) + device_id(2) + state data + checksum(2)
    return bytes.fromhex("43 00 00 00 1a 00 00 00 6e fc b9 57 0f 01 64 00 00 00 ff ff 00 00 ab cd")


@pytest.fixture
def sample_device_data():
    """
    Sample device configuration data for testing.

    Returns a dictionary with typical device configuration.
    """
    return {
        "device_id": 0x1234,
        "name": "Test Light",
        "room": "Living Room",
        "model": "SMART_SWITCH",
        "capabilities": ["on_off", "brightness"],
        "home": 12345,
        "mesh_id": 1,
    }


@pytest.fixture
def sample_group_data():
    """
    Sample group configuration data for testing.

    Returns a dictionary with typical group configuration.
    """
    return {
        "group_id": 0x5678,
        "name": "Living Room Lights",
        "room": "Living Room",
        "device_ids": [0x1234, 0x5678, 0x9ABC],
        "home": 12345,
    }


@pytest.fixture
def mock_device():
    """
    Mock CyncDevice for testing.

    Returns a MagicMock configured with common CyncDevice attributes.
    """
    device = MagicMock()
    device.device_id = 0x1234
    device.name = "Test Light"
    device.room = "Living Room"
    device.model = "SMART_SWITCH"
    device.power_on = False
    device.brightness = 0
    device.color_temp = 0
    device.online = True
    device.offline_count = 0
    device.pending_command = False
    device.ready_to_control = True
    device.tcp_device = AsyncMock()
    device.tcp_device.register_callback = MagicMock()
    device.set_power = AsyncMock()
    device.set_brightness = AsyncMock()
    device.handle_offline_report = MagicMock()
    device.handle_online_report = MagicMock()
    return device


@pytest.fixture
def mock_group():
    """
    Mock CyncGroup for testing.

    Returns a MagicMock configured with common CyncGroup attributes.
    """
    group = MagicMock()
    group.group_id = 0x5678
    group.name = "Living Room Lights"
    group.room = "Living Room"
    group.power_on = False
    group.brightness = 0
    group.devices = []
    group.tcp_device = AsyncMock()
    group.tcp_device.register_callback = MagicMock()
    group.set_power = AsyncMock()
    group.set_brightness = AsyncMock()
    return group


@pytest.fixture
def mock_global_object():
    """
    Mock GlobalObject for testing.

    Returns a MagicMock configured with common GlobalObject attributes.
    """
    g = MagicMock()
    g.devices = {}
    g.groups = {}
    g.tcp_devices = {}
    g.mqtt_client = AsyncMock()
    g.uuid = "test-uuid-1234"
    return g


@pytest.fixture
def stream_reader():
    """Mock asyncio.StreamReader with proper sync/async methods.

    Returns a MagicMock configured for StreamReader where:
    - Sync methods (at_eof, feed_eof) are MagicMock
    - Async methods (read, readexactly) are AsyncMock
    """
    reader = MagicMock()
    reader.at_eof = MagicMock(return_value=False)
    reader.feed_eof = MagicMock()
    reader.read = AsyncMock()
    reader.readexactly = AsyncMock()
    return reader


@pytest.fixture
def stream_writer():
    """Mock asyncio.StreamWriter with proper sync/async methods.

    Returns a MagicMock configured for StreamWriter where:
    - Sync methods (is_closing, close, write, get_extra_info) are MagicMock
    - Async methods (drain, wait_closed) are AsyncMock
    """
    writer = MagicMock()
    writer.is_closing = MagicMock(return_value=False)
    writer.close = MagicMock()
    writer.write = MagicMock()
    writer.get_extra_info = MagicMock(return_value=("192.168.1.100", 50001))
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    return writer


@pytest.fixture
def real_tcp_device():
    """Create a real CyncTCPDevice instance for testing"""
    from cync_controller.devices import CyncTCPDevice

    # Create reader and writer with proper sync/async methods
    reader = MagicMock()
    reader.at_eof = MagicMock(return_value=False)
    reader.feed_eof = MagicMock()

    writer = MagicMock()
    writer.is_closing = MagicMock(return_value=False)
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    writer.drain = AsyncMock()
    writer.write = MagicMock()

    # Initialize queue_id after creation
    tcp_device = CyncTCPDevice(reader=reader, writer=writer, address="192.168.1.100")
    tcp_device.queue_id = bytes([0x00, 0x00, 0x00])
    return tcp_device
