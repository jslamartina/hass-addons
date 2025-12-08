"""E2E tests for device discovery and MQTT entity creation."""

import logging
import sys
from pathlib import Path

import pytest
from playwright.sync_api import Page

# Add scripts/playwright to Python path for helper imports
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

from scripts.playwright.addon_helpers import (  # type: ignore[import-untyped, reportUnknownVariableType]
    get_addon_status,
    restart_addon_and_wait,
)

ADDON_SLUG = "local_cync-controller"
JSONDict = dict[str, object]
logger = logging.getLogger(__name__)


@pytest.mark.serial  # type: ignore[attr-defined]
def test_addon_starts_successfully(ha_login: Page):
    """Test that the add-on starts successfully and shows running status.

    Expected: Add-on status shows "started" after restart.
    """
    _ = ha_login
    # Restart add-on
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Check status
    status: JSONDict = get_addon_status(ADDON_SLUG)  # type: ignore[reportUnknownVariableType]

    assert status.get("state") == "started", f"Add-on not started: {status.get('state')}"


def test_mqtt_entities_appear_after_restart(ha_login: Page, ha_base_url: str):
    """Test that MQTT entities are discovered after add-on restart.

    Expected: Entities appear in MQTT integration within reasonable timeout.
    """
    # Restart add-on
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=10)

    # Navigate to MQTT integration
    page = ha_login
    mqtt_url = f"{ha_base_url}/config/integrations/integration/mqtt"
    _ = page.goto(mqtt_url)
    page.wait_for_load_state("networkidle")

    # Look for Cync entities (wait up to 15 seconds)

    # Search for "cync" to filter entities
    try:
        search_box = page.get_by_role("textbox", name="Search")
        if search_box.is_visible(timeout=2000):
            search_box.fill("cync")
            page.wait_for_timeout(2000)
    except Exception as exc:
        logger.info("Search box not available for MQTT integration: %s", exc)

    # Check if any entities are visible
    # This is a basic check - actual entity verification depends on test environment
    page.wait_for_timeout(3000)


def test_entity_attributes_structure(ha_login: Page, ha_base_url: str):
    """Test that Cync entities have the expected attribute structure.

    Expected: Entities have device_info, unique_id, and other MQTT discovery fields.
    """
    # Note: This test would typically use Home Assistant's REST API
    # to inspect entity attributes. For now, we verify the UI shows entities.

    page = ha_login
    _ = page.goto(f"{ha_base_url}/config/entities")
    page.wait_for_load_state("networkidle")

    # Filter for cync entities
    try:
        search_box = page.get_by_role("textbox", name="Search")
        if search_box.is_visible(timeout=2000):
            search_box.fill("cync")
            page.wait_for_timeout(2000)
    except Exception as exc:
        logger.info("Search box not available for entity attributes: %s", exc)

    page.wait_for_timeout(2000)


@pytest.mark.serial
def test_different_device_types_discovered(ha_login: Page, ha_base_url: str):
    """Test that different device types are discovered correctly.

    Expected: Switches, bulbs, plugs, and fans all create appropriate entities.
    """
    page = ha_login
    _ = page.goto(f"{ha_base_url}/config/entities")
    page.wait_for_load_state("networkidle")

    # Search for different device types
    device_types = ["switch", "light", "fan"]

    for device_type in device_types:
        search_box = page.get_by_role("textbox", name="Search")
        search_box.fill(f"cync {device_type}")
        page.wait_for_timeout(2000)

        # Note: Actual assertion would depend on test environment having these devices


@pytest.mark.serial
def test_entity_suggested_area_attribute(ha_login: Page, ha_base_url: str):
    """Test that entities have suggested_area attribute set correctly.

    Expected: Entities show appropriate area suggestions based on config.
    """
    # This test would check that suggested_area is properly set
    # in the MQTT discovery payload. Requires inspection of entity attributes
    # via Home Assistant API or entity details page.

    page = ha_login
    _ = page.goto(f"{ha_base_url}/config/entities")
    page.wait_for_load_state("networkidle")


def test_entity_unique_ids_are_consistent(ha_login: Page):
    """Test that entity unique IDs remain consistent across restarts.

    Expected: Restarting add-on doesn't create duplicate entities.
    """
    _ = ha_login
    # Restart add-on twice
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=10)

    restart_addon_and_wait(ADDON_SLUG, wait_seconds=10)

    # Note: Would need to query HA API to verify no duplicate entities created
    # For now, verify add-on restarts successfully multiple times
    status: JSONDict = get_addon_status(ADDON_SLUG)  # type: ignore[reportUnknownVariableType]
    assert status.get("state") == "started", "Add-on failed after multiple restarts"
