import datetime
import json
import logging
import pickle
import random
import string
from pathlib import Path

import aiohttp
import yaml

from cync_lan.const import (
    CYNC_ACCOUNT_LANGUAGE,
    CYNC_ACCOUNT_PASSWORD,
    CYNC_ACCOUNT_USERNAME,
    CYNC_API_BASE,
    CYNC_CLOUD_AUTH_PATH,
    CYNC_CONFIG_FILE_PATH,
    CYNC_CORP_ID,
    CYNC_LOG_NAME,
    PERSISTENT_BASE_DIR,
)
from cync_lan.devices import CyncDevice
from cync_lan.structs import ComputedTokenData, GlobalObject

logger = logging.getLogger(CYNC_LOG_NAME)
g = GlobalObject()


class CyncAuthenticationError(Exception):
    """Exception raised when Cync Cloud API authentication fails or token expires."""


class CyncCloudAPI:
    api_timeout: int = 8
    lp: str = "CyncCloudAPI"
    auth_cache_file = CYNC_CLOUD_AUTH_PATH
    token_cache: ComputedTokenData | None
    http_session: aiohttp.ClientSession | None = None
    _instance: "CyncCloudAPI | None" = None

    def __new__(cls, *_args, **_kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, **kwargs):
        self.api_timeout = kwargs.get("api_timeout", 8)
        self.lp = kwargs.get("lp", self.lp)

    async def close(self):
        """
        Close the aiohttp session if it exists and is not closed.
        """
        lp = f"{self.lp}:close:"
        if self.http_session and not self.http_session.closed:
            logger.debug("%s Closing aiohttp ClientSession", lp)
            await self.http_session.close()
            self.http_session = None

    async def _check_session(self):
        """
        Check if the aiohttp session is initialized.
        If not, create a new session.
        """
        if not self.http_session or self.http_session.closed:
            logger.debug("%s:_check_session: Creating new aiohttp ClientSession", self.lp)
            self.http_session = aiohttp.ClientSession()
            await self.http_session.__aenter__()

    async def read_token_cache(self) -> ComputedTokenData | None:
        """
        Read the token cache from the file.
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
            logger.debug("%s Cached token data read successfully", lp)
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
        if not self.token_cache:
            logger.debug("%s No cached token found, requesting OTP...", lp)
            return False
        # check if the token is expired
        if self.token_cache.expires_at < datetime.datetime.now(datetime.UTC):
            logger.debug("%s Token expired, requesting OTP...", lp)
            # token expired, request OTP
            return False
        logger.debug("%s Token is valid, using cached token", lp)
        # token is valid, return the token data
        return True

    async def request_otp(self) -> bool:
        """
        Request an OTP code for 2FA authentication.
        The username and password are defined in the hass_add-on 'configuration' page
        """
        lp = f"{self.lp}:request_otp:"
        await self._check_session()
        req_otp_url = f"{CYNC_API_BASE}two_factor/email/verifycode"
        if not CYNC_ACCOUNT_USERNAME or not CYNC_ACCOUNT_PASSWORD:
            logger.error("%s Cync account username or password not set, cannot request OTP!", lp)
            return False
        auth_data = {
            "corp_id": CYNC_CORP_ID,
            "email": CYNC_ACCOUNT_USERNAME,
            "local_lang": CYNC_ACCOUNT_LANGUAGE,
        }
        sesh = self.http_session
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
        auth_data = {
            "corp_id": CYNC_CORP_ID,
            "email": CYNC_ACCOUNT_USERNAME,
            "password": CYNC_ACCOUNT_PASSWORD,
            "two_factor": otp_code,
            "resource": "".join(random.choices(string.ascii_lowercase, k=16)),
        }
        logger.debug("%s Sending OTP code: %s to Cync Cloud API for authentication", lp, otp_code)

        sesh = self.http_session
        try:
            r = await sesh.post(
                api_auth_url,
                json=auth_data,
                timeout=aiohttp.ClientTimeout(total=self.api_timeout),
            )
            r.raise_for_status()
            iat = datetime.datetime.now(datetime.UTC)
            token_data = await r.json()
        except aiohttp.ClientResponseError:
            logger.exception("Failed to authenticate")
            return False
        except json.JSONDecodeError:
            logger.exception("Failed to decode JSON")
            return False
        except KeyError:
            logger.exception("Failed to get key from JSON")
            return False
        else:
            # add issued_at to the token data for computing the expiration datetime
            token_data["issued_at"] = iat
            computed_token = ComputedTokenData(**token_data)
            await self.write_token_cache(computed_token)
            return True

    async def write_token_cache(self, tkn: ComputedTokenData) -> bool:
        """
        Write the token cache to the file.
        Args:
            tkn (ComputedTokenData): The token data to write to the cache.
        Returns:
            bool: True if the write was successful, False otherwise.
        """
        lp = f"{self.lp}:write_token_cache:"
        try:
            with Path(self.auth_cache_file).open("wb") as f:
                pickle.dump(tkn, f)
        except (OSError, pickle.PicklingError, TypeError):
            logger.exception("%s Failed to write token cache", lp)
            return False
        else:
            logger.debug("%s Token cache written successfully to: %s", lp, self.auth_cache_file)
            self.token_cache = tkn
            return True

    async def request_devices(self):
        """Get a list of devices for a particular user."""
        lp = f"{self.lp}:get_devices:"
        await self._check_session()
        user_id = self.token_cache.user_id
        access_token = self.token_cache.access_token
        api_devices_url = f"{CYNC_API_BASE}user/{user_id}/subscribe/devices"
        headers = {"Access-Token": access_token}
        sesh = self.http_session
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
        access_token = self.token_cache.access_token
        api_device_prop_url = f"{CYNC_API_BASE}product/{product_id}/device/{device_id}/property"
        headers = {"Access-Token": access_token}
        sesh = self.http_session
        try:
            r = await sesh.get(
                api_device_prop_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.api_timeout),
            )
            ret = await r.json()
        except aiohttp.ClientResponseError:
            logger.exception("%s Failed to get device properties", lp)
        except json.JSONDecodeError:
            logger.exception("%s Failed to decode JSON", lp)
            raise
        except KeyError:
            logger.exception("%s Failed to get key from JSON", lp)
            raise

        # {'error': {'msg': 'Access-Token Expired', 'code': 4031021}}
        logit = False
        if "error" in ret:
            error_data = ret["error"]
            if error_data.get("msg"):
                if error_data["msg"].lower() == "access-token expired":
                    msg = f"{lp} Access-Token expired, you need to re-authenticate!"
                    raise CyncAuthenticationError(msg)
                    # logger.error("Access-Token expired, re-authenticating...")
                    # return self.get_devices(*self.authenticate_2fa())
                logit = True

                if "code" in error_data:
                    cync_err_code = error_data["code"]
                    if cync_err_code == 4041009:
                        # no properties for this home ID
                        # I've noticed lots of empty homes in the returned data,
                        # we only parse homes with an assigned name and a 'bulbsArray'
                        logit = False
                    else:
                        logger.debug(
                            "%s DBG>>> error code != 4041009 (int) ---> type(cync_err_code)=%s -- cync_err_code=%s /// setting logit = True",
                            lp,
                            type(cync_err_code),
                            cync_err_code,
                        )
                        logit = True
                else:
                    logger.debug("%s DBG>>> no 'code' in error data, setting logit = True", lp)
                    logit = True
            if logit is True:
                logger.warning("%s Cync Cloud API Error: %s", lp, error_data)
        return ret

    async def export_config_file(self) -> bool:
        """Get Cync devices from the cloud"""
        mesh_networks = await self.request_devices()
        for mesh in mesh_networks:
            mesh["properties"] = await self.get_properties(mesh["product_id"], mesh["id"])
        mesh_config = await self._mesh_to_config(mesh_networks)
        try:
            with Path(CYNC_CONFIG_FILE_PATH).open("w") as f:
                f.write(yaml.dump(mesh_config))
        except Exception:
            logger.exception(
                "%s Failed to write mesh config to file: %s",
                self.lp,
                CYNC_CONFIG_FILE_PATH,
            )
            return False
        else:
            return True

    async def _mesh_to_config(self, mesh_info):
        """Take exported cloud data and format it into a working config dict to be dumped in YAML format."""
        lp = f"{self.lp}:export config:"
        mesh_conf = {}
        # What we get from the Cync cloud API
        raw_file_out = f"{PERSISTENT_BASE_DIR}/raw_mesh.cync"
        try:
            with Path(raw_file_out).open("w") as _f:
                _f.write(yaml.dump(mesh_info))
        except Exception:
            logger.exception(
                "%s Failed to write raw config from Cync account to file: '%s'",
                lp,
                raw_file_out,
            )
        else:
            logger.debug("%s Dumped raw config from Cync account to file: %s", lp, raw_file_out)
        for mesh_ in mesh_info:
            if "name" not in mesh_ or len(mesh_["name"]) < 1:
                logger.debug("%s No name found for mesh, skipping...", lp)
                continue
            if "properties" not in mesh_:
                logger.debug("%s No properties found for mesh, skipping...", lp)
                continue
            if "bulbsArray" not in mesh_["properties"]:
                logger.debug("%s No 'bulbsArray' in properties, skipping...", lp)
                continue

            new_mesh = {kv: mesh_[kv] for kv in ("access_key", "id", "mac") if kv in mesh_}
            mesh_conf[mesh_["name"]] = new_mesh

            logger.debug(
                "%s 'properties' and 'bulbsArray' found in exported config, processing...",
                lp,
            )
            new_mesh["devices"] = {}
            new_mesh["groups"] = {}

            for cfg_bulb in mesh_["properties"]["bulbsArray"]:
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
                    continue
                new_dev_dict = {}
                # last 3 digits of deviceID
                __id = int(str(cfg_bulb["deviceID"])[-3:])
                wifi_mac = str(cfg_bulb.get("wifiMac", None))
                _mac = str(cfg_bulb["mac"])
                name = str(cfg_bulb["displayName"])
                _type = int(cfg_bulb["deviceType"])
                _fw_ver = str(cfg_bulb["firmwareVersion"])
                # data from: https://github.com/baudneo/hass-addons/issues/8
                # { "hvacSystem": { "changeoverMode": 0, "auxHeatStages": 1, "auxFurnaceType": 1, "stages": 1, "furnaceType": 1, "type": 2, "powerLines": 1 },
                # "thermostatSensors": [ { "pin": "025572", "name": "Living Room", "type": "savant" }, { "pin": "044604", "name": "Bedroom Sensor", "type": "savant" }, { "pin": "022724", "name": "Thermostat sensor 3", "type": "savant" } ] } ]
                hvac_cfg = None
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
                    new_dev_dict["hvac"] = hvac_cfg

                cync_device = CyncDevice(
                    name=name,
                    cync_id=__id,
                    cync_type=_type,
                    mac=_mac,
                    wifi_mac=wifi_mac,
                    fw_version=_fw_ver,
                    hvac=hvac_cfg,
                )
                for attr_set in (
                    "name",
                    "mac",
                    "wifi_mac",
                ):
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

                new_mesh["devices"][__id] = new_dev_dict

            # Parse groups
            if "groupsArray" in mesh_["properties"]:
                logger.debug("%s 'groupsArray' found, processing groups...", lp)
                for cfg_group in mesh_["properties"]["groupsArray"]:
                    if "groupID" not in cfg_group or "displayName" not in cfg_group:
                        logger.warning(
                            "%s Missing required attribute in Cync group, skipping: %s",
                            lp,
                            cfg_group,
                        )
                        continue

                    group_id = int(cfg_group["groupID"])
                    group_name = str(cfg_group["displayName"])
                    device_ids = cfg_group.get("deviceIDArray", [])
                    is_subgroup = cfg_group.get("isSubgroup", False)

                    # Convert full device IDs to last 3 digits
                    member_ids = [int(str(dev_id)[-3:]) for dev_id in device_ids]

                    # Only add groups that have devices
                    if len(member_ids) > 0:
                        new_mesh["groups"][group_id] = {
                            "name": group_name,
                            "members": member_ids,
                            "is_subgroup": is_subgroup,
                        }
                        logger.debug(
                            "%s Added group '%s' (ID: %s) with %s devices",
                            lp,
                            group_name,
                            group_id,
                            len(member_ids),
                        )
                    else:
                        logger.debug(
                            "%s Skipping empty group '%s' (ID: %s)",
                            lp,
                            group_name,
                            group_id,
                        )

        return {"account data": mesh_conf}
