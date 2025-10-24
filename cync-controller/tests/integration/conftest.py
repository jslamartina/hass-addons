"""
Shared fixtures for integration tests.

This module provides reusable fixtures for testing Cync LAN integration
with real MQTT broker and mock devices in Docker containers.
"""

import asyncio
import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import yaml
from aiomqtt import Client as MQTTClient


@pytest.fixture(scope="session")
def integration_fixtures_dir():
    """Path to integration test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def device_configs(integration_fixtures_dir):
    """
    Load device configurations from fixtures/devices.yaml.

    Returns dict with 'devices' and 'groups' lists.
    """
    devices_file = integration_fixtures_dir / "devices.yaml"
    with open(devices_file) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def test_devices(device_configs):
    """List of test device configurations."""
    return device_configs["devices"]


@pytest.fixture(scope="session")
def test_groups(device_configs):
    """List of test group configurations."""
    return device_configs["groups"]


@pytest.fixture
def test_device_1(test_devices):
    """First test device (0x1234 - Living Room Light)."""
    return test_devices[0]


@pytest.fixture
def test_device_2(test_devices):
    """Second test device (0x5678 - Bedroom Light)."""
    return test_devices[1]


@pytest.fixture
def test_group_1(test_groups):
    """First test group (0xABCD - Living Room Lights)."""
    return test_groups[0]


@pytest.fixture
def mqtt_host():
    """MQTT broker hostname."""
    return os.environ.get("MQTT_HOST", "localhost")


@pytest.fixture
def mqtt_port():
    """MQTT broker port."""
    return int(os.environ.get("MQTT_PORT", "1883"))


@pytest.fixture
def mqtt_user():
    """MQTT username."""
    return os.environ.get("MQTT_USER", "test_user")


@pytest.fixture
def mqtt_pass():
    """MQTT password."""
    return os.environ.get("MQTT_PASS", "test_pass")


@pytest.fixture
async def mqtt_client(mqtt_host, mqtt_port, mqtt_user, mqtt_pass) -> AsyncGenerator[MQTTClient]:
    """
    Create and connect to MQTT broker for testing.

    Yields connected MQTT client, automatically disconnects after test.
    """
    client = MQTTClient(hostname=mqtt_host, port=mqtt_port, username=mqtt_user, password=mqtt_pass)

    try:
        await client.__aenter__()
        yield client
    finally:
        await client.__aexit__(None, None, None)


@pytest.fixture
def cync_controller_host():
    """Cync Controller hostname."""
    return os.environ.get("CYNC_CONTROLLER_HOST", "localhost")


@pytest.fixture
def cync_controller_port():
    """Cync Controller TCP port."""
    return int(os.environ.get("CYNC_CONTROLLER_PORT", "23779"))


@pytest.fixture
def sample_control_on_packet():
    """
    Sample 0x73 control packet - turn on command.

    Returns bytes representing a control packet to turn device on.
    """
    # 0x73 packet: Control command (turn on)
    # Structure: header(1) + padding(3) + length(2) + device_id(2) + payload + checksum(2)
    return bytes.fromhex("73 00 00 00 00 1e 34 12 01 00 00 00 64 00 00 00 00 00 00 00 00 00 00 00 ab cd")


@pytest.fixture
def sample_control_off_packet():
    """
    Sample 0x73 control packet - turn off command.

    Returns bytes representing a control packet to turn device off.
    """
    return bytes.fromhex("73 00 00 00 00 1e 34 12 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 ab cd")


@pytest.fixture
def sample_mesh_info_packet():
    """
    Sample 0x83 mesh info packet.

    Returns bytes representing a mesh info response.
    """
    return bytes.fromhex(
        "83 00 00 00 00 2c 34 12 01 00 00 00 00 00 00 00 01 02 03 04 05 06 07 08 09 0a 0b 0c 0d 0e 0f ab cd"
    )


@pytest.fixture
def sample_broadcast_packet():
    """
    Sample 0x43 broadcast packet.

    Returns bytes representing a device state broadcast.
    """
    return bytes.fromhex("43 00 00 00 00 1a 34 12 01 64 00 00 ff ff 00 00 ab cd")


@pytest.fixture
async def wait_for_mqtt_message(mqtt_client):
    """
    Helper to wait for specific MQTT message.

    Returns async function that waits for message on topic with timeout.

    Example:
        wait = wait_for_mqtt_message
        message = await wait("homeassistant/light/+/config", timeout=5.0)
    """

    async def _wait(topic_filter: str, timeout: float = 5.0):
        """Wait for message matching topic filter."""
        try:
            await mqtt_client.subscribe(topic_filter)
            async with asyncio.timeout(timeout):
                async for message in mqtt_client.messages:
                    if message.topic.matches(topic_filter):
                        return message
        except TimeoutError:
            return None

    return _wait


@pytest.fixture
async def collect_mqtt_messages(mqtt_client):
    """
    Helper to collect multiple MQTT messages.

    Returns async function that collects messages for duration.

    Example:
        collect = collect_mqtt_messages
        messages = await collect("cync_lan/#", duration=2.0)
    """

    async def _collect(topic_filter: str, duration: float = 2.0):
        """Collect all messages matching topic filter for duration."""
        messages = []
        await mqtt_client.subscribe(topic_filter)

        try:
            async with asyncio.timeout(duration):
                async for message in mqtt_client.messages:
                    if message.topic.matches(topic_filter):
                        messages.append(message)
        except TimeoutError:
            pass  # Expected - we collect for duration

        return messages

    return _collect


@pytest.fixture(scope="session")
def docker_compose_file():
    """Path to docker-compose.test.yml file."""
    return Path(__file__).parent / "docker-compose.test.yml"


# Pytest markers for integration tests
def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (deselect with '-m \"not integration\"')"
    )
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    )
    config.addinivalue_line(
        "markers",
        "requires_docker: marks tests that require Docker environment",
    )
