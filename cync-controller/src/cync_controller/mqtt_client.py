"""
Cync Controller MQTT Client Module

This module provides backward compatibility by re-exporting all MQTT classes
from the new modular structure. The actual implementations are now in the
cync_controller.mqtt package.
"""

# Re-export all classes from the mqtt package for backward compatibility
from cync_controller.mqtt import (
    MQTTClient,
    MQTTCommandRouter,
    MQTTStateUpdater,
    HomeAssistantDiscovery,
    CommandProcessor,
    DeviceCommand,
    SetPowerCommand,
    SetBrightnessCommand,
    slugify,
)

__all__ = [
    "MQTTClient",
    "MQTTCommandRouter",
    "MQTTStateUpdater",
    "HomeAssistantDiscovery",
    "CommandProcessor",
    "DeviceCommand",
    "SetPowerCommand",
    "SetBrightnessCommand",
    "slugify",
]