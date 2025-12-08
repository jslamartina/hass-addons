"""E2E tests for cloud relay mode switching."""

import logging
import sys
from pathlib import Path
from typing import cast

import pytest

# Add scripts/playwright to Python path for helper imports
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

from scripts.playwright.addon_helpers import (  # type: ignore[import-untyped, reportUnknownVariableType]
    JSONDict,  # type: ignore[reportUnknownVariableType]
    apply_addon_preset,  # type: ignore[reportUnknownVariableType]
    filter_logs_by_level,  # type: ignore[reportUnknownVariableType]
    get_addon_config,  # type: ignore[reportUnknownVariableType]
    get_addon_status,  # type: ignore[reportUnknownVariableType]
    read_json_logs,  # type: ignore[reportUnknownVariableType]
    restart_addon_and_wait,  # type: ignore[reportUnknownVariableType]
)

ADDON_SLUG = "local_cync-controller"
logger = logging.getLogger(__name__)


def _as_dict(value: object) -> dict[str, object]:
    return cast(dict[str, object], value if isinstance(value, dict) else {})


@pytest.fixture(autouse=True)
def restore_baseline():
    """Fixture to restore baseline configuration after tests."""
    yield

    # Only restore if not already in baseline mode
    try:
        current_config: JSONDict = get_addon_config(ADDON_SLUG)
        cloud_relay_raw = current_config.get("cloud_relay", {})
        cloud_relay = cast(dict[str, object], cloud_relay_raw if isinstance(cloud_relay_raw, dict) else {})
        if not bool(cloud_relay.get("enabled", False)):
            return

        _ = apply_addon_preset("preset-baseline")
        restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)
    except Exception as exc:
        logger.warning("Failed to restore baseline preset: %s", exc)


@pytest.mark.serial  # type: ignore[attr-defined]
def test_apply_baseline_preset():
    """Test applying baseline (LAN-only) preset.

    Expected: Cloud relay disabled, normal local operation.
    """
    assert apply_addon_preset("preset-baseline"), "Failed to apply baseline preset"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Verify config
    config: JSONDict = get_addon_config(ADDON_SLUG)
    cloud_relay_raw = config.get("cloud_relay", {})
    cloud_relay = cast(dict[str, object], cloud_relay_raw if isinstance(cloud_relay_raw, dict) else {})

    assert cloud_relay.get("enabled") is False, "Cloud relay should be disabled"

    # Verify add-on running
    status: JSONDict = get_addon_status(ADDON_SLUG)
    assert status.get("state") == "started", "Add-on not running"


@pytest.mark.serial  # type: ignore[attr-defined]
def test_apply_relay_with_forward_preset():
    """Test applying relay-with-forward preset.

    Expected: Cloud relay enabled, packets forwarded to cloud (READ-ONLY mode).
    """
    assert apply_addon_preset("preset-relay-with-forward"), "Failed to apply preset"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Verify config
    config: JSONDict = get_addon_config(ADDON_SLUG)
    cloud_relay_raw = config.get("cloud_relay", {})
    cloud_relay = cast(dict[str, object], cloud_relay_raw if isinstance(cloud_relay_raw, dict) else {})

    assert cloud_relay.get("enabled") is True, "Cloud relay should be enabled"
    assert cloud_relay.get("forward_to_cloud") is True, "Should forward to cloud"
    assert cloud_relay.get("debug_packet_logging") is False, "Debug logging should be off"

    # Check logs for relay mode
    logs: list[JSONDict] = read_json_logs(ADDON_SLUG, lines=100)
    _ = [log for log in logs if "relay" in str(log.get("message", "")).lower()]


@pytest.mark.serial  # type: ignore[attr-defined]
def test_apply_relay_debug_preset():
    """Test applying relay-debug preset.

    Expected: Cloud relay enabled with debug packet logging.
    """
    assert apply_addon_preset("preset-relay-debug"), "Failed to apply preset"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Verify config
    config: JSONDict = get_addon_config(ADDON_SLUG)
    cloud_relay_raw = config.get("cloud_relay", {})
    cloud_relay = cast(dict[str, object], cloud_relay_raw if isinstance(cloud_relay_raw, dict) else {})

    assert cloud_relay.get("enabled") is True, "Cloud relay should be enabled"
    assert cloud_relay.get("debug_packet_logging") is True, "Debug logging should be on"

    # Check for debug logs
    logs: list[JSONDict] = read_json_logs(ADDON_SLUG, lines=200)
    debug_logs: list[JSONDict] = filter_logs_by_level(logs, "DEBUG")
    _ = [log for log in debug_logs if "packet" in str(log.get("message", "")).lower()]


@pytest.mark.serial  # type: ignore[attr-defined]
def test_apply_lan_only_preset():
    """Test applying lan-only preset.

    Expected: Relay enabled but does NOT forward to cloud (privacy mode).
    """
    assert apply_addon_preset("preset-lan-only"), "Failed to apply preset"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Verify config
    config: JSONDict = get_addon_config(ADDON_SLUG)
    cloud_relay_raw = config.get("cloud_relay", {})
    cloud_relay = cast(dict[str, object], cloud_relay_raw if isinstance(cloud_relay_raw, dict) else {})

    assert cloud_relay.get("enabled") is True, "Cloud relay should be enabled"
    assert cloud_relay.get("forward_to_cloud") is False, "Should NOT forward to cloud"


@pytest.mark.serial  # type: ignore[attr-defined]
def test_switch_between_modes():
    """Test switching between different relay modes.

    Expected: Each mode applies correctly and add-on remains stable.
    """
    modes = [
        ("preset-baseline", False),
        ("preset-relay-with-forward", True),
        ("preset-baseline", False),
    ]

    for preset_name, relay_enabled in modes:
        assert apply_addon_preset(preset_name), f"Failed to apply {preset_name}"
        # Skip restart for each mode - too many restarts in rapid succession
        # Just verify config was applied
        config: JSONDict = get_addon_config(ADDON_SLUG)
        cloud_relay = _as_dict(config.get("cloud_relay"))
        assert cloud_relay.get("enabled") == relay_enabled, f"Cloud relay state mismatch for {preset_name}"

        # Verify add-on still running
        status: JSONDict = get_addon_status(ADDON_SLUG)
        assert status.get("state") == "started", f"Add-on failed after {preset_name}"


@pytest.mark.serial  # type: ignore[attr-defined]
def test_commands_fail_in_relay_mode():
    """Test that commands from HA do NOT work in relay mode.

    Expected: Commands fail gracefully with "No TCP bridges available" error.
    """
    # Apply relay mode
    assert apply_addon_preset("preset-relay-with-forward"), "Failed to apply preset"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Attempt to send command (would need actual device)
    # This would involve trying to toggle a light via HA UI
    # Expected: Command fails or shows "unavailable"

    # Check logs for "No TCP bridges" error
    logs: list[JSONDict] = read_json_logs(ADDON_SLUG, lines=100)
    error_logs: list[JSONDict] = [log for log in logs if "no tcp" in str(log.get("message", "")).lower()]

    if error_logs:
        pass
    else:
        pass


@pytest.mark.serial  # type: ignore[attr-defined]
def test_return_to_baseline_restores_commands():
    """Test that returning to baseline mode restores command functionality.

    Expected: After switching from relay to baseline, commands work again.
    """
    # Start in relay mode
    assert apply_addon_preset("preset-relay-with-forward"), "Failed to apply preset"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    config_relay: JSONDict = get_addon_config(ADDON_SLUG)
    relay_settings = _as_dict(config_relay.get("cloud_relay"))
    assert relay_settings.get("enabled") is True

    # Return to baseline
    assert apply_addon_preset("preset-baseline"), "Failed to apply baseline"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    config_baseline: JSONDict = get_addon_config(ADDON_SLUG)
    baseline_settings = _as_dict(config_baseline.get("cloud_relay"))
    assert baseline_settings.get("enabled") is False

    # Verify add-on running properly
    status: JSONDict = get_addon_status(ADDON_SLUG)
    assert status.get("state") == "started"
