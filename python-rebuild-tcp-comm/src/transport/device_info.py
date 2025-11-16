"""Device information dataclass for parsed device structs.

This module provides the DeviceInfo dataclass for representing parsed DEVICE_TYPE_LENGTH_BYTES-byte
device structures from 0x83 (status broadcast) and 0x43 (device info) packets.

The DEVICE_TYPE_LENGTH_BYTES-byte device struct format is copied and adapted from legacy code
(cync-controller/src/cync_controller/structs.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Protocol constants
DEVICE_TYPE_LENGTH_BYTES = 24
DEVICE_ID_LENGTH_BYTES = 4
UUID_STRING_MIN_LENGTH = 36
DEVICE_TYPE_BRIDGE = 0x01
DEVICE_TYPE_BULB = 0x02
DEVICE_TYPE_SWITCH = 0x03


@dataclass
class DeviceInfo:
    """Parsed DEVICE_TYPE_LENGTH_BYTES-byte device structure from mesh info response.

    This dataclass represents a single device's information extracted from
    0x83 status broadcast or 0x43 device info packets.

    Struct Format (DEVICE_TYPE_LENGTH_BYTES bytes total):
        - Bytes 0-3: device_id (4 bytes) - Unique device identifier
        - Bytes 4-7: capabilities (4 bytes) - Device type and feature flags
        - Bytes 8-11: state data (4 bytes) - On/off, brightness, color, etc.
        - Bytes 12-23: additional fields (12 bytes) - Extended device info

    Attributes:
        device_id: 4-byte unique device identifier
        device_type: Device type extracted from capabilities (bridge, bulb, switch, etc.)
        capabilities: Capabilities bitmask (device type, features, supported operations)
        state: Parsed state dictionary (on/off, brightness, color, etc.)
        raw_bytes: Original DEVICE_TYPE_LENGTH_BYTES-byte struct for debugging and analysis
        correlation_id: UUID v7 for tracking this device info through logs/metrics

    Example:
        >>> device_info = DeviceInfo(
        ...     device_id=bytes([0x39, 0x87, 0xC8, 0x57]),
        ...     device_type=0x01,  # Bridge device
        ...     capabilities=0x01000000,
        ...     state={'on': True, 'brightness': 255},
        ...     raw_bytes=b'...',  # DEVICE_TYPE_LENGTH_BYTES bytes
        ...     correlation_id='01936d45-3c4e-7890-abcd-ef1234567890'
        ... )

    Legacy Reference:
        Adapted from cync-controller/src/cync_controller/structs.py
        Device struct definitions and parsing logic

    """

    device_id: bytes  # 4 bytes - unique device identifier
    device_type: int  # Device type (bridge=0x01, bulb=0x02, switch=0x03, etc.)
    capabilities: int  # Capabilities bitmask (features, supported operations)
    state: dict[str, Any]  # Parsed state (on/off, brightness, color, etc.)
    raw_bytes: bytes  # Original DEVICE_TYPE_LENGTH_BYTES-byte struct for debugging
    correlation_id: str  # UUID v7 for tracking

    def __post_init__(self) -> None:
        """Validate device info fields after initialization."""
        # Validate device_id length
        if len(self.device_id) != DEVICE_ID_LENGTH_BYTES:
            error_msg = f"device_id must be 4 bytes, got {len(self.device_id)}"
            raise ValueError(error_msg)

        # Validate raw_bytes length
        if len(self.raw_bytes) != DEVICE_TYPE_LENGTH_BYTES:
            error_msg = (
                f"raw_bytes must be DEVICE_TYPE_LENGTH_BYTES bytes, got {len(self.raw_bytes)}"
            )
            raise ValueError(error_msg)

        # Validate correlation_id format (UUID v7 string)
        # Note: isinstance check required for runtime safety - type annotations are not
        # enforced at runtime, and __repr__ uses slicing ([:8]) which requires str type.
        # An object with __len__ but no slicing support would pass length check but crash later.
        if (
            not isinstance(self.correlation_id, str)  # type: ignore[redundant-expr]
            or len(self.correlation_id) < UUID_STRING_MIN_LENGTH
        ):
            error_msg = f"correlation_id must be UUID string, got {self.correlation_id}"
            raise ValueError(error_msg)

    def device_id_hex(self) -> str:
        """Return device_id as hex string for display."""
        return self.device_id.hex()

    def is_bridge(self) -> bool:
        """Check if this device is a bridge/hub device."""
        return self.device_type == DEVICE_TYPE_BRIDGE

    def is_bulb(self) -> bool:
        """Check if this device is a light bulb."""
        return self.device_type == DEVICE_TYPE_BULB

    def is_switch(self) -> bool:
        """Check if this device is a switch."""
        return self.device_type == DEVICE_TYPE_SWITCH

    def __repr__(self) -> str:
        """String representation for logging and debugging."""
        return (
            f"DeviceInfo(device_id={self.device_id_hex()}, "
            f"type={self.device_type}, "
            f"state={self.state}, "
            f"correlation_id={self.correlation_id[:8]}...)"
        )


class MeshInfoRequestError(Exception):
    """Exception raised when mesh info request fails.

    Attributes:
        reason: Error reason code (not_primary, send_failed, timeout)
        message: Human-readable error message

    """

    def __init__(self, reason: str, message: str):
        self.reason = reason
        self.message = message
        super().__init__(f"{reason}: {message}")


class DeviceInfoRequestError(Exception):
    """Exception raised when device info request fails.

    Attributes:
        reason: Error reason code (send_failed, timeout)
        message: Human-readable error message

    """

    def __init__(self, reason: str, message: str):
        self.reason = reason
        self.message = message
        super().__init__(f"{reason}: {message}")


class DeviceStructParseError(Exception):
    """Exception raised when parsing device struct fails.

    Attributes:
        message: Human-readable error message describing parse failure

    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
