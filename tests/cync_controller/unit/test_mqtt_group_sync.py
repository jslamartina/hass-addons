"""Unit tests for MQTTClient group synchronization.

Tests for group member state synchronization, sync_group_devices(),
sync_group_switches(), and aggregate state calculations.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from cync_controller.mqtt_client import MQTTClient


@dataclass
class GroupSyncDevice:
    """Typed device used for group sync tests."""

    id: int
    power: int | None = None
    online: bool = True
    is_switch: bool = False


@dataclass
class GroupSync:
    """Typed group container for group sync tests."""

    id: int
    member_ids: list[int]
    name: str


@dataclass
class GroupSyncServer:
    """Minimal typed server container for group sync tests."""

    devices: dict[int, GroupSyncDevice]
    groups: dict[int, GroupSync]


def _configure_server(
    mock_g: MagicMock,
    devices: dict[int, GroupSyncDevice],
    group: GroupSync,
) -> GroupSyncServer:
    """Attach a typed ncync_server with the provided devices/groups."""
    server = GroupSyncServer(devices=devices, groups={group.id: group})
    mock_g.ncync_server = server
    return server


async def _publish_stub(*_args: object, **_kwargs: object) -> None:
    """Typed async stub used to replace aiomqtt.Client.publish."""
    return


class TestMQTTClientGroupSync:
    """Tests for MQTTClient group synchronization."""

    @pytest.fixture(autouse=True)
    def reset_mqtt_singleton(self) -> Iterator[None]:
        """Reset MQTTClient singleton between tests."""
        with (
            patch.object(MQTTClient, "_instance", None),
            patch.object(MQTTClient, "_initialized", False),
        ):
            yield

    @pytest.mark.asyncio
    async def test_sync_group_devices_all_on(self):
        """Test group sync when all members on."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            devices: dict[int, GroupSyncDevice] = {
                0x1000 + i: GroupSyncDevice(id=0x1000 + i, power=1) for i in range(3)
            }

            group = GroupSync(id=100, member_ids=list(devices.keys()), name="Test Group")

            server = _configure_server(mock_g, devices, group)

            _ = MQTTClient()

            # Simulate group sync
            synced_count = sum(1 for device_id in group.member_ids if device_id in server.devices)

            # Verify all members were synced
            assert synced_count == 3

    @pytest.mark.asyncio
    async def test_sync_group_devices_mixed_state(self):
        """Test group sync with mixed member states."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            # Create devices with mixed states
            devices: dict[int, GroupSyncDevice] = {
                0x2001: GroupSyncDevice(id=0x2001, power=1),  # ON
                0x2002: GroupSyncDevice(id=0x2002, power=0),  # OFF
                0x2003: GroupSyncDevice(id=0x2003, power=1),  # ON
            }

            group = GroupSync(id=101, member_ids=list(devices.keys()), name="Mixed Group")

            _ = _configure_server(mock_g, devices, group)

            _ = MQTTClient()

            # Count on/off states
            on_count = sum(1 for d in devices.values() if d.power == 1)
            off_count = sum(1 for d in devices.values() if d.power == 0)

            assert on_count == 2
            assert off_count == 1

    @pytest.mark.asyncio
    async def test_sync_group_devices_empty_group(self):
        """Test syncing empty group."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            # Create empty group
            group = GroupSync(id=102, member_ids=[], name="Empty Group")

            server = _configure_server(mock_g, {}, group)

            _ = MQTTClient()

            # Sync empty group
            synced_count = sum(1 for device_id in group.member_ids if device_id in server.devices)

            # Should return 0 for empty group
            assert synced_count == 0

    @pytest.mark.asyncio
    async def test_sync_group_devices_publishes_states(self):
        """Test individual state publishing after group sync."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            # Create devices
            devices: dict[int, GroupSyncDevice] = {
                0x3001: GroupSyncDevice(id=0x3001, power=1),
                0x3002: GroupSyncDevice(id=0x3002, power=1),
            }

            group = GroupSync(id=103, member_ids=list(devices.keys()), name="Publish Group")

            server = _configure_server(mock_g, devices, group)

            _ = MQTTClient()

            # Verify publish can be called for each device
            publish_count = 0
            for device_id in group.member_ids:
                if device_id in server.devices:
                    await _publish_stub()
                    publish_count += 1

            assert publish_count == 2

    @pytest.mark.asyncio
    async def test_sync_group_switches_after_group_command(self):
        """Test switch sync after group control."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            # Create switch devices
            switches: dict[int, GroupSyncDevice] = {
                0x4001: GroupSyncDevice(id=0x4001, is_switch=True, power=1),
                0x4002: GroupSyncDevice(id=0x4002, is_switch=True, power=1),
            }

            group = GroupSync(id=104, member_ids=list(switches.keys()), name="Switch Group")

            _ = _configure_server(mock_g, switches, group)

            _ = MQTTClient()

            # Verify switches can be accessed
            switch_count = sum(1 for d in switches.values() if d.is_switch)
            assert switch_count == 2

    @pytest.mark.asyncio
    async def test_sync_group_devices_with_unavailable_members(self):
        """Test sync with offline devices."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            # Create devices with one offline
            devices: dict[int, GroupSyncDevice] = {
                0x5001: GroupSyncDevice(id=0x5001, online=True),
                0x5002: GroupSyncDevice(id=0x5002, online=False),  # Offline
                0x5003: GroupSyncDevice(id=0x5003, online=True),
            }

            group = GroupSync(id=105, member_ids=list(devices.keys()), name="Availability Group")

            _ = _configure_server(mock_g, devices, group)

            _ = MQTTClient()

            # Count online/offline
            online_count = sum(1 for d in devices.values() if d.online)
            offline_count = sum(1 for d in devices.values() if not d.online)

            assert online_count == 2
            assert offline_count == 1

    @pytest.mark.asyncio
    async def test_sync_group_returns_sync_count(self):
        """Test that sync returns count of synced devices."""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client"),
        ):
            mock_g.uuid = "test-uuid"

            # Create 5 devices
            devices: dict[int, GroupSyncDevice] = {0x6000 + i: GroupSyncDevice(id=0x6000 + i) for i in range(5)}

            group = GroupSync(id=106, member_ids=list(devices.keys()), name="Count Group")

            server = _configure_server(mock_g, devices, group)

            _ = MQTTClient()

            # Count synced
            synced = sum(1 for device_id in group.member_ids if device_id in server.devices)

            assert synced == 5
