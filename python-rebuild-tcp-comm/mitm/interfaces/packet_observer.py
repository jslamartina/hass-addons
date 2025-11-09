"""Observer interface for MITM packet capture.

This module defines the Protocol interface for plugins that observe packet events
from the MITM proxy. Uses structural subtyping (Protocol) enforced by mypy at
type-check time - no inheritance required.
"""

from enum import Enum
from typing import Protocol


class PacketDirection(Enum):
    """Direction of packet flow."""

    DEVICE_TO_CLOUD = "device_to_cloud"
    CLOUD_TO_DEVICE = "cloud_to_device"


class PacketObserver(Protocol):
    """Type protocol for MITM packet observers.

    Enforced by mypy at type-check time. No inheritance required.
    Plugins implement these methods to receive packet notifications.
    """

    def on_packet_received(
        self, direction: PacketDirection, data: bytes, connection_id: int
    ) -> None:
        """Called when packet received.

        Args:
            direction: Direction of packet flow
            data: Raw packet bytes
            connection_id: Connection identifier
        """
        ...

    def on_connection_established(self, connection_id: int) -> None:
        """Called when connection established.

        Args:
            connection_id: Connection identifier
        """
        ...

    def on_connection_closed(self, connection_id: int) -> None:
        """Called when connection closed.

        Args:
            connection_id: Connection identifier
        """
        ...
