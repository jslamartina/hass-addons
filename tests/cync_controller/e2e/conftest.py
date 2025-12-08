"""Pytest fixtures for E2E tests using Playwright."""

import logging
import os
import re
from pathlib import Path

import pytest
from _pytest.outcomes import skip as pytest_skip
from playwright.sync_api import Page

logger = logging.getLogger(__name__)


def _resolve_repo_root() -> Path:
    """Return the repo root, honoring overrides for worktrees."""
    env_root = os.getenv("HASS_ADDONS_ROOT")
    if env_root:
        repo_root = Path(env_root).expanduser().resolve()
        logger.debug("Using HASS_ADDONS_ROOT override for repo root: %s", repo_root)
        return repo_root

    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / ".git").exists():
            logger.debug("Located repo root via .git at: %s", candidate)
            return candidate

    fallback = current.parent
    logger.warning(
        "Unable to find .git when resolving repo root from %s; falling back to %s",
        current,
        fallback,
    )
    return fallback


def _credentials_file() -> Path:
    """Resolve the credentials file path."""
    env_creds = os.getenv("HASS_CREDENTIALS_FILE")
    if env_creds:
        return Path(env_creds).expanduser().resolve()
    return _resolve_repo_root() / "hass-credentials.env"


@pytest.fixture(scope="session")
def browser_context_args():
    """Configure browser context for tests."""
    return {
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True,
    }  # type: ignore[return-value]


@pytest.fixture(scope="session")
def ha_credentials() -> dict[str, str]:
    """Load Home Assistant credentials from environment or file."""
    # Try environment variables first
    username = os.getenv("HA_USERNAME")
    password = os.getenv("HA_PASSWORD")

    # Fall back to credentials file
    if not username or not password:
        creds_file = _credentials_file()
        if creds_file.exists():
            with creds_file.open() as f:
                for line in f:
                    if line.startswith("HASS_USERNAME="):
                        username = line.split("=", 1)[1].strip()
                    elif line.startswith("HASS_PASSWORD="):
                        password = line.split("=", 1)[1].strip()

    if not username or not password:
        pytest_skip("Home Assistant credentials not found")

    return {"username": username, "password": password}


@pytest.fixture(scope="session")
def ha_base_url():
    """Get Home Assistant base URL."""
    return os.getenv("HA_URL", "http://localhost:8123")


@pytest.fixture
def ha_login(page: Page, ha_base_url: str, ha_credentials: dict[str, str]):
    """Log into Home Assistant and return the authenticated page."""
    # Navigate to Home Assistant
    _ = page.goto(ha_base_url)

    # Check if already logged in
    if page.url.startswith(f"{ha_base_url}/lovelace") or page.url.startswith(f"{ha_base_url}/config"):
        return page

    # Wait for login form
    _ = page.wait_for_selector('input[name="username"], input[type="text"]', timeout=10000)

    # Fill credentials
    username_input = page.locator('input[name="username"], input[type="text"]').first
    password_input = page.locator('input[name="password"], input[type="password"]').first

    username_input.fill(ha_credentials["username"])
    password_input.fill(ha_credentials["password"])

    # Submit form
    submit_button = page.get_by_role("button", name=re.compile(r"sign in|log in", re.IGNORECASE))
    submit_button.click()

    # Wait for redirect to dashboard
    page.wait_for_url(re.compile(r"/lovelace|/config"), timeout=10000)

    return page


@pytest.fixture
def ingress_page(ha_login: Page, ha_base_url: str):
    """Navigate to Cync Controller ingress page."""
    page = ha_login

    # Navigate to ingress page
    # Try direct URL first
    ingress_url = f"{ha_base_url}/local_cync-controller/ingress"
    _ = page.goto(ingress_url)

    # Verify we're on the ingress page by checking for expected elements
    # After fix: Button is always visible if config exists; only show #startButton if no config
    # Wait for page to load first
    page.wait_for_load_state("networkidle")
    # Check for any of the possible elements
    try:
        _ = page.wait_for_selector(
            "button:has-text('Restart'), #startButton, #otpInput, #restartButton, #successSection", timeout=3000
        )
    except Exception:
        # If none found, the page might still be loading, wait a bit more
        page.wait_for_timeout(1000)

    return page


@pytest.fixture
def ha_config_page(ha_login: Page, ha_base_url: str):
    """Navigate to Home Assistant configuration page."""
    page = ha_login
    _ = page.goto(f"{ha_base_url}/config/dashboard")
    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture
def addon_config_page(ha_config_page: Page, ha_base_url: str):
    """Navigate to Cync Controller add-on page."""
    page = ha_config_page

    # Click Settings
    settings_link = page.get_by_role("link", name=re.compile(r"settings", re.IGNORECASE))
    if settings_link.is_visible():
        settings_link.click()

    # Navigate to Add-ons
    _ = page.goto(f"{ha_base_url}/hassio/dashboard")
    page.wait_for_load_state("networkidle")

    # Click on Cync Controller add-on
    addon_link = page.get_by_text(re.compile(r"cync controller", re.IGNORECASE))
    addon_link.first.click()

    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture
def cync_devices_page(ha_login: Page, ha_base_url: str):
    """Navigate to Cync devices in Home Assistant."""
    page = ha_login

    # Navigate to MQTT integration
    _ = page.goto(f"{ha_base_url}/config/integrations/integration/mqtt")
    page.wait_for_load_state("networkidle")

    return page
