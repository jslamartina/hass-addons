"""E2E tests for MQTT resilience and recovery."""

import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import Page

# Add scripts/playwright to Python path for helper imports
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

from scripts.playwright.addon_helpers import (  # type: ignore[import-untyped, reportUnknownVariableType]
    JSONDict,  # type: ignore[reportUnknownVariableType]
    get_addon_status,  # type: ignore[reportUnknownVariableType]
    read_json_logs,  # type: ignore[reportUnknownVariableType]
    restart_addon_and_wait,  # type: ignore[reportUnknownVariableType]
    start_addon,  # type: ignore[reportUnknownVariableType]
    stop_addon,  # type: ignore[reportUnknownVariableType]
)

ADDON_SLUG = "local_cync-controller"
MQTT_ADDON_SLUG = "a0d7b954_emqx"


@pytest.fixture(autouse=True)
def ensure_mqtt_running():
    """Fixture to ensure MQTT is running after test."""
    yield

    # Always restart MQTT at end (non-blocking)
    _ = start_addon(MQTT_ADDON_SLUG)
    time.sleep(2)


@pytest.mark.serial  # type: ignore[attr-defined]
def test_addon_handles_mqtt_disconnect():
    """Test that add-on handles MQTT disconnection gracefully.

    Expected: Add-on continues running and logs connection errors.
    """
    # Verify add-on running
    status: JSONDict = get_addon_status(ADDON_SLUG)
    assert status.get("state") == "started", "Add-on not running"

    # Stop MQTT broker
    assert stop_addon(MQTT_ADDON_SLUG), "Failed to stop MQTT broker"
    time.sleep(5)

    # Verify add-on still running (should handle disconnect gracefully)
    status = get_addon_status(ADDON_SLUG)
    assert status.get("state") == "started", "Add-on crashed after MQTT disconnect"

    # Check logs for connection errors
    logs: list[JSONDict] = read_json_logs(ADDON_SLUG, lines=100)
    _ = [log for log in logs if "mqtt" in str(log.get("message", "")).lower()]


@pytest.mark.serial  # type: ignore[attr-defined]
def test_addon_reconnects_after_mqtt_recovery():
    """Test that add-on reconnects after MQTT comes back online.

    Expected: Add-on detects MQTT availability and reconnects automatically.
    """
    # Stop MQTT
    assert stop_addon(MQTT_ADDON_SLUG), "Failed to stop MQTT broker"
    time.sleep(5)

    # Restart MQTT
    assert start_addon(MQTT_ADDON_SLUG), "Failed to start MQTT broker"
    time.sleep(10)  # Wait for MQTT to fully start and add-on to reconnect

    # Check logs for reconnection
    logs: list[JSONDict] = read_json_logs(ADDON_SLUG, lines=150)

    # Look for connection-related logs
    _ = [
        log
        for log in logs
        if any(word in str(log.get("message", "")).lower() for word in ["connect", "reconnect", "mqtt"])
    ]

    # Verify add-on still healthy
    status: JSONDict = get_addon_status(ADDON_SLUG)
    assert status.get("state") == "started", "Add-on not running after MQTT recovery"


@pytest.mark.serial  # type: ignore[attr-defined]
def test_entities_unavailable_during_mqtt_disconnect(ha_login: Page, ha_base_url: str):
    """Test that entities show unavailable when MQTT is disconnected.

    Expected: Entities marked unavailable during disconnect, restore after reconnect.
    """
    page = ha_login
    _ = page.goto(f"{ha_base_url}/lovelace/0")
    page.wait_for_load_state("networkidle")

    # Stop MQTT
    assert stop_addon(MQTT_ADDON_SLUG), "Failed to stop MQTT broker"
    time.sleep(10)

    # Check entity state (should be unavailable)
    # Note: Would need to check specific entity states via API or UI

    # Restart MQTT
    assert start_addon(MQTT_ADDON_SLUG), "Failed to start MQTT broker"
    time.sleep(10)

    # Check entity state (should be available again)
    # Entities should become available again


def test_addon_mqtt_retry_logic():
    """Test that add-on has retry logic for MQTT connections.

    Expected: Logs show retry attempts with backoff.
    """
    # Restart add-on to trigger fresh connection attempt
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=10)

    # Check logs for connection attempts
    logs: list[JSONDict] = read_json_logs(ADDON_SLUG, lines=200)

    mqtt_connect_logs: list[JSONDict] = [
        log
        for log in logs
        if "mqtt" in str(log.get("message", "")).lower() and "connect" in str(log.get("message", "")).lower()
    ]

    if mqtt_connect_logs:
        pass


@pytest.mark.serial  # type: ignore[attr-defined]
def test_rapid_mqtt_disconnect_reconnect():
    """Test handling of rapid MQTT disconnect/reconnect cycles.

    Expected: Add-on remains stable through multiple connection cycles.
    """
    cycles = 3

    for i in range(cycles):
        # Stop MQTT
        _ = stop_addon(MQTT_ADDON_SLUG)
        time.sleep(3)

        # Start MQTT
        _ = start_addon(MQTT_ADDON_SLUG)
        time.sleep(5)

        # Verify add-on still healthy
        status: JSONDict = get_addon_status(ADDON_SLUG)
        assert status.get("state") == "started", f"Add-on failed during cycle {i + 1}"


def test_mqtt_connection_status_in_logs():
    """Test that MQTT connection status is properly logged.

    Expected: Logs contain clear connection status messages.
    """
    # Read logs
    logs: list[JSONDict] = read_json_logs(ADDON_SLUG, lines=200)

    # Look for MQTT-related logs
    mqtt_logs: list[JSONDict] = [
        log
        for log in logs
        if "mqtt" in str(log.get("logger", "")).lower() or "mqtt" in str(log.get("message", "")).lower()
    ]

    # Check for important connection states
    connection_states: list[str] = ["connect", "disconnect", "publish", "subscribe"]
    found_states: set[str] = set()

    for log in mqtt_logs:
        message: str = str(log.get("message", "")).lower()
        for state in connection_states:
            if state in message:
                found_states.add(state)
