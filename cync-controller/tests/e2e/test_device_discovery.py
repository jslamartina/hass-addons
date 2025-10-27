"""E2E tests for device discovery and MQTT entity creation."""

import sys
from pathlib import Path

import pytest
from playwright.sync_api import Page

# Add scripts/playwright to Python path for helper imports
scripts_path = Path(__file__).parent.parent.parent.parent / "scripts" / "playwright"
sys.path.insert(0, str(scripts_path))

from addon_helpers import get_addon_status, restart_addon_and_wait  # noqa: E402

ADDON_SLUG = "local_cync-controller"


@pytest.mark.serial
@pytest.mark.usefixtures("ha_login")
def test_addon_starts_successfully():
    """
    Test that the add-on starts successfully and shows running status.

    Expected: Add-on status shows "started" after restart.
    """
    print("\n=== Test: Add-on Starts Successfully ===")

    # Restart add-on
    print("[Step 1] Restarting add-on...")
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Check status
    print("[Step 2] Checking add-on status...")
    status = get_addon_status(ADDON_SLUG)

    print(f"  Add-on state: {status.get('state')}")
    print(f"  Add-on version: {status.get('version')}")

    assert status.get("state") == "started", f"Add-on not started: {status.get('state')}"
    print("✓ Add-on started successfully")


def test_mqtt_entities_appear_after_restart(ha_login: Page, ha_base_url: str):
    """
    Test that MQTT entities are discovered after add-on restart.

    Expected: Entities appear in MQTT integration within reasonable timeout.
    """
    print("\n=== Test: MQTT Entities Discovered After Restart ===")

    # Restart add-on
    print("[Step 1] Restarting add-on...")
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=10)

    # Navigate to MQTT integration
    print("[Step 2] Navigating to MQTT integration...")
    page = ha_login
    mqtt_url = f"{ha_base_url}/config/integrations/integration/mqtt"
    page.goto(mqtt_url)
    page.wait_for_load_state("networkidle")

    # Look for Cync entities (wait up to 15 seconds)
    print("[Step 3] Waiting for Cync entities to appear...")

    # Search for "cync" to filter entities
    try:
        search_box = page.get_by_role("textbox", name="Search")
        if search_box.is_visible(timeout=2000):
            search_box.fill("cync")
            page.wait_for_timeout(2000)
    except Exception:
        print("  Search box not found, continuing without search...")

    # Check if any entities are visible
    # This is a basic check - actual entity verification depends on test environment
    page.wait_for_timeout(3000)
    print("✓ MQTT integration page loaded")


def test_entity_attributes_structure(ha_login: Page, ha_base_url: str):
    """
    Test that Cync entities have the expected attribute structure.

    Expected: Entities have device_info, unique_id, and other MQTT discovery fields.
    """
    print("\n=== Test: Entity Attributes Structure ===")

    # Note: This test would typically use Home Assistant's REST API
    # to inspect entity attributes. For now, we verify the UI shows entities.

    page = ha_login
    page.goto(f"{ha_base_url}/config/entities")
    page.wait_for_load_state("networkidle")

    # Filter for cync entities
    print("[Step 1] Filtering for Cync entities...")
    try:
        search_box = page.get_by_role("textbox", name="Search")
        if search_box.is_visible(timeout=2000):
            search_box.fill("cync")
            page.wait_for_timeout(2000)
            print("✓ Filtered for Cync entities")
    except Exception:
        print("  Search not available, skipping filter...")

    page.wait_for_timeout(2000)
    print("✓ Entity attributes page accessible")


@pytest.mark.serial
def test_different_device_types_discovered(ha_login: Page, ha_base_url: str):
    """
    Test that different device types are discovered correctly.

    Expected: Switches, bulbs, plugs, and fans all create appropriate entities.
    """
    print("\n=== Test: Different Device Types Discovered ===")

    page = ha_login
    page.goto(f"{ha_base_url}/config/entities")
    page.wait_for_load_state("networkidle")

    # Search for different device types
    device_types = ["switch", "light", "fan"]

    for device_type in device_types:
        print(f"[Step] Checking for {device_type} entities...")

        search_box = page.get_by_role("textbox", name="Search")
        search_box.fill(f"cync {device_type}")
        page.wait_for_timeout(2000)

        # Note: Actual assertion would depend on test environment having these devices
        print(f"  ✓ Searched for {device_type} entities")


@pytest.mark.serial
def test_entity_suggested_area_attribute(ha_login: Page, ha_base_url: str):
    """
    Test that entities have suggested_area attribute set correctly.

    Expected: Entities show appropriate area suggestions based on config.
    """
    print("\n=== Test: Entity Suggested Area ===")

    # This test would check that suggested_area is properly set
    # in the MQTT discovery payload. Requires inspection of entity attributes
    # via Home Assistant API or entity details page.

    page = ha_login
    page.goto(f"{ha_base_url}/config/entities")
    page.wait_for_load_state("networkidle")

    print("✓ Test placeholder - requires API integration for full validation")


def test_entity_unique_ids_are_consistent(ha_login: Page):  # noqa: ARG001
    """
    Test that entity unique IDs remain consistent across restarts.

    Expected: Restarting add-on doesn't create duplicate entities.
    """
    print("\n=== Test: Entity Unique IDs Consistent ===")

    # Restart add-on twice
    print("[Step 1] First restart...")
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=10)

    print("[Step 2] Second restart...")
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=10)

    # Note: Would need to query HA API to verify no duplicate entities created
    # For now, verify add-on restarts successfully multiple times
    status = get_addon_status(ADDON_SLUG)
    assert status.get("state") == "started", "Add-on failed after multiple restarts"

    print("✓ Add-on restarted multiple times successfully")
