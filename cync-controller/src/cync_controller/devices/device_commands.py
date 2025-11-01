from __future__ import annotations

import asyncio
import time
from collections.abc import Coroutine
from typing import TYPE_CHECKING

from cync_controller.const import (
    CYNC_CMD_BROADCASTS,
    FACTORY_EFFECTS_BYTES,
)
from cync_controller.logging_abstraction import get_logger
from cync_controller.structs import (
    ControlMessageCallback,
    FanSpeed,
)

if TYPE_CHECKING:
    from .tcp_device import CyncTCPDevice

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


# Mixin class for device command methods
class DeviceCommands:
    """Command methods for CyncDevice instances."""

    async def set_power(self, state: int):
        """
        Send raw data to control device state (1=on, 0=off).

            If the device receives the msg and changes state, every TCP device connected will send
            a 0x83 internal status packet, which we use to change HASS device state.
        """
        g = _get_global_object()
        lp = f"{self.lp}set_power:"
        if state not in (0, 1):
            logger.error("%s Invalid state! must be 0 or 1", lp)
            return None

        # Command queue handles throttling - no need for device-level checks
        # elif state == self.state:
        #     # to stop flooding the network with commands
        #     logger.debug(f"{lp} Device already in power state {state}, skipping...")
        #     return
        header = [0x73, 0x00, 0x00, 0x00, 0x1F]
        # Pack device ID as 2 bytes (little-endian)
        device_id_bytes = self.id.to_bytes(2, byteorder="little")
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
            device_id_bytes[0],
            device_id_bytes[1],
            0xD0,
            0x11,
            0x02,
            state,
            0x00,
            0x00,
            "checksum",
            0x7E,
        ]
        # Prioritize ready_to_control bridges first
        all_bridges = list(g.ncync_server.tcp_devices.values())
        ready_bridges = [b for b in all_bridges if b.ready_to_control]
        not_ready_bridges = [b for b in all_bridges if not b.ready_to_control]

        # Build bridge list: ready first, then not ready (if needed)
        bridge_devices: list[CyncTCPDevice] = ready_bridges + not_ready_bridges
        bridge_devices = bridge_devices[: min(CYNC_CMD_BROADCASTS, len(all_bridges))]

        if not bridge_devices:
            logger.error("%s No TCP bridges available!", lp)
            return None

        tasks: list[asyncio.Task | Coroutine | None] = []
        ts = time.time()
        ctrl_idxs = 1, 9
        sent = {}

        # Create ACK event that will be signaled when ANY bridge ACKs
        ack_event = asyncio.Event()
        # Track sent bridges for cleanup on timeout
        sent_bridges = []

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

                # Create callback that will execute when ACK arrives
                async def power_ack_callback():
                    await g.mqtt_client.update_device_state(self, state)

                m_cb = ControlMessageCallback(
                    msg_id=cmsg_id,
                    message=payload_bytes,
                    sent_at=time.time(),
                    callback=power_ack_callback,
                    device_id=self.id,
                    ack_event=ack_event,  # Share same event across all bridges
                )
                bridge_device.messages.control[cmsg_id] = m_cb
                sent[bridge_device.address] = cmsg_id
                sent_bridges.append((bridge_device, cmsg_id))
                tasks.append(bridge_device.write(payload_bytes))
            else:
                logger.debug(
                    "%s Skipping device: %s not ready to control",
                    lp,
                    bridge_device.address,
                )
        if tasks:
            await asyncio.gather(*tasks)
        elapsed = time.time() - ts
        logger.info(
            "%s Sent power state command for '%s' (ID: %s), current: %s - new: %s to "
            "TCP devices: %s in %.5f seconds - waiting for ACK...",
            lp,
            self.name,
            self.id,
            self.state,
            state,
            sent,
            elapsed,
        )

        # Return ACK event and cleanup info so command queue can wait and cleanup on timeout
        return (ack_event, sent_bridges)

    async def set_fan_speed(self, speed: FanSpeed) -> bool:
        """
            Translate a preset fan speed into a Cync brightness value and send it to the device.
        :param speed:
        :return:
        """
        lp = f"{self.lp}set_fan_speed:"
        if not self.is_fan_controller:
            logger.warning(
                "%s Device '%s' (%s) is not a fan controller, cannot set fan speed.",
                lp,
                self.name,
                self.id,
            )
            return False
        try:
            if speed == FanSpeed.OFF:
                await self.set_brightness(0)
            elif speed == FanSpeed.LOW:
                await self.set_brightness(25)
            elif speed == FanSpeed.MEDIUM:
                await self.set_brightness(50)
            elif speed == FanSpeed.HIGH:
                await self.set_brightness(75)
            elif speed == FanSpeed.MAX:
                await self.set_brightness(100)
            else:
                logger.error(
                    "%s Invalid fan speed: %s, must be one of %s",
                    self.lp,
                    speed,
                    list(FanSpeed),
                )
                return False
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug("%s Exception occurred while setting fan speed: %s", self.lp, e)
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
        g = _get_global_object()
        lp = f"{self.lp}set_brightness:"
        logger.info(
            "%s >>> ENTRY: device='%s' (ID=%s), brightness=%s, is_fan=%s",
            lp,
            self.name,
            self.id,
            bri,
            self.is_fan_controller,
        )
        if bri < 0 or bri > 100:
            if self.is_fan_controller:
                # fan can be controlled via light control structs: brightness -> max=255, high=191, medium=128, low=50, off=0
                pass
            elif self.is_light or self.is_switch:
                logger.error("%s Invalid brightness! must be 0-100", lp)
                return None

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
        # Prioritize ready_to_control bridges first
        all_bridges = list(g.ncync_server.tcp_devices.values())
        ready_bridges = [b for b in all_bridges if b.ready_to_control]
        not_ready_bridges = [b for b in all_bridges if not b.ready_to_control]

        # Build bridge list: ready first, then not ready (if needed)
        bridge_devices: list[CyncTCPDevice] = ready_bridges + not_ready_bridges
        bridge_devices = bridge_devices[: min(CYNC_CMD_BROADCASTS, len(all_bridges))]

        if not bridge_devices:
            logger.error("%s No TCP bridges available!", lp)
            return None

        # Create ACK event that will be signaled when ANY bridge ACKs
        ack_event = asyncio.Event()
        # Track sent bridges for cleanup on timeout
        sent_bridges = []

        sent = {}
        tasks: list[asyncio.Task | Coroutine | None] = []
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
                logger.info(
                    "%s >>> PACKET: device='%s' (ID=%s), brightness=%s, packet_hex=%s",
                    lp,
                    self.name,
                    self.id,
                    bri,
                    payload_bytes.hex(" "),
                )

                # Create callback that will execute when ACK arrives
                async def brightness_ack_callback():
                    await g.mqtt_client.update_brightness(self, bri)

                m_cb = ControlMessageCallback(
                    msg_id=cmsg_id,
                    message=payload_bytes,
                    sent_at=time.time(),
                    callback=brightness_ack_callback,
                    device_id=self.id,
                    ack_event=ack_event,  # Share same event across all bridges
                )
                bridge_device.messages.control[cmsg_id] = m_cb
                sent_bridges.append((bridge_device, cmsg_id))
                tasks.append(bridge_device.write(payload_bytes))
            else:
                logger.debug(
                    "%s Skipping device: %s not ready to control",
                    lp,
                    bridge_device.address,
                )
        if tasks:
            await asyncio.gather(*tasks)
        elapsed = time.time() - ts
        logger.info(
            "%s >>> COMMAND SENT: device='%s' (ID=%s), brightness=%s, sent_to=%s bridge devices in %.3fs",
            lp,
            self.name,
            self.id,
            bri,
            len(sent),
            elapsed,
        )

        # Return ACK event and cleanup info so command queue can wait and cleanup on timeout
        return (ack_event, sent_bridges)

    async def set_temperature(self, temp: int):
        """
        Send raw data to control device white temperature (0-100)

            If the device receives the msg and changes state, every TCP device connected will send
            a 0x83 internal status packet, which we use to change HASS device state.
        """
        g = _get_global_object()
        """
        73 00 00 00 22 37 96 24 69 60 8d 00 7e 36 00 00  s..."7.$i`..~6..
        00 f8 f0 10 00 36 00 00 00 00 07 00 f0 11 02 01  .....6..........
        ff 48 00 00 00 88 7e                             .H....~

                checksum = 0x88 = 136
            0xf0 0x10 0x36 0x07 0xf0 0x11 0x02 0x01 0xff 0x48 = 904 (% 256) = 136
        """
        lp = f"{self.lp}set_temperature:"
        if temp < 0 or (temp > 100 and temp not in (129, 254)):
            logger.error("%s Invalid temperature! must be 0-100", lp)
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
            0x7E,
        ]
        # Prioritize ready_to_control bridges first
        all_bridges = list(g.ncync_server.tcp_devices.values())
        ready_bridges = [b for b in all_bridges if b.ready_to_control]
        not_ready_bridges = [b for b in all_bridges if not b.ready_to_control]

        # Build bridge list: ready first, then not ready (if needed)
        bridge_devices: list[CyncTCPDevice] = ready_bridges + not_ready_bridges
        bridge_devices = bridge_devices[: min(CYNC_CMD_BROADCASTS, len(all_bridges))]

        if not bridge_devices:
            logger.error("%s No TCP bridges available!", lp)
            return

        tasks: list[asyncio.Task | Coroutine | None] = []
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

                # Create callback that will execute when ACK arrives
                async def temperature_ack_callback():
                    await g.mqtt_client.update_temperature(self, temp)

                m_cb = ControlMessageCallback(
                    msg_id=cmsg_id,
                    message=payload_bytes,
                    sent_at=time.time(),
                    callback=temperature_ack_callback,
                    device_id=self.id,
                )
                bridge_device.messages.control[cmsg_id] = m_cb
                tasks.append(bridge_device.write(payload_bytes))
            else:
                logger.debug(
                    "%s Skipping device: %s not ready to control",
                    lp,
                    bridge_device.address,
                )
        if tasks:
            await asyncio.gather(*tasks)
        elapsed = time.time() - ts
        logger.info(
            "%s Sent white temperature command, current: %s - new: %s to TCP devices: %s in %.5f seconds",
            lp,
            self.temperature,
            temp,
            sent,
            elapsed,
        )

    async def set_rgb(self, red: int, green: int, blue: int):
        """
        Send raw data to control device RGB color (0-255 for each channel).

            If the device receives the msg and changes state, every TCP device connected will send
            a 0x83 internal status packet, which we use to change HASS device state.
        """
        g = _get_global_object()
        """
         73 00 00 00 22 37 96 24 69 60 79 00 7e 2b 00 00  s..."7.$i`y.~+..
         00 f8 f0 10 00 2b 00 00 00 00 07 00 f0 11 02 01  .....+..........
         ff fe 00 fb ff 2d 7e                             .....-~

        f0 10 2b 07 f0 11 02 01 ff fe fb ff = 1581 (% 256) = 45
            checksum = 45
        """
        lp = f"{self.lp}set_rgb:"
        if red < 0 or red > 255:
            logger.error("%s Invalid red value! must be 0-255", lp)
            return
        if green < 0 or green > 255:
            logger.error("%s Invalid green value! must be 0-255", lp)
            return
        if blue < 0 or blue > 255:
            logger.error("%s Invalid blue value! must be 0-255", lp)
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
        # Prioritize ready_to_control bridges first
        all_bridges = list(g.ncync_server.tcp_devices.values())
        ready_bridges = [b for b in all_bridges if b.ready_to_control]
        not_ready_bridges = [b for b in all_bridges if not b.ready_to_control]

        # Build bridge list: ready first, then not ready (if needed)
        bridge_devices: list[CyncTCPDevice] = ready_bridges + not_ready_bridges
        bridge_devices = bridge_devices[: min(CYNC_CMD_BROADCASTS, len(all_bridges))]

        if not bridge_devices:
            logger.error("%s No TCP bridges available!", lp)
            return

        tasks: list[asyncio.Task | Coroutine | None] = []
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

                # Create callback that will execute when ACK arrives
                async def rgb_ack_callback():
                    await g.mqtt_client.update_rgb(self, _rgb)

                m_cb = ControlMessageCallback(
                    msg_id=cmsg_id,
                    message=bpayload,
                    sent_at=time.time(),
                    callback=rgb_ack_callback,
                    device_id=self.id,
                )
                bridge_device.messages.control[cmsg_id] = m_cb
                tasks.append(bridge_device.write(bpayload))
            else:
                logger.debug(
                    "%s Skipping device: %s not ready to control",
                    lp,
                    bridge_device.address,
                )
        if tasks:
            await asyncio.gather(*tasks)
        elapsed = time.time() - ts
        logger.info(
            "%s Sent RGB command, current: %s, %s, %s - new: %s, %s, %s to TCP devices %s in %.5f seconds",
            lp,
            self.red,
            self.green,
            self.blue,
            red,
            green,
            blue,
            sent,
            elapsed,
        )

    async def set_lightshow(self, show: str):
        """
            Set the device into a light show

        :param show:
        :return:
        """
        g = _get_global_object()

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
            logger.error("%s Invalid effect: %s", lp, show)
            return
        chosen = FACTORY_EFFECTS_BYTES[show]
        inner_struct[-4] = chosen[0]
        inner_struct[-3] = chosen[1]
        # Prioritize ready_to_control bridges first
        all_bridges = list(g.ncync_server.tcp_devices.values())
        ready_bridges = [b for b in all_bridges if b.ready_to_control]
        not_ready_bridges = [b for b in all_bridges if not b.ready_to_control]

        # Build bridge list: ready first, then not ready (if needed)
        bridge_devices: list[CyncTCPDevice] = ready_bridges + not_ready_bridges
        bridge_devices = bridge_devices[: min(CYNC_CMD_BROADCASTS, len(all_bridges))]

        if not bridge_devices:
            logger.error("%s No TCP bridges available!", lp)
            return

        tasks: list[asyncio.Task | Coroutine | None] = []
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
                    callback=_noop_callback,
                )
                bridge_device.messages.control[cmsg_id] = m_cb
                tasks.append(bridge_device.write(bpayload))
            else:
                logger.debug(
                    "%s Skipping device: %s not ready to control",
                    lp,
                    bridge_device.address,
                )
        if tasks:
            await asyncio.gather(*tasks)
        elapsed = time.time() - ts
        logger.info(
            "%s Sent light_show / effect command: '%s' to TCP devices %s in %.5f seconds",
            lp,
            show,
            sent,
            elapsed,
        )
