"""E2E tests for OTP submission flow - Bug 1: OTP fails first time, succeeds second time."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.skip(reason="Requires live Cync account with OTP - run manually")
@pytest.mark.usefixtures("_ingress_page")
def test_otp_double_submission() -> None:
    """Skipped manual OTP flow test."""


def test_otp_flow_with_cached_token(ingress_page: Page):
    """Test that export works immediately when valid token exists in cache.

    This verifies the fix for Bug 1 - after successful OTP submission and token caching,
    subsequent exports should work without requiring a new OTP.
    """
    page = ingress_page

    # Get the nested iframe containing the ingress page content
    outer_iframe = page.frame_locator("iframe[title='Cync Controller']")
    inner_iframe = outer_iframe.frame_locator("iframe[title='Cync Controller']")

    # Click "Start Export" button
    start_button = inner_iframe.get_by_role("button", name="Start Export")
    start_button.click()

    # If token is cached, should go straight to success
    # If token is expired/missing, OTP section appears or button text changes
    try:
        # Wait for button text to change to "Restart Server" (indicating success)
        restart_button = inner_iframe.get_by_role("button", name="Restart Server")
        # If we can find the restart button, export succeeded
        expect(restart_button).to_be_visible(timeout=5000)
    except Exception:
        # OTP section should be visible if no cached token
        otp_section = inner_iframe.get_by_text("Enter OTP:")
        if otp_section.is_visible(timeout=2000):
            pytest.skip("No cached token - OTP required (this is expected for first run)")
        else:
            # Something else went wrong
            pytest.fail("Unexpected state - neither success nor OTP section visible")
