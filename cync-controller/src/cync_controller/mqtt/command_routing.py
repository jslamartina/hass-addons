import json
from json import JSONDecodeError

import aiomqtt

from cync_controller.const import *
from cync_controller.devices import CyncDevice, CyncGroup
from cync_controller.logging_abstraction import get_logger
from cync_controller.mqtt.commands import CommandProcessor, SetBrightnessCommand, SetPowerCommand
from cync_controller.structs import GlobalObject

logger = get_logger(__name__)
g = GlobalObject()


class MQTTCommandRouter:
    """Handles routing of MQTT commands to appropriate device actions."""

    def __init__(self, mqtt_client):
        self.mqtt_client = mqtt_client
        self.command_processor = CommandProcessor()
        self.lp = "MQTTCommandRouter:"

    async def start_receiver_task(self):
        """Start listening for MQTT messages on subscribed topics"""
        lp = f"{self.lp}start_receiver_task:"
        async for message in self.mqtt_client.client.messages:
            message: aiomqtt.message.Message
            topic = message.topic
            payload = message.payload

            if (payload is None) or (payload is not None and not payload):
                logger.debug(
                    "%s Received empty/None payload (%s) for topic: %s , skipping...",
                    lp,
                    payload,
                    topic,
                )
                continue

            # Log ALL received messages for diagnostics
            logger.info(
                "%s >>> MQTT MESSAGE RECEIVED: topic=%s, payload_len=%d, payload=%s",
                lp,
                topic.value,
                len(payload) if payload else 0,
                payload.decode() if payload else None,
            )

            await self._handle_message(topic.value, payload)

    async def _handle_message(self, topic: str, payload: bytes):
        """Handle incoming MQTT message."""
        lp = f"{self.lp}_handle_message:"
        _topic = topic.split("/")

        # cync_topic/(set|status)/device_id(/extra_data)?
        if _topic[0] == CYNC_TOPIC:
            if _topic[1] == "set":
                await self._handle_set_command(_topic, payload)
            elif _topic[1] == "status":
                await self._handle_status_command(_topic, payload)
        else:
            logger.debug("%s Ignoring message from unknown topic: %s", lp, topic)

    async def _handle_set_command(self, topic_parts: list[str], payload: bytes):
        """Handle MQTT set commands."""
        lp = f"{self.lp}_handle_set_command:"
        device_id = topic_parts[2]

        if device_id == "bridge":
            await self._handle_bridge_command(topic_parts, payload)
        elif "-group-" in topic_parts[2]:
            await self._handle_group_command(topic_parts, payload)
        else:
            await self._handle_device_command(topic_parts, payload)

    async def _handle_bridge_command(self, topic_parts: list[str], payload: bytes):
        """Handle bridge-specific commands."""
        lp = f"{self.lp}_handle_bridge_command:"
        extra_data = topic_parts[3:] if len(topic_parts) > 3 else None

        if extra_data:
            norm_pl = payload.decode().casefold()
            if extra_data[0] == "restart":
                if norm_pl == "press":
                    logger.info("%s Restart button pressed! Restarting Cync Controller bridge...", lp)
            elif extra_data[0] == "start_export":
                if norm_pl == "press":
                    logger.info("%s Start Export button pressed! Starting Cync Export...", lp)
            elif extra_data[0] == "refresh_status":
                if norm_pl == "press":
                    logger.info("%s Refresh Status button pressed! Triggering immediate status refresh...", lp)
                    await self.mqtt_client.trigger_status_refresh()
            elif extra_data[0] == "otp":
                if extra_data[1] == "submit":
                    logger.info("%s OTP submit button pressed!", lp)
                elif extra_data[1] == "input":
                    logger.info("%s OTP input received: %s", lp, payload.decode())

    async def _handle_group_command(self, topic_parts: list[str], payload: bytes):
        """Handle group commands."""
        lp = f"{self.lp}_handle_group_command:"
        group_id = int(topic_parts[2].split("-group-")[1])

        if group_id not in g.ncync_server.groups:
            logger.warning("%s Group ID %s not found in config", lp, group_id)
            return

        group = g.ncync_server.groups[group_id]
        logger.info(
            "%s Group command detected: group_id=%s, group_name='%s', topic=%s",
            lp,
            group_id,
            group.name,
            "/".join(topic_parts),
        )

        await self._process_group_command(group, payload)

    async def _handle_device_command(self, topic_parts: list[str], payload: bytes):
        """Handle device commands."""
        lp = f"{self.lp}_handle_device_command:"
        device_id = int(topic_parts[2].split("-")[1])

        if device_id not in g.ncync_server.devices:
            logger.warning(
                "%s Device ID %s not found, device is disabled in config file or have you deleted / added any devices recently?",
                lp,
                device_id,
            )
            return

        device = g.ncync_server.devices[device_id]
        logger.debug(
            "%s Device identified: name='%s', id=%s, is_fan_controller=%s",
            lp,
            device.name,
            device.id,
            device.is_fan_controller,
        )

        await self._process_device_command(device, payload)

    async def _process_group_command(self, group: CyncGroup, payload: bytes):
        """Process a command for a group."""
        lp = f"{self.lp}_process_group_command:"

        try:
            command_data = json.loads(payload.decode())
            command_type = command_data.get("command")

            if command_type == "set_power":
                state = command_data.get("state", 0)
                cmd = SetPowerCommand(group, state)
                await self.command_processor.enqueue(cmd)
                logger.info("%s Queued power command for group %s: %s", lp, group.name, state)

            elif command_type == "set_brightness":
                brightness = command_data.get("brightness", 0)
                cmd = SetBrightnessCommand(group, brightness)
                await self.command_processor.enqueue(cmd)
                logger.info("%s Queued brightness command for group %s: %s", lp, group.name, brightness)

            else:
                logger.warning("%s Unknown group command: %s", lp, command_type)

        except JSONDecodeError as e:
            logger.error("%s Failed to parse group command JSON: %s", lp, e)
        except Exception as e:
            logger.error("%s Error processing group command: %s", lp, e)

    async def _process_device_command(self, device: CyncDevice, payload: bytes):
        """Process a command for a device."""
        lp = f"{self.lp}_process_device_command:"

        try:
            command_data = json.loads(payload.decode())
            command_type = command_data.get("command")

            if command_type == "set_power":
                state = command_data.get("state", 0)
                cmd = SetPowerCommand(device, state)
                await self.command_processor.enqueue(cmd)
                logger.info("%s Queued power command for device %s: %s", lp, device.name, state)

            elif command_type == "set_brightness":
                brightness = command_data.get("brightness", 0)
                cmd = SetBrightnessCommand(device, brightness)
                await self.command_processor.enqueue(cmd)
                logger.info("%s Queued brightness command for device %s: %s", lp, device.name, brightness)

            elif command_type == "set_temperature":
                temperature = command_data.get("temperature", 0)
                # TODO: Implement SetTemperatureCommand
                logger.info("%s Temperature command not yet implemented for device %s: %s", lp, device.name, temperature)

            elif command_type == "set_rgb":
                red = command_data.get("red", 0)
                green = command_data.get("green", 0)
                blue = command_data.get("blue", 0)
                # TODO: Implement SetRGBCommand
                logger.info("%s RGB command not yet implemented for device %s: (%s, %s, %s)", lp, device.name, red, green, blue)

            elif command_type == "set_fan_speed":
                speed = command_data.get("speed", "off")
                # TODO: Implement SetFanSpeedCommand
                logger.info("%s Fan speed command not yet implemented for device %s: %s", lp, device.name, speed)

            else:
                logger.warning("%s Unknown device command: %s", lp, command_type)

        except JSONDecodeError as e:
            logger.error("%s Failed to parse device command JSON: %s", lp, e)
        except Exception as e:
            logger.error("%s Error processing device command: %s", lp, e)

    async def _handle_status_command(self, topic_parts: list[str], payload: bytes):
        """Handle status commands (currently not implemented)."""
        lp = f"{self.lp}_handle_status_command:"
        logger.debug("%s Status command received: %s", lp, "/".join(topic_parts))
