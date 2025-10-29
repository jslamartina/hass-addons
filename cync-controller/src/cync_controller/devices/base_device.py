import asyncio

from cync_controller.logging_abstraction import get_logger
from cync_controller.metadata.model_info import DeviceClassification, DeviceTypeInfo, device_type_map
from cync_controller.structs import (
    DeviceStatus,
    GlobalObject,
)
from cync_controller.devices.device_commands import DeviceCommandsMixin

logger = get_logger(__name__)
g = GlobalObject()


async def _noop_callback():
    """No-op async callback function used as placeholder for unused callbacks."""


class CyncDevice(DeviceCommandsMixin):
    """
    A class to represent a Cync device imported from a config file. This class is used to manage the state of the device
    and send commands to it by using its device ID defined when the device was added to your Cync account.
    """

    lp = "CyncDevice:"
    id: int = None
    name: str = None
    cync_type: int | None = None
    mac: str | None = None
    wifi_mac: str | None = None
    fw_version: str | None = None
    home_id: int | None = None
    hvac: dict | None = None
    hass_id: str | None = None
    pending_command: bool = False
    status: DeviceStatus | None = None

    def __init__(
        self,
        cync_id: int,
        cync_type: int | None = None,
        name: str | None = None,
        mac: str | None = None,
        wifi_mac: str | None = None,
        fw_version: str | None = None,
        home_id: int | None = None,
        hvac: dict | None = None,
    ):
        if cync_id is None:
            msg = "Device ID must be provided"
            raise ValueError(msg)
        self.id = cync_id
        self.name = name
        self.cync_type = cync_type
        self.mac = mac
        self.wifi_mac = wifi_mac
        self.fw_version = fw_version
        self.home_id = home_id
        self.hvac = hvac
        self.hass_id = f"{home_id}-device-{cync_id}"
        self.lp = f"CyncDevice:{self.name}({cync_id}):"

        # Initialize device status
        self.status = DeviceStatus()

    @property
    def is_hvac(self) -> bool:
        """Check if this device is an HVAC device."""
        return self.hvac is not None

    @property
    def version(self) -> str:
        """Get the device firmware version."""
        return self.fw_version or "Unknown"

    @property
    def mac(self) -> str | None:
        """Get the device MAC address."""
        return self.mac

    @mac.setter
    def mac(self, value: str | None):
        """Set the device MAC address."""
        self.mac = value

    @property
    def bt_only(self) -> bool:
        """Check if this device is Bluetooth only (no WiFi)."""
        return self.wifi_mac is None

    @property
    def has_wifi(self) -> bool:
        """Check if this device has WiFi capability."""
        return self.wifi_mac is not None

    @property
    def is_light(self) -> bool:
        """Check if this device is a light."""
        if self.cync_type is None:
            return False
        device_info = device_type_map.get(self.cync_type)
        return device_info is not None and device_info.classification == DeviceClassification.LIGHT

    @property
    def is_switch(self) -> bool:
        """Check if this device is a switch."""
        if self.cync_type is None:
            return False
        device_info = device_type_map.get(self.cync_type)
        return device_info is not None and device_info.classification == DeviceClassification.SWITCH

    @property
    def is_plug(self) -> bool:
        """Check if this device is a plug."""
        if self.cync_type is None:
            return False
        device_info = device_type_map.get(self.cync_type)
        return device_info is not None and device_info.classification == DeviceClassification.PLUG

    @property
    def is_fan_controller(self) -> bool:
        """Check if this device is a fan controller."""
        if self.cync_type is None:
            return False
        device_info = device_type_map.get(self.cync_type)
        return device_info is not None and device_info.classification == DeviceClassification.FAN_CONTROLLER

    @property
    def is_dimmable(self) -> bool:
        """Check if this device supports dimming."""
        if self.cync_type is None:
            return False
        device_info = device_type_map.get(self.cync_type)
        return device_info is not None and device_info.is_dimmable

    @property
    def supports_rgb(self) -> bool:
        """Check if this device supports RGB color control."""
        if self.cync_type is None:
            return False
        device_info = device_type_map.get(self.cync_type)
        return device_info is not None and device_info.supports_rgb

    @property
    def supports_temperature(self) -> bool:
        """Check if this device supports color temperature control."""
        if self.cync_type is None:
            return False
        device_info = device_type_map.get(self.cync_type)
        return device_info is not None and device_info.supports_temperature

    @property
    def supports_brightness(self) -> bool:
        """Check if this device supports brightness control."""
        if self.cync_type is None:
            return False
        device_info = device_type_map.get(self.cync_type)
        return device_info is not None and device_info.supports_brightness

    @property
    def online(self) -> bool:
        """Check if this device is online."""
        return self.status is not None and self.status.online

    @property
    def current_status(self) -> DeviceStatus | None:
        """Get the current device status."""
        return self.status

    @property
    def state(self) -> int:
        """Get the current device state (0=off, 1=on)."""
        return self.status.state if self.status else 0

    @property
    def brightness(self) -> int:
        """Get the current device brightness (0-100)."""
        return self.status.brightness if self.status else 0

    @property
    def temperature(self) -> int:
        """Get the current device color temperature (0-100)."""
        return self.status.temperature if self.status else 0

    @property
    def red(self) -> int:
        """Get the current red component (0-255)."""
        return self.status.red if self.status else 0

    @property
    def green(self) -> int:
        """Get the current green component (0-255)."""
        return self.status.green if self.status else 0

    @property
    def blue(self) -> int:
        """Get the current blue component (0-255)."""
        return self.status.blue if self.status else 0

    @property
    def rgb(self) -> tuple[int, int, int]:
        """Get the current RGB values as a tuple."""
        return (self.red, self.green, self.blue)

    def get_ctrl_msg_id_bytes(self):
        """Get the next control message ID as bytes."""
        # Simple incrementing counter for message IDs
        # In a real implementation, this would be more sophisticated
        msg_id = (id(self) + hash(self.name or "")) % 65536
        return msg_id.to_bytes(2, byteorder="big")

    def __repr__(self):
        return f"<CyncDevice: {self.id}>"

    def __str__(self):
        return f"CyncDevice:{self.id}:"