"""Unit tests for MQTT command routing helpers."""

from __future__ import annotations

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from _pytest.logging import LogCaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from cync_controller.mqtt import command_routing
from cync_controller.mqtt.command_routing import CommandRouter, CommandTasks
from cync_controller.structs import CyncDeviceProtocol, CyncGroupProtocol, FanSpeed, GlobalObject


@pytest.fixture
def mock_ncync_server(monkeypatch: MonkeyPatch) -> MagicMock:
    """Patch command_routing.g with a mock GlobalObject."""
    server = MagicMock()
    server.devices = {}
    server.groups = {}

    mock_g = MagicMock(spec=GlobalObject)
    mock_g.ncync_server = server
    monkeypatch.setattr(command_routing, "g", mock_g)  # type: ignore[call-overload]
    return server


class CommandRouterTestHarness(CommandRouter):
    """Expose protected helpers for targeted unit tests."""

    def parse_topic(self, topic_parts: list[str], lp: str):
        return self._parse_topic_and_get_target(topic_parts, lp)

    async def fan_percentage(
        self,
        percentage: int,
        device: CyncDeviceProtocol,
        lp: str,
        tasks: CommandTasks,
    ) -> None:
        await self._handle_fan_percentage(percentage, device, lp, tasks)

    async def fan_preset(
        self,
        preset: str,
        device: CyncDeviceProtocol,
        lp: str,
        tasks: CommandTasks,
    ) -> None:
        await self._handle_fan_preset(preset, device, lp, tasks)

    async def extra_data(
        self,
        extra_data: list[str],
        payload: bytes,
        device: CyncDeviceProtocol | None,
        lp: str,
        tasks: CommandTasks,
    ) -> None:
        await self._handle_extra_data(extra_data, payload, device, lp, tasks)


@pytest.fixture
def router(_mock_ncync_server: MagicMock) -> CommandRouterTestHarness:
    """Create a CommandRouter with a minimal MQTT client stub."""
    _ = _mock_ncync_server

    def _passthrough(value: int) -> int:
        return value

    mqtt_client = MagicMock()
    mqtt_client.lp = "test:"
    mqtt_client.kelvin2cync = MagicMock(side_effect=_passthrough)
    mqtt_client.trigger_status_refresh = AsyncMock()
    return CommandRouterTestHarness(mqtt_client)


def _make_device(is_fan: bool = False) -> CyncDeviceProtocol:
    device = cast(CyncDeviceProtocol, MagicMock(spec=CyncDeviceProtocol))
    device.name = "Device"
    device.id = 10
    device.is_fan_controller = is_fan
    device.set_brightness = AsyncMock()
    device.set_fan_speed = AsyncMock()
    return device


def _make_group() -> CyncGroupProtocol:
    group = cast(CyncGroupProtocol, MagicMock(spec=CyncGroupProtocol))
    group.name = "Group"
    group.id = 1
    return group


def test_parse_topic_returns_device(router: CommandRouterTestHarness, mock_ncync_server: MagicMock) -> None:
    """Device topics should resolve to a device target."""
    device = _make_device()
    mock_ncync_server.devices = {10: device}

    result_device, result_group, target_type = router.parse_topic(
        ["cync", "set", "cync-10"],
        "lp:",
    )

    assert result_device is device
    assert result_group is None
    assert target_type == "DEVICE"


def test_parse_topic_returns_group(router: CommandRouterTestHarness, mock_ncync_server: MagicMock) -> None:
    """Group topics should resolve to a group target."""
    group = _make_group()
    mock_ncync_server.groups = {1: group}

    device, result_group, target_type = router.parse_topic(
        ["cync", "set", "cync-group-1"],
        "lp:",
    )

    assert device is None
    assert result_group is group
    assert target_type == "GROUP"


def test_parse_topic_unknown_group(router: CommandRouterTestHarness, mock_ncync_server: MagicMock) -> None:
    """Missing groups should result in UNKNOWN targets."""
    mock_ncync_server.groups = {}

    device, group, target_type = router.parse_topic(
        ["cync", "set", "cync-group-99"],
        "lp:",
    )

    assert device is None
    assert group is None
    assert target_type == "UNKNOWN"


@pytest.mark.asyncio
async def test_handle_fan_percentage_maps_expected_value(router: CommandRouterTestHarness) -> None:
    """Fan percentage should map to brightness values."""
    device = _make_device(is_fan=True)
    tasks: CommandTasks = []

    await router.fan_percentage(62, device, "lp:", tasks)
    results: list[object] = await asyncio.gather(*tasks)
    assert results is not None

    cast(AsyncMock, device.set_brightness).assert_awaited_once_with(75)


@pytest.mark.asyncio
async def test_handle_fan_preset_sets_speed(router: CommandRouterTestHarness) -> None:
    """Fan preset should enqueue set_fan_speed with the mapped FanSpeed."""
    device = _make_device(is_fan=True)
    tasks: CommandTasks = []

    await router.fan_preset("high", device, "lp:", tasks)
    results: list[object] = await asyncio.gather(*tasks)
    assert results is not None

    cast(AsyncMock, device.set_fan_speed).assert_awaited_once_with(FanSpeed.HIGH)


@pytest.mark.asyncio
async def test_handle_extra_data_warns_on_non_fan(router: CommandRouterTestHarness, caplog: LogCaptureFixture) -> None:
    """Fan commands against non-fan devices should warn."""
    device = _make_device(is_fan=False)
    tasks: CommandTasks = []

    await router.extra_data(["percentage"], b"50", device, "lp:", tasks)

    assert "non-fan device" in caplog.text
    assert tasks == []


@pytest.mark.asyncio
async def test_handle_extra_data_for_fan_percentage(router: CommandRouterTestHarness) -> None:
    """Fan commands for fan devices should schedule work."""
    device = _make_device(is_fan=True)
    tasks: CommandTasks = []

    await router.extra_data(["percentage"], b"25", device, "lp:", tasks)
    assert tasks, "Expected tasks to be scheduled for fan percentage command"
    results: list[object] = await asyncio.gather(*tasks)
    assert results is not None
    cast(AsyncMock, device.set_brightness).assert_awaited_once_with(25)
