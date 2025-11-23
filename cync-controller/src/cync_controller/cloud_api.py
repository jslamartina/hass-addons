"""Cync Cloud API client for authentication and device discovery.

Provides functionality to authenticate with the Cync Cloud API, request device
properties, and retrieve mesh configuration for local device management.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import secrets
import string
from pathlib import Path
from typing import Self, TypedDict, cast

import aiohttp
import yaml
from pydantic import BaseModel, computed_field

from cync_controller.const import (
    CYNC_ACCOUNT_LANGUAGE,
    CYNC_ACCOUNT_PASSWORD,
    CYNC_ACCOUNT_USERNAME,
    CYNC_API_BASE,
    CYNC_CLOUD_AUTH_PATH,
    CYNC_CONFIG_FILE_PATH,
    CYNC_CORP_ID,
    PERSISTENT_BASE_DIR,
)
from cync_controller.logging_abstraction import get_logger

logger = get_logger(__name__)

# Cync Cloud API error codes
CYNC_ERROR_CODE_NOT_FOUND = 4041009


class CyncAuthenticationError(Exception):
    """Exception raised when Cync Cloud API authentication fails or token expires."""


class AuthRequestData(TypedDict):
    """Type definition for authentication request data (OTP request)."""

    corp_id: str
    email: str
    local_lang: str


class AuthOTPData(TypedDict):
    """Type definition for OTP authentication request data."""

    corp_id: str
    email: str
    password: str
    two_factor: int
    resource: str


class ErrorResponseDict(TypedDict, total=False):
    """Type definition for error responses from API."""

    msg: str
    code: int


class ApiResponseDict(TypedDict, total=False):
    """Type definition for API responses that may contain errors."""

    error: ErrorResponseDict


class MeshInfoDict(TypedDict, total=False):
    """Type definition for mesh network information from API."""

    name: str
    access_key: str
    id: str
    mac: str
    product_id: str
    properties: dict[str, object]  # Complex nested structure, use object instead of Any


class RawTokenData(BaseModel):
    """Model for cloud token data.

    API Auth Response structure:
        {
            'access_token': '...',
            'refresh_token': '...',
            'user_id': 769963474,
            'expire_in': 604800,
            'authorize': '...'
        }
    """

    access_token: str
    user_id: str | int
    expire_in: str | int
    refresh_token: str
    authorize: str


class ComputedTokenData(RawTokenData):
    """Extended token data model with computed expiration time.

    Adds issued_at timestamp and computes expires_at based on expire_in duration.
    """

    issued_at: datetime.datetime

    @computed_field
    @property
    def expires_at(self) -> datetime.datetime | None:
        """Calculate the expiration time of the token based on the issued time and expires_in.

        Returns:
            datetime.datetime: The expiration time in UTC.

        """
        if self.issued_at and self.expire_in:
            expire_seconds = float(self.expire_in)
            return self.issued_at + datetime.timedelta(seconds=expire_seconds)
        return None


class CyncCloudAPI:
    """Cync Cloud API client for authentication and device discovery.

    Singleton class that manages authentication with the Cync Cloud API,
    handles token caching, and provides methods to request device properties
    and mesh configuration.
    """

    api_timeout: int = 8
    lp: str = "CyncCloudAPI"
    auth_cache_file: str = CYNC_CLOUD_AUTH_PATH
    token_cache: ComputedTokenData | None = None
    http_session: aiohttp.ClientSession | None = None
    _instance: CyncCloudAPI | None = None

    def __new__(cls, **_kwargs: object) -> Self:
        """Create or return the singleton instance of CyncCloudAPI.

        Implements the singleton pattern to ensure only one instance exists.

        Returns:
            Self: The singleton instance.

        """
        if cls._instance is None:
            new_instance = super().__new__(cls)
            cls._instance = new_instance
            return new_instance
        instance = cls._instance
        return cast("Self", instance)

    def __init__(self, **kwargs: object) -> None:
        """Initialize the CyncCloudAPI instance.

        Args:
            **kwargs: Optional keyword arguments for api_timeout and lp.

        """
        api_timeout_val = kwargs.get("api_timeout", 8)
        lp_val = kwargs.get("lp", self.lp)
        if isinstance(api_timeout_val, int):
            self.api_timeout = api_timeout_val
        if isinstance(lp_val, str):
            self.lp = lp_val

    async def close(self) -> None:
        """Close the aiohttp session if it exists and is not closed."""
        lp = f"{self.lp}:close:"
        if self.http_session and not self.http_session.closed:
            logger.debug("%s Closing aiohttp ClientSession", lp)
            await self.http_session.close()
            self.http_session = None

    async def _check_session(self) -> None:
        """Check if the aiohttp session is initialized.

        If not, create a new session.
        """
        if not self.http_session or self.http_session.closed:
            logger.debug("%s:_check_session: Creating new aiohttp ClientSession", self.lp)
            self.http_session = aiohttp.ClientSession()
            _ = await self.http_session.__aenter__()

    def _parse_token_fields(self, raw_dict: dict[str, object]) -> ComputedTokenData | None:
        """Parse token fields from raw dictionary."""
        access_token_val: object | None = raw_dict.get("access_token")
        user_id_val: object | None = raw_dict.get("user_id")
        expire_in_val: object | None = raw_dict.get("expire_in")
        refresh_token_val: object | None = raw_dict.get("refresh_token")
        authorize_val: object | None = raw_dict.get("authorize")
        issued_at_val: object | None = raw_dict.get("issued_at")

        required_fields = [
            access_token_val,
            user_id_val,
            expire_in_val,
            refresh_token_val,
            authorize_val,
            issued_at_val,
        ]
        if any(v is None for v in required_fields):
            return None

        # Parse issued_at
        if isinstance(issued_at_val, str):
            issued_at = datetime.datetime.fromisoformat(issued_at_val)
        elif isinstance(issued_at_val, datetime.datetime):
            issued_at = issued_at_val
        else:
            issued_at = datetime.datetime.now(datetime.UTC)

        if not isinstance(user_id_val, (str, int)):
            return None
        user_id: str | int = user_id_val

        if not isinstance(expire_in_val, (str, int)):
            return None
        expire_in: str | int = expire_in_val

        return ComputedTokenData(
            access_token=str(access_token_val),
            user_id=user_id,
            expire_in=expire_in,
            refresh_token=str(refresh_token_val),
            authorize=str(authorize_val),
            issued_at=issued_at,
        )

    async def read_token_cache(self) -> ComputedTokenData | None:
        """Read the token cache from the file.

        Returns:
            CloudTokenData: The cached token data if available, otherwise None.

        """
        lp = f"{self.lp}:read_token_cache:"
        auth_file = self.auth_cache_file

        def _read_json() -> ComputedTokenData | None:
            """Read JSON file synchronously (runs in thread pool)."""
            with Path(auth_file).open("r", encoding="utf-8") as f:
                json_result: object = cast("object", json.load(f))
                if not isinstance(json_result, dict):
                    return None
                raw_dict: dict[str, object] = cast("dict[str, object]", json_result)

            # Convert datetime string back to datetime object
            if "issued_at" in raw_dict and isinstance(raw_dict["issued_at"], str):
                raw_dict["issued_at"] = datetime.datetime.fromisoformat(raw_dict["issued_at"])

            return self._parse_token_fields(raw_dict)

        try:
            token_data: ComputedTokenData | None = await asyncio.to_thread(_read_json)
        except FileNotFoundError:
            logger.debug("%s Token cache file not found: %s", lp, auth_file)
            return None
        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
            logger.warning("%s Failed to parse token cache: %s", lp, e)
            return None

        if not token_data:
            logger.debug("%s Cached token data is EMPTY!", lp)
            return None
        logger.info("%s Cached token data read successfully", lp)
        return token_data

    async def check_token(self) -> bool:
        """Check if we need to request a new OTP code for 2FA authentication."""
        lp = f"{self.lp}:check_tkn:"
        # read the token cache
        self.token_cache = await self.read_token_cache()
        token_cache = self.token_cache
        if not token_cache:
            logger.debug("%s No cached token found, requesting OTP...", lp)
            return False
        # check if the token is expired
        # Type narrowing: token_cache is not None after the check above
        # expires_at can return None if issued_at or expire_in are missing
        if token_cache.expires_at is None:
            logger.debug("%s Token expiration time is None (malformed token), requesting OTP...", lp)
            return False
        if token_cache.expires_at < datetime.datetime.now(datetime.UTC):
            logger.debug("%s Token expired, requesting OTP...", lp)
            # token expired, request OTP
            return False
        logger.debug("%s Token is valid, using cached token", lp)
        # token is valid, return the token data
        return True

    async def request_otp(self) -> bool:
        """Request an OTP code for 2FA authentication.

        The username and password are defined in the hass_add-on 'configuration' page.
        """
        lp = f"{self.lp}:request_otp:"
        await self._check_session()
        req_otp_url = f"{CYNC_API_BASE}two_factor/email/verifycode"
        if not CYNC_ACCOUNT_USERNAME or not CYNC_ACCOUNT_PASSWORD:
            logger.error("%s Cync account username or password not set, cannot request OTP!", lp)
            return False
        auth_data: AuthRequestData = {
            "corp_id": CYNC_CORP_ID,
            "email": CYNC_ACCOUNT_USERNAME,
            "local_lang": CYNC_ACCOUNT_LANGUAGE,
        }
        sesh = self.http_session
        if not sesh:
            logger.error("%s HTTP session is None, cannot request OTP", lp)
            return False
        try:
            otp_r = await sesh.post(
                req_otp_url,
                json=auth_data,
                timeout=aiohttp.ClientTimeout(total=self.api_timeout),
            )
            otp_r.raise_for_status()
        except aiohttp.ClientResponseError:
            logger.exception("%s Failed to request OTP code", lp)
            return False
        else:
            return True

    def _validate_otp_code(self, otp_code: int, lp: str) -> int | None:
        """Validate and convert OTP code to integer."""
        if not otp_code:
            logger.error("OTP code must be provided")
            return None
        try:
            return int(otp_code)
        except (ValueError, TypeError):
            logger.exception("%s OTP code must be an integer, got %s", lp, type(otp_code))
            return None

    def _prepare_auth_data(self, otp_code: int) -> AuthOTPData | None:
        """Prepare authentication data for OTP request."""
        if not CYNC_ACCOUNT_USERNAME or not CYNC_ACCOUNT_PASSWORD:
            return None
        resource_str = "".join(secrets.choice(string.ascii_lowercase) for _ in range(16))
        return {
            "corp_id": CYNC_CORP_ID,
            "email": CYNC_ACCOUNT_USERNAME,
            "password": CYNC_ACCOUNT_PASSWORD,
            "two_factor": otp_code,
            "resource": resource_str,
        }

    def _parse_token_response(
        self,
        token_data: dict[str, object],
        iat: datetime.datetime,
        lp: str,
    ) -> ComputedTokenData | None:
        """Parse token response and create ComputedTokenData."""
        access_token_val: object | None = token_data.get("access_token")
        user_id_val: object | None = token_data.get("user_id")
        expire_in_val: object | None = token_data.get("expire_in")
        refresh_token_val: object | None = token_data.get("refresh_token")
        authorize_val: object | None = token_data.get("authorize")

        if any(v is None for v in [access_token_val, user_id_val, expire_in_val, refresh_token_val, authorize_val]):
            logger.error("%s Missing required fields in token response", lp)
            return None

        if not isinstance(user_id_val, (str, int)):
            logger.error("%s Invalid user_id type in token response", lp)
            return None
        user_id: str | int = user_id_val

        if not isinstance(expire_in_val, (str, int)):
            logger.error("%s Invalid expire_in type in token response", lp)
            return None
        expire_in: str | int = expire_in_val

        return ComputedTokenData(
            access_token=str(access_token_val),
            user_id=user_id,
            expire_in=expire_in,
            refresh_token=str(refresh_token_val),
            authorize=str(authorize_val),
            issued_at=iat,
        )

    async def _authenticate_with_otp(
        self,
        auth_data: AuthOTPData,
        lp: str,
    ) -> dict[str, object] | None:
        """Perform OTP authentication request and return token data."""
        api_auth_url = f"{CYNC_API_BASE}user_auth/two_factor"
        sesh = self.http_session
        if not sesh:
            logger.error("%s HTTP session is None, cannot send OTP", lp)
            return None

        try:
            r = await sesh.post(
                api_auth_url,
                json=auth_data,
                timeout=aiohttp.ClientTimeout(total=self.api_timeout),
            )
            r.raise_for_status()
            json_result: object = cast("object", await r.json())
            if not isinstance(json_result, dict):
                msg = "Invalid token response format"
                raise TypeError(msg)
            return cast("dict[str, object]", json_result)
        except aiohttp.ClientResponseError as e:
            logger.exception(
                "HTTP error during authentication",
                extra={
                    "status": e.status,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return None
        except json.JSONDecodeError as e:
            logger.exception(
                "Invalid JSON response",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return None
        except KeyError as e:
            logger.exception(
                "Missing required field in response",
                extra={
                    "missing_key": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return None

    async def send_otp(self, otp_code: int) -> bool:
        """Send OTP code to authenticate with Cync Cloud API.

        Args:
            otp_code: The one-time password code received via email.

        Returns:
            bool: True if authentication was successful, False otherwise.

        """
        lp = f"{self.lp}:send_otp:"
        await self._check_session()

        validated_otp = self._validate_otp_code(otp_code, lp)
        if validated_otp is None:
            return False

        auth_data = self._prepare_auth_data(validated_otp)
        if auth_data is None:
            logger.error("%s Missing credentials", lp)
            return False

        logger.debug("%s Sending OTP code: %s to Cync Cloud API for authentication", lp, validated_otp)

        token_data = await self._authenticate_with_otp(auth_data, lp)
        if token_data is None:
            return False

        iat = datetime.datetime.now(datetime.UTC)
        computed_token = self._parse_token_response(token_data, iat, lp)
        if computed_token is None:
            return False

        # CRITICAL: Set token in memory FIRST before attempting file write
        self.token_cache = computed_token
        logger.info("%s  Token set in memory cache (user_id: %s)", lp, computed_token.user_id)

        write_success = await self.write_token_cache(computed_token)
        if not write_success:
            logger.warning("%s Token set in memory but file write failed - token will be lost on restart", lp)

        return True

    async def write_token_cache(self, tkn: ComputedTokenData) -> bool:
        """Write the token cache to the file.

        Args:
            tkn (ComputedTokenData): The token data to write to the cache.

        Returns:
            bool: True if the write was successful, False otherwise.

        """
        lp = f"{self.lp}:write_token_cache:"

        def _write_json() -> None:
            """Write JSON file synchronously (runs in thread pool)."""
            # Ensure parent directory exists
            Path(self.auth_cache_file).parent.mkdir(parents=True, exist_ok=True)
            # Convert to dict and serialize datetime to ISO format
            data: dict[str, object] = cast("dict[str, object]", tkn.model_dump())
            if "issued_at" in data and isinstance(data["issued_at"], datetime.datetime):
                data["issued_at"] = data["issued_at"].isoformat()
            with Path(self.auth_cache_file).open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

        try:
            await asyncio.to_thread(_write_json)
        except (OSError, TypeError, ValueError):
            logger.exception("%s Failed to write token cache", lp)
            return False
        else:
            logger.info("%s  Token cache written successfully to file: %s", lp, self.auth_cache_file)
            # Note: self.token_cache should already be set by caller before this function
            return True

    def _check_token_and_session(self) -> tuple[str, str, aiohttp.ClientSession]:
        """Check token cache and session, return credentials."""
        if not self.token_cache:
            msg = "Token cache is None, cannot request devices"
            raise CyncAuthenticationError(msg)
        user_id = self.token_cache.user_id
        access_token = self.token_cache.access_token
        sesh = self.http_session
        if not sesh:
            msg = "HTTP session is None, cannot request devices"
            raise RuntimeError(msg)
        return str(user_id), access_token, sesh

    def _process_devices_response(self, raw_ret: object, lp: str) -> list[dict[str, object]]:
        """Process devices API response."""
        if isinstance(raw_ret, dict):
            raw_ret_dict: dict[str, object] = cast("dict[str, object]", raw_ret)
            error_val: object | None = raw_ret_dict.get("error")
            if error_val and isinstance(error_val, dict):
                error_val_dict: dict[str, object] = cast("dict[str, object]", error_val)
                error_msg_val: object | None = error_val_dict.get("msg")
                if error_msg_val and isinstance(error_msg_val, str) and error_msg_val.lower() == "access-token expired":
                    logger.error("%s Access-Token expired, you need to re-authenticate!", lp)
            return [raw_ret_dict]  # Wrap single dict in list for consistency
        if isinstance(raw_ret, list):
            return cast("list[dict[str, object]]", raw_ret)
        msg = "Invalid response format: expected dict or list"
        raise ValueError(msg)

    async def request_devices(self) -> list[dict[str, object]]:
        """Get a list of devices for a particular user.

        Returns:
            list[dict[str, object]]: List of dictionaries containing device information from the API.

        """
        lp = f"{self.lp}:get_devices:"
        await self._check_session()
        user_id, access_token, sesh = self._check_token_and_session()

        api_devices_url = f"{CYNC_API_BASE}user/{user_id}/subscribe/devices"
        headers = {"Access-Token": access_token}

        try:
            r = await sesh.get(
                api_devices_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.api_timeout),
            )
        except aiohttp.ClientResponseError:
            logger.exception("%s Failed to get devices", lp)
            raise
        except json.JSONDecodeError:
            logger.exception("%s Failed to decode JSON", lp)
            raise
        except KeyError:
            logger.exception("%s Failed to get key from JSON", lp)
            raise

        json_result: object = cast("object", await r.json())
        return self._process_devices_response(json_result, lp)

    async def get_properties(self, product_id: str, device_id: str) -> dict[str, object]:
        """Get properties for a single device.

        Properties contain a device list (bulbsArray), groups (groupsArray),
        and saved light effects (lightShows).

        Args:
            product_id: The product ID of the device.
            device_id: The device ID.

        Returns:
            dict[str, object]: Dictionary containing device properties.

        """
        lp = f"{self.lp}:get_properties:"
        await self._check_session()
        if not self.token_cache:
            msg = "Token cache is None, cannot get properties"
            raise CyncAuthenticationError(msg)
        access_token = self.token_cache.access_token
        api_device_prop_url = f"{CYNC_API_BASE}product/{product_id}/device/{device_id}/property"
        headers = {"Access-Token": access_token}
        sesh = self.http_session
        if not sesh:
            msg = "HTTP session is None, cannot get properties"
            raise RuntimeError(msg)
        try:
            r = await sesh.get(
                api_device_prop_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.api_timeout),
            )
            json_result: object = cast("object", await r.json())
            if not isinstance(json_result, dict):
                msg = "Invalid response format: expected dict"
                raise TypeError(msg)
            ret: dict[str, object] = cast("dict[str, object]", json_result)
        except aiohttp.ClientResponseError:
            logger.exception("%s Failed to get device properties", lp)
            raise
        except json.JSONDecodeError:
            logger.exception("%s Failed to decode JSON", lp)
            raise
        except KeyError:
            logger.exception("%s Failed to get key from JSON", lp)
            raise

        self._handle_properties_error(ret, lp)
        return ret

    def _handle_properties_error(self, ret: dict[str, object], lp: str) -> None:
        """Handle error responses from get_properties."""
        if "error" not in ret:
            return

        error_val: object = ret["error"]
        if not isinstance(error_val, dict):
            return

        error_data: dict[str, object] = cast("dict[str, object]", error_val)
        error_msg_val: object | None = error_data.get("msg")
        if not error_msg_val or not isinstance(error_msg_val, str):
            return

        error_msg: str = error_msg_val
        if error_msg.lower() == "access-token expired":
            msg = f"{lp} Access-Token expired, you need to re-authenticate!"
            raise CyncAuthenticationError(msg)

        logit = True
        code_val: object | None = error_data.get("code")
        if code_val is not None:
            if isinstance(code_val, int) and code_val == CYNC_ERROR_CODE_NOT_FOUND:
                logit = False
            else:
                logger.debug(
                    (
                        "%s DBG>>> error code != %s (int) ---> type(cync_err_code)=%s -- "
                        "cync_err_code=%s /// setting logit = True"
                    ),
                    lp,
                    CYNC_ERROR_CODE_NOT_FOUND,
                    type(code_val),
                    code_val,
                )
        else:
            logger.debug("%s DBG>>> no 'code' in error data, setting logit = True", lp)

        if logit:
            logger.warning("%s Cync Cloud API Error: %s", lp, error_data)

    async def export_config_file(self) -> bool:
        """Get Cync devices from the cloud."""
        mesh_networks = await self.request_devices()
        for mesh in mesh_networks:
            product_id = mesh.get("product_id")
            mesh_id = mesh.get("id")
            if isinstance(product_id, str) and isinstance(mesh_id, str):
                mesh["properties"] = await self.get_properties(product_id, mesh_id)
        mesh_config = await self._mesh_to_config(mesh_networks)

        def _write_yaml() -> None:
            """Write YAML file synchronously (runs in thread pool)."""
            # Ensure parent directory exists
            Path(CYNC_CONFIG_FILE_PATH).parent.mkdir(parents=True, exist_ok=True)
            with Path(CYNC_CONFIG_FILE_PATH).open("w") as f:
                _ = f.write(yaml.dump(mesh_config))

        try:
            await asyncio.to_thread(_write_yaml)
        except Exception:
            logger.exception(
                "%s Failed to write mesh config to file: %s",
                self.lp,
                CYNC_CONFIG_FILE_PATH,
            )
            return False
        else:
            return True

    def _write_raw_mesh_file(self, mesh_info: list[dict[str, object]], lp: str) -> None:
        """Write raw mesh data to file."""
        raw_file_out = f"{PERSISTENT_BASE_DIR}/raw_mesh.cync"
        try:
            Path(raw_file_out).parent.mkdir(parents=True, exist_ok=True)
            with Path(raw_file_out).open("w") as _f:
                _ = _f.write(yaml.dump(mesh_info))
            logger.debug("%s Dumped raw config from Cync account to file: %s", lp, raw_file_out)
        except Exception:
            logger.exception(
                "%s Failed to write raw config from Cync account to file: '%s'",
                lp,
                raw_file_out,
            )

    def _process_mesh_device(
        self,
        cfg_bulb: dict[str, object],
        lp: str,
    ) -> tuple[int, dict[str, object]] | None:
        """Process a single device from mesh config. Returns (device_id, device_dict) or None."""
        from cync_controller.devices.base_device import CyncDevice

        if any(
            checkattr not in cfg_bulb
            for checkattr in (
                "deviceID",
                "displayName",
                "mac",
                "deviceType",
                "firmwareVersion",
            )
        ):
            logger.warning(
                "%s Missing required attribute in Cync bulb, skipping: %s",
                lp,
                cfg_bulb,
            )
            return None

        device_id_val = cfg_bulb.get("deviceID")
        wifi_mac_val = cfg_bulb.get("wifiMac")
        mac_val = cfg_bulb.get("mac")
        name_val = cfg_bulb.get("displayName")
        device_type_val = cfg_bulb.get("deviceType")
        fw_ver_val = cfg_bulb.get("firmwareVersion")

        __id = int(str(device_id_val)[-3:]) if device_id_val else 0
        wifi_mac = str(wifi_mac_val) if wifi_mac_val else ""
        _mac = str(mac_val) if mac_val else ""
        name = str(name_val) if name_val else ""
        _type = int(device_type_val) if isinstance(device_type_val, (int, str)) else 0
        _fw_ver = str(fw_ver_val) if fw_ver_val else ""

        hvac_cfg: dict[str, object] | None = None
        if "hvacSystem" in cfg_bulb:
            hvac_system_val: object = cfg_bulb["hvacSystem"]
            if isinstance(hvac_system_val, dict):
                hvac_cfg = cast("dict[str, object]", hvac_system_val)
                thermostat_sensors_val: object | None = cfg_bulb.get("thermostatSensors")
                if thermostat_sensors_val is not None:
                    hvac_cfg["thermostatSensors"] = thermostat_sensors_val
            logger.debug(
                "%s Found HVAC device '%s' (ID: %s): %s",
                lp,
                name,
                __id,
                hvac_cfg,
            )

        cync_device = CyncDevice(
            cync_id=__id,
            cync_type=_type,
            name=name,
            mac=_mac,
            wifi_mac=wifi_mac,
            fw_version=_fw_ver,
            home_id=None,  # home_id not available in this context
            hvac=hvac_cfg,
        )

        new_dev_dict: dict[str, object] = {}
        if hvac_cfg:
            new_dev_dict["hvac"] = hvac_cfg

        for attr_set in ("name", "mac", "wifi_mac"):
            attr_result: object = cast("object", getattr(cync_device, attr_set))
            if attr_result:
                new_dev_dict[attr_set] = attr_result
            else:
                logger.warning("%s Attribute not found for bulb: %s", lp, attr_set)

        new_dev_dict["type"] = _type
        new_dev_dict["is_plug"] = cync_device.is_plug
        new_dev_dict["supports_temperature"] = cync_device.supports_temperature
        new_dev_dict["supports_rgb"] = cync_device.supports_rgb
        new_dev_dict["fw"] = _fw_ver

        return __id, new_dev_dict

    def _process_mesh_group(
        self,
        cfg_group: dict[str, object],
        lp: str,
    ) -> tuple[int, dict[str, object]] | None:
        """Process a single group from mesh config. Returns (group_id, group_dict) or None."""
        if "groupID" not in cfg_group or "displayName" not in cfg_group:
            logger.warning(
                "%s Missing required attribute in Cync group, skipping: %s",
                lp,
                cfg_group,
            )
            return None

        group_id_val: object | None = cfg_group.get("groupID")
        group_name_val: object | None = cfg_group.get("displayName")
        device_id_array_val: object = cfg_group.get("deviceIDArray", [])

        group_id = int(group_id_val) if isinstance(group_id_val, (int, str)) else 0
        group_name = str(group_name_val) if group_name_val else ""
        device_ids: list[int] = []
        if isinstance(device_id_array_val, list):
            device_id_list: list[object] = cast("list[object]", device_id_array_val)
            device_ids.extend(int(d_val) for d_val in device_id_list if isinstance(d_val, (int, str)))
        is_subgroup_val: object = cfg_group.get("isSubgroup", False)
        is_subgroup = bool(is_subgroup_val) if isinstance(is_subgroup_val, bool) else False
        member_ids: list[int] = [int(str(dev_id)[-3:]) for dev_id in device_ids]

        if len(member_ids) == 0:
            logger.debug(
                "%s Skipping empty group '%s' (ID: %s)",
                lp,
                group_name,
                group_id,
            )
            return None

        logger.debug(
            "%s Added group '%s' (ID: %s) with %s devices",
            lp,
            group_name,
            group_id,
            len(member_ids),
        )

        return group_id, {
            "name": group_name,
            "members": member_ids,
            "is_subgroup": is_subgroup,
        }

    def _validate_mesh_entry(
        self,
        mesh_dict: dict[str, object],
        lp: str,
    ) -> tuple[str, dict[str, object]] | None:
        """Validate mesh entry and return name and properties dict if valid."""
        mesh_name_val: object | None = mesh_dict.get("name")
        if not mesh_name_val or not isinstance(mesh_name_val, str) or len(mesh_name_val) < 1:
            logger.debug("%s No name found for mesh, skipping...", lp)
            return None
        properties_val: object | None = mesh_dict.get("properties")
        if not properties_val or not isinstance(properties_val, dict):
            logger.debug("%s No properties found for mesh, skipping...", lp)
            return None
        properties_dict: dict[str, object] = cast("dict[str, object]", properties_val)
        bulbs_array_val: object | None = properties_dict.get("bulbsArray")
        if not bulbs_array_val or not isinstance(bulbs_array_val, list):
            logger.debug("%s No 'bulbsArray' in properties, skipping...", lp)
            return None
        return mesh_name_val, properties_dict

    def _process_mesh_devices(
        self,
        bulbs_array_val: object,
        new_mesh: dict[str, object],
        lp: str,
    ) -> None:
        """Process devices from bulbs array."""
        bulbs_list: list[object] = cast("list[object]", bulbs_array_val)
        for cfg_bulb_raw in bulbs_list:
            if isinstance(cfg_bulb_raw, dict):
                cfg_bulb_dict: dict[str, object] = cast("dict[str, object]", cfg_bulb_raw)
                result = self._process_mesh_device(cfg_bulb_dict, lp)
                if result:
                    __id, new_dev_dict = result
                    devices_dict = new_mesh.get("devices")
                    if isinstance(devices_dict, dict):
                        devices_dict[__id] = new_dev_dict

    def _process_mesh_groups(
        self,
        properties_dict: dict[str, object],
        new_mesh: dict[str, object],
        lp: str,
    ) -> None:
        """Process groups from properties dict."""
        groups_array_val: object | None = properties_dict.get("groupsArray")
        if groups_array_val and isinstance(groups_array_val, list):
            logger.debug("%s 'groupsArray' found, processing groups...", lp)
            groups_list: list[object] = cast("list[object]", groups_array_val)
            for cfg_group_raw in groups_list:
                if isinstance(cfg_group_raw, dict):
                    cfg_group_dict: dict[str, object] = cast("dict[str, object]", cfg_group_raw)
                    result = self._process_mesh_group(cfg_group_dict, lp)
                    if result:
                        group_id, group_dict = result
                        groups_dict = new_mesh.get("groups")
                        if isinstance(groups_dict, dict):
                            groups_dict[group_id] = group_dict

    async def _mesh_to_config(
        self,
        mesh_info: list[dict[str, object]],
    ) -> dict[str, dict[str, dict[str, object]]]:
        """Take exported cloud data and format it into a working config dict to be dumped in YAML format."""
        lp = f"{self.lp}:export config:"
        mesh_conf: dict[str, dict[str, object]] = {}
        self._write_raw_mesh_file(mesh_info, lp)

        for mesh_ in mesh_info:
            mesh_dict: dict[str, object] = mesh_
            validation_result = self._validate_mesh_entry(mesh_dict, lp)
            if validation_result is None:
                continue
            mesh_name_val, properties_dict = validation_result

            new_mesh: dict[str, object] = {kv: mesh_dict[kv] for kv in ("access_key", "id", "mac") if kv in mesh_dict}
            mesh_conf[mesh_name_val] = new_mesh

            logger.debug(
                "%s 'properties' and 'bulbsArray' found in exported config, processing...",
                lp,
            )
            new_mesh["devices"] = {}
            new_mesh["groups"] = {}

            bulbs_array_val: object | None = properties_dict.get("bulbsArray")
            if bulbs_array_val and isinstance(bulbs_array_val, list):
                bulbs_list: list[object] = cast("list[object]", bulbs_array_val)
                self._process_mesh_devices(bulbs_list, new_mesh, lp)

            self._process_mesh_groups(properties_dict, new_mesh, lp)

        return {"account data": mesh_conf}
