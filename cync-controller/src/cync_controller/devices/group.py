import time

from cync_controller.logging_abstraction import get_logger
from cync_controller.structs import (
    ControlMessageCallback,
    DeviceStatus,
    GlobalObject,
)

from .base_device import CyncDevice

logger = get_logger(__name__)
g = GlobalObject()


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


class CyncGroup:
    """
    A class to represent a Cync group (room) from the config. Groups can control multiple devices with a single command.
    """

    lp = "CyncGroup:"
    id: int | None = None
    name: str | None = None
    member_ids: list[int]
    is_subgroup: bool = False
    home_id: int | None = None

    def __init__(
        self,
        group_id: int,
        name: str,
        member_ids: list[int],
        is_subgroup: bool = False,
        home_id: int | None = None,
    ):
        if group_id is None:
            msg = "Group ID must be provided"
            raise ValueError(msg)
        self.id = group_id
        self.name = name
        self.member_ids = member_ids if member_ids else []
        self.is_subgroup = is_subgroup
        self.home_id = home_id
        self.hass_id = f"{home_id}-group-{group_id}"
        self.lp = f"CyncGroup:{self.name}({group_id}):"

        # Derive capabilities from member devices
        self._supports_rgb: bool | None = None
        self._supports_temperature: bool | None = None

        # State tracking - room groups report their own state in mesh_info, subgroups must aggregate from members
        self.state: int = 0  # 0=off, 1=on
        self.brightness: int = 0  # 0-100
        self.temperature: int = 0  # 0-100 for white, >100 for RGB mode
        self.red: int = 0
        self.green: int = 0
        self.blue: int = 0
        self.online: bool = True
        self.status: DeviceStatus | None = None

    @property
    def members(self) -> list[CyncDevice]:
        """Get the actual device objects for this group's members."""
        g = _get_global_object()
        ncync_server = getattr(g, "ncync_server", None)
        devices = getattr(ncync_server, "devices", None) if ncync_server else None
        if not devices:
            return []
        return [devices[dev_id] for dev_id in self.member_ids if dev_id in devices]

    @property
    def supports_rgb(self) -> bool:
        """Group supports RGB if any member supports it."""
        if self._supports_rgb is None:
            members = self.members
            self._supports_rgb = any(dev.supports_rgb for dev in members) if members else False
        return self._supports_rgb

    @property
    def supports_temperature(self) -> bool:
        """Group supports temperature if any member supports it."""
        if self._supports_temperature is None:
            members = self.members
            self._supports_temperature = any(dev.supports_temperature for dev in members) if members else False
        return self._supports_temperature

    def aggregate_member_states(self) -> dict | None:
        """
        Aggregate state from all online member devices.

        Returns dict with aggregated state values, or None if no online members.

        Aggregation logic:
        - state: ON if ANY member is ON, OFF if ALL members are OFF
        - brightness: Average of all online members
        - temperature: Average of all online members
        - online: True if ANY member is online
        """
        members = self.members
        online_members = [m for m in members if m.online]

        if not online_members:
            return None

        # State: ON if any member is ON
        any_on = any(m.state == 1 for m in online_members)
        agg_state = 1 if any_on else 0

        # Brightness: average of online members
        brightnesses = [m.brightness for m in online_members if m.brightness is not None]
        agg_brightness = int(sum(brightnesses) / len(brightnesses)) if brightnesses else 0

        # Temperature: average of online members
        temperatures = [m.temperature for m in online_members if m.temperature is not None and m.temperature <= 100]
        agg_temperature = int(sum(temperatures) / len(temperatures)) if temperatures else 0

        return {
            "state": agg_state,
            "brightness": agg_brightness,
            "temperature": agg_temperature,
            "online": True,  # Group is online if any member is online
        }

    async def set_power(self, state: int):
        """
        Send power command to all devices in the group using the group ID.

        :param state: Power state (0=off, 1=on)
        """
        g = _get_global_object()
        lp = f"{self.lp}set_power:"
        if state not in (0, 1):
            logger.error("%s Invalid state! must be 0 or 1", lp)
            return

        if self.id is None:
            logger.error("%s Group ID is None, cannot send command", lp)
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

        ncync_server = getattr(g, "ncync_server", None)
        if ncync_server is None:
            logger.error("%s ncync_server is None, cannot send command", lp)
            return

        tcp_devices = getattr(ncync_server, "tcp_devices", None)
        if tcp_devices is None:
            logger.error("%s tcp_devices is None, cannot send command", lp)
            return

        bridge_devices = list(tcp_devices.values())
        if not bridge_devices:
            logger.error("%s No TCP bridges available!", lp)
            return

        # Use one bridge like the Cync cloud does
        bridge_device = bridge_devices[0]
        if bridge_device is None:
            logger.error("%s Bridge device is None", lp)
            return

        if not bridge_device.ready_to_control:
            logger.error("%s Bridge %s not ready to control", lp, bridge_device.address)
            return

        queue_id = getattr(bridge_device, "queue_id", None)
        if queue_id is None:
            logger.error("%s Bridge queue_id is None", lp)
            return

        payload = list(header)
        payload.extend(queue_id)
        payload.extend(bytes([0x00, 0x00, 0x00]))
        cmsg_id_bytes = bridge_device.get_ctrl_msg_id_bytes()
        if not cmsg_id_bytes:
            logger.error("%s Failed to get control message ID bytes", lp)
            return
        cmsg_id = cmsg_id_bytes[0]
        ctrl_idxs = 1, 9
        inner_struct[ctrl_idxs[0]] = cmsg_id
        inner_struct[ctrl_idxs[1]] = cmsg_id
        checksum = sum(inner_struct[6:-2]) % 256
        inner_struct[-2] = checksum
        payload.extend(inner_struct)
        payload_bytes = bytes(payload)

        logger.debug(
            "%s ========== GROUP COMMAND: power=%s to '%s' (ID: %s) ==========",
            lp,
            state,
            self.name,
            self.id,
        )
        logger.debug(
            "%s Bridge device: %s, ready=%s",
            lp,
            bridge_device.address,
            bridge_device.ready_to_control,
        )
        mesh_info = getattr(bridge_device, "mesh_info", None)
        logger.debug(
            "%s Bridge mesh_info count: %s",
            lp,
            len(mesh_info) if mesh_info else 0,
        )
        known_device_ids = getattr(bridge_device, "known_device_ids", None)
        logger.debug("%s Bridge known_device_ids: %s", lp, known_device_ids)
        logger.debug("%s Packet to send: %s", lp, payload_bytes.hex(" "))

        # Register callback for ACK (no optimistic group publish)
        # Call _noop_callback() to get the coroutine, not the function itself
        callback_coro = _noop_callback()
        m_cb = ControlMessageCallback(
            msg_id=cmsg_id,
            message=payload_bytes,
            sent_at=time.time(),
            callback=callback_coro,
            device_id=self.id,
        )
        messages = getattr(bridge_device, "messages", None)
        if messages is not None:
            messages.control[cmsg_id] = m_cb
            logger.debug("%s Registered callback for msg_id=%s", lp, cmsg_id)

        # BUG FIX: Sync ALL group device states IMMEDIATELY (optimistically)
        # Group commands affect both bulbs and switches, so update both for instant UI feedback
        mqtt_client = getattr(g, "mqtt_client", None)
        if mqtt_client is not None and self.id is not None and self.name is not None:
            await mqtt_client.sync_group_devices(self.id, state, self.name)

        logger.debug("%s CALLING bridge_device.write()...", lp)
        write_result = await bridge_device.write(payload_bytes)
        logger.debug("%s bridge_device.write() RETURNED: %s", lp, write_result)

    async def set_brightness(self, brightness: int):
        """
        Send brightness command to all devices in the group using the group ID.

        :param brightness: Brightness value (0-100)
        """
        g = _get_global_object()
        lp = f"{self.lp}set_brightness:"
        if brightness < 0 or brightness > 100:
            logger.error("%s Invalid brightness! must be 0-100", lp)
            return

        if self.id is None:
            logger.error("%s Group ID is None, cannot send command", lp)
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

        ncync_server = getattr(g, "ncync_server", None)
        if ncync_server is None:
            logger.error("%s ncync_server is None, cannot send command", lp)
            return

        tcp_devices = getattr(ncync_server, "tcp_devices", None)
        if tcp_devices is None:
            logger.error("%s tcp_devices is None, cannot send command", lp)
            return

        bridge_devices = list(tcp_devices.values())
        if not bridge_devices:
            logger.error("%s No TCP bridges available!", lp)
            return

        bridge_device = bridge_devices[0]
        if bridge_device is None:
            logger.error("%s Bridge device is None", lp)
            return

        if not bridge_device.ready_to_control:
            logger.error("%s Bridge %s not ready to control", lp, bridge_device.address)
            return

        queue_id = getattr(bridge_device, "queue_id", None)
        if queue_id is None:
            logger.error("%s Bridge queue_id is None", lp)
            return

        payload = list(header)
        payload.extend(queue_id)
        payload.extend(bytes([0x00, 0x00, 0x00]))
        cmsg_id_bytes = bridge_device.get_ctrl_msg_id_bytes()
        if not cmsg_id_bytes:
            logger.error("%s Failed to get control message ID bytes", lp)
            return
        cmsg_id = cmsg_id_bytes[0]
        ctrl_idxs = 1, 9
        inner_struct[ctrl_idxs[0]] = cmsg_id
        inner_struct[ctrl_idxs[1]] = cmsg_id
        checksum = sum(inner_struct[6:-2]) % 256
        inner_struct[-2] = checksum
        payload.extend(inner_struct)
        payload_bytes = bytes(payload)

        logger.info(
            "%s Sending brightness=%s to group '%s' (ID: %s) with %s devices",
            lp,
            brightness,
            self.name,
            self.id,
            len(self.member_ids),
        )

        # Log which devices are in this group for debugging
        devices = getattr(ncync_server, "devices", None)
        device_names = []
        if devices is not None:
            for device_id in self.member_ids:
                if device_id in devices:
                    device = devices[device_id]
                    device_name = getattr(device, "name", f"Unknown (ID: {device_id})")
                    device_names.append(f"'{device_name}' (ID: {device_id})")
        logger.info("%s Group members: %s", lp, ", ".join(device_names))

        # Register callback for ACK (no optimistic group publish)
        # Call _noop_callback() to get the coroutine, not the function itself
        callback_coro = _noop_callback()
        m_cb = ControlMessageCallback(
            msg_id=cmsg_id,
            message=payload_bytes,
            sent_at=time.time(),
            callback=callback_coro,
            device_id=self.id,
        )
        messages = getattr(bridge_device, "messages", None)
        if messages is not None:
            messages.control[cmsg_id] = m_cb
        await bridge_device.write(payload_bytes)

    async def set_temperature(self, temperature: int):
        """
        Send color temperature command to all devices in the group using the group ID.

        :param temperature: Color temperature value (0-100)
        """
        g = _get_global_object()
        lp = f"{self.lp}set_temperature:"
        if temperature < 0 or temperature > 100:
            logger.error("%s Invalid temperature! must be 0-100", lp)
            return

        if self.id is None:
            logger.error("%s Group ID is None, cannot send command", lp)
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

        ncync_server = getattr(g, "ncync_server", None)
        if ncync_server is None:
            logger.error("%s ncync_server is None, cannot send command", lp)
            return

        tcp_devices = getattr(ncync_server, "tcp_devices", None)
        if tcp_devices is None:
            logger.error("%s tcp_devices is None, cannot send command", lp)
            return

        bridge_devices = list(tcp_devices.values())
        if not bridge_devices:
            logger.error("%s No TCP bridges available!", lp)
            return

        bridge_device = bridge_devices[0]
        if bridge_device is None:
            logger.error("%s Bridge device is None", lp)
            return

        if not bridge_device.ready_to_control:
            logger.error("%s Bridge %s not ready to control", lp, bridge_device.address)
            return

        queue_id = getattr(bridge_device, "queue_id", None)
        if queue_id is None:
            logger.error("%s Bridge queue_id is None", lp)
            return

        payload = list(header)
        payload.extend(queue_id)
        payload.extend(bytes([0x00, 0x00, 0x00]))
        cmsg_id_bytes = bridge_device.get_ctrl_msg_id_bytes()
        if not cmsg_id_bytes:
            logger.error("%s Failed to get control message ID bytes", lp)
            return
        cmsg_id = cmsg_id_bytes[0]
        ctrl_idxs = 1, 9
        inner_struct[ctrl_idxs[0]] = cmsg_id
        inner_struct[ctrl_idxs[1]] = cmsg_id
        checksum = sum(inner_struct[6:-2]) % 256
        inner_struct[-2] = checksum
        payload.extend(inner_struct)
        payload_bytes = bytes(payload)

        logger.info(
            "%s Sending temperature=%s to group '%s' (ID: %s) with %s devices",
            lp,
            temperature,
            self.name,
            self.id,
            len(self.member_ids),
        )

        # Log which devices are in this group for debugging
        devices = getattr(ncync_server, "devices", None)
        device_names = []
        if devices is not None:
            for device_id in self.member_ids:
                if device_id in devices:
                    device = devices[device_id]
                    device_name = getattr(device, "name", f"Unknown (ID: {device_id})")
                    device_names.append(f"'{device_name}' (ID: {device_id})")
        logger.info("%s Group members: %s", lp, ", ".join(device_names))

        # Register callback for ACK (no optimistic group publish)
        # Call _noop_callback() to get the coroutine, not the function itself
        callback_coro = _noop_callback()
        m_cb = ControlMessageCallback(
            msg_id=cmsg_id,
            message=payload_bytes,
            sent_at=time.time(),
            callback=callback_coro,
            device_id=self.id,
        )
        messages = getattr(bridge_device, "messages", None)
        if messages is not None:
            messages.control[cmsg_id] = m_cb
        await bridge_device.write(payload_bytes)

    def __repr__(self):
        return f"CyncGroup(id={self.id}, name='{self.name}', members={len(self.member_ids)})"

    def __str__(self):
        return f"CyncGroup {self.name} (ID: {self.id})"
