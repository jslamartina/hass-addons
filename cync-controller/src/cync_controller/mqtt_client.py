"""Backward compatibility wrapper for MQTTClient.

This module re-exports MQTTClient, command classes, aiomqtt, g, and constants from the mqtt modules to maintain
backward compatibility with existing imports and test patches:
    from cync_controller.mqtt_client import MQTTClient, CommandProcessor, DeviceCommand
    patch("cync_controller.mqtt_client.aiomqtt.Client")
    patch("cync_controller.mqtt_client.g")
    patch("cync_controller.mqtt_client.CYNC_TOPIC")

The implementation has been refactored into focused modules under mqtt/:
- mqtt/client.py: Core MQTTClient class
- mqtt/commands.py: Command classes
- mqtt/discovery.py: Discovery helper
- mqtt/command_routing.py: Message routing
- mqtt/state_updates.py: State publishing
"""

import asyncio

import aiomqtt

from cync_controller.const import (
    CYNC_HASS_BIRTH_MSG,
    CYNC_HASS_TOPIC,
    CYNC_HASS_WILL_MSG,
    CYNC_MAXK,
    CYNC_MINK,
    CYNC_MQTT_HOST,
    CYNC_MQTT_PASS,
    CYNC_MQTT_PORT,
    CYNC_MQTT_USER,
    CYNC_TOPIC,
)
from cync_controller.mqtt.client import MQTTClient
from cync_controller.mqtt.commands import CommandProcessor, DeviceCommand, SetBrightnessCommand, SetPowerCommand
from cync_controller.structs import GlobalObject

# Re-export g for backward compatibility with tests
g = GlobalObject()

__all__ = [
    "CYNC_HASS_BIRTH_MSG",
    "CYNC_HASS_TOPIC",
    "CYNC_HASS_WILL_MSG",
    "CYNC_MAXK",
    "CYNC_MINK",
    "CYNC_MQTT_HOST",
    "CYNC_MQTT_PASS",
    "CYNC_MQTT_PORT",
    "CYNC_MQTT_USER",
    "CYNC_TOPIC",
    "CommandProcessor",
    "DeviceCommand",
    "MQTTClient",
    "SetBrightnessCommand",
    "SetPowerCommand",
    "aiomqtt",
    "asyncio",
    "g",
]
