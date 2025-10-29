"""
Cync Controller MQTT Package

This package contains the MQTT client and related functionality for communicating
with Home Assistant and managing device states via MQTT.
"""

from cync_controller.mqtt.client import MQTTClient
from cync_controller.mqtt.command_routing import MQTTCommandRouter
from cync_controller.mqtt.commands import (
    CommandProcessor,
    DeviceCommand,
    SetBrightnessCommand,
    SetPowerCommand,
    slugify,
)
from cync_controller.mqtt.discovery import HomeAssistantDiscovery
from cync_controller.mqtt.state_updates import MQTTStateUpdater

__all__ = [
    "CommandProcessor",
    "DeviceCommand",
    "HomeAssistantDiscovery",
    "MQTTClient",
    "MQTTCommandRouter",
    "MQTTStateUpdater",
    "SetBrightnessCommand",
    "SetPowerCommand",
    "slugify",
]
