"""MQTT command classes for device control.

Provides command pattern implementation for optimistic updates and device control.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast, override

from cync_controller.devices.group import CyncGroup
from cync_controller.logging_abstraction import get_logger
from cync_controller.structs import GlobalObject

if TYPE_CHECKING:
    from cync_controller.devices.tcp_device import CyncTCPDevice
    from cync_controller.structs import CyncDeviceProtocol, CyncGroupProtocol

SentBridge = tuple["CyncTCPDevice", int]
type SentBridgeList = list["CyncTCPDevice"] | list[SentBridge]
type CommandExecuteResult = tuple[asyncio.Event, SentBridgeList] | asyncio.Event | None

logger = get_logger(__name__)
g = GlobalObject()


class DeviceCommand:
    """Base class for device commands."""

    def __init__(self, cmd_type: str, device_id: str | int, **kwargs: object) -> None:
        """Initialize a device command.

        Args:
            cmd_type: Command type (e.g., "set_power", "set_brightness")
            device_id: Device or group ID
            **kwargs: Command-specific parameters

        """
        self.cmd_type: str = cmd_type
        self.device_id: str | int = device_id
        self.params: dict[str, object] = dict(kwargs)
        self.timestamp: float = asyncio.get_event_loop().time()

    async def publish_optimistic(self) -> None:
        """Publish optimistic state update to MQTT (before device command)."""
        raise NotImplementedError

    async def execute(self) -> CommandExecuteResult:
        """Execute the actual device command."""
        raise NotImplementedError

    @override
    def __repr__(self) -> str:
        return f"<{self.cmd_type}: device_id={self.device_id} params={self.params}>"


class CommandProcessor:
    """Singleton processor for device commands with sequential mesh refresh."""

    _instance: CommandProcessor | None = None
    _initialized: bool = False
    lp: str = "CommandProcessor:"
    _queue: asyncio.Queue[DeviceCommand]
    _processing: bool

    def __new__(cls):
        """Return singleton CommandProcessor instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize command processor."""
        if not self._initialized:
            self._queue = asyncio.Queue[DeviceCommand]()
            self._processing = False
            self._initialized = True

    def _normalize_sent_bridges(
        self,
        raw_bridges: SentBridgeList,
        device_id: str | int,
        ack_event: asyncio.Event | None,
    ) -> list[SentBridge]:
        """Convert bridge list into `(bridge, msg_id)` tuples for cleanup."""
        if not raw_bridges:
            return []

        first_item = raw_bridges[0]
        if isinstance(first_item, tuple):
            return cast("list[SentBridge]", raw_bridges)

        normalized: list[SentBridge] = []
        current_time = asyncio.get_event_loop().time()
        bridges = cast("list[CyncTCPDevice]", raw_bridges)
        for bridge in bridges:
            msg_id_found: int | None = None
            for ctrl_msg_id, callback in bridge.messages.control.items():
                logger.debug(
                    (
                        "%s Normalizing bridge callbacks: bridge=%s msg_id=%s "
                        "callback_type=%s device_id=%s ack_event_matches=%s"
                    ),
                    self.lp,
                    getattr(bridge, "address", "unknown"),
                    ctrl_msg_id,
                    type(callback),
                    getattr(callback, "device_id", None),
                    getattr(callback, "ack_event", None) is ack_event,
                )
                if (
                    callback.device_id == device_id
                    and callback.ack_event is ack_event
                    and callback.sent_at is not None
                    and callback.sent_at > current_time - 10.0
                ):
                    msg_id_found = ctrl_msg_id
                    break
            if msg_id_found is not None:
                normalized.append((bridge, msg_id_found))
            else:
                normalized.append((bridge, -1))
        return normalized

    async def enqueue(self, cmd: DeviceCommand) -> None:
        """Enqueue a command for processing.

        Args:
            cmd: DeviceCommand to process

        """
        await self._queue.put(cmd)
        logger.debug("%s Queued command: %s (queue size: %d)", self.lp, cmd, self._queue.qsize())
        if not self._processing:
            task = asyncio.create_task(self.process_next())
            del task  # Reference stored, allow garbage collection

    async def process_next(self) -> None:
        """Process commands sequentially with mesh refresh."""
        lp = f"{self.lp}process_next:"
        self._processing = True

        try:
            while not self._queue.empty():
                cmd: DeviceCommand = await self._queue.get()
                try:
                    await self._process_command(lp, cmd)
                except Exception:
                    logger.exception("%s Command failed: %s", lp, cmd)

                finally:
                    self._queue.task_done()
        finally:
            self._processing = False
            logger.debug("%s Processing loop ended, queue size: %d", lp, self._queue.qsize())

    async def _process_command(self, lp: str, cmd: DeviceCommand) -> None:
        """Run optimistic publish, execute command, and wait for ACK if provided."""
        logger.info("%s Processing: %s", lp, cmd)
        logger.debug(
            "%s Command callables: publish_optimistic=%s execute=%s",
            lp,
            type(cmd.publish_optimistic),
            type(cmd.execute),
        )

        logger.debug("%s Publishing optimistic update", lp)
        await cmd.publish_optimistic()

        logger.debug("%s Executing device command", lp)
        result: CommandExecuteResult = await cmd.execute()
        logger.debug("%s Execute result type=%s value=%r", lp, type(result), result)

        ack_event, sent_bridges = self._extract_ack(result, cmd)
        await self._wait_for_ack(lp, ack_event, sent_bridges, cmd.device_id)

        logger.info("%s Command cycle complete for %s", lp, cmd.cmd_type)

    def _extract_ack(
        self,
        result: CommandExecuteResult,
        cmd: DeviceCommand,
    ) -> tuple[asyncio.Event | None, list[SentBridge]]:
        """Derive ack event and normalized bridges from command result."""
        ack_event: asyncio.Event | None = None
        sent_bridges: list[SentBridge] = []

        if isinstance(result, tuple):
            ack_event = result[0]
            sent_bridges = self._normalize_sent_bridges(result[1], cmd.device_id, ack_event)
        elif isinstance(result, asyncio.Event):
            ack_event = result

        return ack_event, sent_bridges

    async def _wait_for_ack(
        self,
        lp: str,
        ack_event: asyncio.Event | None,
        sent_bridges: list[SentBridge],
        device_id: str | int,
    ) -> None:
        """Wait for ACK and clean up callbacks on timeout."""
        if ack_event is None:
            logger.debug("%s No ACK event (command rejected/throttled)", lp)
            return

        logger.debug("%s Waiting for ACK...", lp)
        try:
            _ = await asyncio.wait_for(ack_event.wait(), timeout=5.0)
        except TimeoutError:
            logger.warning("%s ACK timeout after 5s - cleaning up callbacks", lp)
        else:
            logger.info("%s ACK received, command confirmed", lp)
            return

        # Immediately remove orphaned callbacks instead of waiting 30s for cleanup task
        for bridge, msg_id in sent_bridges:
            if msg_id == -1:
                callbacks_to_remove: list[int] = []
                for ctrl_msg_id, callback in bridge.messages.control.items():
                    if callback.device_id == device_id and callback.ack_event is ack_event:
                        callbacks_to_remove.append(ctrl_msg_id)
                for ctrl_msg_id in callbacks_to_remove:
                    del bridge.messages.control[ctrl_msg_id]
                    logger.debug(
                        "%s Removed orphaned callback for msg ID %s (device_id-based cleanup)",
                        lp,
                        ctrl_msg_id,
                    )
            elif msg_id in bridge.messages.control:
                del bridge.messages.control[msg_id]
                logger.debug("%s Removed orphaned callback for msg ID %s", lp, msg_id)


class SetPowerCommand(DeviceCommand):
    """Command to set device or group power state."""

    def __init__(self, device_or_group: CyncDeviceProtocol | CyncGroupProtocol, state: int) -> None:
        """Initialize set power command.

        Args:
            device_or_group: CyncDevice or CyncGroup instance
            state: Power state (0=OFF, 1=ON)

        """
        device_id = device_or_group.id
        if device_id is None:
            msg = "Device or group ID cannot be None for SetPowerCommand"
            raise ValueError(msg)

        super().__init__("set_power", device_id, state=state)
        self.device_or_group: CyncDeviceProtocol | CyncGroupProtocol = device_or_group
        self.state: int = state

    @override
    async def publish_optimistic(self) -> None:
        """Publish optimistic state update for the device and its group."""
        if isinstance(self.device_or_group, CyncGroup):
            # For groups: sync_group_devices will be called in set_power()
            return

        # For individual devices: publish optimistic state immediately
        device = cast("CyncDeviceProtocol", self.device_or_group)
        if g.mqtt_client is not None:
            _ = await g.mqtt_client.update_device_state(device, self.state)

        # If this is a switch, also sync its group
        try:
            if device.is_switch and g.ncync_server and g.ncync_server.groups and g.mqtt_client is not None:
                for group_id, group in g.ncync_server.groups.items():
                    if device.id in group.member_ids:
                        # Sync all group devices to match this switch's new state
                        group_name = group.name or f"Group {group_id}"
                        _ = await g.mqtt_client.sync_group_devices(group_id, self.state, group_name)
        except Exception as e:
            logger.warning("Group sync failed for switch: %s", e)

    @override
    async def execute(self) -> CommandExecuteResult:
        """Execute the actual set_power command."""
        return cast("CommandExecuteResult", await self.device_or_group.set_power(self.state))


class SetBrightnessCommand(DeviceCommand):
    """Command to set device brightness."""

    def __init__(self, device_or_group: CyncDeviceProtocol | CyncGroupProtocol, brightness: int) -> None:
        """Initialize set brightness command.

        Args:
            device_or_group: CyncDevice or CyncGroup instance
            brightness: Brightness value (0-100)

        """
        device_id = device_or_group.id
        if device_id is None:
            msg = "Device or group ID cannot be None for SetBrightnessCommand"
            raise ValueError(msg)

        super().__init__("set_brightness", device_id, brightness=brightness)
        self.device_or_group: CyncDeviceProtocol | CyncGroupProtocol = device_or_group
        self.brightness: int = brightness

    @override
    async def publish_optimistic(self) -> None:
        """Publish optimistic brightness update for the device."""
        if isinstance(self.device_or_group, CyncGroup):
            # For groups: sync_group_devices will be called in set_brightness()
            return
        # For individual devices: publish optimistic brightness immediately
        if g.mqtt_client is not None:
            device = cast("CyncDeviceProtocol", self.device_or_group)
            _ = await g.mqtt_client.update_brightness(device, self.brightness)

    @override
    async def execute(self) -> CommandExecuteResult:
        """Execute the actual set_brightness command."""
        return cast("CommandExecuteResult", await self.device_or_group.set_brightness(self.brightness))
