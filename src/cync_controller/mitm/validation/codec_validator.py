"""Phase 1a codec validator plugin.

This plugin observes packet events from the MITM proxy and validates them
using Phase 1a codec components (CyncProtocol and PacketFramer).
"""

import logging

from cync_controller.mitm.interfaces.packet_observer import PacketDirection
from cync_controller.protocol.cync_protocol import CyncProtocol
from cync_controller.protocol.exceptions import PacketDecodeError, PacketFramingError
from cync_controller.protocol.packet_framer import PacketFramer

logger = logging.getLogger(__name__)


class CodecValidatorPlugin:
    """Phase 1a codec validator plugin.

    Validates packets from MITM proxy using CyncProtocol and PacketFramer.
    Maintains separate framers for each connection to handle TCP streaming.
    """

    def __init__(self) -> None:
        """Initialize plugin with protocol decoder."""
        self.protocol = CyncProtocol()
        self.framers: dict[int, PacketFramer] = {}
        logger.info("CodecValidatorPlugin initialized")

    def on_packet_received(self, direction: PacketDirection, data: bytes, connection_id: int) -> None:
        """Validate packet with Phase 1a codec.

        Args:
            direction: Direction of packet flow
            data: Raw packet bytes
            connection_id: Connection identifier

        """
        # Initialize framer for this connection if not exists
        if connection_id not in self.framers:
            self.framers[connection_id] = PacketFramer()

        try:
            # Extract complete packets from TCP stream
            packets = self.framers[connection_id].feed(data)

            # Decode and validate each packet
            for packet_bytes in packets:
                decoded = self.protocol.decode_packet(packet_bytes)
                logger.info(
                    "Phase 1a codec validated",
                    extra={
                        "direction": direction.value,
                        "type": f"0x{decoded.packet_type:02x}",
                        "length": decoded.length,
                        "connection_id": connection_id,
                    },
                )
        except (PacketDecodeError, PacketFramingError) as e:
            logger.exception(
                "Phase 1a validation failed: %s",
                extra={
                    "direction": direction.value,
                    "connection_id": connection_id,
                    "error_type": type(e).__name__,
                },
            )

    def on_connection_established(self, connection_id: int) -> None:
        """Handle connection established event.

        Args:
            connection_id: Connection identifier

        """
        self.framers[connection_id] = PacketFramer()
        logger.info("Codec validator ready for connection %d", connection_id)

    def on_connection_closed(self, connection_id: int) -> None:
        """Handle connection closed event.

        Args:
            connection_id: Connection identifier

        """
        logger.info("Connection closed: %d", connection_id)
        # Clean up framers for this connection
        self.framers.pop(connection_id, None)
