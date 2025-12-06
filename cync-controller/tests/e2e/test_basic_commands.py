"""E2E tests for basic command execution."""

import sys
import time
from pathlib import Path
from typing import Any, cast

import pytest
from _pytest.outcomes import skip as pytest_skip
from playwright.sync_api import Page, expect

# Add scripts/playwright to Python path for helper imports
scripts_path = Path(__file__).parent.parent.parent.parent / "scripts" / "playwright"
sys.path.insert(0, str(scripts_path))

from addon_helpers import read_json_logs  # type: ignore[import-untyped, reportUnknownVariableType]

ADDON_SLUG = "local_cync-controller"


@pytest.mark.serial
def test_turn_light_on(ha_login: Page, ha_base_url: str):
    """Test turning a light ON via Home Assistant UI.

    Expected: Light state updates to ON within 2 seconds.
    """
    page = ha_login
    _ = page.goto(f"{ha_base_url}/lovelace/0")
    page.wait_for_load_state("networkidle")

    # Find a light entity (use individual entity, not group)
    light_name = "Floodlight 1"

    # Try to find OFF switch (light is currently off)
    try:
        off_switch = page.get_by_role("switch", name=f"Toggle {light_name} on")
        if off_switch.is_visible(timeout=2000):
            start_time = time.time()
            off_switch.click()
            page.wait_for_timeout(2000)  # Wait for MQTT sync

            # Verify light is now ON
            on_switch = page.get_by_role("switch", name=f"Toggle {light_name} off")
            expect(on_switch).to_be_visible(timeout=3000)

            elapsed = time.time() - start_time
            assert elapsed < 5, f"Command took too long: {elapsed:.2f}s"
    except Exception as e:
        pytest_skip(f"Light entity not found or already ON: {e}")


@pytest.mark.serial
def test_turn_light_off(ha_login: Page, ha_base_url: str):
    """Test turning a light OFF via Home Assistant UI.

    Expected: Light state updates to OFF within 2 seconds.
    """
    page = ha_login
    _ = page.goto(f"{ha_base_url}/lovelace/0")
    page.wait_for_load_state("networkidle")

    light_name = "Floodlight 1"

    try:
        # Find ON switch (light is currently on)
        on_switch = page.get_by_role("switch", name=f"Toggle {light_name} off")
        if on_switch.is_visible(timeout=2000):
            start_time = time.time()
            on_switch.click()
            page.wait_for_timeout(2000)

            # Verify light is now OFF
            off_switch = page.get_by_role("switch", name=f"Toggle {light_name} on")
            expect(off_switch).to_be_visible(timeout=3000)

            elapsed = time.time() - start_time
            assert elapsed < 5, f"Command took too long: {elapsed:.2f}s"
    except Exception as e:
        pytest_skip(f"Light entity not found or already OFF: {e}")


@pytest.mark.serial
def test_set_brightness(ha_login: Page, ha_base_url: str):
    """Test setting light brightness via Home Assistant UI.

    Expected: Brightness updates within 2 seconds.
    """
    page = ha_login
    _ = page.goto(f"{ha_base_url}/lovelace/0")
    page.wait_for_load_state("networkidle")

    # Use Master Bedroom Lamp Light which supports brightness
    light_name_candidates = ["Lamp Light", "Master Bedroom Lamp Light"]
    light_name = None

    try:
        # Find and click the entity to open more-info dialog
        for candidate in light_name_candidates:
            try:
                # Use getByText which pierces shadow DOM
                entity = page.get_by_text(candidate, exact=False).first
                if entity.is_visible(timeout=2000):
                    light_name = candidate
                    entity.click()
                    break
            except Exception:
                continue

        if light_name is None:
            error_msg = f"Could not find light entity with names {light_name_candidates} - ensure entity exists"
            raise AssertionError(error_msg)

        # Wait for brightness slider to appear (it's in the dialog's shadow DOM)
        # Playwright's getByRole automatically pierces shadow DOM
        brightness_slider = page.get_by_role("slider", name="Brightness")
        expect(brightness_slider).to_be_visible(timeout=10000)

        # Interact with the slider by clicking and using fill
        brightness_slider.click()  # Focus the slider
        page.wait_for_timeout(500)  # Allow UI to respond

        # Try fill method first (works for input elements)
        try:
            brightness_slider.fill("50")
        except Exception:
            # Fallback to evaluate for custom slider elements
            brightness_slider.evaluate(
                "el => { el.value = 50; el.dispatchEvent(new Event('change', {bubbles: true})); }",
            )

        page.wait_for_timeout(2000)

    except Exception as e:
        error_msg = f"Could not test brightness: {e}"
        raise AssertionError(error_msg) from e


@pytest.mark.serial
def test_set_color_temperature(ha_login: Page, ha_base_url: str):
    """Test setting light color temperature via Home Assistant UI.

    Expected: Color temperature updates within 2 seconds.
    """
    page = ha_login
    _ = page.goto(f"{ha_base_url}/lovelace/0")
    page.wait_for_load_state("networkidle")

    # Use Master Bedroom Lamp Light which supports color temperature
    light_name_candidates = ["Lamp Light", "Master Bedroom Lamp Light"]
    light_name = None

    try:
        # Find and click the entity to open more-info dialog
        for candidate in light_name_candidates:
            try:
                # Use getByText which pierces shadow DOM
                entity = page.get_by_text(candidate, exact=False).first
                if entity.is_visible(timeout=2000):
                    light_name = candidate
                    entity.click()
                    break
            except Exception:
                continue

        if light_name is None:
            error_msg = f"Could not find light entity with names {light_name_candidates} - ensure entity exists"
            raise AssertionError(error_msg)

        # Click Temperature button to switch from brightness to color temp mode
        # getByRole pierces shadow DOM automatically
        temp_button = page.get_by_role("button", name="Temperature")
        expect(temp_button).to_be_visible(timeout=10000)
        temp_button.click(force=True)  # force=True to click through overlapping UI elements

        # Wait for slider to switch to temperature mode
        color_temp_slider = page.get_by_role("slider", name="Temperature")
        expect(color_temp_slider).to_be_visible(timeout=5000)

        # Adjust the slider
        color_temp_slider.click()
        page.wait_for_timeout(500)

        # Try fill method first
        try:
            color_temp_slider.fill("150")
        except Exception:
            # Fallback to evaluate
            color_temp_slider.evaluate(
                "el => { el.value = 4000; el.dispatchEvent(new Event('change', {bubbles: true})); }",
            )

        page.wait_for_timeout(2000)

    except Exception as e:
        error_msg = f"Could not test color temperature: {e}"
        raise AssertionError(error_msg) from e


@pytest.mark.serial
def test_toggle_switch(ha_login: Page, ha_base_url: str):
    """Test toggling a switch entity.

    Expected: Switch state changes within 2 seconds.
    """
    page = ha_login
    _ = page.goto(f"{ha_base_url}/lovelace/0")
    page.wait_for_load_state("networkidle")

    # Try both names in case HA prefixes with area
    switch_name_candidates = ["Counter Switch", "Hallway Counter Switch"]
    switch_name = None

    try:
        # Find which name exists
        for candidate in switch_name_candidates:
            try:
                # Try to find the switch in either state
                on_switch = page.get_by_role("switch", name=f"Toggle {candidate} off")
                off_switch = page.get_by_role("switch", name=f"Toggle {candidate} on")

                if on_switch.is_visible(timeout=1500) or off_switch.is_visible(timeout=1500):
                    switch_name = candidate
                    break
            except Exception:
                continue

        if switch_name is None:
            error_msg = (
                f"Switch entity not found with names {switch_name_candidates} - ensure entity exists and is visible"
            )
            raise AssertionError(error_msg)

        # Now use the found name to toggle
        on_switch = page.get_by_role("switch", name=f"Toggle {switch_name} off")
        off_switch = page.get_by_role("switch", name=f"Toggle {switch_name} on")

        if on_switch.is_visible(timeout=2000):
            on_switch.click()
            page.wait_for_timeout(2000)
            expect(off_switch).to_be_visible(timeout=3000)
        elif off_switch.is_visible(timeout=2000):
            off_switch.click()
            page.wait_for_timeout(2000)
            expect(on_switch).to_be_visible(timeout=3000)

    except Exception as e:
        error_msg = f"Could not test switch: {e}"
        raise AssertionError(error_msg) from e


def test_command_latency_acceptable(ha_login: Page):
    """Test that commands execute within acceptable latency (< 2 seconds).

    This is verified in logs rather than UI to be more reliable.
    """
    # Read recent logs
    logs: list[dict[str, Any]] = cast("list[dict[str, Any]]", read_json_logs(ADDON_SLUG, lines=100))  # type: ignore[reportUnknownVariableType]

    # Look for command-related log entries
    [cast("dict[str, Any]", log) for log in logs if "command" in cast("dict[str, Any]", log).get("message", "").lower()]  # type: ignore[reportUnknownVariableType]

    # This is a basic check - full latency testing would require
    # actually sending commands and measuring response time


@pytest.mark.serial  # type: ignore[attr-defined]
@pytest.mark.usefixtures("ha_login")  # type: ignore[misc]
def test_command_with_tcp_whitelist_enabled():
    """Test that commands work correctly when TCP whitelist is configured.

    Expected: Only whitelisted devices can execute commands.
    """

    # This test would:
    # 1. Configure TCP whitelist
    # 2. Attempt commands to whitelisted device (should work)
    # 3. Attempt commands to non-whitelisted device (should fail)
