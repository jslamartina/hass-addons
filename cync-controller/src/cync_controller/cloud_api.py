from __future__ import annotations

import datetime
import json
import pickle
import random
import string
from pathlib import Path
from typing import Any, TypedDict

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


class MeshInfoDict(TypedDict, total=False):
    """Type definition for mesh network information from API."""

    name: str
    access_key: str
    id: str
    mac: str
    product_id: str
    properties: dict[str, Any]  # Complex nested structure, keep as Any for now


class RawTokenData(BaseModel):
    """Model for cloud token data."""

    # API Auth Response:
    # {
    # 'access_token': '1007d2ad150c4000-2407d4d081dbea53DAwQjkzNUM2RDE4QjE0QTIzMjNGRjAwRUU4ODNEQUE5RTFCMjhBOQ==',
    # 'refresh_token': 'REY3NjVENEQwQTM4NjE2OEM3QjNGMUZEQjQyQzU0MEIzRTU4NzMyRDdFQzZFRUYyQTUxNzE4RjAwNTVDQ0Y3Mw==',
    # 'user_id': 769963474,
    # 'expire_in': 604800,
    # 'authorize': '2207d2c8d2c9e406'
    # }
    access_token: str
    user_id: str | int
    expire_in: str | int
    refresh_token: str
    authorize: str


class ComputedTokenData(RawTokenData):
    issued_at: datetime.datetime

    @computed_field
    @property
    def expires_at(self) -> datetime.datetime | None:
        """Calculate the expiration time of the token based on the issued time and expires_in.

        Returns:
            datetime.datetime: The expiration time in UTC.

        """
        if self.issued_at and self.expire_in:
            expire_seconds = float(self.expire_in) if isinstance(self.expire_in, (str, int)) else 0.0
            return self.issued_at + datetime.timedelta(seconds=expire_seconds)
        return None


class CyncCloudAPI:
    api_timeout: int = 8
    lp: str = "CyncCloudAPI"
    auth_cache_file: str = CYNC_CLOUD_AUTH_PATH
    token_cache: ComputedTokenData | None = None
    http_session: aiohttp.ClientSession | None = None
    _instance: CyncCloudAPI | None = None

    def __new__(cls, *args: object, **kwargs: object) -> CyncCloudAPI:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, **kwargs: object) -> None:
        self.api_timeout = kwargs.get("api_timeout", 8)
        self.lp = kwargs.get("lp", self.lp)

    async def close(self):
        """Close the aiohttp session if it exists and is not closed."""
        lp = f"{self.lp}:close:"
        if self.http_session and not self.http_session.closed:
            logger.debug("%s Closing aiohttp ClientSession", lp)
            await self.http_session.close()
            self.http_session = None

    async def _check_session(self):
        """Check if the aiohttp session is initialized.
        If not, create a new session.
        """
        if not self.http_session or self.http_session.closed:
            logger.debug("%s:_check_session: Creating new aiohttp ClientSession", self.lp)
            self.http_session = aiohttp.ClientSession()
            _ = await self.http_session.__aenter__()

    async def read_token_cache(self) -> ComputedTokenData | None:
        """Read the token cache from the file.

        Returns:
            CloudTokenData: The cached token data if available, otherwise None.

        """
        lp = f"{self.lp}:read_token_cache:"
        try:
            with Path(self.auth_cache_file).open("rb") as f:
                token_data: ComputedTokenData | None = pickle.load(f)
        except FileNotFoundError:
            logger.debug("%s Token cache file not found: %s", lp, self.auth_cache_file)
            return None
        else:
            if not token_data:
                logger.debug("%s Cached token data is EMPTY!", lp)
                return None
            logger.info("%s Cached token data read successfully", lp)
            return token_data
            # add issued_at to the token data for computing the expiration datetime
            # iat = datetime.datetime.now(datetime.UTC)
            # token_data["issued_at"] = iat
            # return ComputedTokenData(**token_data)

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
        assert token_cache is not None  # Type guard for pyright
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
        The username and password are defined in the hass_add-on 'configuration' page
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

    async def send_otp(self, otp_code: int) -> bool:
        lp = f"{self.lp}:send_otp:"
        await self._check_session()
        if not otp_code:
            logger.error("OTP code must be provided")
            return False
        if not isinstance(otp_code, int):
            try:
                otp_code = int(otp_code)
            except ValueError:
                logger.exception("%s OTP code must be an integer, got %s", lp, type(otp_code))
                return False

        api_auth_url = f"{CYNC_API_BASE}user_auth/two_factor"
        if not CYNC_ACCOUNT_USERNAME or not CYNC_ACCOUNT_PASSWORD:
            logger.error("%s Missing credentials", lp)
            return False
        auth_data: AuthOTPData = {
            "corp_id": CYNC_CORP_ID,
            "email": CYNC_ACCOUNT_USERNAME,
            "password": CYNC_ACCOUNT_PASSWORD,
            "two_factor": otp_code,
            "resource": "".join(random.choices(string.ascii_lowercase, k=16)),
        }
        logger.debug("%s Sending OTP code: %s to Cync Cloud API for authentication", lp, otp_code)

        sesh = self.http_session
        if not sesh:
            logger.error("%s HTTP session is None, cannot send OTP", lp)
            return False
        success = False
        try:
            r = await sesh.post(
                api_auth_url,
                json=auth_data,
                timeout=aiohttp.ClientTimeout(total=self.api_timeout),
            )
            r.raise_for_status()
            iat = datetime.datetime.now(datetime.UTC)
            token_data = await r.json()
        except aiohttp.ClientResponseError as e:
            logger.exception(
                "HTTP error during authentication",
                extra={
                    "status": e.status,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
        except json.JSONDecodeError as e:
            logger.exception(
                "Invalid JSON response",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
        except KeyError as e:
            logger.exception(
                "Missing required field in response",
                extra={
                    "missing_key": str(e),
                    "error_type": type(e).__name__,
                },
            )
        else:
            # add issued_at to the token data for computing the expiration datetime
            token_data["issued_at"] = iat
            computed_token = ComputedTokenData(**token_data)

            # CRITICAL: Set token in memory FIRST before attempting file write
            # This ensures subsequent calls can use the token even if file write fails
            self.token_cache = computed_token
            logger.info("%s  Token set in memory cache (user_id: %s)", lp, computed_token.user_id)

            # Then attempt to write to persistent cache file
            write_success = await self.write_token_cache(computed_token)
            if not write_success:
                logger.warning("%s Token set in memory but file write failed - token will be lost on restart", lp)

            success = True

        return success

    async def write_token_cache(self, tkn: ComputedTokenData) -> bool:
        """Write the token cache to the file.

        Args:
            tkn (ComputedTokenData): The token data to write to the cache.

        Returns:
            bool: True if the write was successful, False otherwise.

        """
        lp = f"{self.lp}:write_token_cache:"
        try:
            # Ensure parent directory exists
            Path(self.auth_cache_file).parent.mkdir(parents=True, exist_ok=True)
            with Path(self.auth_cache_file).open("wb") as f:
                pickle.dump(tkn, f)
        except (OSError, pickle.PicklingError, TypeError):
            logger.exception("%s Failed to write token cache", lp)
            return False
        else:
            logger.info("%s  Token cache written successfully to file: %s", lp, self.auth_cache_file)
            # Note: self.token_cache should already be set by caller before this function
            return True

    async def request_devices(self):
        """Get a list of devices for a particular user."""
        lp = f"{self.lp}:get_devices:"
        await self._check_session()
        if not self.token_cache:
            msg = "Token cache is None, cannot request devices"
            raise CyncAuthenticationError(msg)
        user_id = self.token_cache.user_id
        access_token = self.token_cache.access_token
        api_devices_url = f"{CYNC_API_BASE}user/{user_id}/subscribe/devices"
        headers = {"Access-Token": access_token}
        sesh = self.http_session
        if not sesh:
            msg = "HTTP session is None, cannot request devices"
            raise RuntimeError(msg)
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
        else:
            ret = await r.json()

        # {'error': {'msg': 'Access-Token Expired', 'code': 4031021}}
        if "error" in ret:
            error_data = ret["error"]
            if "msg" in error_data and error_data["msg"] and error_data["msg"].lower() == "access-token expired":
                logger.error("%s Access-Token expired, you need to re-authenticate!", lp)
                # logger.error("%s Access-Token expired, re-authenticating...", lp)
                # return self.get_devices(*self.authenticate_2fa())
        return ret

    async def get_properties(self, product_id: str, device_id: str):
        """Get properties for a single device. Properties contain a device list (bulbsArray), groups (groupsArray), and saved light effects (lightShows)."""
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
        ret: dict[str, Any] | None = None
        try:
            r = await sesh.get(
                api_device_prop_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.api_timeout),
            )
            ret = await r.json()
        except aiohttp.ClientResponseError:
            logger.exception("%s Failed to get device properties", lp)
            raise
        except json.JSONDecodeError:
            logger.exception("%s Failed to decode JSON", lp)
            raise
        except KeyError:
            logger.exception("%s Failed to get key from JSON", lp)
            raise

        if ret is None:
            msg = "Failed to get properties: response is None"
            raise RuntimeError(msg)

        self._handle_properties_error(ret, lp)
        return ret

    def _handle_properties_error(self, ret: dict[str, Any], lp: str) -> None:
        """Handle error responses from get_properties."""
        if "error" not in ret:
            return

        error_data = ret["error"]
        if not error_data.get("msg"):
            return

        if error_data["msg"].lower() == "access-token expired":
            msg = f"{lp} Access-Token expired, you need to re-authenticate!"
            raise CyncAuthenticationError(msg)

        logit = True
        if "code" in error_data:
            cync_err_code = error_data["code"]
            if cync_err_code == 4041009:
                logit = False
            else:
                logger.debug(
                    "%s DBG>>> error code != 4041009 (int) ---> type(cync_err_code)=%s -- cync_err_code=%s /// setting logit = True",
                    lp,
                    type(cync_err_code),
                    cync_err_code,
                )
        else:
            logger.debug("%s DBG>>> no 'code' in error data, setting logit = True", lp)

        if logit:
            logger.warning("%s Cync Cloud API Error: %s", lp, error_data)

    async def export_config_file(self) -> bool:
        """Get Cync devices from the cloud"""
        mesh_networks = await self.request_devices()
        for mesh in mesh_networks:
            mesh["properties"] = await self.get_properties(mesh["product_id"], mesh["id"])
        mesh_config: dict[str, dict[str, Any]] = await self._mesh_to_config(mesh_networks)
        try:
            # Ensure parent directory exists
            Path(CYNC_CONFIG_FILE_PATH).parent.mkdir(parents=True, exist_ok=True)
            with Path(CYNC_CONFIG_FILE_PATH).open("w") as f:
                _ = f.write(yaml.dump(mesh_config))
        except Exception:
            logger.exception(
                "%s Failed to write mesh config to file: %s",
                self.lp,
                CYNC_CONFIG_FILE_PATH,
            )
            return False
        else:
            return True

    def _write_raw_mesh_file(self, mesh_info: list[dict[str, Any]], lp: str) -> None:
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
        cfg_bulb: dict[str, Any],
        lp: str,
    ) -> tuple[int, dict[str, Any]] | None:
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

        __id = int(str(cfg_bulb["deviceID"])[-3:])
        wifi_mac = str(cfg_bulb.get("wifiMac"))
        _mac = str(cfg_bulb["mac"])
        name = str(cfg_bulb["displayName"])
        _type = int(cfg_bulb["deviceType"])
        _fw_ver = str(cfg_bulb["firmwareVersion"])

        hvac_cfg: dict[str, Any] | None = None
        if "hvacSystem" in cfg_bulb:
            hvac_cfg = cfg_bulb["hvacSystem"]
            if "thermostatSensors" in cfg_bulb:
                hvac_cfg["thermostatSensors"] = cfg_bulb["thermostatSensors"]
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

        new_dev_dict: dict[str, Any] = {}
        if hvac_cfg:
            new_dev_dict["hvac"] = hvac_cfg

        for attr_set in ("name", "mac", "wifi_mac"):
            value = getattr(cync_device, attr_set)
            if value:
                new_dev_dict[attr_set] = value
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
        cfg_group: dict[str, Any],
        lp: str,
    ) -> tuple[int, dict[str, Any]] | None:
        """Process a single group from mesh config. Returns (group_id, group_dict) or None."""
        if "groupID" not in cfg_group or "displayName" not in cfg_group:
            logger.warning(
                "%s Missing required attribute in Cync group, skipping: %s",
                lp,
                cfg_group,
            )
            return None

        group_id = int(cfg_group["groupID"])
        group_name = str(cfg_group["displayName"])
        device_ids: list[int] = [int(d) for d in cfg_group.get("deviceIDArray", [])]
        is_subgroup: bool = cfg_group.get("isSubgroup", False)
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

    async def _mesh_to_config(self, mesh_info: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Take exported cloud data and format it into a working config dict to be dumped in YAML format."""
        lp = f"{self.lp}:export config:"
        mesh_conf: dict[str, dict[str, Any]] = {}
        self._write_raw_mesh_file(mesh_info, lp)

        for mesh_ in mesh_info:
            mesh_dict: dict[str, Any] = mesh_
            if "name" not in mesh_dict or len(mesh_dict["name"]) < 1:
                logger.debug("%s No name found for mesh, skipping...", lp)
                continue
            if "properties" not in mesh_dict:
                logger.debug("%s No properties found for mesh, skipping...", lp)
                continue
            if "bulbsArray" not in mesh_dict["properties"]:
                logger.debug("%s No 'bulbsArray' in properties, skipping...", lp)
                continue

            new_mesh: dict[str, Any] = {kv: mesh_dict[kv] for kv in ("access_key", "id", "mac") if kv in mesh_dict}
            mesh_conf[mesh_dict["name"]] = new_mesh

            logger.debug(
                "%s 'properties' and 'bulbsArray' found in exported config, processing...",
                lp,
            )
            new_mesh["devices"] = {}
            new_mesh["groups"] = {}

            for cfg_bulb_raw in mesh_dict["properties"]["bulbsArray"]:
                result = self._process_mesh_device(cfg_bulb_raw, lp)
                if result:
                    __id, new_dev_dict = result
                    new_mesh["devices"][__id] = new_dev_dict

            if "groupsArray" in mesh_dict["properties"]:
                logger.debug("%s 'groupsArray' found, processing groups...", lp)
                for cfg_group_raw in mesh_dict["properties"]["groupsArray"]:
                    result = self._process_mesh_group(cfg_group_raw, lp)
                    if result:
                        group_id, group_dict = result
                        new_mesh["groups"][group_id] = group_dict

        return {"account data": mesh_conf}
