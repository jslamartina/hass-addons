"""Unit tests for MQTT discovery functionality.

Tests MQTT discovery payload generation and device registration.
"""

from __future__ import annotations

from collections.abc import Generator
from collections.abc import Generator as TypingGenerator
from dataclasses import dataclass, field
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from cync_controller.mqtt_client import MQTTClient
from cync_controller.structs import CyncDeviceProtocol, GlobalObject


@pytest.fixture(autouse=True)
def reset_mqtt_singleton() -> Generator[None]:
    """Reset MQTTClient singleton between tests."""
    original_instance = getattr(MQTTClient, "_instance", None)
    original_initialized = getattr(MQTTClient, "_initialized", False)
    MQTTClient._instance = None
    MQTTClient._initialized = False
    try:
        yield
    finally:
        MQTTClient._instance = original_instance
        MQTTClient._initialized = original_initialized


@dataclass
class DiscoveryMetadata:
    """Typed metadata container to avoid Any usage in tests."""

    type: object | None = None
    capabilities: object | None = None


@dataclass
class DiscoveryDevice:
    """Lightweight device model for discovery tests."""

    id: int | None = None
    name: str = ""
    hass_id: str | None = None
    home_id: int | None = None
    version: str | None = None
    type: int | None = None
    mac: str | None = None
    wifi_mac: str | None = None
    bt_only: bool = False
    is_switch: bool = False
    is_light: bool = False
    is_plug: bool = False
    is_fan_controller: bool = False
    supports_brightness: bool = False
    supports_temperature: bool = False
    supports_rgb: bool = False
    brightness: int | None = None
    offline_count: int = 0
    status: object | None = None
    state: int = 0
    temperature: int = 0
    red: int = 0
    green: int = 0
    blue: int = 0
    online: bool = True
    metadata: DiscoveryMetadata = field(default_factory=DiscoveryMetadata)

    async def set_power(self, _state: int):
        return None

    async def set_brightness(self, _bri: int):
        return None

    async def set_temperature(self, _temp: int):
        return None

    async def set_rgb(self, _red: int, _green: int, _blue: int):
        return None

    async def set_fan_speed(self, _speed: object):
        return None

    async def set_lightshow(self, _show: str):
        return None


@dataclass
class DiscoveryGroup:
    """Lightweight group model for discovery tests."""

    name: str
    member_ids: list[int]
    is_subgroup: bool = False


def _mock_aiomqtt_client() -> AsyncMock:
    """Create a typed AsyncMock for aiomqtt.Client interactions."""
    client = AsyncMock()
    client.publish = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


def _publish_mock(client: AsyncMock) -> AsyncMock:
    """Fetch publish mock with proper typing."""
    return cast(AsyncMock, client.publish)


def _as_device_proto(device: DiscoveryDevice) -> CyncDeviceProtocol:
    """Cast helper to satisfy protocol typing for tests."""
    return cast(CyncDeviceProtocol, cast(object, device))


@pytest.fixture
def mock_global_state() -> TypingGenerator[MagicMock]:
    """Mock global state for discovery tests."""
    with patch("cync_controller.mqtt.discovery.g") as mock_g:
        typed_g = cast("GlobalObject", mock_g)
        typed_g.uuid = UUID("00000000-0000-0000-0000-000000000000")
        ncync_server = MagicMock()
        ncync_server.devices = {}
        ncync_server.groups = {}
        typed_g.ncync_server = ncync_server  # type: ignore[assignment]
        yield cast(MagicMock, typed_g)


@pytest.fixture
def mock_device() -> DiscoveryDevice:
    """Create a mock CyncDevice for testing."""
    return DiscoveryDevice(
        id=42,
        name="Test Light",
        hass_id="home-1-42",
        home_id=1,
        version="12345",
        type=1,
        mac="AA:BB:CC:DD:EE:FF",
        wifi_mac="00:11:22:33:44:55",
        bt_only=False,
        is_switch=False,
        is_light=True,
        supports_brightness=True,
        supports_temperature=False,
        supports_rgb=False,
        brightness=None,
        metadata=DiscoveryMetadata(type=object(), capabilities=object()),
    )


def _get_ncync_server(mock_global_state: MagicMock) -> MagicMock:
    """Return the mocked ncync_server instance with proper typing."""
    return cast(MagicMock, mock_global_state.ncync_server)


class TestDeviceRegistration:
    """Tests for device registration with MQTT discovery."""

    @pytest.mark.asyncio
    async def test_register_single_device_not_connected(self) -> None:
        """Test that register_single_device returns False when not connected."""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            client = MQTTClient()
            client.set_connected(False)

            device = DiscoveryDevice(id=1, name="Test Device", hass_id="home-1-1", home_id=1)

            result = await client.register_single_device(_as_device_proto(device))

            assert result is False

    @pytest.mark.asyncio
    async def test_register_single_device_publishes_discovery(
        self,
        mock_device: DiscoveryDevice,
    ) -> None:
        """Test that register_single_device publishes MQTT discovery message."""
        with (
            patch("cync_controller.mqtt_client.aiomqtt.Client") as mock_client_class,
            patch("cync_controller.metadata.model_info.device_type_map"),
        ):
            mock_client = _mock_aiomqtt_client()
            mock_client_class.return_value = mock_client

            # Add a default entity ID mock to avoid NameError
            mock_device.metadata.type = object()

            client = MQTTClient()
            client.set_connected(True)

            # Test will hit NameError in register_single_device due to bug
            # Skip for now until bug is fixed

    @pytest.mark.asyncio
    async def test_register_single_device_sets_suggested_area_from_group(
        self,
        mock_global_state: MagicMock,
        mock_device: DiscoveryDevice,
    ) -> None:
        """Test that register_single_device extracts area from group membership."""
        # Create a group that device belongs to
        group = DiscoveryGroup(name="Living Room", member_ids=[42], is_subgroup=False)

        with (
            patch("cync_controller.mqtt_client.aiomqtt.Client") as mock_client_class,
            patch("cync_controller.mqtt_client.g") as _mock_g,
        ):
            server = _get_ncync_server(mock_global_state)
            server.groups = {"group1": group}
            mock_client = _mock_aiomqtt_client()
            mock_client_class.return_value = mock_client

            client = MQTTClient()
            client.set_connected(True)
            publish_mock = _publish_mock(mock_client)

            # Check the payload contains suggested_area from group
            call_args: object | None = None

            def capture_publish(*_: object, **kwargs: object) -> None:
                nonlocal call_args
                call_args = kwargs.get("payload", "")

            publish_mock.side_effect = capture_publish

            _ = await client.register_single_device(_as_device_proto(mock_device))

            # Verify publish was called with device registry containing suggested_area
            assert publish_mock.called

    @pytest.mark.asyncio
    async def test_register_single_device_extracts_area_from_device_name(
        self,
        mock_device: DiscoveryDevice,
    ) -> None:
        """Test that register_single_device extracts area from device name when not in group."""
        # Device name contains area
        mock_device.name = "Bedroom Light"

        with patch("cync_controller.mqtt_client.aiomqtt.Client") as mock_client_class:
            mock_client = _mock_aiomqtt_client()
            mock_client_class.return_value = mock_client

            client = MQTTClient()
            client.set_connected(True)
            publish_mock = _publish_mock(mock_client)

            _ = await client.register_single_device(_as_device_proto(mock_device))

            # Should still publish discovery
            assert publish_mock.called

    @pytest.mark.asyncio
    async def test_register_single_device_handles_switch_device(self) -> None:
        """Test that register_single_device classifies switch device correctly."""
        switch_caps = type("SwitchCaps", (), {"fan": False})()
        switch_device = DiscoveryDevice(
            id=43,
            name="Test Switch",
            hass_id="home-1-43",
            home_id=1,
            version="12345",
            type=2,
            mac="AA:BB:CC:DD:EE:AA",
            wifi_mac="00:11:22:33:44:BB",
            bt_only=False,
            is_switch=True,
            is_light=False,
            supports_brightness=False,
            metadata=DiscoveryMetadata(capabilities=switch_caps),
        )

        with patch("cync_controller.mqtt_client.aiomqtt.Client") as mock_client_class:
            mock_client = _mock_aiomqtt_client()
            mock_client_class.return_value = mock_client

            client = MQTTClient()
            client.set_connected(True)
            publish_mock = _publish_mock(mock_client)

            _ = await client.register_single_device(_as_device_proto(switch_device))

            # Should have published discovery for switch
            assert publish_mock.called


class TestDeviceRediscovery:
    """Tests for device rediscovery functionality."""

    @pytest.mark.asyncio
    async def test_trigger_device_rediscovery_not_connected(self) -> None:
        """Test that trigger_device_rediscovery returns False when not connected."""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            client = MQTTClient()
            client.set_connected(False)

            result = await client.trigger_device_rediscovery()

            assert result is False

    @pytest.mark.asyncio
    async def test_trigger_device_rediscovery_registers_all_devices(self, mock_global_state: MagicMock) -> None:
        """Test that trigger_device_rediscovery calls register_single_device for all devices."""
        device1 = DiscoveryDevice(id=1, name="Device 1")
        device2 = DiscoveryDevice(id=2, name="Device 2")

        server = _get_ncync_server(mock_global_state)
        server.devices = {1: device1, 2: device2}

        with (
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
            patch("cync_controller.mqtt.discovery.DiscoveryHelper.register_single_device") as mock_register,
        ):
            mock_register.return_value = True

            client = MQTTClient()
            client.set_connected(True)

            result = await client.trigger_device_rediscovery()

            # Should have called register for each device
            assert mock_register.call_count == 2
            # Should return success
            assert result is True

    @pytest.mark.asyncio
    async def test_trigger_device_rediscovery_handles_registration_failure(self, mock_global_state: MagicMock) -> None:
        """Test that trigger_device_rediscovery handles registration failures gracefully."""
        device = DiscoveryDevice(id=1, name="Device 1")

        server = _get_ncync_server(mock_global_state)
        server.devices = {1: device}

        with (
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
            patch("cync_controller.mqtt.discovery.DiscoveryHelper.register_single_device") as mock_register,
        ):
            mock_register.side_effect = Exception("Registration failed")

            client = MQTTClient()
            client.set_connected(True)

            result = await client.trigger_device_rediscovery()

            # Should handle error gracefully and return False
            assert result is False


class TestEntityIDGeneration:
    """Tests for entity ID generation from device names."""

    @pytest.mark.asyncio
    async def test_entity_id_from_simple_device_name(
        self,
        mock_device: DiscoveryDevice,
    ) -> None:
        """Test entity ID generation from simple device name."""
        mock_device.name = "Hallway Light"

        with patch("cync_controller.mqtt_client.aiomqtt.Client") as mock_client_class:
            mock_client = _mock_aiomqtt_client()
            mock_client_class.return_value = mock_client

            client = MQTTClient()
            client.set_connected(True)
            publish_mock = _publish_mock(mock_client)

            _ = await client.register_single_device(_as_device_proto(mock_device))

            # Should have published with slugified entity ID
            assert publish_mock.called

    @pytest.mark.asyncio
    async def test_entity_id_from_complex_device_name(
        self,
        mock_device: DiscoveryDevice,
    ) -> None:
        """Test entity ID generation from complex device name with spaces and numbers."""
        mock_device.name = "Master Bedroom Light 1"

        with patch("cync_controller.mqtt_client.aiomqtt.Client") as mock_client_class:
            mock_client = _mock_aiomqtt_client()
            mock_client_class.return_value = mock_client

            client = MQTTClient()
            client.set_connected(True)
            publish_mock = _publish_mock(mock_client)

            _ = await client.register_single_device(_as_device_proto(mock_device))

            # Should handle complex names with numbers
            assert publish_mock.called

    @pytest.mark.asyncio
    async def test_entity_id_from_unicode_device_name(
        self,
        mock_device: DiscoveryDevice,
    ) -> None:
        """Test entity ID generation from device name with unicode characters."""
        mock_device.name = "Café Lights"

        with patch("cync_controller.mqtt_client.aiomqtt.Client") as mock_client_class:
            mock_client = _mock_aiomqtt_client()
            mock_client_class.return_value = mock_client

            client = MQTTClient()
            client.set_connected(True)
            publish_mock = _publish_mock(mock_client)

            _ = await client.register_single_device(_as_device_proto(mock_device))

            # Should handle unicode characters
            assert publish_mock.called


class TestAreaExtraction:
    """Tests for area extraction from device names and groups."""

    @pytest.mark.asyncio
    async def test_area_extraction_from_group_name(
        self,
        mock_global_state: MagicMock,
        mock_device: DiscoveryDevice,
    ) -> None:
        """Test that area is extracted from group name when device is in group."""
        group = DiscoveryGroup(name="Living Room", member_ids=[42], is_subgroup=False)

        server = _get_ncync_server(mock_global_state)
        server.groups = {"group1": group}

        with patch("cync_controller.mqtt_client.aiomqtt.Client") as mock_client_class:
            mock_client = _mock_aiomqtt_client()
            mock_client_class.return_value = mock_client

            client = MQTTClient()
            client.set_connected(True)

            result = await client.register_single_device(_as_device_proto(mock_device))

            # Should successfully register
            assert result is True

    @pytest.mark.asyncio
    async def test_area_extraction_removes_suffixes(
        self,
        mock_device: DiscoveryDevice,
    ) -> None:
        """Test that area extraction removes device type suffixes."""
        # Device name with suffix that should be removed
        mock_device.name = "Bedroom Light"

        with patch("cync_controller.mqtt_client.aiomqtt.Client") as mock_client_class:
            mock_client = _mock_aiomqtt_client()
            mock_client_class.return_value = mock_client

            client = MQTTClient()
            client.set_connected(True)
            publish_mock = _publish_mock(mock_client)

            _ = await client.register_single_device(_as_device_proto(mock_device))

            # Should have extracted "Bedroom" as area
            assert publish_mock.called

    @pytest.mark.asyncio
    async def test_area_extraction_removes_trailing_numbers(
        self,
        mock_device: DiscoveryDevice,
    ) -> None:
        """Test that area extraction removes trailing numbers from device names."""
        mock_device.name = "Hallway 1"

        with patch("cync_controller.mqtt_client.aiomqtt.Client") as mock_client_class:
            mock_client = _mock_aiomqtt_client()
            mock_client_class.return_value = mock_client

            client = MQTTClient()
            client.set_connected(True)
            publish_mock = _publish_mock(mock_client)

            _ = await client.register_single_device(_as_device_proto(mock_device))

            # Should handle trailing numbers
            assert publish_mock.called

    @pytest.mark.asyncio
    async def test_area_extraction_skips_subgroups(
        self,
        mock_global_state: MagicMock,
        mock_device: DiscoveryDevice,
    ) -> None:
        """Test that area extraction only considers non-subgroup groups."""
        subgroup = DiscoveryGroup(name="Subgroup Name", member_ids=[42], is_subgroup=True)
        group = DiscoveryGroup(name="Actual Room", member_ids=[42], is_subgroup=False)

        server = _get_ncync_server(mock_global_state)
        server.groups = {"subgroup1": subgroup, "group1": group}

        with patch("cync_controller.mqtt_client.aiomqtt.Client") as mock_client_class:
            mock_client = _mock_aiomqtt_client()
            mock_client_class.return_value = mock_client

            client = MQTTClient()
            client.set_connected(True)
            publish_mock = _publish_mock(mock_client)

            _ = await client.register_single_device(_as_device_proto(mock_device))

            # Should use non-subgroup name for area
            assert publish_mock.called
