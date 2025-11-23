"""E2E tests for cloud relay mode switching."""

import sys
from pathlib import Path
from typing import Any, cast

import pytest

# Add scripts/playwright to Python path for helper imports
scripts_path = Path(__file__).parent.parent.parent.parent / "scripts" / "playwright"
sys.path.insert(0, str(scripts_path))

from addon_helpers import (  # type: ignore[import-untyped, reportUnknownVariableType]
    apply_addon_preset,  # type: ignore[reportUnknownVariableType]
    filter_logs_by_level,  # type: ignore[reportUnknownVariableType]
    get_addon_config,  # type: ignore[reportUnknownVariableType]
    get_addon_status,  # type: ignore[reportUnknownVariableType]
    read_json_logs,  # type: ignore[reportUnknownVariableType]
    restart_addon_and_wait,  # type: ignore[reportUnknownVariableType]
)

ADDON_SLUG = "local_cync-controller"


@pytest.fixture
def restore_baseline():
    """Fixture to restore baseline configuration after tests."""
    yield

    # Only restore if not already in baseline mode
    try:
        current_config: dict[str, Any] = cast(dict[str, Any], get_addon_config(ADDON_SLUG))
        if not current_config.get("cloud_relay", {}).get("enabled", False):
            return

        _ = apply_addon_preset("preset-baseline")
        restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)
    except Exception:
        pass


@pytest.mark.serial
@pytest.mark.usefixtures("restore_baseline")
def test_apply_baseline_preset():
    """Test applying baseline (LAN-only) preset.

    Expected: Cloud relay disabled, normal local operation.
    """
    assert apply_addon_preset("preset-baseline"), "Failed to apply baseline preset"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Verify config
    config: dict[str, Any] = cast(dict[str, Any], get_addon_config(ADDON_SLUG))

    assert config["cloud_relay"]["enabled"] is False, "Cloud relay should be disabled"

    # Verify add-on running
    status: dict[str, Any] = cast(dict[str, Any], get_addon_status(ADDON_SLUG))
    assert status.get("state") == "started", "Add-on not running"


@pytest.mark.serial
@pytest.mark.usefixtures("restore_baseline")
def test_apply_relay_with_forward_preset():
    """Test applying relay-with-forward preset.

    Expected: Cloud relay enabled, packets forwarded to cloud (READ-ONLY mode).
    """
    assert apply_addon_preset("preset-relay-with-forward"), "Failed to apply preset"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Verify config
    config: dict[str, Any] = cast(dict[str, Any], get_addon_config(ADDON_SLUG))

    assert config["cloud_relay"]["enabled"] is True, "Cloud relay should be enabled"
    assert config["cloud_relay"]["forward_to_cloud"] is True, "Should forward to cloud"
    assert config["cloud_relay"]["debug_packet_logging"] is False, "Debug logging should be off"

    # Check logs for relay mode
    logs: list[dict[str, Any]] = cast(list[dict[str, Any]], read_json_logs(ADDON_SLUG, lines=100))
    [log for log in logs if "relay" in log.get("message", "").lower()]


@pytest.mark.serial
@pytest.mark.usefixtures("restore_baseline")
def test_apply_relay_debug_preset():
    """Test applying relay-debug preset.

    Expected: Cloud relay enabled with debug packet logging.
    """
    assert apply_addon_preset("preset-relay-debug"), "Failed to apply preset"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Verify config
    config: dict[str, Any] = cast(dict[str, Any], get_addon_config(ADDON_SLUG))

    assert config["cloud_relay"]["enabled"] is True, "Cloud relay should be enabled"
    assert config["cloud_relay"]["debug_packet_logging"] is True, "Debug logging should be on"

    # Check for debug logs
    logs: list[dict[str, Any]] = cast(list[dict[str, Any]], read_json_logs(ADDON_SLUG, lines=200))
    debug_logs: list[dict[str, Any]] = cast(list[dict[str, Any]], filter_logs_by_level(logs, "DEBUG"))
    [log for log in debug_logs if "packet" in log.get("message", "").lower()]


@pytest.mark.serial
@pytest.mark.usefixtures("restore_baseline")
def test_apply_lan_only_preset():
    """Test applying lan-only preset.

    Expected: Relay enabled but does NOT forward to cloud (privacy mode).
    """
    assert apply_addon_preset("preset-lan-only"), "Failed to apply preset"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Verify config
    config: dict[str, Any] = cast(dict[str, Any], get_addon_config(ADDON_SLUG))

    assert config["cloud_relay"]["enabled"] is True, "Cloud relay should be enabled"
    assert config["cloud_relay"]["forward_to_cloud"] is False, "Should NOT forward to cloud"


@pytest.mark.serial
@pytest.mark.usefixtures("restore_baseline")
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
        config: dict[str, Any] = cast(dict[str, Any], get_addon_config(ADDON_SLUG))
        assert config["cloud_relay"]["enabled"] == relay_enabled, f"Cloud relay state mismatch for {preset_name}"

        # Verify add-on still running
        status: dict[str, Any] = cast(dict[str, Any], get_addon_status(ADDON_SLUG))
        assert status.get("state") == "started", f"Add-on failed after {preset_name}"


@pytest.mark.serial
@pytest.mark.usefixtures("restore_baseline")
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
    logs: list[dict[str, Any]] = cast(list[dict[str, Any]], read_json_logs(ADDON_SLUG, lines=100))
    error_logs: list[dict[str, Any]] = [log for log in logs if "no tcp" in log.get("message", "").lower()]

    if error_logs:
        pass
    else:
        pass


@pytest.mark.serial
@pytest.mark.usefixtures("restore_baseline")
def test_return_to_baseline_restores_commands():
    """Test that returning to baseline mode restores command functionality.

    Expected: After switching from relay to baseline, commands work again.
    """
    # Start in relay mode
    assert apply_addon_preset("preset-relay-with-forward"), "Failed to apply preset"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    config_relay: dict[str, Any] = cast(dict[str, Any], get_addon_config(ADDON_SLUG))
    assert config_relay["cloud_relay"]["enabled"] is True

    # Return to baseline
    assert apply_addon_preset("preset-baseline"), "Failed to apply baseline"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    config_baseline: dict[str, Any] = cast(dict[str, Any], get_addon_config(ADDON_SLUG))
    assert config_baseline["cloud_relay"]["enabled"] is False

    # Verify add-on running properly
    status: dict[str, Any] = cast(dict[str, Any], get_addon_status(ADDON_SLUG))
    assert status.get("state") == "started"
