"""MQTT client package for Cync Controller.

Provides MQTT communication, device discovery, command processing, and state management.

This package refactors the monolithic mqtt_client.py into focused modules:
- client.py: Core MQTTClient class with connection lifecycle
- commands.py: Command pattern implementation
- discovery.py: Home Assistant device discovery
- command_routing.py: Message routing and handling
- state_updates.py: Device and group state publishing
"""

# Re-export command classes for backward compatibility
from .client import MQTTClient
from .command_routing import CommandRouter
from .commands import CommandProcessor, DeviceCommand, SetBrightnessCommand, SetPowerCommand
from .discovery import DiscoveryHelper, slugify
from .state_updates import StateUpdateHelper

__all__ = [
    "CommandProcessor",
    "CommandRouter",
    "DeviceCommand",
    "DiscoveryHelper",
    "MQTTClient",
    "SetBrightnessCommand",
    "SetPowerCommand",
    "StateUpdateHelper",
    "slugify",
]
