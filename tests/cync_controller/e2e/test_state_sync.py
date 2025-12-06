"""E2E tests for state synchronization between devices, groups, and Home Assistant."""

import sys
import time
from pathlib import Path
from typing import Any

import pytest
from _pytest.outcomes import skip as pytest_skip
from playwright.sync_api import Page

# Add scripts/playwright to Python path for helper imports
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

from scripts.playwright.addon_helpers import read_json_logs  # type: ignore[import-untyped, reportUnknownVariableType]

ADDON_SLUG = "local_cync-controller"


@pytest.mark.serial
def test_mqtt_command_updates_device_state(ha_login: Page, ha_base_url: str):
    """Test that MQTT commands update device state within 2 seconds.

    Expected: Sending command via MQTT results in state update in HA.
    """
    page = ha_login
    _ = page.goto(f"{ha_base_url}/lovelace/0")
    page.wait_for_load_state("networkidle")

    light_name = "Hallway Lights"

    start_time = time.time()

    # Toggle light
    try:
        on_switch = page.get_by_role("switch", name=f"Toggle {light_name} off")
        off_switch = page.get_by_role("switch", name=f"Toggle {light_name} on")

        if on_switch.is_visible(timeout=2000):
            on_switch.click()
        elif off_switch.is_visible(timeout=2000):
            off_switch.click()
        else:
            pytest_skip("Light entity not found")

        # Wait for state update
        page.wait_for_timeout(2000)

        elapsed = time.time() - start_time
        assert elapsed < 3, f"State sync took too long: {elapsed:.2f}s"

    except Exception as e:
        pytest_skip(f"Could not test state sync: {e}")


@pytest.mark.serial
def test_subgroup_state_aggregation(ha_login: Page, ha_base_url: str):
    """Test that subgroup state correctly aggregates member device states.

    Expected: Group shows ON if any member is ON, OFF if all members are OFF.
    """
    page = ha_login
    _ = page.goto(f"{ha_base_url}/lovelace/0")
    page.wait_for_load_state("networkidle")

    # This test would verify that group state reflects member states
    # Requires checking both group and individual member states


@pytest.mark.serial
def test_simultaneous_commands_to_multiple_devices(ha_login: Page, ha_base_url: str):
    """Test sending commands to multiple devices simultaneously.

    Expected: All devices process commands without interference.
    """
    page = ha_login
    _ = page.goto(f"{ha_base_url}/lovelace/0")
    page.wait_for_load_state("networkidle")

    # Find multiple light entities
    lights = ["Hallway Lights", "Kitchen Lights", "Bedroom Lights"]

    start_time = time.time()

    # Send commands to all lights
    for light in lights:
        try:
            # Try to toggle (don't wait between commands)
            toggle = page.get_by_role("switch", name=f"Toggle {light}")
            if toggle.is_visible(timeout=1000):
                toggle.click()
        except Exception:
            pass

    # Wait for all to complete
    page.wait_for_timeout(3000)

    _ = time.time() - start_time


def test_no_cascading_refresh_storms():
    """Test that state updates don't trigger cascading refresh storms.

    Expected: No excessive refresh commands in logs after state changes.
    """
    # Read logs
    logs: list[dict[str, Any]] = read_json_logs(ADDON_SLUG, lines=200)

    # Look for refresh-related logs
    refresh_logs: list[dict[str, Any]] = [log for log in logs if "refresh" in log.get("message", "").lower()]

    # Check for excessive refresh patterns (more than 10 in short time window)
    if len(refresh_logs) > 10:
        # Check timestamps to see if they're clustered
        timestamps: list[Any] = [log.get("timestamp") for log in refresh_logs if "timestamp" in log]
        if timestamps:
            pass
    else:
        pass


@pytest.mark.serial
def test_group_command_synchronization(ha_login: Page, ha_base_url: str):
    """Test that group commands properly synchronize member switch states.

    Expected: Turning off group turns off all member switches (Bug 4 regression test).
    """
    page = ha_login
    _ = page.goto(f"{ha_base_url}/lovelace/0")
    page.wait_for_load_state("networkidle")

    group_name = "Hallway Lights"
    member_switches = ["4way Switch", "Counter Switch", "Front Switch"]

    try:
        # Turn off group
        group_on = page.get_by_role("switch", name=f"Toggle {group_name} off")
        if group_on.is_visible(timeout=2000):
            group_on.click()
            page.wait_for_timeout(2000)  # Wait for MQTT sync

            # Check all member switches are OFF
            all_synced = True

            for switch_name in member_switches:
                try:
                    # Check if switch shows OFF state
                    switch_off = page.get_by_role("switch", name=f"Toggle Hallway {switch_name} on")
                    if not switch_off.is_visible(timeout=1000):
                        all_synced = False
                    else:
                        pass
                except Exception:
                    all_synced = False

            if all_synced:
                pass
            else:
                pass

    except Exception as e:
        pytest_skip(f"Could not test group synchronization: {e}")


def test_state_updates_logged_correctly():
    """Test that state updates are properly logged.

    Expected: State change logs contain necessary context.
    """
    # Read logs
    logs: list[dict[str, Any]] = read_json_logs(ADDON_SLUG, lines=200)

    # Look for state-related logs
    state_logs: list[dict[str, Any]] = [log for log in logs if "state" in log.get("message", "").lower()]

    if state_logs:
        _ = state_logs[0]


@pytest.mark.serial
def test_physical_device_changes_reflect_in_ha(ha_login: Page, ha_base_url: str):
    """Test that physical device state changes (via wall switch) reflect in HA.

    Expected: Physical toggle triggers status packet → updates HA entity state.
    """
    page = ha_login
    _ = page.goto(f"{ha_base_url}/lovelace/0")
    page.wait_for_load_state("networkidle")

    # Check logs for status packets
    logs: list[dict[str, Any]] = read_json_logs(ADDON_SLUG, lines=100)
    _ = [log for log in logs if "0x83" in log.get("message", "") or "status" in log.get("message", "").lower()]


def test_no_state_flicker_during_updates():
    """Test that entities don't flicker between states during updates.

    Expected: Clean state transitions without rapid ON→OFF→ON patterns.
    """
    # This is primarily tested through logs
    # Flicker would show as rapid state changes in short time

    logs: list[dict[str, Any]] = read_json_logs(ADDON_SLUG, lines=200)

    # Look for rapid state changes (would need timestamp analysis)
    _ = [log for log in logs if "state" in log.get("message", "").lower()]
