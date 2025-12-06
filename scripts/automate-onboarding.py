"""Home Assistant Onboarding Automation Script

Based on reverse-engineered protocol analysis.
Uses HTTP REST API to complete onboarding steps.

Usage:
    python3 scripts/automate-onboarding.py
    HA_URL=http://localhost:8123 python3 scripts/automate-onboarding.py
"""

import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from urllib.parse import urljoin

import requests
from colorama import Fore, Style, init

init(autoreset=True)

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


class OnboardingError(Exception):
    """Base exception for onboarding errors"""


class OnboardingClient:
    """Client for Home Assistant onboarding API"""

    def __init__(self, base_url: str, auth_token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.session = requests.Session()

        if self.auth_token:
            self.session.headers["Authorization"] = f"Bearer {self.auth_token}"
        self.session.headers["Content-Type"] = "application/json"

    def _log_info(self, message: str):
        print(f"{Fore.GREEN}[onboarding]{Style.RESET_ALL} {message}")

    def _log_success(self, message: str):
        print(f"{Fore.GREEN}[onboarding] ✅{Style.RESET_ALL} {message}")

    def _log_warn(self, message: str):
        print(f"{Fore.YELLOW}[onboarding] ⚠️{Style.RESET_ALL}  {message}")

    def _log_error(self, message: str):
        print(f"{Fore.RED}[onboarding] ❌{Style.RESET_ALL} {message}")

    def get_onboarding_status(
        self,
        require_auth: bool = False,
    ) -> list[dict[str, Any]] | None:
        """Get current onboarding status.

        Args:
            require_auth: If False, try without auth first (for initial state)

        """
        self._log_info("Checking onboarding status...")

        url = urljoin(self.base_url, "/api/onboarding")
        try:
            # Try without auth first if not required (works when onboarding is in progress)
            auth_token: str | None = cast("str | None", self.auth_token)  # type: ignore[reportUnknownMemberType]
            if not require_auth and not auth_token:
                try:
                    response = requests.get(url, timeout=10)
                    if response.status_code == 200:
                        return response.json()
                    if response.status_code == 404:
                        # 404 means either: (1) no owner user yet, or (2) already complete
                        # Attempt user creation to disambiguate (idempotent operation)
                        self._log_info(
                            "Onboarding endpoint returns 404 (not available)",
                        )
                        return None
                    if response.status_code == 401:
                        # 401 without auth token means auth is required
                        # This doesn't necessarily mean onboarding is complete
                        # We need auth to check the actual status
                        self._log_info(
                            "Auth required to check onboarding status (HTTP 401)",
                        )
                        # Return None to indicate we need auth - caller should get auth and retry
                        # We'll distinguish this case from "complete" by checking if we have auth
                        return None
                except requests.exceptions.RequestException:
                    # Fall through to try with session if available
                    pass

            # Try with session (includes auth if available)
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
            if response.status_code == 404:
                # 404 means either: (1) no owner user yet, or (2) already complete
                # Attempt user creation to disambiguate (idempotent operation)
                self._log_info("Onboarding endpoint returns 404 (not available)")
                return None
            if response.status_code == 401:
                # 401 with auth token means invalid/expired token - NOT complete
                # Need to refresh token and retry
                self._log_warn("Unauthorized (401) - token may be invalid or expired")
                self._log_info("Token refresh required to check onboarding status")
                # Return a special marker to indicate 401 (not None, which means complete)
                # Caller should refresh token and retry
                raise ValueError("401_UNAUTHORIZED")
            self._log_warn(f"Unexpected status code: {response.status_code}")
            return None
        except ValueError as e:
            # Re-raise 401 errors so caller can handle token refresh
            if "401_UNAUTHORIZED" in str(e):
                raise
            return None
        except requests.exceptions.RequestException as e:
            self._log_warn(f"Failed to get onboarding status: {e}")
            return None

    def discover_incomplete_steps(self) -> list[str]:
        """Discover incomplete onboarding steps"""
        try:
            status = self.get_onboarding_status()
            if not status:
                return []

            incomplete = [step["step"] for step in status if not step.get("done", False)]
            return incomplete
        except ValueError as e:
            # Handle 401 errors - propagate to caller for token refresh
            if "401_UNAUTHORIZED" in str(e):
                raise
            return []

    def complete_user(
        self,
        name: str | None = None,
        username: str | None = None,
        password: str | None = None,
        language: str = "en",
    ) -> tuple[bool, int | None]:
        """Complete user step (create first user)

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
            http_code = response.status_code

            if http_code in (200, 201):
                self._log_success("User step completed successfully")
                # Extract token from response if available
                try:
                    body = response.json()
                    if "access_token" in body:
                        new_token = body["access_token"]
                        self._log_info("Access token received from user creation")
                        # Update session with new token
                        self.auth_token = new_token
                        self.session.headers["Authorization"] = f"Bearer {new_token}"
                        # Update credentials file
                        # Save short-lived onboarding token as ONBOARDING_TOKEN (not LONG_LIVED_ACCESS_TOKEN)
                        credentials_file = REPO_ROOT / "hass-credentials.env"
                        if credentials_file.exists():
                            content = credentials_file.read_text()
                            # Update or add ONBOARDING_TOKEN
                            if "ONBOARDING_TOKEN=" in content:
                                import re as re_module

                                content = re_module.sub(
                                    r"ONBOARDING_TOKEN=.*",
                                    f"ONBOARDING_TOKEN={new_token}",
                                    content,
                                )
                            else:
                                content += f"\nONBOARDING_TOKEN={new_token}\n"
                            credentials_file.write_text(content)
                            self._log_info(
                                "Updated credentials file with onboarding token (ONBOARDING_TOKEN)",
                            )
                        else:
                            # Create file if it doesn't exist
                            credentials_file.write_text(
                                f"ONBOARDING_TOKEN={new_token}\n",
                            )
                            self._log_info(
                                "Created credentials file with onboarding token (ONBOARDING_TOKEN)",
                            )

                        # Immediately create a long-lived token from the onboarding token
                        self._log_info(
                            "Creating long-lived token from onboarding token...",
                        )
                        long_lived_token = create_long_lived_token_from_existing(
                            new_token,
                        )
                        if long_lived_token:
                            self._log_success("Successfully created long-lived token")
                            # Update session with long-lived token
                            self.auth_token = long_lived_token
                            self.session.headers["Authorization"] = f"Bearer {long_lived_token}"
                        else:
                            self._log_warn(
                                "Failed to create long-lived token, using onboarding token",
                            )
                            # Continue with onboarding token - fallback script will try later
                except Exception as e:
                    # Token extraction is optional
                    self._log_warn(f"Error processing token: {e}")
                return True, None
            if http_code == 403:
                self._log_info("User step already completed (user exists)")
                return True, None
            if http_code == 400:
                self._log_warn(
                    "HTTP 400 - may need HA restart or wait for initialization",
                )
                self._log_warn("RESTART_NEEDED: restart_code=2")
                self._log_info(f"Response: {response.text}")
                self._log_info(
                    "💡 Consider restarting Home Assistant Core: ha core restart",
                )
                return False, 2
            self._log_error(f"Failed to complete user step (HTTP {http_code})")
            self._log_info(f"Response: {response.text}")
            return False, None

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
        latitude: float = ONBOARDING_LATITUDE,
        longitude: float = ONBOARDING_LONGITUDE,
        elevation: int = ONBOARDING_ELEVATION,
        unit_system: str = ONBOARDING_UNIT_SYSTEM,
        time_zone: str = ONBOARDING_TIME_ZONE,
        refresh_token_fn: Callable[[bool], str | None] | None = None,
    ) -> tuple[bool, int | None]:
        """Complete core_config step (location configuration)

        Returns:
            Tuple[success: bool, restart_needed: Optional[int]]
            restart_needed: 2 if restart needed, None otherwise

        """
        # Note: Onboarding endpoints may work without auth for initial setup
        # But authenticated requests are preferred

        self._log_info("Completing core_config step (location configuration)...")
        self._log_info(
            f"Using location: lat={latitude}, lon={longitude}, elev={elevation}, units={unit_system}, tz={time_zone}",
        )

        payload = {
            "latitude": latitude,
            "longitude": longitude,
            "elevation": elevation,
            "unit_system": unit_system,
            "time_zone": time_zone,
        }

        url = urljoin(self.base_url, "/api/onboarding/core_config")

        try:
            response = self.session.post(url, json=payload, timeout=30)
            http_code = response.status_code

            if http_code in (200, 201):
                self._log_success("Core config step completed successfully")
                return True, None
            if http_code == 403:
                self._log_info("Core config step already completed")
                return True, None
            if http_code == 400:
                self._log_warn(
                    "HTTP 400 - may need HA restart or wait for initialization",
                )
                self._log_warn("RESTART_NEEDED: restart_code=2")
                self._log_info(f"Response: {response.text}")
                self._log_info(
                    "💡 Consider restarting Home Assistant Core: ha core restart",
                )
                return False, 2
            if http_code == 401:
                self._log_error("Unauthorized - invalid token")
                # Try refreshing token and retry
                if refresh_token_fn:
                    self._log_info("Attempting to refresh token and retry...")
                    fresh_token: str | None = refresh_token_fn(True)
                    if fresh_token:
                        self.auth_token = fresh_token  # type: ignore[reportUnknownMemberType]
                        self.session.headers["Authorization"] = f"Bearer {fresh_token}"
                        try:
                            response = self.session.post(url, json=payload, timeout=30)
                            if response.status_code in (200, 201, 403):
                                self._log_success(
                                    "Core config step completed successfully",
                                )
                                return True, None
                        except Exception:
                            pass
                return False, None
            self._log_error(
                f"Failed to complete core_config step (HTTP {http_code})",
            )
            self._log_info(f"Response: {response.text}")
            return False, None

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
        """Complete analytics step

        Returns:
            Tuple[success: bool, restart_needed: Optional[int]]

        """
        auth_token: str | None = cast("str | None", self.auth_token)  # type: ignore[reportUnknownMemberType]
        if not auth_token:
            self._log_error("Authentication token required for analytics step")
            return False, None

        opt_status = "opt-in" if analytics_enabled else "opt-out"
        self._log_info(f"Completing analytics step ({opt_status})...")

        payload = {"analytics": analytics_enabled}
        url = urljoin(self.base_url, "/api/onboarding/analytics")

        try:
            response = self.session.post(url, json=payload, timeout=30)
            http_code = response.status_code

            if http_code in (200, 201):
                self._log_success("Analytics step completed successfully")
                return True, None
            if http_code == 403:
                self._log_info("Analytics step already completed")
                return True, None
            if http_code == 400:
                self._log_warn(
                    "HTTP 400 - may need HA restart or wait for initialization",
                )
                self._log_warn("RESTART_NEEDED: restart_code=2")
                self._log_info(f"Response: {response.text}")
                self._log_info(
                    "💡 Consider restarting Home Assistant Core: ha core restart",
                )
                return False, 2
            if http_code == 401:
                self._log_error("Unauthorized - invalid token")
                # Try refreshing token and retry
                if refresh_token_fn:
                    self._log_info("Attempting to refresh token and retry...")
                    fresh_token: str | None = refresh_token_fn(True)
                    if fresh_token:
                        self.auth_token = fresh_token  # type: ignore[reportUnknownMemberType]
                        self.session.headers["Authorization"] = f"Bearer {fresh_token}"
                        try:
                            response = self.session.post(url, json=payload, timeout=30)
                            if response.status_code in (200, 201, 403):
                                self._log_success(
                                    "Analytics step completed successfully",
                                )
                                return True, None
                        except Exception:
                            pass
                return False, None
            self._log_error(f"Failed to complete analytics step (HTTP {http_code})")
            self._log_info(f"Response: {response.text}")
            return False, None

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
        payload: dict[str, Any] | None = None,
        refresh_token_fn: Callable[[bool], str | None] | None = None,
    ) -> tuple[bool, int | None]:
        """Complete integration step (if applicable)

        Returns:
            Tuple[success: bool, restart_needed: Optional[int]]

        """
        auth_token: str | None = cast("str | None", self.auth_token)  # type: ignore[reportUnknownMemberType]
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
            response = self.session.post(url, json=payload, timeout=30)
            http_code = response.status_code

            if http_code in (200, 201):
                self._log_success("Integration step completed successfully")
                return True, None
            if http_code == 403:
                self._log_info("Integration step already completed")
                return True, None
            if http_code == 400:
                self._log_warn(
                    "HTTP 400 - may need HA restart or wait for initialization",
                )
                self._log_info(f"Response: {response.text}")
                return False, 2
            if http_code == 401:
                self._log_error("Unauthorized - invalid token")
                return False, None
            self._log_error(
                f"Failed to complete integration step (HTTP {http_code})",
            )
            self._log_info(f"Response: {response.text}")
            return False, None

        except requests.exceptions.RequestException as e:
            self._log_error(f"Request failed: {e}")
            return False, None


def create_long_lived_token_from_existing(existing_token: str) -> str | None:
    """Create a long-lived access token from an existing token (e.g., onboarding token)"""
    print("[onboarding] Creating long-lived token from existing token...")

    token_script = REPO_ROOT / "scripts" / "create-token-from-existing.js"
    if not token_script.exists():
        print(
            "[onboarding] ⚠️  Token bootstrap script not found, skipping long-lived token creation",
        )
        return None

    import re
    import subprocess

    print("[onboarding] Using token bootstrap script to create long-lived token...")
    env = os.environ.copy()
    env["HA_URL"] = HA_URL
    env["EXISTING_TOKEN"] = existing_token
    # Also set ONBOARDING_TOKEN as fallback
    env["ONBOARDING_TOKEN"] = existing_token

    try:
        result = subprocess.run(
            ["node", str(token_script)],
            check=False,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Extract token from output - try "Full token:" first, then any JWT pattern
        token_match = re.search(
            r"Full token: (eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)",
            result.stdout,
        )
        if not token_match:
            # Fallback to any JWT pattern
            token_match = re.search(
                r"(eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)",
                result.stdout,
            )

        if token_match:
            token = token_match.group(1) if token_match.groups() else token_match.group(0)
            print("[onboarding] ✅ Successfully created long-lived token")

            # Update credentials file if it exists
            credentials_file = REPO_ROOT / "hass-credentials.env"
            if credentials_file.exists():
                content = credentials_file.read_text()
                # Update or add LONG_LIVED_ACCESS_TOKEN
                if "LONG_LIVED_ACCESS_TOKEN=" in content:
                    import re as re_module

                    content = re_module.sub(
                        r"LONG_LIVED_ACCESS_TOKEN=.*",
                        f"LONG_LIVED_ACCESS_TOKEN={token}",
                        content,
                    )
                else:
                    content += f"\nLONG_LIVED_ACCESS_TOKEN={token}\n"
                credentials_file.write_text(content)
                print("[onboarding] ✅ Updated credentials file with long-lived token")
            else:
                # Create file if it doesn't exist
                credentials_file.write_text(f"LONG_LIVED_ACCESS_TOKEN={token}\n")
                print("[onboarding] ✅ Created credentials file with long-lived token")

            return token
        print(
            "[onboarding] ⚠️  Failed to extract long-lived token from script output",
        )
        if result.stderr:
            print(f"[onboarding] Error: {result.stderr}")
        return None

    except subprocess.TimeoutExpired:
        print("[onboarding] ⚠️  Token creation script timed out")
        return None
    except Exception as e:
        print(f"[onboarding] ⚠️  Failed to run token bootstrap script: {e}")
        return None


def get_auth_token(force_refresh: bool = False) -> str | None:
    """Get authentication token from environment or create one"""
    if AUTH_TOKEN and not force_refresh:
        return AUTH_TOKEN

    if force_refresh:
        print("[onboarding] Refreshing authentication token...")
    else:
        print("[onboarding] No authentication token found, attempting to get one...")

    # Check if we have credentials
    if not HASS_USERNAME or not HASS_PASSWORD:
        print(
            "[onboarding] ❌ No credentials available (HASS_USERNAME and HASS_PASSWORD required)",
        )
        return None

    # Try to get token via WebSocket script if available
    token_script = REPO_ROOT / "scripts" / "create-token-websocket.js"
    if token_script.exists():
        import re
        import subprocess

        print("[onboarding] Using WebSocket token creation script...")
        env = os.environ.copy()
        env["HA_URL"] = HA_URL
        env["HASS_USERNAME"] = HASS_USERNAME
        env["HASS_PASSWORD"] = HASS_PASSWORD

        try:
            result = subprocess.run(
                ["node", str(token_script)],
                check=False,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Extract token from output - try "Full token:" first, then any JWT pattern
            token_match = re.search(
                r"Full token: (eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)",
                result.stdout,
            )
            if not token_match:
                # Fallback to any JWT pattern
                token_match = re.search(
                    r"(eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)",
                    result.stdout,
                )

            if token_match:
                token = token_match.group(1) if token_match.groups() else token_match.group(0)
                print("[onboarding] ✅ Successfully created authentication token")

                # Update credentials file if it exists
                credentials_file = REPO_ROOT / "hass-credentials.env"
                if credentials_file.exists():
                    content = credentials_file.read_text()
                    # Update or add LONG_LIVED_ACCESS_TOKEN
                    if "LONG_LIVED_ACCESS_TOKEN=" in content:
                        import re as re_module

                        content = re_module.sub(
                            r"LONG_LIVED_ACCESS_TOKEN=.*",
                            f"LONG_LIVED_ACCESS_TOKEN={token}",
                            content,
                        )
                    else:
                        content += f"\nLONG_LIVED_ACCESS_TOKEN={token}\n"
                    credentials_file.write_text(content)
                    print("[onboarding] ✅ Updated credentials file with new token")

                return token
            print("[onboarding] ❌ Failed to extract token from script output")
            if result.stderr:
                print(f"[onboarding] Error: {result.stderr}")
            return None

        except subprocess.TimeoutExpired:
            print("[onboarding] ❌ Token creation script timed out")
            return None
        except Exception as e:
            print(f"[onboarding] ❌ Failed to run token script: {e}")
            return None

    print("[onboarding] ❌ Failed to obtain authentication token")
    return None


def main():
    """Main execution"""
    print("=" * 40)
    print("Home Assistant Onboarding Automation")
    print("=" * 40)
    print()

    # Pre-flight validation
    print("[onboarding] Validating environment...")

    # Check required environment variables
    if not HASS_USERNAME or not HASS_PASSWORD:
        print("[onboarding] ❌ HASS_USERNAME and HASS_PASSWORD are required")
        print("[onboarding] Set them via environment variables or hass-credentials.env")
        sys.exit(1)

    if not HA_URL:
        print("[onboarding] ❌ HA_URL is required")
        sys.exit(1)

    # Validate HA URL format
    if not HA_URL.startswith(("http://", "https://")):
        print(f"[onboarding] ❌ Invalid HA_URL format: {HA_URL}")
        print("[onboarding] URL must start with http:// or https://")
        sys.exit(1)

    # Check if HA URL is reachable (basic connectivity test)
    print(f"[onboarding] Checking if Home Assistant is reachable at {HA_URL}...")
    try:
        response = requests.get(f"{HA_URL.rstrip('/')}/api/", timeout=10)
        print(
            f"[onboarding] ✅ Home Assistant is reachable (HTTP {response.status_code})",
        )
    except requests.exceptions.ConnectionError:
        print(f"[onboarding] ❌ Cannot connect to Home Assistant at {HA_URL}")
        print("[onboarding] Please ensure Home Assistant is running and accessible")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print(f"[onboarding] ⚠️  Connection to {HA_URL} timed out")
        print("[onboarding] Home Assistant may be slow to respond - continuing anyway")
    except requests.exceptions.RequestException as e:
        print(f"[onboarding] ⚠️  Error checking HA reachability: {e}")
        print("[onboarding] Continuing anyway - will fail later if unreachable")

    # Check for Node.js if token creation might be needed (only warn, don't fail)
    import shutil

    if not shutil.which("node"):
        print("[onboarding] ⚠️  Node.js not found - token creation may fail if needed")
        print("[onboarding] Token may be created via user creation endpoint instead")

    print(f"[onboarding] Home Assistant URL: {HA_URL}")
    print(f"[onboarding] Username: {HASS_USERNAME}")

    # Simplified bootstrap flow: Handle two scenarios
    # 1. Fresh bootstrap: No user exists yet -> create user first (doesn't require auth)
    # 2. Token refresh: User exists but token expired/invalid -> refresh token
    #
    # Key insight: get_onboarding_status() without auth returns None for both 401 and 404
    # /api/onboarding returns 404 in two cases: no owner user yet, OR onboarding complete
    # We can't distinguish "no user" vs "complete" without trying user creation first
    # So we attempt user creation in a way that's safe if user already exists (idempotent)

    print("[onboarding] Attempting fresh onboarding (user creation)...")
    client_for_user_creation = OnboardingClient(
        HA_URL,
        None,
    )  # No auth needed for user creation
    success, restart_code = client_for_user_creation.complete_user()

    if success:
        print("[onboarding] ✅ User creation completed")

        # Check if we got a token from user creation
        auth_token_check: str | None = cast("str | None", client_for_user_creation.auth_token)  # type: ignore[reportUnknownMemberType]
        if auth_token_check:
            print("[onboarding] ✅ Token obtained from user creation")
            client = client_for_user_creation  # Use client with token
            # Now get incomplete steps with auth
            incomplete_steps = client.discover_incomplete_steps()
        else:
            # User was created but no token returned - try WebSocket
            print(
                "[onboarding] No token in response, trying WebSocket token creation...",
            )
            auth_token = get_auth_token()
            if auth_token:
                client = OnboardingClient(HA_URL, auth_token)
                print("[onboarding] ✅ Token obtained via WebSocket")
                incomplete_steps = client.discover_incomplete_steps()
            else:
                print("[onboarding] ⚠️  No token available, continuing anyway")
                client = client_for_user_creation
                incomplete_steps = client.discover_incomplete_steps()
    else:
        # User creation failed - could mean user already exists (403) or other error
        if restart_code == 2:
            print("[onboarding] ⚠️  User creation indicates HA restart needed")
            print("[onboarding] 💡 Home Assistant Core may need to be restarted")
        else:
            print("[onboarding] ❌ User creation failed")

        # Try to proceed with existing user (get token and check status)
        print("[onboarding] Attempting to continue with existing user...")
        auth_token = get_auth_token()
        if not auth_token:
            print("[onboarding] ❌ Cannot get authentication token")
            sys.exit(1)

        client = OnboardingClient(HA_URL, auth_token)
        print("[onboarding] ✅ Token obtained")
        incomplete_steps = client.discover_incomplete_steps()

    if not incomplete_steps:
        print("[onboarding] ✅ All onboarding steps are already complete!")
        sys.exit(0)

    print(f"[onboarding] Incomplete onboarding steps: {', '.join(incomplete_steps)}")

    # Complete each incomplete step
    needs_restart = False

    for step in incomplete_steps:
        if step == "core_config":
            success, restart_code = client.complete_core_config(
                refresh_token_fn=get_auth_token,
            )
            if success:
                print("[onboarding] ✅ Core config step completed")
            elif restart_code == 2:
                needs_restart = True
            else:
                print("[onboarding] ⚠️  Core config step failed, continuing...")
            time.sleep(2)

        elif step == "analytics":
            success, restart_code = client.complete_analytics(
                refresh_token_fn=get_auth_token,
            )
            if success:
                print("[onboarding] ✅ Analytics step completed")
            elif restart_code == 2:
                needs_restart = True
            else:
                print("[onboarding] ⚠️  Analytics step failed, continuing...")
            time.sleep(2)

        elif step == "integration":
            success, restart_code = client.complete_integration(
                refresh_token_fn=get_auth_token,
            )
            if success:
                print("[onboarding] ✅ Integration step completed")
            elif restart_code == 2:
                needs_restart = True
            else:
                print("[onboarding] ⚠️  Integration step failed, continuing...")
            time.sleep(2)

        elif step == "user":
            # User step already handled upfront, skip in loop
            print("[onboarding] User step already completed")
        else:
            print(f"[onboarding] ⚠️  Unknown onboarding step: {step}")

    # Verify completion
    print("[onboarding] Verifying onboarding completion...")
    remaining_steps = client.discover_incomplete_steps()

    if remaining_steps:
        print(
            f"[onboarding] ⚠️  Some onboarding steps may still be incomplete: {', '.join(remaining_steps)}",
        )
        if needs_restart:
            print(
                "[onboarding] 💡 Consider restarting Home Assistant Core: ha core restart",
            )
        sys.exit(1)
    else:
        print("[onboarding] ✅ All onboarding steps completed successfully!")
        sys.exit(0)


if __name__ == "__main__":
    main()
