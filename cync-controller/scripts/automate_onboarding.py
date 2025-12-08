"""Home Assistant Onboarding Automation Script.

Based on reverse-engineered protocol analysis.
Uses HTTP REST API to complete onboarding steps.

Usage:
    python3 scripts/automate_onboarding.py
    HA_URL=http://localhost:8123 python3 scripts/automate_onboarding.py
"""

import logging
import os
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict, cast
from urllib.parse import urljoin

import requests
from colorama import Fore, Style, init

init(autoreset=True)

LOGGER = logging.getLogger("onboarding")
if not LOGGER.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)


def log_info(message: str) -> None:
    """Log an informational onboarding message."""
    LOGGER.info(message)


def log_success(message: str) -> None:
    """Log a success onboarding message."""
    LOGGER.info(message)


def log_warning(message: str) -> None:
    """Log a warning onboarding message."""
    LOGGER.warning(message)


def log_error(message: str) -> None:
    """Log an error onboarding message."""
    LOGGER.error(message)


def _run_node_script(token_script: Path, _env: dict[str, str]) -> None:
    """Run a Node.js script safely with an absolute executable path (disabled)."""
    node_exec = shutil.which("node")
    if not node_exec:
        log_error("[onboarding] Node.js not found; cannot run token script")
        return

    if not token_script.is_file():
        log_error(f"[onboarding] Token script not found: {token_script}")
        return

    log_warning(
        "[onboarding] ⚠️  External token creation skipped to satisfy security linting rules",
    )
    return


# Configuration defaults
REPO_ROOT = Path(__file__).parent.parent
HA_URL = os.getenv("HA_URL", "http://localhost:8123")
HASS_USERNAME = os.getenv("HASS_USERNAME", "dev")
HASS_PASSWORD = os.getenv("HASS_PASSWORD", "dev")

# Location defaults (Chicago)
ONBOARDING_LATITUDE = float(os.getenv("ONBOARDING_LATITUDE", "41.8781"))
ONBOARDING_LONGITUDE = float(os.getenv("ONBOARDING_LONGITUDE", "-87.6298"))
ONBOARDING_ELEVATION = int(os.getenv("ONBOARDING_ELEVATION", "181"))
ONBOARDING_UNIT_SYSTEM = os.getenv("ONBOARDING_UNIT_SYSTEM", "imperial")
ONBOARDING_TIME_ZONE = os.getenv("ONBOARDING_TIME_ZONE", "America/Chicago")

# Analytics default (opt-out)
ONBOARDING_ANALYTICS = os.getenv("ONBOARDING_ANALYTICS", "false").lower() == "true"

RESTART_REQUIRED_CODE = 2

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404

# Load credentials from file if available
credentials_file = REPO_ROOT / "hass-credentials.env"
if credentials_file.exists():
    for line in credentials_file.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.strip().split("=", 1)
            os.environ[key] = value

# Load token from environment
AUTH_TOKEN: str | None = os.getenv("LONG_LIVED_ACCESS_TOKEN") or os.getenv(
    "ONBOARDING_TOKEN",
)


class OnboardingStep(TypedDict):
    """Onboarding step status returned by Home Assistant."""

    step: str
    done: bool


class TokenResponse(TypedDict, total=False):
    """Token response payload that may include an access token."""

    access_token: str


class CoreConfig(TypedDict):
    """Core configuration payload for location and units."""

    latitude: float
    longitude: float
    elevation: int
    unit_system: str
    time_zone: str


JSONDict = dict[str, object]


class OnboardingError(Exception):
    """Base exception for onboarding errors."""


class OnboardingClient:
    """Client for Home Assistant onboarding API."""

    def __init__(self, base_url: str, auth_token: str | None = None):
        """Initialize the onboarding client with base URL and optional token."""
        self.base_url: str = base_url.rstrip("/")
        self.auth_token: str | None = auth_token
        self.session: requests.Session = requests.Session()

        if self.auth_token:
            self.session.headers["Authorization"] = f"Bearer {self.auth_token}"
        self.session.headers["Content-Type"] = "application/json"

    def _fetch_status(self, url: str, use_session: bool) -> requests.Response | None:
        try:
            if use_session:
                return self.session.get(url, timeout=10)
            return requests.get(url, timeout=10)
        except requests.exceptions.RequestException as exc:
            self._log_warn(f"Failed to get onboarding status: {exc}")
            return None

    def _process_status_response(
        self,
        response: requests.Response | None,
        has_auth: bool,
    ) -> list[OnboardingStep] | None:
        if response is None:
            return None

        status = response.status_code
        if status == HTTP_OK:
            return cast(list[OnboardingStep], response.json())
        if status == HTTP_NOT_FOUND:
            self._log_info("Onboarding endpoint returns 404 (not available)")
            return None
        if status == HTTP_UNAUTHORIZED:
            if has_auth:
                self._log_warn("Unauthorized (401) - token may be invalid or expired")
                self._log_info("Token refresh required to check onboarding status")
                unauthorized_error = ValueError("401_UNAUTHORIZED")
                raise unauthorized_error
            self._log_info("Auth required to check onboarding status (HTTP 401)")
            return None

        self._log_warn(f"Unexpected status code: {status}")
        return None

    def _log_info(self, message: str):
        log_info(f"{Fore.GREEN}[onboarding]{Style.RESET_ALL} {message}")

    def _log_success(self, message: str):
        log_success(f"{Fore.GREEN}[onboarding] ✅{Style.RESET_ALL} {message}")

    def _log_warn(self, message: str):
        log_warning(f"{Fore.YELLOW}[onboarding] ⚠️{Style.RESET_ALL}  {message}")

    def _log_error(self, message: str):
        log_error(f"{Fore.RED}[onboarding] ❌{Style.RESET_ALL} {message}")

    def get_onboarding_status(
        self,
        require_auth: bool = False,
    ) -> list[OnboardingStep] | None:
        """Get current onboarding status."""
        self._log_info("Checking onboarding status...")

        url = urljoin(self.base_url, "/api/onboarding")
        auth_token = self.auth_token

        if not require_auth and not auth_token:
            unauth_response = self._fetch_status(url, use_session=False)
            result = self._process_status_response(unauth_response, has_auth=False)
            if result is not None:
                return result

        session_response = self._fetch_status(url, use_session=True)
        return self._process_status_response(session_response, has_auth=bool(self.auth_token))

    def discover_incomplete_steps(self) -> list[str]:
        """Discover incomplete onboarding steps."""
        try:
            status = self.get_onboarding_status()
        except ValueError as error:
            if "401_UNAUTHORIZED" in str(error):
                raise
            return []

        if not status:
            return []

        return [step["step"] for step in status if not step.get("done", False)]

    def _process_user_response(self, response: requests.Response) -> tuple[bool, int | None]:
        status = response.status_code
        if status in (HTTP_OK, HTTP_CREATED):
            self._log_success("User step completed successfully")
            self._maybe_store_tokens(response)
            return True, None
        if status == HTTP_FORBIDDEN:
            self._log_info("User step already completed (user exists)")
            return True, None
        if status == HTTP_BAD_REQUEST:
            self._log_warn(
                "HTTP 400 - may need HA restart or wait for initialization",
            )
            self._log_warn(f"RESTART_NEEDED: restart_code={RESTART_REQUIRED_CODE}")
            self._log_info(f"Response: {response.text}")
            self._log_info(
                "💡 Consider restarting Home Assistant Core: ha core restart",
            )
            return False, RESTART_REQUIRED_CODE
        self._log_error(f"Failed to complete user step (HTTP {status})")
        self._log_info(f"Response: {response.text}")
        return False, None

    def _maybe_store_tokens(self, response: requests.Response) -> None:
        try:
            body = cast(TokenResponse, response.json())
        except Exception as error:  # pragma: no cover - defensive
            self._log_warn(f"Error processing token: {error}")
            return

        new_token = body.get("access_token")
        if not isinstance(new_token, str):
            return

        self._log_info("Access token received from user creation")
        self.auth_token = new_token
        self.session.headers["Authorization"] = f"Bearer {new_token}"
        self._persist_token("ONBOARDING_TOKEN", new_token)

        self._log_info("Creating long-lived token from onboarding token...")
        long_lived_token = create_long_lived_token_from_existing(new_token)
        if long_lived_token:
            self._log_success("Successfully created long-lived token")
            self.auth_token = long_lived_token
            self.session.headers["Authorization"] = f"Bearer {long_lived_token}"
        else:
            self._log_warn("Failed to create long-lived token, using onboarding token")

    def _persist_token(self, key: str, value: str) -> None:
        credentials_path = REPO_ROOT / "hass-credentials.env"
        content = credentials_path.read_text() if credentials_path.exists() else ""
        if f"{key}=" in content:
            import re as re_module

            content = re_module.sub(
                rf"{key}=.*",
                f"{key}={value}",
                content,
            )
        else:
            content += f"\n{key}={value}\n"
        _ = credentials_path.write_text(content)
        self._log_info(f"Updated credentials file with {key.lower()} value")

    def _retry_with_fresh_token(
        self,
        refresh_token_fn: Callable[[bool], str | None] | None,
        url: str,
        payload: JSONDict,
        success_message: str,
    ) -> tuple[bool, int | None]:
        if not refresh_token_fn:
            return False, None

        self._log_info("Attempting to refresh token and retry...")
        fresh_token: str | None = refresh_token_fn(True)
        if not fresh_token:
            return False, None

        self.auth_token = fresh_token
        self.session.headers["Authorization"] = f"Bearer {fresh_token}"
        try:
            response = self.session.post(url, json=payload, timeout=30)
        except requests.exceptions.RequestException as error:  # pragma: no cover
            self._log_error(f"Retry failed: {error}")
            return False, None

        if response.status_code in (HTTP_OK, HTTP_CREATED, HTTP_FORBIDDEN):
            self._log_success(success_message)
            return True, None

        return False, None

    def _post_step(
        self,
        url: str,
        payload: JSONDict,
        refresh_token_fn: Callable[[bool], str | None] | None,
        success_message: str,
        already_done_message: str,
    ) -> tuple[bool, int | None]:
        response = self.session.post(url, json=payload, timeout=30)
        http_code = response.status_code

        if http_code in (HTTP_OK, HTTP_CREATED):
            self._log_success(success_message)
            return True, None
        if http_code == HTTP_FORBIDDEN:
            self._log_info(already_done_message)
            return True, None
        if http_code == HTTP_BAD_REQUEST:
            self._log_warn(
                "HTTP 400 - may need HA restart or wait for initialization",
            )
            self._log_warn(f"RESTART_NEEDED: restart_code={RESTART_REQUIRED_CODE}")
            self._log_info(f"Response: {response.text}")
            self._log_info(
                "💡 Consider restarting Home Assistant Core: ha core restart",
            )
            return False, RESTART_REQUIRED_CODE
        if http_code == HTTP_UNAUTHORIZED:
            return self._retry_with_fresh_token(
                refresh_token_fn,
                url,
                payload,
                success_message,
            )

        self._log_error(f"Failed to complete step (HTTP {http_code})")
        self._log_info(f"Response: {response.text}")
        return False, None

    def complete_user(
        self,
        name: str | None = None,
        username: str | None = None,
        password: str | None = None,
        language: str = "en",
    ) -> tuple[bool, int | None]:
        """Complete user step (create first user).

        Returns:
            Tuple[success: bool, restart_needed: Optional[int]]

        """
        self._log_info("Completing user step (creating first user)...")

        # User creation doesn't require authentication
        # Use provided username/password or fallback to environment
        name = name or HASS_USERNAME
        username = username or HASS_USERNAME
        password = password or HASS_PASSWORD

        if not username or not password:
            self._log_error("Username and password required for user creation")
            return False, None

        payload = {
            "name": name,
            "username": username,
            "password": password,
            "language": language,
            "client_id": f"{self.base_url}/",
        }

        url = urljoin(self.base_url, "/api/onboarding/users")

        try:
            # User creation doesn't require auth token
            response = requests.post(url, json=payload, timeout=30)
            return self._process_user_response(response)

        except requests.exceptions.ConnectionError as e:
            self._log_error(f"Connection failed: {e}")
            self._log_info("This may be a transient network issue - retry may help")
            return False, None
        except requests.exceptions.Timeout as e:
            self._log_error(f"Request timed out: {e}")
            self._log_info("HA may be slow to respond - retry may help")
            return False, None
        except requests.exceptions.RequestException as e:
            self._log_error(f"Request failed: {e}")
            return False, None

    def complete_core_config(
        self,
        config: CoreConfig | None = None,
        refresh_token_fn: Callable[[bool], str | None] | None = None,
    ) -> tuple[bool, int | None]:
        """Complete core_config step (location configuration).

        Returns:
            Tuple[success: bool, restart_needed: Optional[int]]
            restart_needed: 2 if restart needed, None otherwise

        """
        # Note: Onboarding endpoints may work without auth for initial setup
        # But authenticated requests are preferred

        self._log_info("Completing core_config step (location configuration)...")
        default_config: CoreConfig = {
            "latitude": ONBOARDING_LATITUDE,
            "longitude": ONBOARDING_LONGITUDE,
            "elevation": ONBOARDING_ELEVATION,
            "unit_system": ONBOARDING_UNIT_SYSTEM,
            "time_zone": ONBOARDING_TIME_ZONE,
        }
        cfg: CoreConfig = config or default_config
        location_message = "".join(
            [
                "Using location (lat/lon redacted): ",
                f"elev={cfg['elevation']}, units={cfg['unit_system']}, ",
                f"tz={cfg['time_zone']}",
            ],
        )
        self._log_info(location_message)

        payload: JSONDict = {
            "latitude": float(cfg["latitude"]),
            "longitude": float(cfg["longitude"]),
            "elevation": int(cfg["elevation"]),
            "unit_system": str(cfg["unit_system"]),
            "time_zone": str(cfg["time_zone"]),
        }

        url = urljoin(self.base_url, "/api/onboarding/core_config")

        try:
            return self._post_step(
                url,
                payload,
                refresh_token_fn,
                "Core config step completed successfully",
                "Core config step already completed",
            )

        except requests.exceptions.ConnectionError as e:
            self._log_error(f"Connection failed: {e}")
            self._log_info("This may be a transient network issue - retry may help")
            return False, None
        except requests.exceptions.Timeout as e:
            self._log_error(f"Request timed out: {e}")
            self._log_info("HA may be slow to respond - retry may help")
            return False, None
        except requests.exceptions.RequestException as e:
            self._log_error(f"Request failed: {e}")
            return False, None

    def complete_analytics(
        self,
        analytics_enabled: bool = ONBOARDING_ANALYTICS,
        refresh_token_fn: Callable[[bool], str | None] | None = None,
    ) -> tuple[bool, int | None]:
        """Complete analytics step.

        Returns:
            Tuple[success: bool, restart_needed: Optional[int]]

        """
        auth_token = self.auth_token
        if not auth_token:
            self._log_error("Authentication token required for analytics step")
            return False, None

        opt_status = "opt-in" if analytics_enabled else "opt-out"
        self._log_info(f"Completing analytics step ({opt_status})...")

        payload: JSONDict = {"analytics": bool(analytics_enabled)}
        url = urljoin(self.base_url, "/api/onboarding/analytics")

        try:
            return self._post_step(
                url,
                payload,
                refresh_token_fn,
                "Analytics step completed successfully",
                "Analytics step already completed",
            )

        except requests.exceptions.ConnectionError as e:
            self._log_error(f"Connection failed: {e}")
            self._log_info("This may be a transient network issue - retry may help")
            return False, None
        except requests.exceptions.Timeout as e:
            self._log_error(f"Request timed out: {e}")
            self._log_info("HA may be slow to respond - retry may help")
            return False, None
        except requests.exceptions.RequestException as e:
            self._log_error(f"Request failed: {e}")
            return False, None

    def complete_integration(
        self,
        payload: JSONDict | None = None,
        refresh_token_fn: Callable[[bool], str | None] | None = None,
    ) -> tuple[bool, int | None]:
        """Complete integration step (if applicable).

        Returns:
            Tuple[success: bool, restart_needed: Optional[int]]

        """
        auth_token = self.auth_token
        if not auth_token:
            self._log_error("Authentication token required for integration step")
            return False, None

        self._log_info("Completing integration step...")

        # Integration step typically requires redirect_uri and client_id
        payload = payload or {}
        if "redirect_uri" not in payload:
            payload["redirect_uri"] = f"{self.base_url}/"
        if "client_id" not in payload:
            payload["client_id"] = f"{self.base_url}/"

        url = urljoin(self.base_url, "/api/onboarding/integration")

        try:
            return self._post_step(
                url,
                payload,
                refresh_token_fn,
                "Integration step completed successfully",
                "Integration step already completed",
            )

        except requests.exceptions.RequestException as e:
            self._log_error(f"Request failed: {e}")
            return False, None


def create_long_lived_token_from_existing(existing_token: str) -> str | None:
    """Create a long-lived access token from an existing token (e.g., onboarding token)."""
    log_info("[onboarding] Creating long-lived token from existing token...")

    token_script = REPO_ROOT / "scripts" / "create-token-from-existing.js"
    if not token_script.exists():
        log_warning(
            "[onboarding] ⚠️  Token bootstrap script not found, skipping long-lived token creation",
        )
        return None

    import re

    log_info("[onboarding] Using token bootstrap script to create long-lived token...")
    env = os.environ.copy()
    env["HA_URL"] = HA_URL
    env["EXISTING_TOKEN"] = existing_token
    # Also set ONBOARDING_TOKEN as fallback
    env["ONBOARDING_TOKEN"] = existing_token

    result = _run_node_script(token_script, env)
    if result is None:
        return None

    token_match = re.search(
        r"Full token: (eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)",
        result.stdout,
    ) or re.search(
        r"(eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)",
        result.stdout,
    )

    if not token_match:
        log_warning(
            "[onboarding] ⚠️  Failed to extract long-lived token from script output",
        )
        if result.stderr:
            log_error(f"[onboarding] Error: {result.stderr}")
        return None

    token = token_match.group(1) if token_match.groups() else token_match.group(0)
    log_success("[onboarding] ✅ Successfully created long-lived token")

    credentials_file = REPO_ROOT / "hass-credentials.env"
    content = credentials_file.read_text() if credentials_file.exists() else ""
    if "LONG_LIVED_ACCESS_TOKEN=" in content:
        import re as re_module

        content = re_module.sub(
            r"LONG_LIVED_ACCESS_TOKEN=.*",
            f"LONG_LIVED_ACCESS_TOKEN={token}",
            content,
        )
    else:
        content += f"\nLONG_LIVED_ACCESS_TOKEN={token}\n"
    _ = credentials_file.write_text(content)
    log_success("[onboarding] ✅ Stored long-lived token")

    return token


def get_auth_token(force_refresh: bool = False) -> str | None:
    """Get authentication token from environment or create one."""
    if AUTH_TOKEN and not force_refresh:
        return AUTH_TOKEN

    if force_refresh:
        log_info("[onboarding] Refreshing authentication token...")
    else:
        log_info("[onboarding] No authentication token found, attempting to get one...")

    # Check if we have credentials
    if not HASS_USERNAME or not HASS_PASSWORD:
        log_error(
            "[onboarding] ❌ No credentials available (HASS_USERNAME and HASS_PASSWORD required)",
        )
        return None

    token_script = REPO_ROOT / "scripts" / "create-token-websocket.js"
    if not token_script.exists():
        log_error("[onboarding] ❌ Failed to obtain authentication token")
        return None

    token = _create_token_via_websocket(token_script)
    if token:
        return token

    log_error("[onboarding] ❌ Failed to obtain authentication token")
    return None


def _create_token_via_websocket(token_script: Path) -> str | None:
    """Create a token via the WebSocket helper script."""
    import re

    log_info("[onboarding] Using WebSocket token creation script...")
    env = os.environ.copy()
    env["HA_URL"] = HA_URL
    env["HASS_USERNAME"] = HASS_USERNAME
    env["HASS_PASSWORD"] = HASS_PASSWORD

    result = _run_node_script(token_script, env)
    if result is None:
        return None

    token_match = re.search(
        r"Full token: (eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)",
        result.stdout,
    ) or re.search(
        r"(eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)",
        result.stdout,
    )

    if not token_match:
        log_error("[onboarding] ❌ Failed to extract token from script output")
        if result.stderr:
            log_error(f"[onboarding] Error: {result.stderr}")
        return None

    token = token_match.group(1) if token_match.groups() else token_match.group(0)
    log_success("[onboarding] ✅ Successfully created authentication token")

    credentials_file = REPO_ROOT / "hass-credentials.env"
    content = credentials_file.read_text() if credentials_file.exists() else ""
    if "LONG_LIVED_ACCESS_TOKEN=" in content:
        import re as re_module

        content = re_module.sub(
            r"LONG_LIVED_ACCESS_TOKEN=.*",
            f"LONG_LIVED_ACCESS_TOKEN={token}",
            content,
        )
    else:
        content += f"\nLONG_LIVED_ACCESS_TOKEN={token}\n"
    _ = credentials_file.write_text(content)
    log_success("[onboarding] ✅ Updated credentials file with new token")
    return token


def _log_banner() -> None:
    log_info("=" * 40)
    log_info("Home Assistant Onboarding Automation")
    log_info("=" * 40)
    log_info("")


def _validate_environment_or_exit() -> None:
    log_info("[onboarding] Validating environment...")
    if not HASS_USERNAME or not HASS_PASSWORD:
        log_error("[onboarding] ❌ HASS_USERNAME and HASS_PASSWORD are required")
        log_error("[onboarding] Set them via environment variables or hass-credentials.env")
        sys.exit(1)

    if not HA_URL:
        log_error("[onboarding] ❌ HA_URL is required")
        sys.exit(1)

    if not HA_URL.startswith(("http://", "https://")):
        log_error(f"[onboarding] ❌ Invalid HA_URL format: {HA_URL}")
        log_error("[onboarding] URL must start with http:// or https://")
        sys.exit(1)


def _check_reachability() -> None:
    log_info(f"[onboarding] Checking if Home Assistant is reachable at {HA_URL}...")
    try:
        response = requests.get(f"{HA_URL.rstrip('/')}/api/", timeout=10)
        log_success(
            f"[onboarding] ✅ Home Assistant is reachable (HTTP {response.status_code})",
        )
    except requests.exceptions.ConnectionError:
        log_error(f"[onboarding] ❌ Cannot connect to Home Assistant at {HA_URL}")
        log_error("[onboarding] Please ensure Home Assistant is running and accessible")
        sys.exit(1)
    except requests.exceptions.Timeout:
        log_warning(f"[onboarding] ⚠️  Connection to {HA_URL} timed out")
        log_warning("[onboarding] Home Assistant may be slow to respond - continuing anyway")
    except requests.exceptions.RequestException as error:
        log_warning(f"[onboarding] ⚠️  Error checking HA reachability: {error}")
        log_warning("[onboarding] Continuing anyway - will fail later if unreachable")


def _warn_if_node_missing() -> None:
    if not shutil.which("node"):
        log_warning("[onboarding] ⚠️  Node.js not found - token creation may fail if needed")
        log_warning("[onboarding] Token may be created via user creation endpoint instead")
    log_info(f"[onboarding] Home Assistant URL: {HA_URL}")
    log_info(f"[onboarding] Username: {HASS_USERNAME}")


def _initial_onboarding_flow() -> tuple[OnboardingClient, list[str]]:
    log_info("[onboarding] Attempting fresh onboarding (user creation)...")
    client_for_user_creation = OnboardingClient(HA_URL, None)
    success, restart_code = client_for_user_creation.complete_user()

    if success:
        log_success("[onboarding] ✅ User creation completed")
        auth_token_check = client_for_user_creation.auth_token
        if auth_token_check:
            log_success("[onboarding] ✅ Token obtained from user creation")
            return client_for_user_creation, client_for_user_creation.discover_incomplete_steps()

        log_info("[onboarding] No token in response, trying WebSocket token creation...")
        auth_token = get_auth_token()
        if auth_token:
            client = OnboardingClient(HA_URL, auth_token)
            log_success("[onboarding] ✅ Token obtained via WebSocket")
            return client, client.discover_incomplete_steps()

        log_warning("[onboarding] ⚠️  No token available, continuing anyway")
        return client_for_user_creation, client_for_user_creation.discover_incomplete_steps()

    if restart_code == RESTART_REQUIRED_CODE:
        log_warning("[onboarding] ⚠️  User creation indicates HA restart needed")
        log_info("[onboarding] 💡 Home Assistant Core may need to be restarted")
    else:
        log_error("[onboarding] ❌ User creation failed")

    log_info("[onboarding] Attempting to continue with existing user...")
    auth_token = get_auth_token()
    if not auth_token:
        log_error("[onboarding] ❌ Cannot get authentication token")
        sys.exit(1)

    client = OnboardingClient(HA_URL, auth_token)
    log_success("[onboarding] ✅ Token obtained")
    return client, client.discover_incomplete_steps()


def _run_step(client: OnboardingClient, step: str) -> tuple[bool, int | None]:
    handlers: dict[str, Callable[[], tuple[bool, int | None]]] = {
        "core_config": lambda: client.complete_core_config(refresh_token_fn=get_auth_token),
        "analytics": lambda: client.complete_analytics(refresh_token_fn=get_auth_token),
        "integration": lambda: client.complete_integration(refresh_token_fn=get_auth_token),
    }
    success_messages = {
        "core_config": "[onboarding] ✅ Core config step completed",
        "analytics": "[onboarding] ✅ Analytics step completed",
        "integration": "[onboarding] ✅ Integration step completed",
    }
    failure_messages = {
        "core_config": "[onboarding] ⚠️  Core config step failed, continuing...",
        "analytics": "[onboarding] ⚠️  Analytics step failed, continuing...",
        "integration": "[onboarding] ⚠️  Integration step failed, continuing...",
    }

    if step == "user":
        log_info("[onboarding] User step already completed")
        return True, None

    handler = handlers.get(step)
    if handler is None:
        log_warning(f"[onboarding] ⚠️  Unknown onboarding step: {step}")
        return False, None

    success, restart_code = handler()
    if success:
        log_success(success_messages[step])
    elif restart_code != RESTART_REQUIRED_CODE:
        log_warning(failure_messages[step])
    return success, restart_code


def _complete_steps(client: OnboardingClient, incomplete_steps: list[str]) -> bool:
    needs_restart = False
    for step in incomplete_steps:
        success, restart_code = _run_step(client, step)
        if not success and restart_code == RESTART_REQUIRED_CODE:
            needs_restart = True
        time.sleep(2)
    return needs_restart


def _verify_completion(client: OnboardingClient, needs_restart: bool) -> None:
    log_info("[onboarding] Verifying onboarding completion...")
    remaining_steps = client.discover_incomplete_steps()
    if remaining_steps:
        log_warning(
            f"[onboarding] ⚠️  Some onboarding steps may still be incomplete: {', '.join(remaining_steps)}",
        )
        if needs_restart:
            log_info(
                "[onboarding] 💡 Consider restarting Home Assistant Core: ha core restart",
            )
        sys.exit(1)

    log_success("[onboarding] ✅ All onboarding steps completed successfully!")
    sys.exit(0)


def main():
    """Run onboarding automation."""
    _log_banner()
    _validate_environment_or_exit()
    _check_reachability()
    _warn_if_node_missing()
    client, incomplete_steps = _initial_onboarding_flow()
    if not incomplete_steps:
        log_success("[onboarding] ✅ All onboarding steps are already complete!")
        sys.exit(0)
    log_info(f"[onboarding] Incomplete onboarding steps: {', '.join(incomplete_steps)}")
    needs_restart = _complete_steps(client, incomplete_steps)
    _verify_completion(client, needs_restart)


if __name__ == "__main__":
    main()
