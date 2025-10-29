import asyncio
import re
import unicodedata

from cync_controller.devices import CyncDevice, CyncGroup
from cync_controller.logging_abstraction import get_logger
from cync_controller.structs import GlobalObject

logger = get_logger(__name__)
g = GlobalObject()


class DeviceCommand:
    """Base class for device commands."""

    def __init__(self, cmd_type: str, device_id: str | int, **kwargs):
        """
        Initialize a device command.

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

    def __init__(self):
        """Initialize command processor."""
        if not hasattr(self, "_initialized"):
            self._queue = asyncio.Queue()
            self._processing = False
            self._initialized = True
            self.lp = "CommandProcessor:"

    async def enqueue(self, cmd: DeviceCommand):
        """
        Enqueue a command for processing.

        Args:
            cmd: DeviceCommand to process
        """
        await self._queue.put(cmd)
        logger.debug("%s Queued command: %s (queue size: %d)", self.lp, cmd, self._queue.qsize())
        if not self._processing:
            task = asyncio.create_task(self.process_next())
            del task  # Reference stored, allow garbage collection

    async def process_next(self):
        """Process commands sequentially with mesh refresh."""
        lp = f"{self.lp}process_next:"
        self._processing = True

        try:
            while not self._queue.empty():
                cmd = await self._queue.get()

                logger.info("%s Processing: %s", lp, cmd)

                try:
                    # 1 Optimistic MQTT update first (UX feels instant)
                    logger.debug("%s Publishing optimistic update", lp)
                    await cmd.publish_optimistic()

                    # 2 Send to device
                    logger.debug("%s Executing device command", lp)
                    await cmd.execute()

                    # 3 Sync state with mesh refresh (synchronous - wait for completion)

                    logger.debug("%s Triggering mesh refresh", lp)
                    logger.debug("%s Waiting 500ms for optimistic updates to settle", lp)
                    await asyncio.sleep(0.5)

                    if g.mqtt_client:
                        await g.mqtt_client.trigger_status_refresh()

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

    def __init__(self, device_or_group, state: int):
        """
        Initialize set power command.

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
            await g.mqtt_client.update_device_state(self.device_or_group, self.state)

            # If this is a switch, also sync its group
            try:
                if self.device_or_group.is_switch:
                    device = self.device_or_group
                    if g.ncync_server and g.ncync_server.groups:
                        for group_id, group in g.ncync_server.groups.items():
                            if device.id in group.member_ids:
                                # Sync all group devices to match this switch's new state
                                await g.mqtt_client.sync_group_devices(group_id, self.state, group.name)
            except Exception as e:
                logger.warning("Group sync failed for switch: %s", e)

    async def execute(self):
        """Execute the actual set_power command."""
        await self.device_or_group.set_power(self.state)


class SetBrightnessCommand(DeviceCommand):
    """Command to set device brightness."""

    def __init__(self, device_or_group, brightness: int):
        """
        Initialize set brightness command.

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
            # For groups: sync_group_devices will be called in set_brightness()
            pass
        else:
            # For individual devices: publish optimistic brightness immediately
            await g.mqtt_client.update_brightness(self.device_or_group, self.brightness)

    async def execute(self):
        """Execute the actual set_brightness command."""
        await self.device_or_group.set_brightness(self.brightness)


def slugify(text: str) -> str:
    """
    Convert text to a slug suitable for entity IDs.
    E.g., 'Hallway Lights' -> 'hallway_lights'
    """
    # Normalize unicode characters
    text = unicodedata.normalize("NFKD", text)
    # Remove non-ASCII characters
    text = text.encode("ascii", "ignore").decode("ascii")
    # Convert to lowercase
    text = text.lower()
    # Replace spaces and special characters with underscores
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "_", text)
    # Remove leading/trailing underscores
    return text.strip("_")