"""
Cync device classes and TCP communication handlers.

This package provides the core device abstractions for Cync smart devices,
including base device state management, command execution, group coordination,
and TCP packet handling for local device communication.
"""

import asyncio

from cync_controller.const import CYNC_RAW, CYNC_TCP_WHITELIST
from cync_controller.structs import DEVICE_STRUCTS, ControlMessageCallback
from cync_controller.utils import parse_unbound_firmware_version

from .base_device import CyncDevice
from .group import CyncGroup
from .shared import g
from .tcp_device import CyncTCPDevice

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
    "parse_unbound_firmware_version",
]
