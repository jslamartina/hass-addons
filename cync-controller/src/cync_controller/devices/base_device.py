import asyncio
from typing import Any

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


async def _noop_callback():
    """No-op async callback function used as placeholder for unused callbacks."""


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
    """A class to represent a Cync device imported from a config file. This class is used to manage the state of the device
    and send commands to it by using its device ID defined when the device was added to your Cync account.
    """

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
    hvac: dict[str, Any] | None = None
    _online: bool = False
    metadata: DeviceTypeInfo | None = None
    name: str = ""
    offline_count: int = 0

    def __init__(
        self,
        cync_id: int,
        cync_type: int | None = None,
        name: str | None = None,
        mac: str | None = None,
        wifi_mac: str | None = None,
        fw_version: str | None = None,
        home_id: int | None = None,
        hvac: dict[str, Any] | None = None,
    ) -> None:
        self.control_bytes: bytes = bytes([0x00, 0x00])
        if cync_id is None:
            msg = "ID must be provided to constructor"
            raise ValueError(msg)
        self.id = cync_id
        self.type = cync_type
        self.metadata = device_type_map[cync_type] if cync_type is not None and cync_type in device_type_map else None
        self.home_id: int | None = home_id
        self.hass_id: str = f"{home_id}-{cync_id}"
        self._mac = mac
        self.wifi_mac = wifi_mac
        self._version: int | None = None
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

    @property
    def is_hvac(self) -> bool:
        if self._is_hvac is not None:
            return self._is_hvac
        if self.type is not None:
            # Try to determine if the device is HVAC if _is_hvac is not set
            capabilities = getattr(self, "Capabilities", None)
            device_types = getattr(self, "DeviceTypes", None)
            if self.type is None or capabilities is None or device_types is None:
                return False
            return (
                self.type in capabilities.get("HEAT", set())
                or self.type in capabilities.get("COOL", set())
                or self.type in device_types.get("THERMOSTAT", set())
            )
        return False

    @is_hvac.setter
    def is_hvac(self, value: bool) -> None:
        if isinstance(value, bool):
            self._is_hvac = value

    @property
    def version(self) -> int | None:
        return self._version

    @version.setter
    def version(self, value: str | int | None) -> None:
        if value is None:
            return
        if isinstance(value, int):
            self._version = value
        elif isinstance(value, str):
            if value == "":
                logger.debug(
                    "%s in CyncDevice.version().setter, the firmwareVersion "
                    "extracted from the cloud is an empty string!",
                    self.lp,
                )
            else:
                try:
                    _x = int(value.replace(".", "").replace("\0", "").strip())
                except ValueError:
                    logger.exception("%s Failed to convert firmware version to int", self.lp)
                else:
                    self._version = _x

    @property
    def mac(self) -> str | None:
        return str(self._mac) if self._mac is not None else None

    @mac.setter
    def mac(self, value: str) -> None:
        self._mac = str(value)

    @property
    def bt_only(self) -> bool:
        if self.wifi_mac == "00:01:02:03:04:05":
            return True
        if self.metadata:
            return self.metadata.protocol.TCP is False
        return False

    @property
    def has_wifi(self) -> bool:
        if self.metadata:
            return self.metadata.protocol.TCP
        return False

    @property
    def is_light(self):
        if self._is_light is not None:
            return self._is_light
        if self.metadata:
            return self.metadata.type == DeviceClassification.LIGHT
        return False

    @is_light.setter
    def is_light(self, value: bool) -> None:
        if isinstance(value, bool):
            self._is_light = value
        else:
            logger.error(
                "%s is_light must be a boolean value, got %s instead",
                self.lp,
                type(value),
            )

    @property
    def is_switch(self) -> bool:
        if self._is_switch is not None:
            return self._is_switch
        if self.metadata:
            return self.metadata.type == DeviceClassification.SWITCH
        return False

    @is_switch.setter
    def is_switch(self, value: bool) -> None:
        if isinstance(value, bool):
            self._is_switch = value
        else:
            logger.error(
                "%s is_switch must be a boolean value, got %s instead",
                self.lp,
                type(value),
            )

    @property
    def is_plug(self) -> bool:
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
    def is_fan_controller(self):
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
        self._is_fan_controller = value

    @property
    def is_dimmable(self) -> bool:
        if (
            self.metadata
            and self.metadata.type == DeviceClassification.LIGHT
            and isinstance(self.metadata.capabilities, LightCapabilities)
        ):
            return self.metadata.capabilities.dimmable
        return False

    @property
    def supports_rgb(self) -> bool:
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
        """Control packets need a number that gets incremented, it is used as a type of msg ID and
        in calculating the checksum. Result is mod 256 in order to keep it within 0-255.
        """
        id_byte, rollover_byte = self.control_bytes
        # logger.debug(f"{lp} Getting control message ID bytes: ctrl_byte={id_byte} rollover_byte={rollover_byte}")
        id_byte += 1
        if id_byte > 255:
            id_byte = id_byte % 256
            rollover_byte += 1

        self.control_bytes = [id_byte, rollover_byte]
        # logger.debug(f"{lp} new data: ctrl_byte={id_byte} rollover_byte={rollover_byte} // {self.control_bytes=}")
        return self.control_bytes

    @property
    def online(self) -> bool:
        return self._online

    @online.setter
    def online(self, value: bool):
        g = _get_global_object()
        if not isinstance(value, bool):
            msg = f"Online status must be a boolean, got: {type(value)}"
            raise TypeError(msg)
        if value != self._online:
            self._online = value
            if g.mqtt_client and self.id is not None:
                g.tasks.append(asyncio.get_running_loop().create_task(g.mqtt_client.pub_online(self.id, value)))

    @property
    def current_status(self) -> list[int | None]:
        """Return the current status of the device as a list

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
        return self._status

    @status.setter
    def status(self, value: DeviceStatus):
        if self._status != value:
            self._status = value

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value: int | bool | str):
        """Set the state of the device.
        Accepts int, bool, or str. 0, 'f', 'false', 'off', 'no', 'n' are off. 1, 't', 'true', 'on', 'yes', 'y' are on.
        """
        _t = (1, "t", "true", "on", "yes", "y")
        _f = (0, "f", "false", "off", "no", "n")
        if isinstance(value, str):
            value = value.casefold()
        elif isinstance(value, (bool, float)):
            value = int(value)
        elif isinstance(value, int):
            pass
        else:
            msg = f"Invalid type for state: {type(value)}"
            raise TypeError(msg)

        if value in _t:
            value = 1
        elif value in _f:
            value = 0
        else:
            msg = f"Invalid value for state: {value}"
            raise ValueError(msg)

        if value != self._state:
            self._state = value

    @property
    def brightness(self):
        return self._brightness

    @brightness.setter
    def brightness(self, value: int):
        if value < 0 or value > 255:
            msg = f"Brightness must be between 0 and 255, got: {value}"
            raise ValueError(msg)
        if value != self._brightness:
            self._brightness = value

    @property
    def temperature(self):
        return self._temperature

    @temperature.setter
    def temperature(self, value: int):
        if value < 0 or value > 255:
            msg = f"Temperature must be between 0 and 255, got: {value}"
            raise ValueError(msg)
        if value != self._temperature:
            self._temperature = value

    @property
    def red(self) -> int:
        return self._r

    @red.setter
    def red(self, value: int):
        if value < 0 or value > 255:
            msg = f"Red must be between 0 and 255, got: {value}"
            raise ValueError(msg)
        if value != self._r:
            self._r = value

    @property
    def green(self) -> int:
        return self._g

    @green.setter
    def green(self, value: int):
        if value < 0 or value > 255:
            msg = f"Green must be between 0 and 255, got: {value}"
            raise ValueError(msg)
        if value != self._g:
            self._g = value

    @property
    def blue(self) -> int:
        return self._b

    @blue.setter
    def blue(self, value: int):
        if value < 0 or value > 255:
            msg = f"Blue must be between 0 and 255, got: {value}"
            raise ValueError(msg)
        if value != self._b:
            self._b = value

    @property
    def rgb(self):
        """Return the RGB color as a list"""
        return [self._r, self._g, self._b]

    @rgb.setter
    def rgb(self, value: list[int]):
        if len(value) != 3:
            msg = f"RGB value must be a list of 3 integers, got: {value}"
            raise ValueError(msg)
        if value != self.rgb:
            self._r, self._g, self._b = value

    def __repr__(self):
        return f"CyncDevice(id={self.id}, name='{self.name}', state={self._state})"

    def __str__(self):
        return f"CyncDevice {self.name} (ID: {self.id})"
