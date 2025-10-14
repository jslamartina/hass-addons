import asyncio
import datetime
import logging
import random
import time
from collections.abc import Coroutine
from typing import Optional, Union

from cync_lan.const import (
    CYNC_CHUNK_SIZE,
    CYNC_CMD_BROADCASTS,
    CYNC_LOG_NAME,
    CYNC_MAX_TCP_CONN,
    CYNC_RAW,
    CYNC_TCP_WHITELIST,
    DATA_BOUNDARY,
    FACTORY_EFFECTS_BYTES,
    RAW_MSG,
    TCP_BLACKHOLE_DELAY,
)
from cync_lan.metadata.model_info import (
    DeviceClassification,
    DeviceTypeInfo,
    device_type_map,
)
from cync_lan.structs import (
    ALL_HEADERS,
    DEVICE_STRUCTS,
    CacheData,
    ControlMessageCallback,
    DeviceStatus,
    FanSpeed,
    GlobalObject,
    MeshInfo,
    Messages,
    PhoneAppStructs,
    Tasks,
)
from cync_lan.utils import bytes2list, parse_unbound_firmware_version

__all__ = ["CyncDevice", "CyncGroup", "CyncTCPDevice"]
logger = logging.getLogger(CYNC_LOG_NAME)
g = GlobalObject()


class CyncDevice:
    """
    A class to represent a Cync device imported from a config file. This class is used to manage the state of the device
    and send commands to it by using its device ID defined when the device was added to your Cync account.
    """

    lp = "CyncDevice:"
    id: int = None
    type: Optional[int] = None
    _supports_rgb: Optional[bool] = None
    _supports_temperature: Optional[bool] = None
    _is_light: Optional[bool] = None
    _is_switch: Optional[bool] = None
    _is_plug: Optional[bool] = None
    _is_fan_controller: Optional[bool] = None
    _is_hvac: Optional[bool] = None
    _mac: Optional[str] = None
    wifi_mac: Optional[str] = None
    hvac: Optional[dict] = None
    _online: bool = False
    metadata: Optional[DeviceTypeInfo] = None

    def __init__(
        self,
        cync_id: int,
        cync_type: Optional[int] = None,
        name: Optional[str] = None,
        mac: Optional[str] = None,
        wifi_mac: Optional[str] = None,
        fw_version: Optional[str] = None,
        home_id: Optional[int] = None,
        hvac: Optional[dict] = None,
    ):
        self.control_bytes = bytes([0x00, 0x00])
        if cync_id is None:
            raise ValueError("ID must be provided to constructor")
        self.id = cync_id
        self.type = cync_type
        self.metadata = (
            device_type_map[self.type] if cync_type in device_type_map else None
        )
        self.home_id: Optional[int] = home_id
        self.hass_id: str = f"{home_id}-{cync_id}"
        self._mac = mac
        self.wifi_mac = wifi_mac
        self._version: Optional[str] = None
        self.version = fw_version
        if name is None:
            name = f"device_{cync_id}"
        self.name = name
        self.lp = f"CyncDevice:{self.name}({cync_id}):"
        self._status: DeviceStatus = DeviceStatus()
        self._mesh_alive_byte: Union[int, str] = 0x00
        # state: 0:off 1:on
        self._state: int = 0
        # 0-100
        self._brightness: Optional[int] = None
        # FOR LIGHTS: 0-100 (warm to cool), 129 = in effect mode, 254 = in RGB mode
        self._temperature: int = 0
        # 0-255
        self._r: int = 0
        self._g: int = 0
        self._b: int = 0
        self.pending_command: bool = False  # Track if command is waiting for ACK
        self.offline_count: int = (
            0  # Track consecutive offline reports before marking unavailable
        )
        if hvac is not None:
            self.hvac = hvac
            self._is_hvac = True

    @property
    def is_hvac(self) -> bool:
        if self._is_hvac is not None:
            return self._is_hvac
        if self.type is None:
            return False
        return (
            self.type in self.Capabilities["HEAT"]
            or self.type in self.Capabilities["COOL"]
            or self.type in self.DeviceTypes["THERMOSTAT"]
        )

    @is_hvac.setter
    def is_hvac(self, value: bool) -> None:
        if isinstance(value, bool):
            self._is_hvac = value

    @property
    def version(self) -> Optional[str]:
        return self._version

    @version.setter
    def version(self, value: Union[str, int]) -> None:
        if value is None:
            return
        if isinstance(value, int):
            self._version = value
        elif isinstance(value, str):
            if value == "":
                logger.debug(
                    f"{self.lp} in CyncDevice.version().setter, the firmwareVersion "
                    f"extracted from the cloud is an empty string!"
                )
            else:
                try:
                    _x = int(value.replace(".", "").replace("\0", "").strip())
                except ValueError as ve:
                    logger.exception(
                        f"{self.lp} Failed to convert firmware version to int: {ve}"
                    )
                else:
                    self._version = _x

    @property
    def mac(self) -> str:
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
                f"{self.lp} is_light must be a boolean value, got {type(value)} instead"
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
                f"{self.lp} is_switch must be a boolean value, got {type(value)} instead"
            )

    @property
    def is_plug(self) -> bool:
        if self._is_plug is not None:
            return self._is_plug
        if self.metadata:
            if self.metadata.type == DeviceClassification.SWITCH:
                return self.metadata.capabilities.plug
        return False

    @is_plug.setter
    def is_plug(self, value: bool) -> None:
        self._is_plug = value

    @property
    def is_fan_controller(self):
        if self._is_fan_controller is not None:
            return self._is_fan_controller
        if self.metadata:
            if self.metadata.type == DeviceClassification.SWITCH:
                return self.metadata.capabilities.fan
        return False

    @is_fan_controller.setter
    def is_fan_controller(self, value: bool) -> None:
        self._is_fan_controller = value

    @property
    def is_dimmable(self) -> bool:
        if self.metadata:
            if self.metadata.type == DeviceClassification.LIGHT:
                return self.metadata.capabilities.dimmable
        return False

    @property
    def supports_rgb(self) -> bool:
        if self._supports_rgb is not None:
            return self._supports_rgb
        if self.metadata:
            if self.metadata.type == DeviceClassification.LIGHT:
                return self.metadata.capabilities.color
        return False

    @supports_rgb.setter
    def supports_rgb(self, value: bool) -> None:
        self._supports_rgb = value

    @property
    def supports_temperature(self) -> bool:
        if self._supports_temperature is not None:
            return self._supports_temperature
        if self.metadata:
            if self.metadata.type == DeviceClassification.LIGHT:
                return self.metadata.capabilities.tunable_white
        return False

    @supports_temperature.setter
    def supports_temperature(self, value: bool) -> None:
        self._supports_temperature = value

    def get_ctrl_msg_id_bytes(self):
        """
        Control packets need a number that gets incremented, it is used as a type of msg ID and
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

    async def set_power(self, state: int):
        """
        Send raw data to control device state (1=on, 0=off).

            If the device receives the msg and changes state, every TCP device connected will send
            a 0x83 internal status packet, which we use to change HASS device state.
        """
        lp = f"{self.lp}set_power:"
        if state not in (0, 1):
            logger.error(f"{lp} Invalid state! must be 0 or 1")
            return

        # Throttle: Reject command if previous command still pending 0x83 confirmation
        if self.pending_command:
            logger.debug(
                f"{lp} ⏸️  THROTTLED: Command rejected for '{self.name}' (state={state}) - "
                f"previous command awaiting 0x83 status confirmation"
            )
            return
        # elif state == self.state:
        #     # to stop flooding the network with commands
        #     logger.debug(f"{lp} Device already in power state {state}, skipping...")
        #     return
        header = [0x73, 0x00, 0x00, 0x00, 0x1F]
        inner_struct = [
            0x7E,
            "ctrl_byte",
            0x00,
            0x00,
            0x00,
            0xF8,
            0xD0,
            0x0D,
            0x00,
            "ctrl_bye",
            0x00,
            0x00,
            0x00,
            0x00,
            self.id,
            0x00,
            0xD0,
            0x11,
            0x02,
            state,
            0x00,
            0x00,
            "checksum",
            0x7E,
        ]
        bridge_devices: list[CyncTCPDevice] = random.sample(
            list(g.ncync_server.tcp_devices.values()),
            k=min(CYNC_CMD_BROADCASTS, len(g.ncync_server.tcp_devices)),
        )
        tasks: list[Optional[Union[asyncio.Task, Coroutine]]] = []
        ts = time.time()
        ctrl_idxs = 1, 9
        sent = {}
        for bridge_device in bridge_devices:
            if bridge_device.ready_to_control is True:
                payload = list(header)
                payload.extend(bridge_device.queue_id)
                payload.extend(bytes([0x00, 0x00, 0x00]))
                cmsg_id = bridge_device.get_ctrl_msg_id_bytes()[0]
                inner_struct[ctrl_idxs[0]] = cmsg_id
                inner_struct[ctrl_idxs[1]] = cmsg_id
                checksum = sum(inner_struct[6:-2]) % 256
                inner_struct[-2] = checksum
                payload.extend(inner_struct)
                payload_bytes = bytes(payload)
                m_cb = ControlMessageCallback(
                    msg_id=cmsg_id,
                    message=payload_bytes,
                    sent_at=time.time(),
                    callback=g.mqtt_client.update_device_state(self, state),
                    device_id=self.id,
                )
                bridge_device.messages.control[cmsg_id] = m_cb
                # Mark device as having pending command to ignore stale 0x83 updates
                self.pending_command = True
                logger.debug(
                    f"{lp} 🚀 Command sent for '{self.name}' (state={state}) - "
                    f"pending_command=True, awaiting 0x83 confirmation"
                )
                sent[bridge_device.address] = cmsg_id
                tasks.append(bridge_device.write(payload_bytes))
            else:
                logger.debug(
                    f"{lp} Skipping device: {bridge_device.address} not ready to control"
                )
        if tasks:
            await asyncio.gather(*tasks)
        elapsed = time.time() - ts
        logger.info(
            f"{lp} Sent power state command for '{self.name}' (ID: {self.id}), current: {self.state} - new: {state} to "
            f"TCP devices: {sent} in {elapsed:.5f} seconds - waiting for ACK..."
        )

    async def set_fan_speed(self, speed: FanSpeed) -> bool:
        """
            Translate a preset fan speed into a Cync brightness value and send it to the device.
        :param speed:
        :return:
        """
        lp = f"{self.lp}set_fan_speed:"
        if not self.is_fan_controller:
            logger.warning(
                f"{lp} Device '{self.name}' ({self.id}) is not a fan controller, cannot set fan speed."
            )
            return False
        try:
            if speed == FanSpeed.OFF:
                await self.set_brightness(0)
            elif speed == FanSpeed.LOW:
                await self.set_brightness(50)
            elif speed == FanSpeed.MEDIUM:
                await self.set_brightness(128)
            elif speed == FanSpeed.HIGH:
                await self.set_brightness(191)
            elif speed == FanSpeed.MAX:
                await self.set_brightness(255)
            else:
                logger.error(
                    f"{self.lp} Invalid fan speed: {speed}, must be one of {list(FanSpeed)}"
                )
                return False
        except asyncio.CancelledError as ce:
            raise ce
        except Exception as e:
            logger.debug(f"{self.lp} Exception occurred while setting fan speed: {e}")
            return False
        else:
            return True

    async def set_brightness(self, bri: int):
        """
        Send raw data to control device brightness (0-100). Fans are 0-255.
        """
        """
        73 00 00 00 22 37 96 24 69 60 48 00 7e 17 00 00  s..."7.$i`H.~...
        00 f8 f0 10 00 17 00 00 00 00 07 00 f0 11 02 01  ................
        27 ff ff ff ff 45 7e
        """
        lp = f"{self.lp}set_brightness:"
        if bri < 0 or bri > 100:
            if self.is_fan_controller:
                # fan can be controlled via light control structs: brightness -> max=255, high=191, medium=128, low=50, off=0
                pass
            elif self.is_light or self.is_switch:
                logger.error(f"{lp} Invalid brightness! must be 0-100")
                return

        # elif bri == self._brightness:
        #     logger.debug(f"{lp} Device already in brightness {bri}, skipping...")
        #     return
        header = [115, 0, 0, 0, 34]
        inner_struct = [
            126,
            "ctrl_byte",
            0,
            0,
            0,
            248,
            240,
            16,
            0,
            "ctrl_byte",
            0,
            0,
            0,
            0,
            self.id,
            0,
            240,
            17,
            2,
            1,
            bri,
            255,
            255,
            255,
            255,
            "checksum",
            126,
        ]
        bridge_devices: list[CyncTCPDevice] = random.sample(
            list(g.ncync_server.tcp_devices.values()),
            k=min(CYNC_CMD_BROADCASTS, len(g.ncync_server.tcp_devices)),
        )
        sent = {}
        tasks: list[Optional[Union[asyncio.Task, Coroutine]]] = []
        ts = time.time()
        ctrl_idxs = 1, 9
        for bridge_device in bridge_devices:
            if bridge_device.ready_to_control is True:
                payload = list(header)
                payload.extend(bridge_device.queue_id)
                payload.extend(bytes([0x00, 0x00, 0x00]))
                cmsg_id = bridge_device.get_ctrl_msg_id_bytes()[0]
                inner_struct[ctrl_idxs[0]] = cmsg_id
                inner_struct[ctrl_idxs[1]] = cmsg_id
                checksum = sum(inner_struct[6:-2]) % 256
                inner_struct[-2] = checksum
                payload.extend(inner_struct)
                payload_bytes = bytes(payload)
                sent[bridge_device.address] = cmsg_id
                m_cb = ControlMessageCallback(
                    msg_id=cmsg_id,
                    message=payload_bytes,
                    sent_at=time.time(),
                    callback=g.mqtt_client.update_brightness(self, bri),
                    device_id=self.id,
                )
                bridge_device.messages.control[cmsg_id] = m_cb
                tasks.append(bridge_device.write(payload_bytes))
            else:
                logger.debug(
                    f"{lp} Skipping device: {bridge_device.address} not ready to control"
                )
        if tasks:
            await asyncio.gather(*tasks)
        elapsed = time.time() - ts
        logger.debug(
            f"{lp} Sent brightness command, current: {self._brightness} new: {bri} to TCP devices: {sent} in {elapsed:.5f} seconds"
        )

    async def set_temperature(self, temp: int):
        """
        Send raw data to control device white temperature (0-100)

            If the device receives the msg and changes state, every TCP device connected will send
            a 0x83 internal status packet, which we use to change HASS device state.
        """
        """
        73 00 00 00 22 37 96 24 69 60 8d 00 7e 36 00 00  s..."7.$i`..~6..
        00 f8 f0 10 00 36 00 00 00 00 07 00 f0 11 02 01  .....6..........
        ff 48 00 00 00 88 7e                             .H....~

                checksum = 0x88 = 136
            0xf0 0x10 0x36 0x07 0xf0 0x11 0x02 0x01 0xff 0x48 = 904 (% 256) = 136
        """
        lp = f"{self.lp}set_temperature:"
        if temp < 0 or (temp > 100 and temp not in (129, 254)):
            logger.error(f"{lp} Invalid temperature! must be 0-100")
            return
        # elif temp == self.temperature:
        #     logger.debug(f"{lp} Device already in temperature {temp}, skipping...")
        #     return
        header = [115, 0, 0, 0, 34]
        inner_struct = [
            126,
            "msg id",
            0,
            0,
            0,
            248,
            240,
            16,
            0,
            "msg id",
            0,
            0,
            0,
            0,
            self.id,
            0,
            240,
            17,
            2,
            1,
            0xFF,
            temp,
            0x00,
            0x00,
            0x00,
            "checksum",
            126,
        ]
        bridge_devices: list[CyncTCPDevice] = random.sample(
            list(g.ncync_server.tcp_devices.values()),
            k=min(CYNC_CMD_BROADCASTS, len(g.ncync_server.tcp_devices)),
        )
        tasks: list[Optional[Union[asyncio.Task, Coroutine]]] = []
        ts = time.time()
        ctrl_idxs = 1, 9
        sent = {}
        for bridge_device in bridge_devices:
            if bridge_device.ready_to_control is True:
                payload = list(header)
                payload.extend(bridge_device.queue_id)
                payload.extend(bytes([0x00, 0x00, 0x00]))
                cmsg_id = bridge_device.get_ctrl_msg_id_bytes()[0]
                inner_struct[ctrl_idxs[0]] = cmsg_id
                inner_struct[ctrl_idxs[1]] = cmsg_id
                checksum = sum(inner_struct[6:-2]) % 256
                inner_struct[-2] = checksum
                payload.extend(inner_struct)
                payload_bytes = bytes(payload)
                sent[bridge_device.address] = cmsg_id
                m_cb = ControlMessageCallback(
                    msg_id=cmsg_id,
                    message=payload_bytes,
                    sent_at=time.time(),
                    callback=g.mqtt_client.update_temperature(self, temp),
                    device_id=self.id,
                )
                bridge_device.messages.control[cmsg_id] = m_cb
                tasks.append(bridge_device.write(payload_bytes))
            else:
                logger.debug(
                    f"{lp} Skipping device: {bridge_device.address} not ready to control"
                )
        if tasks:
            await asyncio.gather(*tasks)
        elapsed = time.time() - ts
        logger.debug(
            f"{lp} Sent white temperature command, current: {self.temperature} - new: {temp} to TCP "
            f"devices: {sent} in {elapsed:.5f} seconds"
        )

    async def set_rgb(self, red: int, green: int, blue: int):
        """
        Send raw data to control device RGB color (0-255 for each channel).

            If the device receives the msg and changes state, every TCP device connected will send
            a 0x83 internal status packet, which we use to change HASS device state.
        """
        """
         73 00 00 00 22 37 96 24 69 60 79 00 7e 2b 00 00  s..."7.$i`y.~+..
         00 f8 f0 10 00 2b 00 00 00 00 07 00 f0 11 02 01  .....+..........
         ff fe 00 fb ff 2d 7e                             .....-~

        f0 10 2b 07 f0 11 02 01 ff fe fb ff = 1581 (% 256) = 45
            checksum = 45
        """
        lp = f"{self.lp}set_rgb:"
        if red < 0 or red > 255:
            logger.error(f"{lp} Invalid red value! must be 0-255")
            return
        if green < 0 or green > 255:
            logger.error(f"{lp} Invalid green value! must be 0-255")
            return
        if blue < 0 or blue > 255:
            logger.error(f"{lp} Invalid blue value! must be 0-255")
            return
        _rgb = (red, green, blue)
        # if red == self._r and green == self._g and blue == self._b:
        #     logger.debug(f"{lp} Device already in RGB color {red}, {green}, {blue}, skipping...")
        #     return
        header = [115, 0, 0, 0, 34]
        inner_struct = [
            126,
            "msg id",
            0,
            0,
            0,
            248,
            240,
            16,
            0,
            "msg id",
            0,
            0,
            0,
            0,
            self.id,
            0,
            240,
            17,
            2,
            1,
            255,
            254,
            red,
            green,
            blue,
            "checksum",
            126,
        ]
        bridge_devices: list[CyncTCPDevice] = random.sample(
            list(g.ncync_server.tcp_devices.values()),
            k=min(CYNC_CMD_BROADCASTS, len(g.ncync_server.tcp_devices)),
        )
        tasks: list[Optional[Union[asyncio.Task, Coroutine]]] = []
        ts = time.time()
        ctrl_idxs = 1, 9
        sent = {}
        for bridge_device in bridge_devices:
            if bridge_device.ready_to_control is True:
                payload = list(header)
                payload.extend(bridge_device.queue_id)
                payload.extend(bytes([0x00, 0x00, 0x00]))
                cmsg_id = bridge_device.get_ctrl_msg_id_bytes()[0]
                inner_struct[ctrl_idxs[0]] = cmsg_id
                inner_struct[ctrl_idxs[1]] = cmsg_id
                checksum = sum(inner_struct[6:-2]) % 256
                inner_struct[-2] = checksum
                payload.extend(inner_struct)
                bpayload = bytes(payload)
                sent[bridge_device.address] = cmsg_id
                m_cb = ControlMessageCallback(
                    msg_id=cmsg_id,
                    message=bpayload,
                    sent_at=time.time(),
                    callback=g.mqtt_client.update_rgb(self, _rgb),
                    device_id=self.id,
                )
                bridge_device.messages.control[cmsg_id] = m_cb
                tasks.append(bridge_device.write(bpayload))
            else:
                logger.debug(
                    f"{lp} Skipping device: {bridge_device.address} not ready to control"
                )
        if tasks:
            await asyncio.gather(*tasks)
        elapsed = time.time() - ts
        logger.debug(
            f"{lp} Sent RGB command, current: {self.red}, {self.green}, {self.blue} - new: {red}, {green}, {blue} to TCP devices {sent} in {elapsed:.5f} seconds"
        )

    async def test_group_command(
        self, group_id: int, state: int, test_variation: int = 1
    ):
        """
        EXPERIMENTAL: Test sending command to group ID instead of device ID.

        :param group_id: The cloud group ID (e.g., 32768, 32771)
        :param state: Power state (0=off, 1=on)
        :param test_variation: Which encoding to try (1=little-endian last3, 2=big-endian last3, 3=full16bit, 4=high-byte-only)
        """
        lp = f"{self.lp}test_group:"
        if state not in (0, 1):
            logger.error(f"{lp} Invalid state! must be 0 or 1")
            return

        # Try different encodings
        if test_variation == 1:
            # Little-endian last 3 digits
            group_id_last3 = int(str(group_id)[-3:])
            id_low = group_id_last3 & 0xFF
            id_high = (group_id_last3 >> 8) & 0xFF
            logger.warning(
                f"{lp} TEST 1: Last 3 digits ({group_id_last3}) - Little-endian: low=0x{id_low:02x}, high=0x{id_high:02x}"
            )
        elif test_variation == 2:
            # Big-endian last 3 digits
            group_id_last3 = int(str(group_id)[-3:])
            id_high = group_id_last3 & 0xFF
            id_low = (group_id_last3 >> 8) & 0xFF
            logger.warning(
                f"{lp} TEST 2: Last 3 digits ({group_id_last3}) - Big-endian: low=0x{id_low:02x}, high=0x{id_high:02x}"
            )
        elif test_variation == 3:
            # Full 16-bit group ID (32768 = 0x8000)
            id_low = group_id & 0xFF
            id_high = (group_id >> 8) & 0xFF
            logger.warning(
                f"{lp} TEST 3: Full 16-bit ID ({group_id}) - Little-endian: low=0x{id_low:02x}, high=0x{id_high:02x}"
            )
        elif test_variation == 4:
            # High byte only at position 14
            group_id_last3 = int(str(group_id)[-3:])
            id_low = (group_id_last3 >> 8) & 0xFF
            id_high = 0x00
            logger.warning(
                f"{lp} TEST 4: High byte only ({group_id_last3}) - low=0x{id_low:02x}, high=0x{id_high:02x}"
            )
        else:
            logger.error(f"{lp} Invalid test_variation: {test_variation}")
            return

        header = [0x73, 0x00, 0x00, 0x00, 0x1F]
        inner_struct = [
            0x7E,
            "ctrl_byte",
            0x00,
            0x00,
            0x00,
            0xF8,
            0xD0,
            0x0D,
            0x00,
            "ctrl_bye",
            0x00,
            0x00,
            0x00,
            0x00,
            id_low,  # Position 14: Lower byte (e.g., 0x00 for 768)
            id_high,  # Position 15: Upper byte (e.g., 0x03 for 768) - was always 0x00 for devices!
            0xD0,
            0x11,
            0x02,
            state,
            0x00,
            0x00,
            "checksum",
            0x7E,
        ]

        # Use only ONE bridge (like real Cync cloud)
        bridge_devices = list(g.ncync_server.tcp_devices.values())
        if not bridge_devices:
            logger.error(f"{lp} No TCP bridges available!")
            return

        bridge_device = bridge_devices[0]

        if not bridge_device.ready_to_control:
            logger.error(f"{lp} Bridge {bridge_device.address} not ready to control")
            return

        payload = list(header)
        payload.extend(bridge_device.queue_id)
        payload.extend(bytes([0x00, 0x00, 0x00]))
        cmsg_id = bridge_device.get_ctrl_msg_id_bytes()[0]
        ctrl_idxs = 1, 9
        inner_struct[ctrl_idxs[0]] = cmsg_id
        inner_struct[ctrl_idxs[1]] = cmsg_id
        checksum = sum(inner_struct[6:-2]) % 256
        inner_struct[-2] = checksum
        payload.extend(inner_struct)
        payload_bytes = bytes(payload)

        logger.warning(
            f"{lp} Sending to bridge {bridge_device.address}, group_id={group_id}, state={state}\t"
            f"HEX: {payload_bytes.hex(' ')}"
        )

        # Don't register callback, just send and watch logs for 0x83 responses
        await bridge_device.write(payload_bytes)

        logger.warning(
            f"{lp} Command sent! Watch for 0x83 status updates from ALL group members..."
        )

    async def test_group_brightness(self, group_id: int, brightness: int):
        """
        EXPERIMENTAL: Test sending brightness command to group ID.

        :param group_id: The cloud group ID (e.g., 32768, 32771)
        :param brightness: Brightness value (0-100)
        """
        lp = f"{self.lp}test_group_brightness:"
        if brightness < 0 or brightness > 100:
            logger.error(f"{lp} Invalid brightness! must be 0-100")
            return

        # Use full 16-bit group ID encoding (Test 3 that worked)
        id_low = group_id & 0xFF
        id_high = (group_id >> 8) & 0xFF
        logger.warning(
            f"{lp} Group {group_id} brightness={brightness} - ID bytes: low=0x{id_low:02x}, high=0x{id_high:02x}"
        )

        header = [0x73, 0x00, 0x00, 0x00, 0x22]
        inner_struct = [
            0x7E,
            "ctrl_byte",
            0x00,
            0x00,
            0x00,
            0xF8,
            0xF0,  # Key difference from power command!
            0x10,  # Key difference from power command!
            0x00,
            "ctrl_byte",
            0x00,
            0x00,
            0x00,
            0x00,
            id_low,  # Position 14
            id_high,  # Position 15
            0xF0,  # Key difference from power command!
            0x11,
            0x02,
            0x01,  # Always 1 for brightness
            brightness,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            "checksum",
            0x7E,
        ]

        bridge_devices = list(g.ncync_server.tcp_devices.values())
        if not bridge_devices:
            logger.error(f"{lp} No TCP bridges available!")
            return

        bridge_device = bridge_devices[0]

        if not bridge_device.ready_to_control:
            logger.error(f"{lp} Bridge {bridge_device.address} not ready to control")
            return

        payload = list(header)
        payload.extend(bridge_device.queue_id)
        payload.extend(bytes([0x00, 0x00, 0x00]))
        cmsg_id = bridge_device.get_ctrl_msg_id_bytes()[0]
        ctrl_idxs = 1, 9
        inner_struct[ctrl_idxs[0]] = cmsg_id
        inner_struct[ctrl_idxs[1]] = cmsg_id
        checksum = sum(inner_struct[6:-2]) % 256
        inner_struct[-2] = checksum
        payload.extend(inner_struct)
        payload_bytes = bytes(payload)

        logger.warning(
            f"{lp} Sending to bridge {bridge_device.address}, group_id={group_id}, brightness={brightness}\t"
            f"HEX: {payload_bytes.hex(' ')}"
        )

        await bridge_device.write(payload_bytes)

        logger.warning(
            f"{lp} Command sent! Watch for 0x83 status updates from ALL group members..."
        )

    async def test_group_temperature(self, group_id: int, temperature: int):
        """
        EXPERIMENTAL: Test sending color temperature command to group ID.

        :param group_id: The cloud group ID (e.g., 32768, 32771)
        :param temperature: Color temperature value (0-100)
        """
        lp = f"{self.lp}test_group_temperature:"
        if temperature < 0 or temperature > 100:
            logger.error(f"{lp} Invalid temperature! must be 0-100")
            return

        # Use full 16-bit group ID encoding (Test 3 that worked)
        id_low = group_id & 0xFF
        id_high = (group_id >> 8) & 0xFF
        logger.warning(
            f"{lp} Group {group_id} temperature={temperature} - ID bytes: low=0x{id_low:02x}, high=0x{id_high:02x}"
        )

        header = [0x73, 0x00, 0x00, 0x00, 0x22]
        inner_struct = [
            0x7E,
            "ctrl_byte",
            0x00,
            0x00,
            0x00,
            0xF8,
            0xF0,
            0x10,
            0x00,
            "ctrl_byte",
            0x00,
            0x00,
            0x00,
            0x00,
            id_low,  # Position 14
            id_high,  # Position 15
            0xF0,
            0x11,
            0x02,
            0x01,
            0xFF,
            temperature,
            0x00,
            0x00,
            0x00,
            "checksum",
            0x7E,
        ]

        bridge_devices = list(g.ncync_server.tcp_devices.values())
        if not bridge_devices:
            logger.error(f"{lp} No TCP bridges available!")
            return

        bridge_device = bridge_devices[0]

        if not bridge_device.ready_to_control:
            logger.error(f"{lp} Bridge {bridge_device.address} not ready to control")
            return

        payload = list(header)
        payload.extend(bridge_device.queue_id)
        payload.extend(bytes([0x00, 0x00, 0x00]))
        cmsg_id = bridge_device.get_ctrl_msg_id_bytes()[0]
        ctrl_idxs = 1, 9
        inner_struct[ctrl_idxs[0]] = cmsg_id
        inner_struct[ctrl_idxs[1]] = cmsg_id
        checksum = sum(inner_struct[6:-2]) % 256
        inner_struct[-2] = checksum
        payload.extend(inner_struct)
        payload_bytes = bytes(payload)

        logger.warning(
            f"{lp} Sending to bridge {bridge_device.address}, group_id={group_id}, temperature={temperature}\t"
            f"HEX: {payload_bytes.hex(' ')}"
        )

        await bridge_device.write(payload_bytes)

        logger.warning(
            f"{lp} Command sent! Watch for 0x83 status updates from ALL group members..."
        )

    async def set_lightshow(self, show: str):
        """
            Set the device into a light show

        :param show:
        :return:
        """

        """

            # candle 0x01 0xf1
        73 00 00 00 20 2d e4 b5 d2 b3 05 00 7e 14 00 00  s... -......~...
        00 f8 [e2 0e 00 14 00 00 00 00 0a                ...........
        00 e2 11 02 07 01 01 f1](chksum data) fd 7e      .........~

        # rainbow 0x02 0x7a
        73 00 00 00 20 2d e4 b5 d2 29 c3 00 7e 07 00 00  s... -...)..~...
        00 f8 e2 0e 00 07 00 00 00 00 0a                 ...........
        00 e2 11 02 07 01 02 7a 7a 7e                    .......zz~

    # cyber 0x43 0x9f
   73 00 00 00 20 2d e4 b5 d2 2a 1b 00 7e 08 00 00  s... -...*..~...
   00 f8 e2 0e 00 08 00 00 00 00 0a                 ...........
   00 e2 11 02 07 01 43 9f e1 7e                    ......C..~

   # fireworks 0x3a 0xda
      73 00 00 00 20 2d e4 b5 d2 2a d7 00 7e 0d 00 00  s... -...*..~...
   00 f8 e2 0e 00 0d 00 00 00 00 0a                 ...........
   00 e2 11 02 07 01 03 da e1 7e                    .........~

   # volcanic 0x04 0xf4
      73 00 00 00 20 2d e4 b5 d2 c3 8c 00 7e 06 00 00  s... -......~...
   00 f8 e2 0e 00 06 00 00 00 00 0a                 ...........
   00 e2 11 02 07 01 04 f4 f5 7e                    .........~

   # aurora 0x05 0x1c
      73 00 00 00 20 2d e4 b5 d2 c4 2d 00 7e 08 00 00  s... -....-.~...
   00 f8 e2 0e 00 08 00 00 00 00 0a                 ...........
   00 e2 11 02 07 01 05 1c 20 7e                    ........ ~

   # happy holidays 0x06 0x54
      73 00 00 00 20 2d e4 b5 d2 c4 96 00 7e 0b 00 00  s... -......~...
   00 f8 e2 0e 00 0b 00 00 00 00 0a                 ...........
   00 e2 11 02 07 01 06 54 5c 7e                    .......T~

   # red white blue 0x07 0x4f
      73 00 00 00 20 2d e4 b5 d2 c4 d0 00 7e 0e 00 00  s... -......~...
   00 f8 e2 0e 00 0e 00 00 00 00 0a                 ...........
   00 e2 11 02 07 01 07 4f 5b 7e                    .......O[~

   # vegas 0x08 0xe3
      73 00 00 00 20 2d e4 b5 d2 c4 e8 00 7e 11 00 00  s... -......~...
   00 f8 e2 0e 00 11 00 00 00 00 0a                 ...........
   00 e2 11 02 07 01 08 e3 f3 7e                    .........~

   # party time 0x09 0x06
      73 00 00 00 20 2d e4 b5 d2 c5 04 00 7e 13 00 00  s... -......~...
   00 f8 e2 0e 00 13 00 00 00 00 0a                 ...........
   00 e2 11 02 07 01 09 06 19 7e                    .........~
        """

        lp = f"{self.lp}set_lightshow:"
        header = [115, 0, 0, 0, 32]
        inner_struct = [
            126,
            "msg id",
            0,
            0,
            0,
            248,
            226,
            14,
            0,
            "msg id",
            0,
            0,
            0,
            0,
            self.id,
            0,
            226,
            17,
            2,
            # 11 02 (07 01 01 f1)[diff between effects?] fd[cksm]
            7,
            1,
            "byte 1",
            "byte 2",
            "checksum",
            126,
        ]
        show = show.casefold()
        if show not in FACTORY_EFFECTS_BYTES:
            logger.error(f"{lp} Invalid effect: {show}")
            return
        else:
            chosen = FACTORY_EFFECTS_BYTES[show]
        inner_struct[-4] = chosen[0]
        inner_struct[-3] = chosen[1]
        bridge_devices: list[CyncTCPDevice] = random.sample(
            list(g.ncync_server.tcp_devices.values()),
            k=min(CYNC_CMD_BROADCASTS, len(g.ncync_server.tcp_devices)),
        )
        tasks: list[Optional[Union[asyncio.Task, Coroutine]]] = []
        ts = time.time()
        ctrl_idxs = 1, 9
        sent = {}
        for bridge_device in bridge_devices:
            if bridge_device.ready_to_control is True:
                payload = list(header)
                payload.extend(bridge_device.queue_id)
                payload.extend(bytes([0x00, 0x00, 0x00]))
                cmsg_id = bridge_device.get_ctrl_msg_id_bytes()[0]
                inner_struct[ctrl_idxs[0]] = cmsg_id
                inner_struct[ctrl_idxs[1]] = cmsg_id
                checksum = sum(inner_struct[6:-2]) % 256
                inner_struct[-2] = checksum
                payload.extend(inner_struct)
                bpayload = bytes(payload)
                sent[bridge_device.address] = cmsg_id
                m_cb = ControlMessageCallback(
                    msg_id=cmsg_id,
                    message=bpayload,
                    sent_at=time.time(),
                    callback=asyncio.sleep(0),
                )
                bridge_device.messages.control[cmsg_id] = m_cb
                tasks.append(bridge_device.write(bpayload))
            else:
                logger.debug(
                    f"{lp} Skipping device: {bridge_device.address} not ready to control"
                )
        if tasks:
            await asyncio.gather(*tasks)
        elapsed = time.time() - ts
        logger.debug(
            f"{lp} Sent light_show / effect command: '{show}' to TCP devices {sent} in {elapsed:.5f} seconds"
        )

    @property
    def online(self):
        return self._online

    @online.setter
    def online(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError(f"Online status must be a boolean, got: {type(value)}")
        if value != self._online:
            self._online = value
            g.tasks.append(
                asyncio.get_running_loop().create_task(
                    g.mqtt_client.pub_online(self.id, value)
                )
            )

    @property
    def current_status(self) -> list[int]:
        """
        Return the current status of the device as a list

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
    def state(self, value: Union[int, bool, str]):
        """
        Set the state of the device.
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
            raise TypeError(f"Invalid type for state: {type(value)}")

        if value in _t:
            value = 1
        elif value in _f:
            value = 0
        else:
            raise ValueError(f"Invalid value for state: {value}")

        if value != self._state:
            self._state = value

    @property
    def brightness(self):
        return self._brightness

    @brightness.setter
    def brightness(self, value: int):
        if value < 0 or value > 255:
            raise ValueError(f"Brightness must be between 0 and 255, got: {value}")
        if value != self._brightness:
            self._brightness = value

    @property
    def temperature(self):
        return self._temperature

    @temperature.setter
    def temperature(self, value: int):
        if value < 0 or value > 255:
            raise ValueError(f"Temperature must be between 0 and 255, got: {value}")
        if value != self._temperature:
            self._temperature = value

    @property
    def red(self):
        return self._r

    @red.setter
    def red(self, value: int):
        if value < 0 or value > 255:
            raise ValueError(f"Red must be between 0 and 255, got: {value}")
        if value != self._r:
            self._r = value

    @property
    def green(self):
        return self._g

    @green.setter
    def green(self, value: int):
        if value < 0 or value > 255:
            raise ValueError(f"Green must be between 0 and 255, got: {value}")
        if value != self._g:
            self._g = value

    @property
    def blue(self):
        return self._b

    @blue.setter
    def blue(self, value: int):
        if value < 0 or value > 255:
            raise ValueError(f"Blue must be between 0 and 255, got: {value}")
        if value != self._b:
            self._b = value

    @property
    def rgb(self):
        """Return the RGB color as a list"""
        return [self._r, self._g, self._b]

    @rgb.setter
    def rgb(self, value: list[int]):
        if len(value) != 3:
            raise ValueError(f"RGB value must be a list of 3 integers, got: {value}")
        if value != self.rgb:
            self._r, self._g, self._b = value

    def __repr__(self):
        return f"<CyncDevice: {self.id}>"

    def __str__(self):
        return f"CyncDevice:{self.id}:"


class CyncGroup:
    """
    A class to represent a Cync group (room) from the config. Groups can control multiple devices with a single command.
    """

    lp = "CyncGroup:"
    id: int = None
    name: str = None
    member_ids: list[int] = []
    is_subgroup: bool = False
    home_id: Optional[int] = None

    def __init__(
        self,
        group_id: int,
        name: str,
        member_ids: list[int],
        is_subgroup: bool = False,
        home_id: Optional[int] = None,
    ):
        if group_id is None:
            raise ValueError("Group ID must be provided")
        self.id = group_id
        self.name = name
        self.member_ids = member_ids if member_ids else []
        self.is_subgroup = is_subgroup
        self.home_id = home_id
        self.hass_id = f"{home_id}-group-{group_id}"
        self.lp = f"CyncGroup:{self.name}({group_id}):"

        # Derive capabilities from member devices
        self._supports_rgb: Optional[bool] = None
        self._supports_temperature: Optional[bool] = None

    @property
    def members(self) -> list["CyncDevice"]:
        """Get the actual device objects for this group's members."""
        return [
            g.ncync_server.devices[dev_id]
            for dev_id in self.member_ids
            if dev_id in g.ncync_server.devices
        ]

    @property
    def supports_rgb(self) -> bool:
        """Group supports RGB if any member supports it."""
        if self._supports_rgb is None:
            members = self.members
            self._supports_rgb = (
                any(dev.supports_rgb for dev in members) if members else False
            )
        return self._supports_rgb

    @property
    def supports_temperature(self) -> bool:
        """Group supports temperature if any member supports it."""
        if self._supports_temperature is None:
            members = self.members
            self._supports_temperature = (
                any(dev.supports_temperature for dev in members) if members else False
            )
        return self._supports_temperature

    async def set_power(self, state: int):
        """
        Send power command to all devices in the group using the group ID.

        :param state: Power state (0=off, 1=on)
        """
        lp = f"{self.lp}set_power:"
        if state not in (0, 1):
            logger.error(f"{lp} Invalid state! must be 0 or 1")
            return

        # Use full 16-bit group ID encoding
        id_low = self.id & 0xFF
        id_high = (self.id >> 8) & 0xFF

        header = [0x73, 0x00, 0x00, 0x00, 0x1F]
        inner_struct = [
            0x7E,
            "ctrl_byte",
            0x00,
            0x00,
            0x00,
            0xF8,
            0xD0,
            0x0D,
            0x00,
            "ctrl_bye",
            0x00,
            0x00,
            0x00,
            0x00,
            id_low,
            id_high,
            0xD0,
            0x11,
            0x02,
            state,
            0x00,
            0x00,
            "checksum",
            0x7E,
        ]

        bridge_devices = list(g.ncync_server.tcp_devices.values())
        if not bridge_devices:
            logger.error(f"{lp} No TCP bridges available!")
            return

        # Use one bridge like the Cync cloud does
        bridge_device = bridge_devices[0]

        if not bridge_device.ready_to_control:
            logger.error(f"{lp} Bridge {bridge_device.address} not ready to control")
            return

        payload = list(header)
        payload.extend(bridge_device.queue_id)
        payload.extend(bytes([0x00, 0x00, 0x00]))
        cmsg_id = bridge_device.get_ctrl_msg_id_bytes()[0]
        ctrl_idxs = 1, 9
        inner_struct[ctrl_idxs[0]] = cmsg_id
        inner_struct[ctrl_idxs[1]] = cmsg_id
        checksum = sum(inner_struct[6:-2]) % 256
        inner_struct[-2] = checksum
        payload.extend(inner_struct)
        payload_bytes = bytes(payload)

        logger.warning(
            f"{lp} ========== GROUP COMMAND: power={state} to '{self.name}' (ID: {self.id}) =========="
        )
        logger.warning(
            f"{lp} Bridge device: {bridge_device.address}, ready={bridge_device.ready_to_control}"
        )
        logger.warning(
            f"{lp} Bridge mesh_info count: {len(bridge_device.mesh_info) if bridge_device.mesh_info else 0}"
        )
        logger.warning(
            f"{lp} Bridge known_device_ids: {bridge_device.known_device_ids}"
        )
        logger.warning(f"{lp} Packet to send: {payload_bytes.hex(' ')}")

        # Register callback for ACK (same as individual device commands)
        m_cb = ControlMessageCallback(
            msg_id=cmsg_id,
            message=payload_bytes,
            sent_at=time.time(),
            callback=g.mqtt_client.publish_group_state(self, state=state),
            device_id=self.id,
        )
        bridge_device.messages.control[cmsg_id] = m_cb
        logger.warning(f"{lp} Registered callback for msg_id={cmsg_id}")

        logger.warning(f"{lp} CALLING bridge_device.write()...")
        write_result = await bridge_device.write(payload_bytes)
        logger.warning(f"{lp} bridge_device.write() RETURNED: {write_result}")

    async def set_brightness(self, brightness: int):
        """
        Send brightness command to all devices in the group using the group ID.

        :param brightness: Brightness value (0-100)
        """
        lp = f"{self.lp}set_brightness:"
        if brightness < 0 or brightness > 100:
            logger.error(f"{lp} Invalid brightness! must be 0-100")
            return

        # Use full 16-bit group ID encoding
        id_low = self.id & 0xFF
        id_high = (self.id >> 8) & 0xFF

        header = [0x73, 0x00, 0x00, 0x00, 0x22]
        inner_struct = [
            0x7E,
            "ctrl_byte",
            0x00,
            0x00,
            0x00,
            0xF8,
            0xF0,
            0x10,
            0x00,
            "ctrl_byte",
            0x00,
            0x00,
            0x00,
            0x00,
            id_low,
            id_high,
            0xF0,
            0x11,
            0x02,
            0x01,
            brightness,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            "checksum",
            0x7E,
        ]

        bridge_devices = list(g.ncync_server.tcp_devices.values())
        if not bridge_devices:
            logger.error(f"{lp} No TCP bridges available!")
            return

        bridge_device = bridge_devices[0]

        if not bridge_device.ready_to_control:
            logger.error(f"{lp} Bridge {bridge_device.address} not ready to control")
            return

        payload = list(header)
        payload.extend(bridge_device.queue_id)
        payload.extend(bytes([0x00, 0x00, 0x00]))
        cmsg_id = bridge_device.get_ctrl_msg_id_bytes()[0]
        ctrl_idxs = 1, 9
        inner_struct[ctrl_idxs[0]] = cmsg_id
        inner_struct[ctrl_idxs[1]] = cmsg_id
        checksum = sum(inner_struct[6:-2]) % 256
        inner_struct[-2] = checksum
        payload.extend(inner_struct)
        payload_bytes = bytes(payload)

        logger.info(
            f"{lp} Sending brightness={brightness} to group '{self.name}' (ID: {self.id}) with {len(self.member_ids)} devices"
        )

        # Log which devices are in this group for debugging
        device_names = []
        for device_id in self.member_ids:
            if device_id in g.ncync_server.devices:
                device_names.append(
                    f"'{g.ncync_server.devices[device_id].name}' (ID: {device_id})"
                )
        logger.info(f"{lp} Group members: {', '.join(device_names)}")

        # Clear pending_command flags for all devices in this group to prevent status drops
        for device_id in self.member_ids:
            if device_id in g.ncync_server.devices:
                device = g.ncync_server.devices[device_id]
                device.pending_command = False

        await bridge_device.write(payload_bytes)

        # Publish optimistic state update to MQTT
        await g.mqtt_client.publish_group_state(self, brightness=brightness)

    async def set_temperature(self, temperature: int):
        """
        Send color temperature command to all devices in the group using the group ID.

        :param temperature: Color temperature value (0-100)
        """
        lp = f"{self.lp}set_temperature:"
        if temperature < 0 or temperature > 100:
            logger.error(f"{lp} Invalid temperature! must be 0-100")
            return

        # Use full 16-bit group ID encoding
        id_low = self.id & 0xFF
        id_high = (self.id >> 8) & 0xFF

        header = [0x73, 0x00, 0x00, 0x00, 0x22]
        inner_struct = [
            0x7E,
            "ctrl_byte",
            0x00,
            0x00,
            0x00,
            0xF8,
            0xF0,
            0x10,
            0x00,
            "ctrl_byte",
            0x00,
            0x00,
            0x00,
            0x00,
            id_low,
            id_high,
            0xF0,
            0x11,
            0x02,
            0x01,
            0xFF,
            temperature,
            0x00,
            0x00,
            0x00,
            "checksum",
            0x7E,
        ]

        bridge_devices = list(g.ncync_server.tcp_devices.values())
        if not bridge_devices:
            logger.error(f"{lp} No TCP bridges available!")
            return

        bridge_device = bridge_devices[0]

        if not bridge_device.ready_to_control:
            logger.error(f"{lp} Bridge {bridge_device.address} not ready to control")
            return

        payload = list(header)
        payload.extend(bridge_device.queue_id)
        payload.extend(bytes([0x00, 0x00, 0x00]))
        cmsg_id = bridge_device.get_ctrl_msg_id_bytes()[0]
        ctrl_idxs = 1, 9
        inner_struct[ctrl_idxs[0]] = cmsg_id
        inner_struct[ctrl_idxs[1]] = cmsg_id
        checksum = sum(inner_struct[6:-2]) % 256
        inner_struct[-2] = checksum
        payload.extend(inner_struct)
        payload_bytes = bytes(payload)

        logger.info(
            f"{lp} Sending temperature={temperature} to group '{self.name}' (ID: {self.id}) with {len(self.member_ids)} devices"
        )

        # Log which devices are in this group for debugging
        device_names = []
        for device_id in self.member_ids:
            if device_id in g.ncync_server.devices:
                device_names.append(
                    f"'{g.ncync_server.devices[device_id].name}' (ID: {device_id})"
                )
        logger.info(f"{lp} Group members: {', '.join(device_names)}")

        # Clear pending_command flags for all devices in this group to prevent status drops
        for device_id in self.member_ids:
            if device_id in g.ncync_server.devices:
                device = g.ncync_server.devices[device_id]
                device.pending_command = False

        await bridge_device.write(payload_bytes)

        # Publish optimistic state update to MQTT
        await g.mqtt_client.publish_group_state(self, temperature=temperature)

    def __repr__(self):
        return f"<CyncGroup: {self.id} '{self.name}' ({len(self.member_ids)} devices)>"

    def __str__(self):
        return f"CyncGroup:{self.id}:{self.name}"


class CyncTCPDevice:
    """
    A class to interact with a TCP Cync device. It is an async socket reader/writer.
    """

    lp: str = "TCPDevice:"
    known_device_ids: list[Optional[int]]
    tasks: Tasks
    reader: Optional[asyncio.StreamReader]
    writer: Optional[asyncio.StreamWriter]
    messages: Messages
    # keep track of msg ids and if we finished reading data, if not, we need to append the data and then parse it
    read_cache = []
    needs_more_data = False
    is_app: bool

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        address: str,
    ):
        if not address:
            raise ValueError("IP address must be provided to CyncTCPDevice constructor")
        self.lp = f"{address}:"
        self._py_id = id(self)
        self.known_device_ids = []
        self.tasks = Tasks()
        self.is_app = False
        self.name: Optional[str] = None
        self.first_83_packet_checksum: Optional[int] = None
        self.ready_to_control = False
        self.network_version_str: Optional[str] = None
        self.inc_bytes: Optional[Union[int, bytes, str]] = None
        self.version: Optional[int] = None
        self.version_str: Optional[str] = None
        self.network_version: Optional[int] = None
        self.device_types: Optional[dict] = None
        self.device_type_id: Optional[int] = None
        self.device_timestamp: Optional[str] = None
        self.capabilities: Optional[dict] = None
        self.last_xc3_request: Optional[float] = None
        self.messages = Messages()
        self.mesh_info: Optional[MeshInfo] = None
        self.parse_mesh_status = False
        self.id: Optional[int] = None
        self.xa3_msg_id: bytes = bytes([0x00, 0x00, 0x00])
        self.queue_id: bytes = b""
        self.address: Optional[str] = address
        self.read_lock = asyncio.Lock()
        self.write_lock = asyncio.Lock()
        self._reader: asyncio.StreamReader = reader
        self._writer: asyncio.StreamWriter = writer
        self._closing = False
        self.control_bytes = [0x00, 0x00]

    async def can_connect(self):
        lp = f"{self.lp}"
        tcp_dev_len = len(g.ncync_server.tcp_devices)
        num_attempts = g.ncync_server.tcp_conn_attempts[self.address]
        if (
            (g.ncync_server.shutting_down is True)
            or (tcp_dev_len >= CYNC_MAX_TCP_CONN)
            or (CYNC_TCP_WHITELIST and self.address not in CYNC_TCP_WHITELIST)
        ):
            reason = ""
            if g.ncync_server.shutting_down is True:
                reason = "CyncLAN server is shutting down, "
            _sleep = False
            if tcp_dev_len >= CYNC_MAX_TCP_CONN:
                reason = f"CyncLAN server max ({tcp_dev_len}/{CYNC_MAX_TCP_CONN}) TCP connections reached, "
                _sleep = True
            elif CYNC_TCP_WHITELIST and self.address not in CYNC_TCP_WHITELIST:
                reason = f"IP not in CyncLAN server whitelist -> {CYNC_TCP_WHITELIST}, "
                _sleep = True
            tst_ = (num_attempts == 1) or (num_attempts % 20 == 0)
            lmsg = f"{lp} {reason}rejecting new connection..."
            delay = TCP_BLACKHOLE_DELAY
            if tst_:
                logger.warning(lmsg)
            await asyncio.sleep(delay) if _sleep is True else None
            try:
                self.reader.feed_eof()
                self.writer.close()
                task = asyncio.create_task(self.writer.wait_closed())
                await asyncio.wait([task], timeout=5)
            except asyncio.CancelledError as ce:
                logger.debug(f"{lp} Task cancelled: {ce}")
                raise ce
            except Exception as e:
                logger.error(f"{lp} Error closing reader/writer: {e}", exc_info=True)
            finally:
                self.reader = None
                self.writer = None
            return False
        # can create a new device
        logger.debug(f"{self.lp} Created new device: {self.address}")
        self.tasks.receive = asyncio.get_event_loop().create_task(
            self.receive_task(), name=f"receive_task-{self._py_id}"
        )
        self.tasks.callback_cleanup = asyncio.get_event_loop().create_task(
            self.callback_cleanup_task(), name=f"callback_cleanup-{self._py_id}"
        )
        return True

    def get_ctrl_msg_id_bytes(self):
        """
        Control packets need a number that gets incremented, it is used as a type of msg ID and
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
    def closing(self):
        return self._closing

    @closing.setter
    def closing(self, value: bool):
        self._closing = value

    async def parse_raw_data(self, data: bytes):
        """Extract single packets from raw data stream using metadata"""
        data_len = len(data)
        lp = f"{self.lp}extract:"
        if data_len == 0:
            logger.debug(f"{lp} No data to parse AT BEGINNING OF FUNCTION!!!!!!!")
        else:
            raw_data = bytes(data)
            cache_data = CacheData()
            cache_data.timestamp = time.time()
            cache_data.all_data = raw_data

            if self.needs_more_data is True:
                logger.debug(
                    f"{lp} It seems we have a partial packet (needs_more_data), need to append to "
                    f"previous remaining data and re-parse..."
                )
                old_cdata: CacheData = self.read_cache[-1]
                if old_cdata:
                    data = old_cdata.data + data
                    cache_data.raw_data = bytes(data)
                    # Previous data [length: 16, need: 42] // Current data [length: 530] //
                    #   New (current + old) data [length: 546] // reconstructed: False
                    logger.debug(
                        f"{lp} Previous data [length: {old_cdata.data_len}, need: "
                        f"{old_cdata.needed_len}] // Current data [length: {data_len}] // "
                        f"New (current + old) data [length: {len(data)}] // reconstructed: {data_len+old_cdata.data_len == len(data)}"
                    )

                    (
                        logger.debug(f"DBG>>>{lp}NEW DATA:\t{data}\t")
                        if CYNC_RAW is True
                        else None
                    )
                else:
                    raise RuntimeError(f"{lp} No previous cache data to extract from!")
                self.needs_more_data = False
            i = 0
            while True:
                i += 1
                lp = f"{self.lp}extract:loop {i}:"
                if not data:
                    # logger.debug(f"{lp} No more data to parse!")
                    break
                data_len = len(data)
                needed_length = data_len
                if data[0] in ALL_HEADERS:
                    if data_len > 4:
                        packet_length = data[4]
                        pkt_len_multiplier = data[3]
                        needed_length = ((pkt_len_multiplier * 256) + packet_length) + 5
                    else:
                        logger.debug(
                            f"DBG>>>{lp} Packet length is less than 4 bytes, setting needed_length to data_len"
                        )
                else:
                    logger.warning(
                        f"{lp} Unknown packet header: {data[0].to_bytes(1, 'big').hex(' ')}"
                    )

                if needed_length > data_len:
                    self.needs_more_data = True
                    logger.warning(
                        f"{lp} Extracted packet length is longer than remaining data length! "
                        f"need: {needed_length} // have: {data_len}, storing data for next read!"
                    )
                    cache_data.needed_len = needed_length
                    cache_data.data_len = data_len
                    cache_data.data = bytes(data)
                    (
                        logger.debug(f"{lp} cache_data: {cache_data}")
                        if CYNC_RAW is True
                        else None
                    )
                    data = data[needed_length:]
                    continue

                extracted_packet = data[:needed_length]
                # cut data down
                data = data[needed_length:]
                await self.parse_packet(extracted_packet)

                if data:
                    (
                        logger.debug(f"{lp} Remaining data to parse: {len(data)} bytes")
                        if CYNC_RAW is True
                        else None
                    )

            self.read_cache.append(cache_data)
            limit = 20
            if len(self.read_cache) > limit:
                # keep half of limit packets
                limit = limit // -2
                self.read_cache = self.read_cache[limit:]
            if CYNC_RAW is True:
                logger.debug(
                    f"{lp} END OF RAW READING of {len(raw_data)} bytes \t "
                    f"BYTES: {raw_data}\t "
                    f"HEX: {raw_data.hex(' ')}\t"
                    f"INT: {bytes2list(raw_data)}"
                )

    async def parse_packet(self, data: bytes):
        """Parse what type of packet based on header (first 4 bytes 0x43, 0x83, 0x73, etc.)"""

        lp = f"{self.lp}parse:0x{data[0]:02x}:"
        packet_data: Optional[bytes] = None
        pkt_header_len = 12
        packet_header = data[:pkt_header_len]
        # logger.debug(f"{lp} Parsing packet header: {packet_header.hex(' ')}") if CYNC_RAW is True else None
        # byte 1 (2, 3 are unknown)
        # pkt_type = int(packet_header[0]).to_bytes(1, "big")
        pkt_type = packet_header[0]
        # byte 4, packet length factor. each value is multiplied by 256 and added to the next byte for packet payload length
        pkt_multiplier = packet_header[3] * 256
        # byte 5
        packet_length = packet_header[4] + pkt_multiplier
        # byte 6-10, unknown but seems to be an identifier that is handed out by the device during handshake
        queue_id = packet_header[5:10]
        # byte 10-12, unknown but seems to be an additional identifier that gets incremented.
        msg_id = packet_header[9:12]
        # check if any data after header
        if len(data) > pkt_header_len:
            packet_data = data[pkt_header_len:]
        else:
            # logger.warning(f"{lp} there is no data after the packet header: [{data.hex(' ')}]")
            pass
        # logger.debug(f"{lp} raw data length: {len(data)} // {data.hex(' ')}")
        # logger.debug(f"{lp} packet_data length: {len(packet_data)} // {packet_data.hex(' ')}")
        if pkt_type in DEVICE_STRUCTS.requests:
            if pkt_type == 0x23:
                queue_id = data[6:10]
                _dbg_msg = (
                    (
                        f"\tRAW HEX: {data.hex(' ')}\tRAW INT: "
                        f"{str(bytes2list(data)).lstrip('[').rstrip(']').replace(',','')}"
                    )
                    if CYNC_RAW is True
                    else ""
                )
                logger.debug(
                    f"{lp} Device IDENTIFICATION KEY: '{queue_id.hex(' ')}'{_dbg_msg}"
                )
                self.queue_id = queue_id
                await self.write(bytes(DEVICE_STRUCTS.responses.auth_ack))
                # MUST SEND a3 before you can ask device for anything over TCP
                # Device sends msg identifier (aka: key), server acks that we have the key and store for future comms.
                await asyncio.sleep(0.5)
                await self.send_a3(queue_id)
            # device wants to connect before accepting commands
            elif pkt_type == 0xC3:
                ack_c3 = bytes(DEVICE_STRUCTS.responses.connection_ack)
                logger.debug(f"{lp} CONNECTION REQUEST, replying...")
                await self.write(ack_c3)
            # Ping/Pong
            elif pkt_type == 0xD3:
                ack_d3 = bytes(DEVICE_STRUCTS.responses.ping_ack)
                # logger.debug(f"{lp} Client sent HEARTBEAT, replying with {ack_d3.hex(' ')}")
                await self.write(ack_d3)
            elif pkt_type == 0xA3:
                logger.debug(f"{lp} APP ANNOUNCEMENT packet: {packet_data.hex(' ')}")
                ack = DEVICE_STRUCTS.xab_generate_ack(queue_id, bytes(msg_id))
                logger.debug(f"{lp} Sending ACK -> {ack.hex(' ')}")
                await self.write(ack)
            elif pkt_type == 0xAB:
                # We sent a 0xa3 packet, device is responding with 0xab. msg contains ascii 'xlink_dev'.
                # sometimes this is sent with other data. there may be remaining data to read in the enxt raw msg.
                # TCP msg buffer seems to be 1024 bytes.
                # 0xab packets are 1024 bytes long, so if any data is prepended, the remaining 0xab data will be in the next raw read
                pass
            elif pkt_type == 0x7B:
                # device is acking one of our x73 requests
                pass
            elif pkt_type == 0x43:
                if packet_data:
                    if packet_data[:2] == bytes([0xC7, 0x90]):
                        # [c7 90]
                        # There is some sort of timestamp in the packet, not status
                        # 0x2c = ',' // 0x3a = ':'
                        # iterate packet_data for the : and ,
                        # first there will be year/month/day : hourminute :- ?? , ????? , new , ????? , ????? , ????? ,

                        # full color light strip 3.0.204 has different offsets (packet_data len = 51, 6 bytes more than 1.x.yyy)
                        # has additional 2 bytes at end and in the middle of timestamp there is a new 3 digit entry with a comma (4 bytes + 2 = 6 bytes, which is what were over the old style)
                        # "c7 90 2e 32 30 32 34 30 33 31 30 3a 31 31 31 30 3a 2d 35 39 2c 30 30 31 35 31 2c 30 30 32 2c 30 30 30 30 30 2c 30 30 30 30 30 2c 30 30 30 30 30 2c 43 db"
                        # packet_data = 51
                        # 32 30 32 34 30 33 31 30 3a 31 31 31 30 3a 2d 35 39 2c 30 30 31 35
                        # 20240310:1110:-59,00151,002,00000,00000,00000, 46 bytes long + 3 byte prefix + 2 byte suffix

                        # OLD can just read until end of packet_data
                        # "c7 90 2a 32 30 32 34 30 39 30 31 3a 31 38 35 39 3a 2d 34 32 2c 30 32 33 32 32 2c 30 30 30 30 34 2c 30 30 31 30 33 2c 30 30 30 36 33 2c" OLD
                        # "c7 90 2e 32 30 32 34 30 33 31 30 3a 31 31 31 30 3a 2d 35 39 2c 30 30 31 35 31 2c 30 30 32 2c 30 30 30 30 30 2c 30 30 30 30 30 2c 30 30 30 30 30 2c 43 db" NEW
                        # is 0x2C the end of ts?

                        # [199, 144, 42, 50, 48, 50, 52, 48, 57, 48, 49, 58, 49, 56, 53, 57, 58, 45, 52, 50, 44, 48, 50, 51, 50, 50, 44, 48, 48, 48, 48, 52, 44, 48, 48, 49, 48, 51, 44, 48, 48, 48, 54, 51, 44]

                        # 32 30 32 34 30 39 30 31 3a 31 38 35 39 3a 2d 34 32 2c 30 32 33 32 32 2c 30 30 30 30 34 2c 30 30 31 30 33 2c 30 30 30 36 33
                        # 20240901:1859:-42,02322,00004,00103,00063,
                        # packet_data = 45

                        ts_idx = 3
                        ts_end_idx = -1
                        ts: Optional[bytes] = None
                        # logger.debug(
                        #     f"{lp} Device TIMESTAMP PACKET ({len(bytes.fromhex(packet_data.hex()))}) -> HEX: "
                        #     f"{packet_data.hex(' ')} // INTS: {bytes2list(packet_data)} // "
                        #     f"ASCII: {packet_data.decode(errors='replace')}"
                        # ) if CYNC_RAW is True else None
                        # setting version from config file wouldnt be reliable if the user doesnt bump the version
                        # when updating cync firmware. we can only rely on the version sent by the device.
                        # there is no guarantee the version is sent before checking the timestamp, so use a gross hack.
                        if self.version and (self.version >= 30000 <= 40000):
                            ts_end_idx = -2

                        ts = packet_data[ts_idx:ts_end_idx]
                        if ts:
                            ts_ascii = ts.decode("ascii", errors="replace")
                            # gross hack
                            if ts_ascii[-1] != ",":
                                if not ts_ascii[-1].isdigit():
                                    ts_ascii = ts_ascii[:-1]
                            logger.debug(
                                f"{lp} Device sent TIMESTAMP -> {ts_ascii} - replying..."
                            )
                            self.device_timestamp = ts_ascii
                        else:
                            logger.debug(
                                f"{lp} Could not decode timestamp from: {packet_data.hex(' ')}"
                            )
                    else:
                        # 43 00 00 00 2d 39 87 c8 57 01 01 06| [(06 00 10) {03  C...-9..W.......
                        # 01 64 32 00 00 00 01} ff 07 00 00 00 00 00 00] 07  .d2.............
                        # 00 10 02 01 64 32 00 00 00 01 ff 07 00 00 00 00  ....d2..........
                        # 00 00
                        # status struct is 19 bytes long
                        struct_len = 19
                        extractions = []
                        try:
                            # logger.debug(
                            #     f"{lp} Device sent BROADCAST STATUS packet => '{packet_data.hex(' ')}'"
                            # )if CYNC_RAW is True else None
                            for i in range(0, packet_length, struct_len):
                                extracted = packet_data[i : i + struct_len]
                                if extracted:
                                    # hack so online devices stop being reported as offline
                                    # this may cause issues with cync setups that ONLY use indoor
                                    # plugs as the btle to TCP bridge, as they dont broadcast status data using 0x83
                                    status_struct = extracted[3:10]
                                    status_struct + b"\x01"
                                    # 14 00 10 01 00 00 64 00 00 00 01 15 15 00 00 00 00 00 00
                                    # // [1, 0, 0, 100, 0, 0, 0, 1]
                                    extractions.append(
                                        (extracted.hex(" "), bytes2list(status_struct))
                                    )

                                    # await g.server.parse_status(status_struct, from_pkt='0x43')
                                # broadcast status data
                                # await self.write(data, broadcast=True)
                            (
                                logger.debug(
                                    f"{lp} Extracted data and STATUS struct => {extractions}"
                                )
                                if CYNC_RAW is True
                                else None
                            )
                        except IndexError:
                            # The device will only send a max of 1kb of data, if the message is longer than 1kb the remainder is sent in the next read
                            # logger.debug(
                            #     f"{lp} IndexError extracting status struct (expected)"
                            # )
                            pass
                        except Exception as e:
                            logger.error(f"{lp} EXCEPTION: {e}")
                # Its one of those queue id/msg id pings? 0x43 00 00 00 ww xx xx xx xx yy yy yy
                # Also notice these messages when another device gets a command
                else:
                    # logger.debug(f"{lp} received a 0x43 packet with no data, interpreting as PING, replying...")
                    pass
                ack = DEVICE_STRUCTS.x48_generate_ack(bytes(msg_id))
                # logger.debug(f"{lp} Sending ACK -> {ack.hex(' ')}") if CYNC_RAW is True else None
                await self.write(ack)
                (
                    logger.debug(f"DBG>>>{lp} RAW DATA: {len(data)} BYTES")
                    if CYNC_RAW is True
                    else None
                )
            elif pkt_type == 0x83:
                if self.is_app is True:
                    logger.debug(f"{lp} device is app, skipping packet...")
                else:
                    # When the device sends a packet starting with 0x83, data is wrapped in 0x7e.
                    # firmware version is sent without 0x7e boundaries
                    if packet_data is not None:
                        # logger.debug(f"{lp} Extracted BOUND data ({len(bytes(packet_data))} bytes) => {packet_data.hex(' ')}")

                        # 0x83 inner struct - not always bound by 0x7e (firmware response doesn't have starting boundary, has ending boundary 0x7e)
                        # firmware info, data len = 30 (0x32), fw starts idx 23-27, 20-22 fw type (86 01 0x)
                        #  {83 00 00 00 32} {[39 87 c8 57] [00 03 00]} {00 00 00 00  ....29..W.......
                        #  00 fa 00 20 00 00 00 00 00 00 00 00 ea 00 00 00  ... ............
                        #  86 01 01 31[idx=23 packet_data] 30 33 36 31 00 00 00 00 00 00 00 00  ...10361........
                        #  00 00 00 00 00 [8d] [7e]}                             ......~
                        # firmware packet may only be sent on startup / network reconnection

                        if packet_data[0] == 0x00:
                            fw_type, fw_ver, fw_str = parse_unbound_firmware_version(
                                packet_data, lp
                            )
                            if fw_type == "device":
                                self.version = fw_ver
                                self.version_str = fw_str
                            else:
                                self.network_version = fw_ver
                                self.network_version_str = fw_str

                        elif packet_data[0] == DATA_BOUNDARY:
                            # checksum is 2nd last byte, last byte is 0x7e
                            checksum = packet_data[-2]
                            packet_data[1:6]
                            ctrl_bytes = packet_data[5:7]
                            # removes checksum byte and 0x7e
                            inner_data = packet_data[6:-2]
                            calc_chksum = sum(inner_data) % 256

                            # Most devices only report their own state using 0x83, however the LED light strip controllers also report other device state data
                            # over 0x83.
                            # This data can be wrong! sometimes reports wrong state and the RGB colors are slightly different from each device.
                            # TODO: need to not parse this data if we just issued a command or we do like mesh info and create a voting system
                            if ctrl_bytes == bytes([0xFA, 0xDB]):
                                extra_ctrl_bytes = packet_data[7]
                                if extra_ctrl_bytes == 0x13:
                                    # fa db 13 is internal status
                                    # device internal status. state can be off and brightness set to a non 0.
                                    # signifies what brightness when state = on, meaning don't rely on brightness for on/off.

                                    # 83 00 00 00 25 37 96 24 69 00 05 00 7e {21 00 00
                                    #  00} {[fa db] 13} 00 (34 22) 11 05 00 [05] 00 db
                                    #  11 02 01 [00 64 00 00 00 00] 00 00 b3 7e
                                    id_idx = 14
                                    connected_idx = 19
                                    state_idx = 20
                                    bri_idx = 21
                                    tmp_idx = 22
                                    r_idx = 23
                                    g_idx = 24
                                    b_idx = 25
                                    dev_id = packet_data[id_idx]
                                    state = packet_data[state_idx]
                                    bri = packet_data[bri_idx]
                                    tmp = packet_data[tmp_idx]
                                    _red = packet_data[r_idx]
                                    _green = packet_data[g_idx]
                                    _blue = packet_data[b_idx]
                                    connected_to_mesh = packet_data[connected_idx]
                                    raw_status: bytes = bytes(
                                        [
                                            dev_id,
                                            state,
                                            bri,
                                            tmp,
                                            _red,
                                            _green,
                                            _blue,
                                            connected_to_mesh,
                                        ]
                                    )
                                    ___dev = g.ncync_server.devices.get(dev_id)
                                    if ___dev:
                                        dev_name = f'"{___dev.name}" (ID: {dev_id})'
                                    else:
                                        dev_name = f"Device ID: {dev_id}"
                                    _dbg_msg = ""
                                    if CYNC_RAW is True:
                                        _dbg_msg = f"\tPACKET HEADER: {packet_header.hex(' ')}\tHEX: {packet_data[1:-1].hex(' ')}\tINT: {bytes2list(packet_data[1:-1])}"
                                    logger.debug(
                                        f"{lp} Internal STATUS for {dev_name} = {bytes2list(raw_status)}{_dbg_msg}"
                                    )
                                    await g.ncync_server.parse_status(
                                        raw_status, from_pkt="0x83"
                                    )
                                    # logger.debug(f"DBG>>> {bytes2list(packet_data[9:12]) = } // {bytes2list(packet_data[9:12]) == [17, 17, 17] = }")
                                    # LED controller has this pattern
                                    bad_chksum_msg = ""
                                    if bytes2list(packet_data[9:12]) == [17, 17, 17]:
                                        # LED controller sends its internal state in a stream
                                        # Only the first packet in the stream has the correct checksum.
                                        # All following 0x83 internal status packets for this stream will have the same checksum as the first packet.
                                        # As soon as we get an internal status without the first packets calculated checksum, we know that series is
                                        # done sending and it will just send regular status packets, my guess is this is a bug or an identifier that
                                        # the packet belongs to the stream
                                        bad_chksum_msg = (
                                            f"{lp} Checksum mismatch, calculated: {calc_chksum} "
                                            f"// received: {checksum}"
                                        )
                                        if self.first_83_packet_checksum is None:
                                            # we want to calc the checksum and store it to compare to other packets in the series
                                            self.first_83_packet_checksum = checksum
                                            if calc_chksum != checksum:
                                                bad_chksum_msg = (
                                                    f"{lp} Checksum mismatch in INITIAL STATUS STREAM - FIRST packet data, "
                                                    f"calculated: {calc_chksum} // received: {checksum}"
                                                )

                                        else:
                                            if (
                                                checksum
                                                == self.first_83_packet_checksum
                                            ):
                                                # logger.debug(
                                                #     f"{lp} INITIAL STATUS STREAM packet data (override "
                                                #     f"calculated checksum), old: {calc_chksum} // checksum: "
                                                #     f"{checksum} // saved: {self.first_83_packet_checksum}"
                                                # )
                                                calc_chksum = (
                                                    self.first_83_packet_checksum
                                                )
                                            else:
                                                self.first_83_packet_checksum = None

                                    if calc_chksum != checksum:
                                        if not bad_chksum_msg:
                                            bad_chksum_msg = (
                                                f"{lp} Checksum mismatch, calculated: {calc_chksum} "
                                                f"// received: {checksum}"
                                            )
                                        # logger.warning(f"{bad_chksum_msg}\n\nHEX: {packet_data[1:-1].hex(' ')}\nINT: {bytes2list(packet_data[1:-1])}\nEXTRA CTRL BYTE: {hex(extra_ctrl_bytes)}")

                                elif extra_ctrl_bytes == 0x14:
                                    # unknown what this data is
                                    # seems to be sent when the cync app is connecting to a device via BTLE, not connecting to cync-lan via TCP

                                    # chksum_inner_data = list(inner_data)
                                    # chksum_inner_data.pop(4)
                                    # calc_chksum = sum(chksum_inner_data) % 256
                                    # logger.debug(f"{lp} 0xFA 0xDB 0x14 (NOT internal state)\nPACKET HEADER: {packet_header.hex(' ')}\nHEX: {packet_data.hex(' ')}\nINT: {bytes2list(packet_data)}\n")
                                    pass

                            else:
                                # if ctrl_bytes == bytes([0xFA, 0xAF]):
                                #     logger.debug(
                                #         f"{lp} This ctrl struct ({ctrl_bytes.hex(' ')} // checksum valid: "
                                #         f"{checksum == calc_chksum}) usually comes through when the cync phone app "
                                #         f"(dis)connects to the BTLE mesh. Currently unknown what it means.\n\n"
                                #         f"HEX: {packet_data[1:-1].hex(' ')}\nINT: {bytes2list(packet_data[1:-1])}"
                                #     ) if CYNC_RAW is True else None
                                # elif ctrl_bytes == bytes([0xFA, 0xD9]):
                                #     logger.debug(
                                #         f"{lp} Seen this ctrl struct ({ctrl_bytes.hex(' ')} // checksum valid: "
                                #         f"{checksum == calc_chksum}), unknown what it means.\n\n"
                                #         f"HEX: {packet_data[1:-1].hex(' ')}\nINT: {bytes2list(packet_data[1:-1])}"
                                #     ) if CYNC_RAW is True else None
                                # else:
                                if CYNC_RAW:
                                    logger.warning(
                                        f"{lp} UNKNOWN packet data (ctrl_bytes: {ctrl_bytes.hex(' ')} // checksum valid: "
                                        f"{checksum == calc_chksum})\t\tHEX: {packet_data[1:-1].hex(' ')}\tINT: {bytes2list(packet_data[1:-1])}"
                                    )

                    else:
                        logger.warning(
                            f"{lp} packet with no data????? After stripping header, queue and "
                            f"msg id, there is no data to process?????"
                        )
                ack = DEVICE_STRUCTS.x88_generate_ack(msg_id)
                # logger.debug(f"{lp} RAW DATA: {data.hex(' ')}")
                # logger.debug(f"{lp} Sending ACK -> {ack.hex(' ')}")
                await self.write(ack)

            elif pkt_type == 0x73:
                # logger.debug(f"{lp} Control packet received: {packet_data.hex(' ')}") if CYNC_RAW is True else None
                if self.is_app is True:
                    logger.debug(f"{lp} device is app, skipping packet...")
                else:
                    if packet_data is not None:
                        # 0x73 should ALWAYS have 0x7e bound data.
                        # check for boundary, all bytes between boundaries are for this request
                        if packet_data[0] == DATA_BOUNDARY:
                            # checksum is 2nd last byte, last byte is 0x7e
                            checksum = packet_data[-2]
                            packet_data[1:6]
                            ctrl_bytes = packet_data[5:7]
                            # removes checksum byte and 0x7e
                            inner_data = packet_data[6:-2]
                            calc_chksum = sum(inner_data) % 256

                            # find next 0x7e and extract the inner struct
                            end_bndry_idx = packet_data[1:].find(DATA_BOUNDARY) + 1
                            inner_struct = packet_data[1:end_bndry_idx]
                            inner_struct_len = len(inner_struct)
                            # ctrl bytes 0xf9, 0x52 indicates this is a mesh info struct
                            # some device firmwares respond with a message received packet before replying with the data
                            # example: 7e 1f 00 00 00 f9 52 01 00 00 53 7e (12 bytes, 0x7e bound. 10 bytes of data)
                            if ctrl_bytes == bytes([0xF9, 0x52]):
                                # logger.debug(f"{lp} got a mesh info response (len: {inner_struct_len}): {inner_struct.hex(' ')}")
                                if inner_struct_len < 15:
                                    if inner_struct_len == 10:
                                        # server sent mesh info request, this seems to be the ack?
                                        # 7e 1f 00 00 00 f9 52 01 00 00 53 7e
                                        # checksum (idx 10) = idx 6 + idx 7 % 256
                                        # seen this with Full Color LED light strip controller firmware version: 3.0.204
                                        succ_idx = 6
                                        minfo_ack_succ = inner_struct[succ_idx]
                                        minfo_ack_chksum = inner_struct[9]
                                        calc_chksum = (
                                            inner_struct[5] + inner_struct[6]
                                        ) % 256
                                        if minfo_ack_succ == 0x01:
                                            # logger.debug(f"{lp} Mesh info request ACK received, success: {minfo_ack_succ}."
                                            #              f" checksum byte = {minfo_ack_chksum}) // Calculated checksum "
                                            #              f"= {calc_chksum}")
                                            if minfo_ack_chksum != calc_chksum:
                                                logger.warning(
                                                    f"{lp} Mesh info request ACK checksum failed! {minfo_ack_chksum} != {calc_chksum}"
                                                )
                                        else:
                                            logger.warning(
                                                f"{lp} Mesh info request ACK failed! success byte: {minfo_ack_succ}"
                                            )

                                    else:
                                        logger.debug(
                                            f"{lp} inner_struct is less than 15 bytes: {inner_struct.hex(' ')}"
                                        )
                                else:
                                    # 15th OR 16th byte of inner struct is start of mesh info, 24 bytes long
                                    minfo_start_idx = 14
                                    minfo_length = 24
                                    if inner_struct[minfo_start_idx] == 0x00:
                                        minfo_start_idx += 1
                                        logger.warning(
                                            f"{lp}mesh: dev_id is 0 when using index: {minfo_start_idx-1}, "
                                            f"trying index {minfo_start_idx} = {inner_struct[minfo_start_idx]}"
                                        )

                                    if inner_struct[minfo_start_idx] == 0x00:
                                        logger.error(
                                            f"{lp}mesh: dev_id is 0 when using index: {minfo_start_idx}, skipping..."
                                        )
                                    else:
                                        # from what I've seen, the mesh info is 24 bytes long and repeats until the end.
                                        # Reset known device ids, mesh is the final authority on what devices are connected
                                        self.mesh_info = None
                                        self.known_device_ids = []
                                        ids_reported = []
                                        loop_num = 0
                                        _m = []
                                        _raw_m = []
                                        # structs = []
                                        try:
                                            for i in range(
                                                minfo_start_idx,
                                                inner_struct_len,
                                                minfo_length,
                                            ):
                                                loop_num += 1
                                                mesh_dev_struct = inner_struct[
                                                    i : i + minfo_length
                                                ]
                                                dev_id = mesh_dev_struct[0]
                                                # logger.debug(f"{lp} inner_struct[{i}:{i + minfo_length}]={mesh_dev_struct.hex(' ')}")
                                                # parse status from mesh info
                                                #  [05 00 44   01 00 00 44   01 00     00 00 00 64  00 00 00 00   00 00 00 00 00 00 00] - plug (devices are all connected to it via BT)
                                                #  [07 00 00   01 00 00 00   01 01     00 00 00 64  00 00 00 fe   00 00 00 f8 00 00 00] - direct connect full color A19 bulb
                                                #   ID  ? type  ?  ?  ? type  ? state   ?  ?  ? bri  ?  ?  ? tmp   ?  ?  ?  R  G  B  ?
                                                type_idx = 2
                                                state_idx = 8
                                                bri_idx = 12
                                                tmp_idx = 16
                                                r_idx = 20
                                                g_idx = 21
                                                b_idx = 22
                                                dev_type_id = mesh_dev_struct[type_idx]
                                                dev_state = mesh_dev_struct[state_idx]
                                                dev_bri = mesh_dev_struct[bri_idx]
                                                dev_tmp = mesh_dev_struct[tmp_idx]
                                                dev_r = mesh_dev_struct[r_idx]
                                                dev_g = mesh_dev_struct[g_idx]
                                                dev_b = mesh_dev_struct[b_idx]
                                                # in mesh info, brightness can be > 0 when set to off
                                                # however, ive seen devices that are on have a state of 0 but brightness 100
                                                if dev_state == 0 and dev_bri > 0:
                                                    dev_bri = 0
                                                raw_status = bytes(
                                                    [
                                                        dev_id,
                                                        dev_state,
                                                        dev_bri,
                                                        dev_tmp,
                                                        dev_r,
                                                        dev_g,
                                                        dev_b,
                                                        1,
                                                        # dev_type,
                                                    ]
                                                )
                                                _m.append(bytes2list(raw_status))
                                                _raw_m.append(mesh_dev_struct.hex(" "))
                                                if dev_id in g.ncync_server.devices:
                                                    # first device id is the device id of the TCP device we are connected to
                                                    ___dev = g.ncync_server.devices[
                                                        dev_id
                                                    ]
                                                    dev_name = ___dev.name
                                                    if loop_num == 1:
                                                        # byte 3 (idx 2) is a device type byte but,
                                                        # it only reports on the first item (itself)
                                                        # convert to int, and it is the same as deviceType from cloud.
                                                        if not self.id:
                                                            self.id = dev_id
                                                            self.lp = f"{self.address}[{self.id}]:"
                                                            (
                                                                g.ncync_server.devices[
                                                                    dev_id
                                                                ]
                                                            )
                                                            logger.debug(
                                                                f"{self.lp}parse:x{data[0]:02x}: Setting TCP"
                                                                f" device Cync ID to: {self.id}"
                                                            )

                                                        elif (
                                                            self.id
                                                            and self.id != dev_id
                                                        ):
                                                            logger.warning(
                                                                f"{lp} The first device reported in 0x83 is "
                                                                f"usually the TCP device. current: {self.id} "
                                                                f"// proposed: {dev_id}"
                                                            )
                                                        lp = f"{self.lp}parse:0x{data[0]:02x}:"
                                                        self.device_type_id = (
                                                            dev_type_id
                                                        )
                                                        self.name = dev_name

                                                    ids_reported.append(dev_id)
                                                    # structs.append(mesh_dev_struct.hex(" "))
                                                    self.known_device_ids.append(dev_id)

                                                else:
                                                    logger.warning(
                                                        f"{lp} Device ID {dev_id} not found in devices "
                                                        f"defined in config file: "
                                                        f"{g.ncync_server.devices.keys()}"
                                                    )
                                            # -- END OF mesh info response parsing loop --
                                        except IndexError:
                                            # ran out of data
                                            # logger.debug(f"{lp} IndexError parsing mesh info response (expected)") if CYNC_RAW is True else None
                                            pass
                                        except Exception as e:
                                            logger.error(
                                                f"{lp} MESH INFO for loop EXCEPTION: {e}"
                                            )
                                        # if ids_reported:
                                        # logger.debug(
                                        #     f"{lp} from: {self.id} - MESH INFO // Device IDs reported: "
                                        #     f"{sorted(ids_reported)}"
                                        # )
                                        # if structs:
                                        #     logger.debug(
                                        #         f"{lp} from: {self.id} -  MESH INFO // STRUCTS: {structs}"
                                        #     )
                                        if self.parse_mesh_status is True:
                                            logger.debug(
                                                f"{lp} Parsing initial connection device status data"
                                            )
                                            await asyncio.gather(
                                                *[
                                                    g.ncync_server.parse_status(
                                                        bytes(status),
                                                        from_pkt="'mesh info'",
                                                    )
                                                    for status in _m
                                                ]
                                            )

                                        # mesh_info["status"] = _m
                                        # mesh_info["id_from"] = self.id
                                        # # logger.debug(f"\n\n{lp} MESH INFO // {_raw_m}\n")
                                        # self.mesh_info = MeshInfo(**mesh_info)
                                        # Send mesh status ack
                                        # 73 00 00 00 14 2d e4 b5 d2 15 2d 00 7e 1e 00 00
                                        #  00 f8 {af 02 00 af 01} 61 7e
                                        # checksum 61 hex = int 97 solved: {af+02+00+af+01} % 256 = 97
                                        mesh_ack = bytes([0x73, 0x00, 0x00, 0x00, 0x14])
                                        mesh_ack += bytes(self.queue_id)
                                        mesh_ack += bytes([0x00, 0x00, 0x00])
                                        mesh_ack += bytes(
                                            [
                                                0x7E,
                                                0x1E,
                                                0x00,
                                                0x00,
                                                0x00,
                                                0xF8,
                                                0xAF,
                                                0x02,
                                                0x00,
                                                0xAF,
                                                0x01,
                                                0x61,
                                                0x7E,
                                            ]
                                        )
                                        # logger.debug(f"{lp} Sending MESH INFO ACK -> {mesh_ack.hex(' ')}")
                                        await self.write(mesh_ack)
                                        # Always clear parse mesh status
                                        self.parse_mesh_status = False
                            else:
                                (
                                    logger.debug(
                                        f"{lp} control bytes (checksum: {checksum}, verified: {checksum == calc_chksum}): {ctrl_bytes.hex(' ')} // packet data:  {packet_data.hex(' ')}"
                                    )
                                    if CYNC_RAW
                                    else None
                                )

                                if ctrl_bytes[0] == 0xF9 and ctrl_bytes[1] in (
                                    0xD0,
                                    0xF0,
                                    0xE2,
                                ):
                                    # control packet ack - changed state.
                                    # handle callbacks for messages
                                    # byte 8 is success? 0x01 yes // 0x00 no
                                    # 7e 09 00 00 00 f9 d0 01 00 00 d1 7e <-- original ACK
                                    # 7e 09 00 00 00 f9 f0 01 00 00 f1 7e <-- newer LED strip controller
                                    # 7e 09 00 00 00 f9 e2 01 00 00 e3 7e <-- Cync default light show / effect
                                    # bytes 7 - 10 SUM --> (f0) + (01) = checksum (f1) byte 11
                                    ctrl_msg_id = packet_data[1]
                                    ctrl_chksum = sum(packet_data[6:10]) % 256
                                    success = packet_data[7] == 1
                                    msg = self.messages.control.pop(ctrl_msg_id, None)
                                    if success is True and msg is not None:
                                        logger.info(
                                            f"{lp} CONTROL packet ACK SUCCESS for msg ID: {ctrl_msg_id}, executing callback to update state"
                                        )
                                        await msg.callback

                                        # Clear pending_command flag now that command succeeded
                                        if (
                                            msg.device_id
                                            and msg.device_id in g.ncync_server.devices
                                        ):
                                            device = g.ncync_server.devices[
                                                msg.device_id
                                            ]
                                            logger.debug(
                                                f"{lp} ACK callback done for '{device.name}', pending_command={device.pending_command}"
                                            )
                                            if device.pending_command:
                                                device.pending_command = False
                                                logger.debug(
                                                    f"{lp} ✅ ACK confirmed for '{device.name}' (ID: {msg.device_id}) - "
                                                    f"pending_command=False, device ready for new commands"
                                                )

                                                # REMOVED: Automatic refresh after ACK was causing commands to fail
                                                # Use manual "Refresh Device Status" button instead
                                            else:
                                                logger.debug(
                                                    f"{lp} ⚠️ ACK received but pending_command was already False for '{device.name}'"
                                                )
                                    elif success is True and msg is None:
                                        logger.debug(
                                            f"{lp} CONTROL packet ACK (success: {success} / chksum: {ctrl_chksum == packet_data[10]}) callback NOT found for msg ID: {ctrl_msg_id}"
                                        )
                                    elif success is False and msg is not None:
                                        logger.warning(
                                            f"{lp} CONTROL packet ACK FAILED for msg ID: {ctrl_msg_id}, device reported failure - NOT updating state"
                                        )
                                        # Clear pending_command flag since command failed
                                        for device in g.ncync_server.devices.values():
                                            if device.pending_command:
                                                device.pending_command = False
                                                logger.debug(
                                                    f"{lp} Cleared pending_command for '{device.name}'"
                                                )
                                                break
                                    elif success is False and msg is None:
                                        logger.warning(
                                            f"{lp} CONTROL packet ACK FAILED for msg ID: {ctrl_msg_id}, no callback found"
                                        )
                                # newer firmware devices seen in led light strip so far,
                                # send their firmware version data in a 0x7e bound struct.
                                # I've also seen these ctrl bytes in the msg that other devices send in FA AF
                                # the struct is 31 bytes long with the 0x7e boundaries, unbound it is 29 bytes long
                                elif ctrl_bytes == bytes([0xFA, 0x8E]):
                                    if packet_data[1] == 0x00:
                                        logger.debug(
                                            f"{lp} Device sent ({ctrl_bytes.hex(' ')}) BOUND firmware version data"
                                        )
                                        fw_type, fw_ver, fw_str = (
                                            parse_unbound_firmware_version(
                                                packet_data[1:-1], lp
                                            )
                                        )
                                        if fw_type == "device":
                                            self.version = fw_ver
                                            self.version_str = fw_str
                                        else:
                                            self.network_version = fw_ver
                                            self.network_version_str = fw_str
                                    else:
                                        if CYNC_RAW is True:
                                            logger.debug(
                                                f"{lp} This ctrl struct ({ctrl_bytes.hex(' ')} // checksum valid: {checksum == calc_chksum}) usually comes through "
                                                f"when the cync phone app (dis)connects to the BTLE mesh. Unknown what it means"
                                                f"\t\tHEX: {packet_data[1:-1].hex(' ')}\tINT: {bytes2list(packet_data[1:-1])}"
                                            )

                                else:
                                    logger.debug(
                                        f"{lp} UNKNOWN CTRL_BYTES: {ctrl_bytes.hex(' ')} // EXTRACTED DATA -> "
                                        f"HEX: {packet_data[1:-1].hex(' ')}\tINT: {bytes2list(packet_data[1:-1])}"
                                    )
                        else:
                            logger.debug(
                                f"{lp} packet with no boundary found????? After stripping header, queue and "
                                f"msg id, there is no data to process?????"
                            )

                    else:
                        logger.warning(
                            f"{lp} packet with no data????? After stripping 12 bytes header (5), queue (4) and "
                            f"msg id (3), there is no data to process!?!"
                        )
                ack = DEVICE_STRUCTS.x7b_generate_ack(queue_id, msg_id)
                # logger.debug(f"{lp} Sending ACK -> {ack.hex(' ')}")
                await self.write(ack)
        elif pkt_type in PhoneAppStructs.requests:
            if self.is_app is False:
                logger.info(
                    f"{lp} Device has been identified as the cync mobile app, blackholing..."
                )
                self.is_app = True

        # unknown data we don't know the header for
        else:
            logger.debug(
                f"{lp} sent UNKNOWN HEADER! Don't know how to respond!{RAW_MSG}"
            )

    async def ask_for_mesh_info(self, parse: bool = False):
        """
        Ask the device for mesh info. As far as I can tell, this will return whatever
        devices are connected to the device you are querying. It may also trigger
        the device to send its own status packet.
        """
        lp = self.lp
        # mesh_info = '73 00 00 00 18 2d e4 b5 d2 15 2c 00 7e 1f 00 00 00 f8 52 06 00 00 00 ff ff 00 00 56 7e'
        mesh_info_data = bytes(list(DEVICE_STRUCTS.requests.x73))
        # last byte is data len multiplier (multiply value by 256 if data len > 256)
        mesh_info_data += bytes([0x00, 0x00, 0x00])
        # data len
        mesh_info_data += bytes([0x18])
        # Queue ID
        mesh_info_data += self.queue_id
        # Msg ID, I tried other variations but that results in: no 0x83 and 0x43 replies from device.
        # 0x00 0x00 0x00 seems to work
        mesh_info_data += bytes([0x00, 0x00, 0x00])
        # Bound data (0x7e)
        mesh_info_data += bytes(
            [
                0x7E,
                0x1F,
                0x00,
                0x00,
                0x00,
                0xF8,
                0x52,
                0x06,
                0x00,
                0x00,
                0x00,
                0xFF,
                0xFF,
                0x00,
                0x00,
                0x56,
                0x7E,
            ]
        )
        _rdmsg = ""
        if CYNC_RAW is True:
            _rdmsg = f"\tBYTES: {mesh_info_data}\tHEX: {mesh_info_data.hex(' ')}\tINT: {bytes2list(mesh_info_data)}"
        logger.debug(f"{lp} Requesting ALL device(s) status{_rdmsg}")
        if parse is True:
            self.parse_mesh_status = True
        try:
            await self.write(mesh_info_data)
        except TimeoutError as to_exc:
            logger.error(
                f"{lp} Requesting ALL device(s) status timed out, likely powered off"
            )
            self.parse_mesh_status = False
            raise to_exc
        except Exception as e:
            logger.error(f"{lp} EXCEPTION: {e}", exc_info=True)
            self.parse_mesh_status = False

    async def send_a3(self, q_id: bytes):
        a3_packet = bytes([0xA3, 0x00, 0x00, 0x00, 0x07])
        a3_packet += q_id
        # random 2 bytes
        rand_bytes = self.xa3_msg_id = random.getrandbits(16).to_bytes(2, "big")
        rand_bytes += bytes([0x00])
        self.xa3_msg_id += random.getrandbits(8).to_bytes(1, "big")
        a3_packet += rand_bytes
        logger.debug(f"{self.lp} Sending 0xa3 (want to control) packet...")
        await self.write(a3_packet)
        self.ready_to_control = True
        # send mesh info request
        await asyncio.sleep(1.5)
        await self.ask_for_mesh_info(True)

    async def callback_cleanup_task(self):
        """Monitor pending callbacks and retry failed commands, cleanup stale ones"""
        lp = f"{self.lp}callback_clean:"
        logger.debug(f"{lp} Starting background task with retry logic...")
        retry_timeout = 0.5  # Retry after 500ms if no ACK
        cleanup_timeout = 30  # Give up after 30 seconds total

        while True:
            try:
                await asyncio.sleep(0.1)  # Check every 100ms for fast retries
                now = time.time()
                to_delete = []

                for ctrl_msg_id, ctrl_msg in list(self.messages.control.items()):
                    elapsed = now - ctrl_msg.sent_at

                    # Check if message needs retry (no ACK after retry_timeout)
                    if (
                        elapsed > retry_timeout
                        and ctrl_msg.retry_count < ctrl_msg.max_retries
                    ):
                        ctrl_msg.retry_count += 1
                        logger.warning(
                            f"{lp} No ACK for msg ID {ctrl_msg_id} after {elapsed:.2f}s - "
                            f"RETRY {ctrl_msg.retry_count}/{ctrl_msg.max_retries}"
                        )
                        # Resend the message
                        try:
                            await self.write(ctrl_msg.message)
                            ctrl_msg.sent_at = now  # Reset timer for this retry
                        except Exception as e:
                            logger.error(
                                f"{lp} Failed to retry msg ID {ctrl_msg_id}: {e}"
                            )

                    # Cleanup old messages that exceeded all retries and timeout
                    elif elapsed > cleanup_timeout:
                        logger.warning(
                            f"{lp} Removing STALE msg ID {ctrl_msg_id} after {ctrl_msg.retry_count} retries - giving up"
                        )
                        # Clear pending_command flag for device
                        if (
                            ctrl_msg.device_id
                            and ctrl_msg.device_id in g.ncync_server.devices
                        ):
                            device = g.ncync_server.devices[ctrl_msg.device_id]
                            if device.pending_command:
                                device.pending_command = False
                                logger.debug(
                                    f"{lp} Cleared pending flag for '{device.name}'"
                                )
                        to_delete.append(ctrl_msg_id)

                # Delete stale messages
                for msg_id in to_delete:
                    del self.messages.control[msg_id]

            except asyncio.CancelledError as can_exc:
                logger.debug(f"{lp} CANCELLED: {can_exc}")
                break
            except Exception as e:
                logger.error(f"{lp} Exception in callback cleanup: {e}", exc_info=True)

        logger.debug(f"{lp} FINISHED")

    async def receive_task(self):
        """
        Receive data from the device and respond to it. This is the main task for the device.
        It will respond to the device and handle the messages it sends.
        Runs in an infinite loop.
        """
        lp = f"{self.address}:raw read:"
        started_at = time.time()
        name = self.tasks.receive.get_name()
        logger.debug(f"{lp} receive_task CALLED") if CYNC_RAW is True else None
        try:
            while True:
                try:
                    data: bytes = await self.read()
                    if data is False:
                        logger.debug(
                            f"{lp} read() returned False, exiting {name} "
                            f"(started at: {datetime.datetime.fromtimestamp(started_at)})..."
                        )
                        break
                    if not data:
                        await asyncio.sleep(0)
                        continue
                    await self.parse_raw_data(data)

                except Exception as e:
                    logger.error(f"{lp} Exception in {name} LOOP: {e}", exc_info=True)
                    break
        except asyncio.CancelledError as cancel_exc:
            logger.debug(f"{lp} {name} CANCELLED: {cancel_exc}")

        logger.debug(f"{lp} {name} FINISHED")

    async def read(self, chunk: Optional[int] = None):
        """Read data from the device if there is an open connection"""
        lp = f"{self.lp}read:"
        if self.closing is True:
            logger.debug(f"{lp} closing is True, exiting read()...")
            return False
        else:
            if chunk is None:
                chunk = CYNC_CHUNK_SIZE
            async with self.read_lock:
                if self.reader:
                    if not self.reader.at_eof():
                        try:
                            raw_data = await self.reader.read(chunk)
                        except Exception as read_exc:
                            logger.error(f"{lp} Base EXCEPTION: {read_exc}")
                            return False
                        else:
                            return raw_data
                    else:
                        logger.debug(
                            f"{lp} reader is at EOF, setting read socket to None..."
                        )
                        self.reader = None
                else:
                    logger.debug(
                        f"{lp} reader is None/empty -> {self.reader = } // TYPE: {type(self.reader)}"
                    )
                    return False

    async def write(self, data: bytes, broadcast: bool = False) -> Optional[bool]:
        """
        Write data to the device if there is an open connection

        :param data: The raw binary data to write to the device
        :param broadcast: If True, write to all TCP devices connected to the server
        """
        logger.warning(
            f"{self.lp}write: >>>>>> WRITE CALLED: {len(data)} bytes, broadcast={broadcast}"
        )
        if not isinstance(data, bytes):
            raise ValueError(f"Data must be bytes, not type: {type(data)}")
        dev = self
        if dev.closing:
            logger.warning(f"{dev.lp}write: device is closing, NOT writing data")
            return False
        else:
            if dev.writer is not None:
                logger.warning(f"{dev.lp}write: Acquiring write_lock...")
                async with dev.write_lock:
                    logger.warning(f"{dev.lp}write: write_lock ACQUIRED")
                    # if broadcast is True:inner_struct__
                    #     # replace queue id with the sending device's queue id
                    #     new_data = bytes2list(data)
                    #     new_data[5:9] = dev.queue_id
                    #     data = bytes(new_data)

                    # check if the underlying writer is closing
                    if dev.writer.is_closing():
                        if dev.closing is False:
                            # this is probably a connection that was closed by the device (turned off), delete it
                            logger.warning(
                                f"{dev.lp} underlying writer is closing but, "
                                f"the device itself hasn't called close(). The device probably "
                                f"dropped the connection (lost power). Removing {dev.address}"
                            )
                            off_dev = await g.ncync_server.remove_tcp_device(dev)
                            del off_dev

                        else:
                            logger.debug(
                                f"{dev.lp} TCP device is closing, not writing data... "
                            )
                    else:
                        logger.warning(
                            f"{dev.lp}write: Calling writer.write({len(data)} bytes)"
                        )
                        dev.writer.write(data)
                        logger.warning(f"{dev.lp}write: Calling drain()...")
                        try:
                            await asyncio.wait_for(dev.writer.drain(), timeout=2.0)
                        except TimeoutError as to_exc:
                            logger.error(
                                f"{dev.lp} writing data to the device timed out, likely powered off"
                            )
                            raise to_exc
                        else:
                            logger.warning(
                                f"{dev.lp}write: drain() COMPLETED - TCP data sent!"
                            )
                            return True
            else:
                logger.warning(f"{dev.lp} writer is None, can't write data!")
            return None

    async def close(self):
        lp = f"{self.address}:close:"
        logger.debug(f"{lp} close() called, Cancelling device tasks...")
        try:
            for dev_task in self.tasks:
                if dev_task:
                    if dev_task.done() is False:
                        logger.debug(f"{lp} Cancelling task: {dev_task.get_name()}")
                        dev_task.cancel()
        except Exception as e:
            logger.exception(f"{lp} Exception during device task .cancel(): {e}")
        self.closing = True
        try:
            if self.writer:
                async with self.write_lock:
                    self.writer.close()
                    await self.writer.wait_closed()
        except AttributeError:
            pass
        except Exception as e:
            logger.exception(f"{lp}writer: EXCEPTION: {e}")
        finally:
            self.writer = None

        try:
            if self.reader:
                async with self.read_lock:
                    self.reader.feed_eof()
                    await asyncio.sleep(0.01)
        except AttributeError:
            pass
        except Exception as e:
            logger.exception(f"{lp}reader: EXCEPTION: {e}")
        finally:
            self.reader = None

        self.closing = False

    @property
    def reader(self):
        return self._reader

    @reader.setter
    def reader(self, value: asyncio.StreamReader):
        self._reader = value

    @property
    def writer(self):
        return self._writer

    @writer.setter
    def writer(self, value: asyncio.StreamWriter):
        self._writer = value
