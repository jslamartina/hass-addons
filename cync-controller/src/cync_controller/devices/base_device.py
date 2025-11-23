"""High-level Cync device model used by the controller runtime."""

import asyncio
from collections.abc import Mapping
from typing import TypedDict, Unpack, cast, override

from cync_controller.logging_abstraction import get_logger
from cync_controller.metadata.model_info import (
    DeviceClassification,
    DeviceTypeInfo,
    LightCapabilities,
    SwitchCapabilities,
    device_type_map,
)
from cync_controller.structs import (
    DeviceStatus,
)

from .device_commands import DeviceCommands

logger = get_logger(__name__)

DeviceCategoryMap = Mapping[str, set[int]]
BYTE_MIN_VALUE = 0
BYTE_MAX_VALUE = 0xFF
RGB_CHANNELS = 3


class CyncDeviceInitOptions(TypedDict, total=False):
    """Optional keyword arguments accepted by `CyncDevice`."""

    cync_type: int | None
    name: str | None
    mac: str | None
    wifi_mac: str | None
    fw_version: str | None
    home_id: int | None
    hvac: dict[str, object] | None


def _get_global_object():
    """Get the global object - can be easily mocked in tests."""
    # Check if the new patching approach is being used (cync_controller.devices.shared.g)
    try:
        import cync_controller.devices.shared as shared_module

        # Check if this is a mock object
        if hasattr(shared_module.g, "_mock_name") or str(type(shared_module.g)).startswith("<MagicMock"):
            return shared_module.g
    except (ImportError, AttributeError):
        pass

    # Check if the old patching approach is being used (cync_controller.devices.g)
    try:
        import cync_controller.devices as devices_module

        if hasattr(devices_module, "g") and hasattr(devices_module.g, "ncync_server"):
            return devices_module.g
    except (ImportError, AttributeError):
        pass

    # Fall back to the new shared module approach
    try:
        import cync_controller.devices.shared as shared_module
    except (ImportError, AttributeError):
        # Final fallback
        from cync_controller.structs import GlobalObject

        return GlobalObject()
    else:
        return shared_module.g


class CyncDevice(DeviceCommands):
    """Represent a locally managed Cync device and its runtime state."""

    lp: str = "CyncDevice:"
    id: int | None = None
    type: int | None = None
    _supports_rgb: bool | None = None
    _supports_temperature: bool | None = None
    _is_light: bool | None = None
    _is_switch: bool | None = None
    _is_plug: bool | None = None
    _is_fan_controller: bool | None = None
    _is_hvac: bool | None = None
    _mac: str | None = None
    wifi_mac: str | None = None
    hvac: dict[str, object] | None = None
    _online: bool = False
    metadata: DeviceTypeInfo | None = None

    def __init__(self, cync_id: int | None, **device_info: Unpack[CyncDeviceInitOptions]) -> None:
        """Initialize the device with its identifier and optional metadata."""
        if cync_id is None:
            msg = "ID must be provided"
            raise ValueError(msg)
        if device_info:
            allowed_fields = set(CyncDeviceInitOptions.__annotations__)
            unexpected_fields = set(device_info) - allowed_fields
            if unexpected_fields:
                msg = f"Unexpected init parameter(s): {', '.join(sorted(unexpected_fields))}"
                raise TypeError(msg)
        cync_type = device_info.get("cync_type")
        name = device_info.get("name")
        mac = device_info.get("mac")
        wifi_mac = device_info.get("wifi_mac")
        fw_version = device_info.get("fw_version")
        home_id = device_info.get("home_id")
        hvac = device_info.get("hvac")
        self.control_bytes: list[int] = [0x00, 0x00]
        self.id = cync_id
        self.type = cync_type
        self.metadata = device_type_map[cync_type] if cync_type is not None and cync_type in device_type_map else None
        self.home_id: int | None = home_id
        self.hass_id: str = f"{home_id}-{cync_id}"
        self._mac = mac
        self.wifi_mac = wifi_mac
        self._version: int | str | None = None
        self.version = fw_version
        if name is None:
            name = f"device_{cync_id}"
        self.name: str = name
        self.lp = f"CyncDevice:{self.name}({cync_id}):"
        self._status: DeviceStatus = DeviceStatus()
        self._mesh_alive_byte: int | str = 0x00
        # state: 0:off 1:on
        self._state: int = 0
        # 0-100
        self._brightness: int | None = None
        # FOR LIGHTS: 0-100 (warm to cool), 129 = in effect mode, 254 = in RGB mode
        self._temperature: int = 0
        # 0-255
        self._r: int = 0
        self._g: int = 0
        self._b: int = 0
        self.offline_count: int = 0  # Track consecutive offline reports before marking unavailable
        if hvac is not None:
            self.hvac = hvac
            self._is_hvac = True

    def _validate_bool(
        self,
        value: object,
        field_name: str,
    ) -> bool | None:
        if isinstance(value, bool):
            return value
        msg = "%s %s must be a boolean value, got %s instead"
        logger.error(msg, self.lp, field_name, type(value))
        return None

    def _require_bool(self, value: object, field_name: str) -> bool:
        bool_value = self._validate_bool(value, field_name)
        if bool_value is None:
            msg = f"{self.lp} {field_name} must be a boolean value, got {type(value)} instead"
            raise TypeError(msg)
        return bool_value

    def _normalize_state_input(self, raw_value: object) -> int:
        truthy = (1, "t", "true", "on", "yes", "y")
        falsy = (0, "f", "false", "off", "no", "n")

        normalized: int | str
        if isinstance(raw_value, str):
            normalized = raw_value.casefold()
        elif isinstance(raw_value, (bool, int, float)):
            normalized = int(raw_value)
        else:
            msg = f"Invalid type for state: {type(raw_value)}"
            raise TypeError(msg)

        if normalized in truthy:
            return 1
        if normalized in falsy:
            return 0

        msg = f"Invalid value for state: {normalized}"
        raise ValueError(msg)

    def _validate_byte_range(self, value: int, field_name: str) -> None:
        """Validate that a byte-oriented attribute stays within the expected range."""
        if not BYTE_MIN_VALUE <= value <= BYTE_MAX_VALUE:
            msg = f"{field_name} must be between {BYTE_MIN_VALUE} and {BYTE_MAX_VALUE}, got: {value}"
            raise ValueError(msg)

    @property
    def is_hvac(self) -> bool:
        """Return True if the device exposes HVAC capabilities."""
        if self._is_hvac is not None:
            return self._is_hvac
        if self.type is None:
            return False

        capabilities = cast("DeviceCategoryMap | None", getattr(self, "Capabilities", None))
        device_types = cast("DeviceCategoryMap | None", getattr(self, "DeviceTypes", None))
        if capabilities is None or device_types is None:
            return False

        device_type = self.type
        heat_types = capabilities.get("HEAT")
        cool_types = capabilities.get("COOL")
        thermostat_types = device_types.get("THERMOSTAT")
        return (
            (heat_types is not None and device_type in heat_types)
            or (cool_types is not None and device_type in cool_types)
            or (thermostat_types is not None and device_type in thermostat_types)
        )

    @is_hvac.setter
    def is_hvac(self, value: bool) -> None:
        bool_value = self._validate_bool(value, "is_hvac")
        if bool_value is not None:
            self._is_hvac = bool_value

    @property
    def version(self) -> int | str | None:
        """Return the firmware version value currently stored."""
        return self._version

    @version.setter
    def version(self, value: str | int | None) -> None:
        if value is None:
            return
        if isinstance(value, int):
            self._version = value
            return
        if value == "":
            logger.debug(
                "%s in CyncDevice.version().setter, the firmwareVersion extracted from the cloud is an empty string!",
                self.lp,
            )
            return
        try:
            _x = int(value.replace(".", "").replace("\0", "").strip())
        except ValueError:
            logger.exception("%s Failed to convert firmware version to int", self.lp)
        else:
            self._version = _x

    @property
    def mac(self) -> str | None:
        """Return the device MAC address as a string, if available."""
        return str(self._mac) if self._mac is not None else None

    @mac.setter
    def mac(self, value: str) -> None:
        self._mac = str(value)

    @property
    def bt_only(self) -> bool:
        """Return True if this device only supports Bluetooth transport."""
        if self.wifi_mac == "00:01:02:03:04:05":
            return True
        if self.metadata:
            return self.metadata.protocol.TCP is False
        return False

    @property
    def has_wifi(self) -> bool:
        """Return True if the device exposes Wi-Fi or TCP connectivity."""
        if self.metadata:
            return self.metadata.protocol.TCP
        return False

    @property
    @override
    def is_light(self) -> bool:
        if self._is_light is not None:
            return self._is_light
        if self.metadata:
            return self.metadata.type == DeviceClassification.LIGHT
        return False

    @is_light.setter
    def is_light(self, value: bool) -> None:
        bool_value = self._validate_bool(value, "is_light")
        if bool_value is not None:
            self._is_light = bool_value

    @property
    @override
    def is_switch(self) -> bool:
        if self._is_switch is not None:
            return self._is_switch
        if self.metadata:
            return self.metadata.type == DeviceClassification.SWITCH
        return False

    @is_switch.setter
    def is_switch(self, value: bool) -> None:
        bool_value = self._validate_bool(value, "is_switch")
        if bool_value is not None:
            self._is_switch = bool_value

    @property
    def is_plug(self) -> bool:
        """Return True when the switch metadata indicates plug support."""
        if self._is_plug is not None:
            return self._is_plug
        if (
            self.metadata
            and self.metadata.type == DeviceClassification.SWITCH
            and isinstance(self.metadata.capabilities, SwitchCapabilities)
        ):
            return self.metadata.capabilities.plug
        return False

    @is_plug.setter
    def is_plug(self, value: bool) -> None:
        self._is_plug = value

    @property
    @override
    def is_fan_controller(self) -> bool:
        if self._is_fan_controller is not None:
            return self._is_fan_controller
        if (
            self.metadata
            and self.metadata.type == DeviceClassification.SWITCH
            and isinstance(self.metadata.capabilities, SwitchCapabilities)
        ):
            return self.metadata.capabilities.fan
        return False

    @is_fan_controller.setter
    def is_fan_controller(self, value: bool) -> None:
        bool_value = self._validate_bool(value, "is_fan_controller")
        if bool_value is not None:
            self._is_fan_controller = bool_value

    @property
    def is_dimmable(self) -> bool:
        """Return True if metadata indicates dimming capability."""
        if (
            self.metadata
            and self.metadata.type == DeviceClassification.LIGHT
            and isinstance(self.metadata.capabilities, LightCapabilities)
        ):
            return self.metadata.capabilities.dimmable
        return False

    @property
    def supports_rgb(self) -> bool:
        """Return True if metadata reports RGB color capability."""
        if self._supports_rgb is not None:
            return self._supports_rgb
        if (
            self.metadata
            and self.metadata.type == DeviceClassification.LIGHT
            and isinstance(self.metadata.capabilities, LightCapabilities)
        ):
            return self.metadata.capabilities.color
        return False

    @supports_rgb.setter
    def supports_rgb(self, value: bool) -> None:
        self._supports_rgb = value

    @property
    def supports_temperature(self) -> bool:
        """Return True when the device can report or set color temperature."""
        if self._supports_temperature is not None:
            return self._supports_temperature
        if (
            self.metadata
            and self.metadata.type == DeviceClassification.LIGHT
            and isinstance(self.metadata.capabilities, LightCapabilities)
        ):
            return self.metadata.capabilities.tunable_white
        return False

    @supports_temperature.setter
    def supports_temperature(self, value: bool) -> None:
        self._supports_temperature = value

    @property
    def supports_brightness(self) -> bool:
        """Device supports brightness control."""
        return self.is_light or self.is_dimmable

    def get_ctrl_msg_id_bytes(self):
        """Return the next control-message identifier bytes.

        Control packets use this incrementing value as both a checksum input and an ID.
        """
        id_byte, rollover_byte = self.control_bytes
        # logger.debug(f"{lp} Getting control message ID bytes: ctrl_byte={id_byte} rollover_byte={rollover_byte}")
        id_byte += 1
        if id_byte > BYTE_MAX_VALUE:
            id_byte = id_byte % (BYTE_MAX_VALUE + 1)
            rollover_byte += 1

        self.control_bytes = [id_byte, rollover_byte]
        # logger.debug(f"{lp} new data: ctrl_byte={id_byte} rollover_byte={rollover_byte} // {self.control_bytes=}")
        return self.control_bytes

    @property
    def online(self) -> bool:
        """Return True if the device is currently marked online."""
        return self._online

    @online.setter
    def online(self, value: bool) -> None:
        g = _get_global_object()
        try:
            bool_value = self._require_bool(value, "online")
        except TypeError as exc:
            msg = "Online status must be a boolean"
            raise TypeError(msg) from exc
        if bool_value != self._online:
            self._online = bool_value
            if g.mqtt_client and self.id is not None:
                g.tasks.append(asyncio.get_running_loop().create_task(g.mqtt_client.pub_online(self.id, bool_value)))

    @property
    def current_status(self) -> list[int | None]:
        """Return the current status of the device as a list.

        :return: [state, brightness, temperature, red, green, blue]
        """
        return [
            self._state,
            self._brightness,
            self._temperature,
            self._r,
            self._g,
            self._b,
        ]

    @property
    def status(self) -> DeviceStatus:
        """Return the current device status snapshot."""
        return self._status

    @status.setter
    def status(self, value: DeviceStatus):
        if self._status != value:
            self._status = value

    @property
    @override
    def state(self) -> int:
        return self._state

    @state.setter
    def state(self, value: int) -> None:
        """Set the device power state using numeric, boolean, or textual inputs."""
        normalized_value = self._normalize_state_input(value)
        if normalized_value != self._state:
            self._state = normalized_value

    @property
    def brightness(self):
        """Return the cached brightness value."""
        return self._brightness

    @brightness.setter
    def brightness(self, value: int):
        self._validate_byte_range(value, "Brightness")
        if value != self._brightness:
            self._brightness = value

    @property
    @override
    def temperature(self) -> int:
        """Return the cached white temperature value."""
        return self._temperature

    @temperature.setter
    def temperature(self, value: int):
        self._validate_byte_range(value, "Temperature")
        if value != self._temperature:
            self._temperature = value

    @property
    @override
    def red(self) -> int:
        """Return the current red channel value."""
        return self._r

    @red.setter
    def red(self, value: int):
        self._validate_byte_range(value, "Red")
        if value != self._r:
            self._r = value

    @property
    @override
    def green(self) -> int:
        """Return the current green channel value."""
        return self._g

    @green.setter
    def green(self, value: int):
        self._validate_byte_range(value, "Green")
        if value != self._g:
            self._g = value

    @property
    @override
    def blue(self) -> int:
        """Return the current blue channel value."""
        return self._b

    @blue.setter
    def blue(self, value: int):
        self._validate_byte_range(value, "Blue")
        if value != self._b:
            self._b = value

    @property
    def rgb(self):
        """Return the RGB color as a list."""
        return [self._r, self._g, self._b]

    @rgb.setter
    def rgb(self, value: list[int]):
        if len(value) != RGB_CHANNELS:
            msg = f"RGB value must be a list of {RGB_CHANNELS} integers, got: {value}"
            raise ValueError(msg)
        if value != self.rgb:
            self._r, self._g, self._b = value

    @override
    def __repr__(self):
        return f"CyncDevice(id={self.id}, name='{self.name}', state={self._state})"

    @override
    def __str__(self):
        return f"CyncDevice {self.name} (ID: {self.id})"
