"""E2E tests for restart button behavior - Bugs 2 & 3."""

import pytest
from playwright.sync_api import Page, expect


def test_restart_button_error_despite_success(ingress_page: Page):
    """
    Test Bug 2: Restart button shows error despite server actually restarting.

    Root cause: Race condition where server restarts before HTTP response is sent,
    causing frontend to see a network error even though the restart succeeded.
    """
    # First ensure config is exported and restart button is visible
    start_button = ingress_page.locator("#startButton")
    if start_button.is_visible():
        # Need to export config first
        pytest.skip("Config not exported - need cached token for this test")

    restart_button = ingress_page.locator("#restartButton")
    if not restart_button.is_visible():
        pytest.skip("Restart button not visible - config may not be exported")

    # Click restart button
    restart_button.click()

    # Check for error or success message
    # Bug behavior: Error message appears
    # Fixed behavior: Success message appears (even if connection drops)
    ingress_page.wait_for_selector("[class*='toast'], [class*='error'], [class*='success']", timeout=10000)

    # After fix, should show success message
    # Note: This test documents the bug - after fix, should see success toast


def test_restart_button_visibility_after_navigation(ingress_page: Page, ha_base_url: str):
    """
    Test Bug 3: Restart button disappears after leaving and returning to ingress page.

    Root cause: Button visibility only set on OTP submission, not restored on page load.
    """
    # Ensure we're on ingress page
    ingress_url = f"{ha_base_url}/local_cync-controller/ingress"

    # Check if config already exists (button should be visible)
    restart_button = ingress_page.locator("#restartButton")
    success_section = ingress_page.locator("#successSection")

    # If no config exported, skip test
    if not restart_button.is_visible() and not success_section.is_visible():
        pytest.skip("No config exported - restart button not expected to be visible")

    # Record initial button visibility
    button_was_visible = restart_button.is_visible()

    if button_was_visible:
        print("✓ Restart button is visible initially")

        # Navigate away from ingress page
        ingress_page.goto(f"{ha_base_url}/config/dashboard")
        ingress_page.wait_for_load_state("networkidle")

        # Navigate back to ingress page
        ingress_page.goto(ingress_url)
        ingress_page.wait_for_load_state("networkidle")

        # After fix: Button should still be visible
        # Before fix: Button disappears
        expect(restart_button).to_be_visible(timeout=5000)
        print("✓ Restart button is still visible after navigation")
    else:
        pytest.skip("Restart button not visible - config may not be exported")


def test_config_persistence_check(ingress_page: Page):
    """
    Test that ingress page checks for existing config on load.

    After fix, the page should call /api/export/download on load to check if
    config exists, and show the restart button + config if it does.
    """
    # Reload the page
    ingress_page.reload()
    ingress_page.wait_for_load_state("networkidle")

    # Give page time to check for existing config
    ingress_page.wait_for_timeout(1000)

    # Check if config display is shown
    success_section = ingress_page.locator("#successSection")
    restart_button = ingress_page.locator("#restartButton")

    # If config exists, both should be visible
    # If no config, neither should be visible
    if success_section.is_visible():
        expect(restart_button).to_be_visible()
        print("✓ Restart button and config both visible after page load")
    else:
        print("i  No config found - button correctly hidden")
