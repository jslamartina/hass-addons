"""
Cync Controller Devices Module

This module provides backward compatibility by re-exporting all device classes
from the new modular structure. The actual implementations are now in the
cync_controller.devices package.
"""

# Re-export all classes from the devices package for backward compatibility
from cync_controller.devices import (
    CyncDevice,
    CyncGroup,
    CyncTCPDevice,
    DeviceCommandsMixin,
    TCPConnectionManager,
    connection_manager,
    TCPPacketHandler,
    packet_handler,
)

__all__ = [
    "CyncDevice",
    "CyncGroup",
    "CyncTCPDevice",
    "DeviceCommandsMixin",
    "TCPConnectionManager",
    "connection_manager",
    "TCPPacketHandler",
    "packet_handler",
]