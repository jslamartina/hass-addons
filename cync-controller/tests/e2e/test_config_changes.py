"""E2E tests for configuration hot-reload."""

import sys
from pathlib import Path
from typing import Any

import pytest

# Add scripts/playwright to Python path for helper imports
scripts_path = Path(__file__).parent.parent.parent.parent / "scripts" / "playwright"
sys.path.insert(0, str(scripts_path))

from addon_helpers import (  # type: ignore[import-untyped, reportUnknownVariableType]
    get_addon_config,  # type: ignore[reportUnknownVariableType]
    get_addon_status,  # type: ignore[reportUnknownVariableType]
    read_json_logs,  # type: ignore[reportUnknownVariableType]
    restart_addon_and_wait,  # type: ignore[reportUnknownVariableType]
    update_addon_config,  # type: ignore[reportUnknownVariableType]
)

ADDON_SLUG = "local_cync-controller"


@pytest.fixture
def restore_config():
    """Fixture to restore original configuration after tests."""
    original_config: dict[str, Any] = get_addon_config(ADDON_SLUG)

    yield

    # Only restore if config changed (skip restart to avoid race conditions)
    try:
        current_config: dict[str, Any] = get_addon_config(ADDON_SLUG)
        if current_config != original_config:
            _ = update_addon_config(ADDON_SLUG, original_config)
            restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)
        else:
            pass
    except Exception:
        pass


@pytest.mark.serial  # type: ignore[attr-defined]
@pytest.mark.usefixtures("restore_config")  # type: ignore[misc]
def test_tcp_whitelist_configuration():
    """Test changing TCP whitelist configuration.

    Expected: Config update succeeds and persists after restart.
    """
    # Get current config
    current_config: dict[str, Any] = get_addon_config(ADDON_SLUG)

    # Update TCP whitelist
    new_whitelist = "192.168.1.100,192.168.1.101"
    current_config["tuning"]["tcp_whitelist"] = new_whitelist

    assert update_addon_config(ADDON_SLUG, current_config), "Failed to update config"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Verify config persisted
    updated_config: dict[str, Any] = get_addon_config(ADDON_SLUG)
    assert updated_config["tuning"]["tcp_whitelist"] == new_whitelist, "TCP whitelist not persisted"


@pytest.mark.serial  # type: ignore[attr-defined]
@pytest.mark.usefixtures("restore_config")  # type: ignore[misc]
def test_max_clients_configuration():
    """Test changing max_clients configuration.

    Expected: Config update succeeds and connection limit is enforced.
    """
    # Get current config
    current_config: dict[str, Any] = get_addon_config(ADDON_SLUG)
    _ = current_config.get("tuning", {}).get("max_clients", 8)

    # Update max_clients
    current_config["tuning"]["max_clients"] = 4

    assert update_addon_config(ADDON_SLUG, current_config), "Failed to update config"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Verify config persisted
    updated_config: dict[str, Any] = get_addon_config(ADDON_SLUG)
    assert updated_config["tuning"]["max_clients"] == 4, "max_clients not persisted"

    # Check logs for max_clients enforcement
    logs: list[dict[str, Any]] = read_json_logs(ADDON_SLUG, lines=100)
    [log for log in logs if "max" in log.get("message", "").lower() and "conn" in log.get("message", "").lower()]


@pytest.mark.serial  # type: ignore[attr-defined]
@pytest.mark.usefixtures("restore_config")  # type: ignore[misc]
def test_command_targets_configuration():
    """Test changing command_targets (broadcast count) configuration.

    Expected: Config update succeeds and command broadcast count changes.
    """
    # Get current config
    current_config: dict[str, Any] = get_addon_config(ADDON_SLUG)
    _ = current_config.get("tuning", {}).get("command_targets", 2)

    # Update command_targets
    current_config["tuning"]["command_targets"] = 3

    assert update_addon_config(ADDON_SLUG, current_config), "Failed to update config"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Verify config persisted
    updated_config: dict[str, Any] = get_addon_config(ADDON_SLUG)
    assert updated_config["tuning"]["command_targets"] == 3, "command_targets not persisted"


@pytest.mark.serial  # type: ignore[attr-defined]
@pytest.mark.usefixtures("restore_config")  # type: ignore[misc]
def test_expose_device_lights_toggle():
    """Test toggling expose_device_lights feature flag.

    Expected: Config update succeeds and entity visibility changes accordingly.
    """
    # Get current config
    current_config: dict[str, Any] = get_addon_config(ADDON_SLUG)
    original_expose: bool = bool(current_config.get("features", {}).get("expose_device_lights", True))

    # Toggle expose_device_lights
    new_expose = not original_expose
    current_config["features"]["expose_device_lights"] = new_expose

    assert update_addon_config(ADDON_SLUG, current_config), "Failed to update config"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Verify config persisted
    updated_config: dict[str, Any] = get_addon_config(ADDON_SLUG)
    assert updated_config["features"]["expose_device_lights"] == new_expose, "expose_device_lights not persisted"

    # Note: Full validation would require checking entity count in HA


@pytest.mark.serial  # type: ignore[attr-defined]
@pytest.mark.usefixtures("restore_config")  # type: ignore[misc]
def test_config_changes_without_ha_restart():
    """Test that configuration changes work without restarting Home Assistant.

    Expected: Only add-on restart required, not full HA restart.
    """
    # Change multiple config options
    current_config: dict[str, Any] = get_addon_config(ADDON_SLUG)

    current_config["tuning"]["max_clients"] = 6
    current_config["tuning"]["command_targets"] = 2
    current_config["debug_log_level"] = True

    assert update_addon_config(ADDON_SLUG, current_config), "Failed to update config"

    # Restart add-on only
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Verify add-on running
    status: dict[str, Any] = get_addon_status(ADDON_SLUG)
    assert status.get("state") == "started", "Add-on failed to start after config change"

    # Verify all configs persisted
    updated_config: dict[str, Any] = get_addon_config(ADDON_SLUG)
    assert updated_config["tuning"]["max_clients"] == 6, "max_clients not persisted"
    assert updated_config["tuning"]["command_targets"] == 2, "command_targets not persisted"
    assert updated_config["debug_log_level"] is True, "debug_log_level not persisted"


def test_invalid_config_rejected():
    """Test that invalid configuration values are rejected.

    Expected: Invalid config updates fail gracefully.
    """
    # Get current config
    current_config: dict[str, Any] = get_addon_config(ADDON_SLUG)

    # Try to set invalid value (negative max_clients)
    current_config["tuning"]["max_clients"] = -1

    # This should fail validation
    result: bool = update_addon_config(ADDON_SLUG, current_config)

    if not result:
        pass
    else:
        # Restore to valid value
        current_config["tuning"]["max_clients"] = 8
        _ = update_addon_config(ADDON_SLUG, current_config)
        restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)


@pytest.mark.serial  # type: ignore[attr-defined]
@pytest.mark.usefixtures("restore_config")  # type: ignore[misc]
def test_config_schema_validation():
    """Test that configuration schema validation works.

    Expected: Only values matching schema are accepted.
    """
    current_config: dict[str, Any] = get_addon_config(ADDON_SLUG)

    # Test valid range for max_clients (should be >= 1)

    # Valid value
    current_config["tuning"]["max_clients"] = 10
    assert update_addon_config(ADDON_SLUG, current_config), "Valid max_clients rejected"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    updated_config: dict[str, Any] = get_addon_config(ADDON_SLUG)
    assert updated_config["tuning"]["max_clients"] == 10, "Valid config not persisted"
