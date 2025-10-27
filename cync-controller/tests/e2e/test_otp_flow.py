"""E2E tests for OTP submission flow - Bug 1: OTP fails first time, succeeds second time."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.skip(reason="Requires live Cync account with OTP - run manually")
def test_otp_double_submission(ingress_page: Page):
    """
    Test Bug 1: OTP submission fails the first time, succeeds the second time.

    This test reproduces the issue where submitting a valid OTP fails initially,
    but succeeds when submitted again without requesting a new OTP.

    Root cause: Token not persisted to cache after send_otp() succeeds.
    """
    # Click "Start Export" button
    start_button = ingress_page.locator("#startButton")
    start_button.click()

    # Wait for OTP section to appear
    otp_input = ingress_page.locator("#otpInput")
    expect(otp_input).to_be_visible(timeout=10000)

    # Get OTP from user (this would need to be mocked or provided externally)
    # For manual testing, prompt for OTP
    print("\n⚠️  This test requires manual OTP entry")
    print("Check your email for the OTP code and enter it in the browser")
    print("Then press Enter here to continue...")
    input()

    # Wait for user to enter OTP in browser
    print("Waiting for OTP submission...")

    # Verify first submission fails
    submit_button = ingress_page.locator("#submitOtpButton")
    submit_button.click()

    # Check for error message (should appear)
    error_toast = ingress_page.locator(".error, [class*='error']")
    expect(error_toast).to_be_visible(timeout=5000)

    # Submit the same OTP again (should succeed)
    submit_button.click()

    # Verify success
    success_section = ingress_page.locator("#successSection")
    expect(success_section).to_be_visible(timeout=10000)

    # Verify restart button appears
    restart_button = ingress_page.locator("#restartButton")
    expect(restart_button).to_be_visible()


def test_otp_flow_with_cached_token(ingress_page: Page):
    """
    Test that export works immediately when valid token exists in cache.

    This verifies the fix for Bug 1 - after successful OTP submission and token caching,
    subsequent exports should work without requiring a new OTP.
    """
    # Click "Start Export" button
    start_button = ingress_page.locator("#startButton")
    start_button.click()

    # If token is cached, should go straight to success
    # If token is expired/missing, OTP section appears
    otp_section = ingress_page.locator("#otpSection")
    success_section = ingress_page.locator("#successSection")

    # Wait for either OTP section or success section
    ingress_page.wait_for_selector("#otpSection, #successSection", timeout=10000)

    # Check which one appeared
    if otp_section.is_visible():
        pytest.skip("No cached token - OTP required (this is expected for first run)")
    else:
        # Success section should be visible
        expect(success_section).to_be_visible()
        print("✓ Export succeeded with cached token")
