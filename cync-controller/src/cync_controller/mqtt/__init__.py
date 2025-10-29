"""
MQTT client package for Cync Controller.

Provides MQTT communication, device discovery, command processing, and state management.

This package is being gradually refactored from the monolithic mqtt_client.py.
Currently re-exports are provided for backward compatibility.
"""

# Re-export command classes for backward compatibility
from .commands import CommandProcessor, DeviceCommand, SetBrightnessCommand, SetPowerCommand
from .discovery import DiscoveryHelper, slugify

# Note: MQTTClient is NOT imported here to avoid circular imports
# It can be imported directly: from cync_controller.mqtt_client import MQTTClient

__all__ = [
    "CommandProcessor",
    "DeviceCommand",
    "DiscoveryHelper",
    "SetBrightnessCommand",
    "SetPowerCommand",
    "slugify",
]

