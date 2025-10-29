import json

from cync_controller.devices import CyncDevice
from cync_controller.logging_abstraction import get_logger
from cync_controller.structs import GlobalObject

logger = get_logger(__name__)
g = GlobalObject()


class MQTTStateUpdater:
    """Handles MQTT state updates and device synchronization."""

    def __init__(self, mqtt_client):
        self.mqtt_client = mqtt_client
        self.lp = "MQTTStateUpdater:"

    async def update_device_state(self, device: CyncDevice, state: int) -> bool:
        """Update the device state and publish to MQTT for HASS devices to update.

        NOTE: Device availability is managed by server.parse_status() based on the
        connected_to_mesh byte and offline_count threshold. Do not set device.online here.
        """
        lp = f"{self.lp}update_device_state:"
        old_state = device.state
        device.state = state
        # NOTE: pending_command is cleared in the ACK handler (devices.py), not here
        power_status = "OFF" if state == 0 else "ON"
        logger.info(
            "%s Updating device '%s' (ID: %s) state from %s to %s (%s)",
            lp,
            device.name,
            device.id,
            old_state,
            state,
            power_status,
        )
        mqtt_dev_state = {"state": power_status}
        if device.is_plug:
            mqtt_dev_state = power_status.encode()  # send ON or OFF if plug
        elif device.is_switch:
            # Switches only need plain ON/OFF payload (no JSON)
            mqtt_dev_state = power_status.encode()
        else:
            # Lights need color_mode
            if device.supports_temperature:
                mqtt_dev_state["color_mode"] = "color_temp"
            elif device.supports_rgb:
                mqtt_dev_state["color_mode"] = "rgb"
            else:
                mqtt_dev_state["color_mode"] = "brightness"
            mqtt_dev_state = json.dumps(mqtt_dev_state).encode()  # send JSON
        return await self.send_device_status(device, mqtt_dev_state)

    async def update_brightness(self, device: CyncDevice, brightness: int) -> bool:
        """Update device brightness and publish to MQTT."""
        lp = f"{self.lp}update_brightness:"
        device.brightness = brightness

        # Convert to percentage for Home Assistant
        brightness_percent = self.mqtt_client._brightness_to_percentage(brightness)

        logger.info(
            "%s Updating device '%s' (ID: %s) brightness to %s%%",
            lp,
            device.name,
            device.id,
            brightness_percent,
        )

        # Publish brightness update
        brightness_topic = f"{self.mqtt_client.topic}/brightness/{device.hass_id}"
        await self.mqtt_client.publish(brightness_topic, str(brightness_percent).encode())

        return True

    async def update_switch_from_subgroup(self, device: CyncDevice, subgroup_state: int, subgroup_name: str) -> bool:
        """Update a switch device state to match its subgroup state.

        Only updates switches that don't have pending commands (individual commands take precedence).
        Only publishes to MQTT when state actually changes (no redundant updates).

        Args:
            device: The switch device to update
            subgroup_state: The subgroup's confirmed state (0=off, 1=on)
            subgroup_name: Name of the subgroup (for logging)

        Returns:
            True if the state was updated and published, False otherwise
        """
        lp = f"{self.lp}update_switch_from_subgroup:"

        # Safety checks
        if not device.is_switch:
            logger.debug(
                "%s Device '%s' (ID: %s) is not a switch, skipping subgroup sync",
                lp,
                device.name,
                device.id,
            )
            return False

        if device.pending_command:
            logger.debug(
                "%s Device '%s' (ID: %s) has pending command, skipping subgroup sync (individual control takes precedence)",
                lp,
                device.name,
                device.id,
            )
            return False

        # Update the switch to match subgroup state
        old_state = device.state
        logger.warning(
            "%s Syncing switch '%s' (ID: %s) to subgroup '%s' state: %s",
            lp,
            device.name,
            device.id,
            subgroup_name,
            "ON" if subgroup_state else "OFF",
        )

        # Always publish for optimistic feedback on group commands
        # (this function is now only called after explicit group commands, never from aggregation)
        logger.warning(
            "%s Publishing optimistic state update: %s  %s",
            lp,
            "ON" if old_state else "OFF",
            "ON" if subgroup_state else "OFF",
        )
        device.state = subgroup_state

        # Publish state update to MQTT
        power_status = "ON" if subgroup_state else "OFF"
        mqtt_dev_state = power_status.encode()  # Switches use plain ON/OFF payload
        return await self.send_device_status(device, mqtt_dev_state)

    async def sync_group_switches(self, group_id: int, group_state: int, group_name: str) -> int:
        """Sync all switch devices in a group to match the group's state.

        This is called after a group command is executed to ensure switches
        that control the same lights show the correct state in Home Assistant.

        Args:
            group_id: The group ID
            group_state: The group's state (0=off, 1=on)
            group_name: Name of the group (for logging)

        Returns:
            Number of switches synced
        """
        lp = f"{self.lp}sync_group_switches:"

        if group_id not in g.ncync_server.groups:
            logger.warning("%s [BUG4-TRACE] Group %s not found in server groups", lp, group_id)
            return 0

        group = g.ncync_server.groups[group_id]
        synced_count = 0

        logger.warning(
            "%s Syncing %d switches for group '%s' (ID: %s) to state: %s",
            lp,
            len(group.member_ids),
            group_name,
            group_id,
            "ON" if group_state else "OFF",
        )

        for member_id in group.member_ids:
            if member_id in g.ncync_server.devices:
                device = g.ncync_server.devices[member_id]
                logger.debug(
                    "%s Processing member: id=%d, name='%s', is_switch=%s",
                    lp,
                    member_id,
                    device.name,
                    device.is_switch,
                )
                # Sync switch to group state (will only publish if state actually changed)
                if await self.update_switch_from_subgroup(device, group_state, group_name):
                    synced_count += 1
            else:
                logger.debug(
                    "%s Member ID %d not found in devices",
                    lp,
                    member_id,
                )

        logger.warning("%s Synced %s switches for group '%s'", lp, synced_count, group_name)
        return synced_count

    async def sync_group_devices(self, group_id: int, group_state: int, group_name: str) -> int:
        """Sync all devices (switches and bulbs) in a group to match the group's state.

        This is called after a group command is executed to provide immediate optimistic
        feedback for all devices in the group.

        Args:
            group_id: The group ID
            group_state: The group's state (0=off, 1=on)
            group_name: Name of the group (for logging)

        Returns:
            Number of devices synced
        """
        lp = f"{self.lp}sync_group_devices:"

        if group_id not in g.ncync_server.groups:
            logger.warning("%s [BUG4-TRACE] Group %s not found in server groups", lp, group_id)
            return 0

        group = g.ncync_server.groups[group_id]
        synced_count = 0

        logger.info(
            "%s Syncing %d devices for group '%s' (ID: %s) to state: %s",
            lp,
            len(group.member_ids),
            group_name,
            group_id,
            "ON" if group_state else "OFF",
        )

        for member_id in group.member_ids:
            if member_id in g.ncync_server.devices:
                device = g.ncync_server.devices[member_id]
                logger.debug(
                    "%s Processing member: id=%d, name='%s', is_switch=%s, is_bulb=%s",
                    lp,
                    member_id,
                    device.name,
                    device.is_switch,
                    not device.is_switch,
                )

                if device.is_switch:
                    # Sync switch to group state
                    if await self.update_switch_from_subgroup(device, group_state, group_name):
                        synced_count += 1
                # Sync bulb to group state
                elif await self.update_device_state(device, group_state):
                    synced_count += 1
            else:
                logger.debug(
                    "%s Member ID %d not found in devices",
                    lp,
                    member_id,
                )

        logger.info("%s Synced %s devices for group '%s'", lp, synced_count, group_name)
        return synced_count

    async def send_device_status(self, device: CyncDevice, mqtt_dev_state: bytes) -> bool:
        """Send device status to MQTT."""
        lp = f"{self.lp}send_device_status:"
        try:
            topic = f"{self.mqtt_client.topic}/status/{device.hass_id}"
            await self.mqtt_client.publish(topic, mqtt_dev_state)
            logger.debug("%s Published status for device %s: %s", lp, device.name, mqtt_dev_state)
            return True
        except Exception as e:
            logger.error("%s Failed to publish status for device %s: %s", lp, device.name, e)
            return False

    async def trigger_status_refresh(self):
        """Trigger a refresh of all device statuses."""
        lp = f"{self.lp}trigger_status_refresh:"
        logger.info("%s Triggering status refresh for all devices", lp)

        # This would typically trigger a mesh refresh to get current device states
        # Implementation depends on the specific mesh refresh mechanism
