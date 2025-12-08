"""Helpers for coordinating Cync groups across multiple devices."""
# pyright: reportUnnecessaryComparison=false, reportUnnecessaryIsInstance=false

import asyncio
import time
from typing import override

from cync_controller.logging_abstraction import get_logger
from cync_controller.structs import (
    ControlMessageCallback,
    CyncDeviceProtocol,
    CyncTCPDeviceProtocol,
    DeviceStatus,
    GlobalObject,
)

logger = get_logger(__name__)
g = GlobalObject()

PERCENT_MIN = 0
PERCENT_MAX = 100


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
    """Represent a configured Cync group that controls multiple devices."""

    lp: str = "CyncGroup:"
    id: int | None = None
    name: str | None = None
    is_subgroup: bool = False
    home_id: int | None = None

    def __init__(
        self,
        group_id: int | None,
        name: str,
        member_ids: list[int],
        is_subgroup: bool = False,
        home_id: int | None = None,
    ) -> None:
        """Initialize a group aggregate from config metadata."""
        if group_id is None:
            msg = "Group ID must be provided"
            raise ValueError(msg)
        self.id = group_id
        self.name = name
        self.member_ids: list[int] = member_ids if member_ids else []
        self.is_subgroup = is_subgroup
        self.home_id = home_id
        self.hass_id: str = f"{home_id}-group-{group_id}"
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
    def members(self) -> list[CyncDeviceProtocol]:
        """Get the actual device objects for this group's members."""
        g = _get_global_object()
        ncync_server = g.ncync_server
        devices = ncync_server.devices if ncync_server else None
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

    def aggregate_member_states(self) -> dict[str, int | bool] | None:
        """Aggregate state from all online member devices.

        Returns dict with aggregated state values, or None if no online members.

        Aggregation logic:
        - state: ON if ANY member is ON, OFF if ALL members are OFF
        - brightness: Average of all online members
        - temperature: Average of all online members
        - online: True if ANY member is online
        """
        members = self.members
        # Filter to online members only - online is bool, never None per protocol
        online_members: list[CyncDeviceProtocol] = []
        for m in members:
            if m.online:  # online is bool per CyncDeviceProtocol, never None
                online_members.append(m)

        if len(online_members) == 0:
            return None

        # State: ON if any member is ON
        any_on = any(m.state == 1 for m in online_members)
        agg_state = 1 if any_on else 0

        # Brightness: average of online members
        brightnesses: list[int] = []
        for m in online_members:
            # brightness on protocol can be None; keep explicit Optional for type checker
            brightness_value: int | None = m.brightness
            if brightness_value is not None:
                brightnesses.append(brightness_value)
        agg_brightness = int(sum(brightnesses) / len(brightnesses)) if len(brightnesses) > 0 else 0

        # Temperature: average of online members
        # Filter to only include temperatures within valid range (0-100)
        # Note: temperature is always int per CyncDeviceProtocol (line 134)
        temperatures: list[int] = []
        for member in online_members:
            # temperature is int per CyncDeviceProtocol, never None
            temp: int = member.temperature
            if temp <= PERCENT_MAX:
                temperatures.append(temp)
        agg_temperature = int(sum(temperatures) / len(temperatures)) if temperatures else 0

        result: dict[str, int | bool] = {
            "state": agg_state,
            "brightness": agg_brightness,
            "temperature": agg_temperature,
            "online": True,  # Group is online if any member is online
        }
        return result

    def _validate_group_id(self, lp: str) -> bool:
        """Validate that group ID exists."""
        if self.id is None:
            logger.error("%s Group ID is None, cannot send command", lp)
            return False
        return True

    def _get_bridge_device_info(self, lp: str) -> tuple[CyncTCPDeviceProtocol, bytes, int] | None:
        """Get bridge device and related info for sending commands.

        Returns tuple (bridge_device, queue_id, cmsg_id) or None if validation fails.
        """
        g = _get_global_object()
        ncync_server = g.ncync_server
        if ncync_server is None:
            logger.error("%s ncync_server is None, cannot send command", lp)
            return None

        tcp_devices = ncync_server.tcp_devices
        if not tcp_devices:
            logger.error("%s No TCP bridges available!", lp)
            return None

        bridge_devices = list(tcp_devices.values())
        if not bridge_devices or bridge_devices[0] is None:
            if not bridge_devices:
                logger.error("%s No TCP bridges available!", lp)
            else:
                logger.error("%s Bridge device is None", lp)
            return None

        bridge_device = bridge_devices[0]
        if not bridge_device.ready_to_control:
            logger.error("%s Bridge %s not ready to control", lp, bridge_device.address)
            return None

        queue_id = bridge_device.queue_id
        cmsg_id_bytes = bridge_device.get_ctrl_msg_id_bytes()
        if not cmsg_id_bytes:
            logger.error("%s Failed to get control message ID bytes", lp)
            return None

        cmsg_id = cmsg_id_bytes[0]
        return (bridge_device, bytes(queue_id), cmsg_id)

    def _build_group_payload(
        self,
        header: list[int],
        inner_struct: list[int],
        queue_id: bytes,
        cmsg_id: int,
    ) -> bytes:
        """Build payload bytes from header, inner_struct, queue_id, and cmsg_id."""
        payload: list[int] = list(header)
        payload.extend(queue_id)
        payload.extend(bytes([0x00, 0x00, 0x00]))
        ctrl_idxs = 1, 9
        inner_struct[ctrl_idxs[0]] = cmsg_id
        inner_struct[ctrl_idxs[1]] = cmsg_id
        # Filter to only int values for checksum calculation
        checksum: int = sum(inner_struct[6:-2]) % 256
        inner_struct[-2] = checksum
        payload.extend(inner_struct)
        return bytes(payload)

    async def set_power(self, state: int) -> tuple[asyncio.Event, list[CyncTCPDeviceProtocol]] | None:
        """Send power command to all devices in the group using the group ID.

        :param state: Power state (0=off, 1=on)
        """
        lp = f"{self.lp}set_power:"
        if state not in (0, 1):
            logger.error("%s Invalid state! must be 0 or 1", lp)
            return None

        if not self._validate_group_id(lp):
            return None

        group_id = self.id
        if group_id is None:
            return None

        # Use full 16-bit group ID encoding
        id_low: int = group_id & 0xFF
        id_high: int = (group_id >> 8) & 0xFF

        header = [0x73, 0x00, 0x00, 0x00, 0x1F]
        inner_struct: list[int] = [
            0x7E,
            0x00,  # ctrl byte placeholder
            0x00,
            0x00,
            0x00,
            0xF8,
            0xD0,
            0x0D,
            0x00,
            0x00,  # mirrored ctrl byte placeholder
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
            0x00,  # checksum placeholder
            0x7E,
        ]

        bridge_info: tuple[CyncTCPDeviceProtocol, bytes, int] | None = self._get_bridge_device_info(lp)
        if bridge_info is None:
            return None
        bridge_device: CyncTCPDeviceProtocol
        queue_id: bytes
        cmsg_id: int
        bridge_device, queue_id, cmsg_id = bridge_info

        payload_bytes = self._build_group_payload(header, inner_struct, queue_id, cmsg_id)

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
        mesh_info = bridge_device.mesh_info
        mesh_count = len(mesh_info.status) if mesh_info and mesh_info.status else 0
        logger.debug("%s Bridge mesh_info count: %s", lp, mesh_count)
        known_device_ids = bridge_device.known_device_ids
        logger.debug("%s Bridge known_device_ids: %s", lp, known_device_ids)
        logger.debug("%s Packet to send: %s", lp, payload_bytes.hex(" "))

        # Register callback for ACK (no optimistic group publish)
        # Use None for noop callbacks - avoids creating unawaited coroutines
        ack_event = asyncio.Event()
        m_cb = ControlMessageCallback(
            id=cmsg_id,
            message=payload_bytes,
        )
        m_cb.sent_at = time.time()
        m_cb.device_id = self.id
        m_cb.ack_event = ack_event
        bridge_device.messages.control[cmsg_id] = m_cb
        logger.debug("%s Registered callback for msg_id=%s", lp, cmsg_id)

        # BUG FIX: Sync ALL group device states IMMEDIATELY (optimistically)
        # Group commands affect both bulbs and switches, so update both for instant UI feedback
        g = _get_global_object()
        mqtt_client = g.mqtt_client
        if mqtt_client is not None and self.id is not None and self.name is not None:
            _ = await mqtt_client.sync_group_devices(self.id, state, self.name)

        logger.debug("%s CALLING bridge_device.write()...", lp)
        write_result: bool | None = await bridge_device.write(payload_bytes)
        logger.debug("%s bridge_device.write() RETURNED: %s", lp, write_result)

        logger.debug(
            "%s Returning ACK event for group power command",
            lp,
            extra={
                "cmsg_id": cmsg_id,
                "bridge_address": getattr(bridge_device, "address", None),
                "state": state,
            },
        )
        return ack_event, [bridge_device]

    async def set_brightness(self, bri: int) -> tuple[asyncio.Event, list[CyncTCPDeviceProtocol]] | None:
        """Send brightness command to all devices in the group using the group ID.

        :param brightness: Brightness value (0-100)
        """
        lp = f"{self.lp}set_brightness:"
        if bri < PERCENT_MIN or bri > PERCENT_MAX:
            logger.error("%s Invalid brightness! must be 0-100", lp)
            return None

        if not self._validate_group_id(lp):
            return None

        group_id = self.id
        if group_id is None:
            return None

        # Use full 16-bit group ID encoding
        id_low = group_id & 0xFF
        id_high = (group_id >> 8) & 0xFF

        header = [0x73, 0x00, 0x00, 0x00, 0x22]
        inner_struct: list[int] = [
            0x7E,
            0x00,
            0x00,
            0x00,
            0x00,
            0xF8,
            0xF0,
            0x10,
            0x00,
            0x00,
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
            bri,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0x00,
            0x7E,
        ]

        bridge_info: tuple[CyncTCPDeviceProtocol, bytes, int] | None = self._get_bridge_device_info(lp)
        if bridge_info is None:
            return None
        bridge_device: CyncTCPDeviceProtocol
        queue_id: bytes
        cmsg_id: int
        bridge_device, queue_id, cmsg_id = bridge_info

        payload_bytes = self._build_group_payload(header, inner_struct, queue_id, cmsg_id)

        logger.info(
            "%s Sending brightness=%s to group '%s' (ID: %s) with %s devices",
            lp,
            bri,
            self.name,
            self.id,
            len(self.member_ids),
        )

        # Log which devices are in this group for debugging
        g = _get_global_object()
        ncync_server = g.ncync_server
        devices = ncync_server.devices if ncync_server else None
        device_names: list[str] = []
        if devices is not None:
            for device_id in self.member_ids:
                if device_id in devices:
                    device = devices[device_id]
                    device_name = getattr(device, "name", f"Unknown (ID: {device_id})")
                    device_names.append(f"'{device_name}' (ID: {device_id})")
        logger.info("%s Group members: %s", lp, ", ".join(device_names))

        # Register callback for ACK (no optimistic group publish)
        # Use None for noop callbacks - avoids creating unawaited coroutines
        ack_event = asyncio.Event()
        m_cb = ControlMessageCallback(
            id=cmsg_id,
            message=payload_bytes,
        )
        m_cb.sent_at = time.time()
        m_cb.device_id = self.id
        m_cb.ack_event = ack_event
        bridge_device.messages.control[cmsg_id] = m_cb
        _ = await bridge_device.write(payload_bytes)

        return ack_event, [bridge_device]

    async def set_temperature(self, temperature: int):
        """Send color temperature command to all devices in the group using the group ID.

        :param temperature: Color temperature value (0-100)
        """
        lp = f"{self.lp}set_temperature:"
        if temperature < PERCENT_MIN or temperature > PERCENT_MAX:
            logger.error("%s Invalid temperature! must be 0-100", lp)
            return

        if not self._validate_group_id(lp):
            return

        group_id = self.id
        if group_id is None:
            return

        # Use full 16-bit group ID encoding
        id_low = group_id & 0xFF
        id_high = (group_id >> 8) & 0xFF

        header = [0x73, 0x00, 0x00, 0x00, 0x22]
        inner_struct: list[int] = [
            0x7E,
            0x00,
            0x00,
            0x00,
            0x00,
            0xF8,
            0xF0,
            0x10,
            0x00,
            0x00,
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
            0x00,
            0x7E,
        ]

        bridge_info: tuple[CyncTCPDeviceProtocol, bytes, int] | None = self._get_bridge_device_info(lp)
        if bridge_info is None:
            return
        bridge_device: CyncTCPDeviceProtocol
        queue_id: bytes
        cmsg_id: int
        bridge_device, queue_id, cmsg_id = bridge_info

        payload_bytes = self._build_group_payload(header, inner_struct, queue_id, cmsg_id)

        logger.info(
            "%s Sending temperature=%s to group '%s' (ID: %s) with %s devices",
            lp,
            temperature,
            self.name,
            self.id,
            len(self.member_ids),
        )

        # Log which devices are in this group for debugging
        g = _get_global_object()
        ncync_server = g.ncync_server
        devices = ncync_server.devices if ncync_server else None
        device_names: list[str] = []
        if devices is not None:
            for device_id in self.member_ids:
                if device_id in devices:
                    device = devices[device_id]
                    device_name = getattr(device, "name", f"Unknown (ID: {device_id})")
                    device_names.append(f"'{device_name}' (ID: {device_id})")
        logger.info("%s Group members: %s", lp, ", ".join(device_names))

        # Register callback for ACK (no optimistic group publish)
        # Use None for noop callbacks - avoids creating unawaited coroutines
        m_cb = ControlMessageCallback(
            id=cmsg_id,
            message=payload_bytes,
        )
        m_cb.sent_at = time.time()
        m_cb.device_id = self.id
        bridge_device.messages.control[cmsg_id] = m_cb
        _ = await bridge_device.write(payload_bytes)

    @override
    def __repr__(self):
        return f"CyncGroup(id={self.id}, name='{self.name}', members={len(self.member_ids)})"

    @override
    def __str__(self):
        return f"CyncGroup {self.name} (ID: {self.id})"
