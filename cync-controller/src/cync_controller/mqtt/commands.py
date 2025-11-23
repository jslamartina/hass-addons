"""MQTT command classes for device control.

Provides command pattern implementation for optimistic updates and device control.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from cync_controller.devices import CyncGroup
from cync_controller.logging_abstraction import get_logger
from cync_controller.structs import GlobalObject

if TYPE_CHECKING:
    from cync_controller.devices.tcp_device import CyncTCPDevice

logger = get_logger(__name__)
g = GlobalObject()


class DeviceCommand:
    """Base class for device commands."""

    def __init__(self, cmd_type: str, device_id: str | int, **kwargs) -> None:
        """Initialize a device command.

        Args:
            cmd_type: Command type (e.g., "set_power", "set_brightness")
            device_id: Device or group ID
            **kwargs: Command-specific parameters

        """
        self.cmd_type = cmd_type
        self.device_id = device_id
        self.params = kwargs
        self.timestamp = asyncio.get_event_loop().time()

    async def publish_optimistic(self):
        """Publish optimistic state update to MQTT (before device command)."""
        raise NotImplementedError

    async def execute(self):
        """Execute the actual device command."""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{self.cmd_type}: device_id={self.device_id} params={self.params}>"


class CommandProcessor:
    """Singleton processor for device commands with sequential mesh refresh."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize command processor."""
        if not hasattr(self, "_initialized"):
            self._queue = asyncio.Queue()
            self._processing = False
            self._initialized = True
            self.lp = "CommandProcessor:"

    async def enqueue(self, cmd: DeviceCommand):
        """Enqueue a command for processing.

        Args:
            cmd: DeviceCommand to process

        """
        await self._queue.put(cmd)
        logger.debug("%s Queued command: %s (queue size: %d)", self.lp, cmd, self._queue.qsize())
        if not self._processing:
            task = asyncio.create_task(self.process_next())
            del task  # Reference stored, allow garbage collection

    async def process_next(self):  # noqa: PLR0912, PLR0915
        """Process commands sequentially with mesh refresh."""
        lp = f"{self.lp}process_next:"
        self._processing = True

        try:
            while not self._queue.empty():
                cmd: DeviceCommand = cast("DeviceCommand", await self._queue.get())

                logger.info("%s Processing: %s", lp, cmd)

                try:
                    # 1 Optimistic MQTT update first (UX feels instant)
                    logger.debug("%s Publishing optimistic update", lp)
                    await cmd.publish_optimistic()

                    # 2 Send to device and get ACK event + cleanup info
                    logger.debug("%s Executing device command", lp)
                    result: (
                        tuple[asyncio.Event, list[CyncTCPDevice] | list[tuple[CyncTCPDevice, int]]]
                        | asyncio.Event
                        | None
                    ) = cast(
                        "tuple[asyncio.Event, list[CyncTCPDevice] | list[tuple[CyncTCPDevice, int]]] | asyncio.Event | None",
                        await cmd.execute(),
                    )

                    # Unpack result (may be ack_event only or (ack_event, sent_bridges) tuple)
                    if isinstance(result, tuple):
                        ack_event: asyncio.Event = result[0]
                        # sent_bridges is actually list[tuple[CyncTCPDevice, int]] despite type annotation
                        sent_bridges_raw: list[CyncTCPDevice] | list[tuple[CyncTCPDevice, int]] = result[1]
                        if sent_bridges_raw and isinstance(sent_bridges_raw[0], tuple):
                            sent_bridges: list[tuple[CyncTCPDevice, int]] = sent_bridges_raw  # type: ignore[assignment]
                        else:
                            # Convert list[CyncTCPDevice] to list[tuple[CyncTCPDevice, int]] by extracting msg_id from control messages
                            # Match callbacks by device_id and ack_event to find the actual message IDs
                            sent_bridges = []
                            device_id = cmd.device_id
                            # Type narrowing: sent_bridges_raw is list[CyncTCPDevice] at this point
                            bridges_list: list[CyncTCPDevice] = cast("list[CyncTCPDevice]", sent_bridges_raw)
                            for bridge in bridges_list:
                                msg_id_found: int | None = None
                                # Search control messages for callback matching this device and ack_event
                                for ctrl_msg_id, callback in bridge.messages.control.items():
                                    if (
                                        callback.device_id == device_id
                                        and callback.ack_event is ack_event
                                        and callback.sent_at is not None
                                        and callback.sent_at > asyncio.get_event_loop().time() - 10.0
                                    ):
                                        msg_id_found = ctrl_msg_id
                                        break
                                if msg_id_found is not None:
                                    sent_bridges.append((bridge, msg_id_found))
                                else:
                                    # Fallback: log warning but still add bridge for potential cleanup
                                    bridge_address = bridge.address if bridge.address else "unknown"
                                    logger.warning(
                                        "%s Could not find msg_id for bridge %s, device_id=%s - callback cleanup may be incomplete",
                                        lp,
                                        bridge_address,
                                        device_id,
                                    )
                                    # Try to clean up all callbacks for this device_id as fallback
                                    sent_bridges.append(
                                        (bridge, -1),
                                    )  # Use -1 as sentinel to trigger device_id-based cleanup
                    else:
                        ack_event = result
                        sent_bridges: list[tuple[CyncTCPDevice, int]] = []

                    # 3 Wait for ACK with timeout (block queue until command confirmed)
                    if ack_event:
                        logger.debug("%s Waiting for ACK...", lp)
                        try:
                            _ = await asyncio.wait_for(ack_event.wait(), timeout=5.0)
                            logger.info("%s ACK received, command confirmed", lp)
                        except TimeoutError:
                            logger.warning("%s ACK timeout after 5s - cleaning up callbacks", lp)
                            # Immediately remove orphaned callbacks instead of waiting 30s for cleanup task
                            device_id = cmd.device_id
                            for bridge, msg_id in sent_bridges:  # type: ignore[reportUnknownVariableType]
                                if msg_id == -1:
                                    # Fallback: clean up all callbacks for this device_id and ack_event
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
                    else:
                        logger.debug("%s No ACK event (command rejected/throttled)", lp)

                    logger.info("%s Command cycle complete for %s", lp, cmd.cmd_type)

                except Exception:
                    logger.exception("%s Command failed: %s", lp, cmd)

                finally:
                    self._queue.task_done()
        finally:
            self._processing = False
            logger.debug("%s Processing loop ended, queue size: %d", lp, self._queue.qsize())


class SetPowerCommand(DeviceCommand):
    """Command to set device or group power state."""

    def __init__(self, device_or_group, state: int) -> None:
        """Initialize set power command.

        Args:
            device_or_group: CyncDevice or CyncGroup instance
            state: Power state (0=OFF, 1=ON)

        """
        super().__init__("set_power", device_or_group.id, state=state)
        self.device_or_group = device_or_group
        self.state = state

    async def publish_optimistic(self):
        """Publish optimistic state update for the device and its group."""
        if isinstance(self.device_or_group, CyncGroup):
            # For groups: sync_group_devices will be called in set_power()
            pass
        else:
            # For individual devices: publish optimistic state immediately
            if g.mqtt_client is not None:
                await g.mqtt_client.update_device_state(self.device_or_group, self.state)

            # If this is a switch, also sync its group
            try:
                if self.device_or_group.is_switch:
                    device: Any = cast("Any", self.device_or_group)
                    if g.ncync_server and g.ncync_server.groups and g.mqtt_client is not None:
                        for group_id, group in g.ncync_server.groups.items():
                            if device.id in group.member_ids:
                                # Sync all group devices to match this switch's new state
                                await g.mqtt_client.sync_group_devices(group_id, self.state, group.name)
            except Exception as e:
                logger.warning("Group sync failed for switch: %s", e)

    async def execute(self) -> tuple[asyncio.Event, list[CyncTCPDevice]] | None:
        """Execute the actual set_power command."""
        return cast("tuple[asyncio.Event, list[CyncTCPDevice]] | None", await self.device_or_group.set_power(self.state))


class SetBrightnessCommand(DeviceCommand):
    """Command to set device brightness."""

    def __init__(self, device_or_group, brightness: int) -> None:
        """Initialize set brightness command.

        Args:
            device_or_group: CyncDevice or CyncGroup instance
            brightness: Brightness value (0-100)

        """
        super().__init__("set_brightness", device_or_group.id, brightness=brightness)
        self.device_or_group = device_or_group
        self.brightness = brightness

    async def publish_optimistic(self):
        """Publish optimistic brightness update for the device."""
        if isinstance(self.device_or_group, CyncGroup):
            # For groups: sync_group_devices will be called in cole_dset_brightness()
            pass
        # For individual devices: publish optimistic brightness immediately
        elif g.mqtt_client is not None:
            await g.mqtt_client.update_brightness(self.device_or_group, self.brightness)

    async def execute(self) -> tuple[asyncio.Event, list[CyncTCPDevice]] | None:
        """Execute the actual set_brightness command."""
        return cast(
            "tuple[asyncio.Event, list[CyncTCPDevice]] | None", await self.device_or_group.set_brightness(self.brightness),
        )
