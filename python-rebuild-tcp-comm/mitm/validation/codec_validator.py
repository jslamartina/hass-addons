"""Phase 1a codec validator plugin.

This plugin observes packet events from the MITM proxy and validates them
using Phase 1a codec components (to be implemented in later steps).

For now, this is a stub that logs packet events without actual validation.
"""

import logging
from typing import Any

try:
    from mitm.interfaces.packet_observer import PacketDirection
except ModuleNotFoundError:  # pragma: no cover
    # For direct execution as script (when mitm module not in path)
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from interfaces.packet_observer import PacketDirection  # type: ignore[import-not-found, no-redef]

logger = logging.getLogger(__name__)


class CodecValidatorPlugin:
    """Phase 1a codec validator plugin.

    Will wrap CyncProtocol and PacketFramer once they're implemented.
    For now, just logs packet events.
    """

    def __init__(self) -> None:
        """Initialize plugin stub."""
        self.framers: dict[int, Any] = {}  # Will use PacketFramer in future
        logger.info("CodecValidatorPlugin initialized (stub)")

    def on_packet_received(
        self, direction: PacketDirection, data: bytes, connection_id: int
    ) -> None:
        """Validate packet with Phase 1a codec.

        Args:
            direction: Direction of packet flow
            data: Raw packet bytes
            connection_id: Connection identifier
        """
        logger.info(f"Packet received: {direction.value}, {len(data)} bytes, conn {connection_id}")
        # TODO (Phase 1a Steps 1-6): Add actual codec validation here
        # - Use PacketFramer to extract packets from stream
        # - Use CyncProtocol to decode packet structure
        # - Validate checksum and packet integrity
        # - Log validation results

    def on_connection_established(self, connection_id: int) -> None:
        """Called when connection established.

        Args:
            connection_id: Connection identifier
        """
        logger.info(f"Connection established: {connection_id}")
        # TODO (Phase 1a): Initialize PacketFramer for this connection

    def on_connection_closed(self, connection_id: int) -> None:
        """Called when connection closed.

        Args:
            connection_id: Connection identifier
        """
        logger.info(f"Connection closed: {connection_id}")
        # Clean up framers for this connection
        self.framers.pop(connection_id, None)
