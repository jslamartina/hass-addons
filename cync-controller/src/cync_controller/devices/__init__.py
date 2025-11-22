"""
Cync device classes and TCP communication handlers.

This package provides the core device abstractions for Cync smart devices,
including base device state management, command execution, group coordination,
and TCP packet handling for local device communication.
"""

import asyncio

from cync_controller.const import CYNC_RAW, CYNC_TCP_WHITELIST
from cync_controller.structs import DEVICE_STRUCTS, ControlMessageCallback

from .shared import g


# Lazy imports to avoid circular dependencies
# These will be imported on first access
def __getattr__(name: str):
    """Lazy import for device classes to avoid circular dependencies."""
    if name == "CyncDevice":
        from .base_device import CyncDevice

        return CyncDevice
    if name == "CyncGroup":
        from .group import CyncGroup

        return CyncGroup
    if name == "CyncTCPDevice":
        from .tcp_device import CyncTCPDevice

        return CyncTCPDevice
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = [
    "CYNC_RAW",
    "CYNC_TCP_WHITELIST",
    "DEVICE_STRUCTS",
    "ControlMessageCallback",
    "CyncDevice",
    "CyncGroup",
    "CyncTCPDevice",
    "asyncio",
    "g",
]
