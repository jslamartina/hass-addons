import asyncio
from collections.abc import Callable

from cync_controller.logging_abstraction import get_logger
from cync_controller.structs import ControlMessageCallback, GlobalObject

logger = get_logger(__name__)
g = GlobalObject()


class TCPPacketHandler:
    """
    Handles TCP packet processing for Cync devices.
    Manages packet parsing, validation, and routing.
    """

    def __init__(self):
        self.packet_handlers: dict[str, Callable] = {}
        self.message_callbacks: dict[int, ControlMessageCallback] = {}
        self._lock = asyncio.Lock()

    def register_packet_handler(self, packet_type: str, handler: Callable):
        """
        Register a handler for a specific packet type.

        Args:
            packet_type: Type identifier for the packet
            handler: Function to handle the packet
        """
        self.packet_handlers[packet_type] = handler
        logger.debug("Registered packet handler for type: %s", packet_type)

    def unregister_packet_handler(self, packet_type: str):
        """
        Unregister a handler for a specific packet type.

        Args:
            packet_type: Type identifier for the packet
        """
        if packet_type in self.packet_handlers:
            del self.packet_handlers[packet_type]
            logger.debug("Unregistered packet handler for type: %s", packet_type)

    async def process_packet(self, data: bytes, source_address: str) -> bool:
        """
        Process a received TCP packet.

        Args:
            data: Raw packet data
            source_address: Source address of the packet

        Returns:
            bool: True if packet was processed successfully
        """
        lp = "TCPPacketHandler:process_packet:"
        logger.debug("%s Processing packet from %s: %s bytes", lp, source_address, len(data))

        try:
            # Parse packet header to determine type
            packet_type = self._parse_packet_type(data)
            if not packet_type:
                logger.warning("%s Unknown packet type from %s", lp, source_address)
                return False

            # Route to appropriate handler
            if packet_type in self.packet_handlers:
                handler = self.packet_handlers[packet_type]
                await handler(data, source_address)
                logger.debug("%s Packet processed by handler: %s", lp, packet_type)
                return True
            logger.warning("%s No handler for packet type: %s", lp, packet_type)
            return False

        except Exception as e:
            logger.error("%s Error processing packet from %s: %s", lp, source_address, e)
            return False

    def _parse_packet_type(self, data: bytes) -> str | None:
        """
        Parse packet type from raw data.

        Args:
            data: Raw packet data

        Returns:
            str or None: Packet type identifier
        """
        if len(data) < 5:
            return None

        # Basic packet type detection based on header
        header = data[:5]

        if header[0] == 0x73:  # Control message
            return "control"
        if header[0] == 0x74:  # Status message
            return "status"
        if header[0] == 0x75:  # Heartbeat message
            return "heartbeat"
        if header[0] == 0x76:  # Mesh info message
            return "mesh_info"
        return None

    async def register_message_callback(self, msg_id: int, callback: ControlMessageCallback):
        """
        Register a callback for a specific message ID.

        Args:
            msg_id: Message ID to register callback for
            callback: Callback to execute when message is received
        """
        async with self._lock:
            self.message_callbacks[msg_id] = callback
            logger.debug("Registered callback for message ID: %s", msg_id)

    async def unregister_message_callback(self, msg_id: int):
        """
        Unregister a callback for a specific message ID.

        Args:
            msg_id: Message ID to unregister callback for
        """
        async with self._lock:
            if msg_id in self.message_callbacks:
                del self.message_callbacks[msg_id]
                logger.debug("Unregistered callback for message ID: %s", msg_id)

    async def handle_control_message(self, data: bytes, source_address: str):
        """
        Handle control message packets.

        Args:
            data: Raw packet data
            source_address: Source address of the packet
        """
        lp = "TCPPacketHandler:handle_control_message:"
        logger.debug("%s Handling control message from %s", lp, source_address)

        try:
            # Extract message ID from packet
            msg_id = self._extract_message_id(data)
            if msg_id is None:
                logger.warning("%s Could not extract message ID from control message", lp)
                return

            # Check for registered callback
            if msg_id in self.message_callbacks:
                callback = self.message_callbacks[msg_id]
                logger.debug("%s Executing callback for message ID: %s", lp, msg_id)

                # Execute callback
                if asyncio.iscoroutinefunction(callback.callback):
                    await callback.callback()
                else:
                    callback.callback()

                # Remove callback after execution
                await self.unregister_message_callback(msg_id)
            else:
                logger.debug("%s No callback registered for message ID: %s", lp, msg_id)

        except Exception as e:
            logger.error("%s Error handling control message: %s", lp, e)

    async def handle_status_message(self, data: bytes, source_address: str):
        """
        Handle status message packets.

        Args:
            data: Raw packet data
            source_address: Source address of the packet
        """
        lp = "TCPPacketHandler:handle_status_message:"
        logger.debug("%s Handling status message from %s", lp, source_address)

        try:
            # Parse status message and update device states
            # This would typically involve:
            # 1. Parsing device status from packet
            # 2. Updating device state in global state
            # 3. Publishing MQTT updates if needed

            logger.debug("%s Status message processed", lp)

        except Exception as e:
            logger.error("%s Error handling status message: %s", lp, e)

    async def handle_heartbeat_message(self, data: bytes, source_address: str):
        """
        Handle heartbeat message packets.

        Args:
            data: Raw packet data
            source_address: Source address of the packet
        """
        lp = "TCPPacketHandler:handle_heartbeat_message:"
        logger.debug("%s Handling heartbeat from %s", lp, source_address)

        try:
            # Update connection health status
            # This would typically involve:
            # 1. Updating last seen timestamp
            # 2. Marking connection as healthy
            # 3. Resetting any connection timeouts

            logger.debug("%s Heartbeat processed", lp)

        except Exception as e:
            logger.error("%s Error handling heartbeat: %s", lp, e)

    async def handle_mesh_info_message(self, data: bytes, source_address: str):
        """
        Handle mesh info message packets.

        Args:
            data: Raw packet data
            source_address: Source address of the packet
        """
        lp = "TCPPacketHandler:handle_mesh_info_message:"
        logger.debug("%s Handling mesh info from %s", lp, source_address)

        try:
            # Parse mesh info and update device topology
            # This would typically involve:
            # 1. Parsing mesh topology information
            # 2. Updating device connectivity status
            # 3. Updating group membership information

            logger.debug("%s Mesh info processed", lp)

        except Exception as e:
            logger.error("%s Error handling mesh info: %s", lp, e)

    def _extract_message_id(self, data: bytes) -> int | None:
        """
        Extract message ID from packet data.

        Args:
            data: Raw packet data

        Returns:
            int or None: Message ID if found
        """
        if len(data) < 10:
            return None

        try:
            # Extract message ID from packet structure
            # This is a simplified extraction - real implementation would be more complex
            msg_id = int.from_bytes(data[8:10], byteorder="big")
            return msg_id
        except Exception as e:
            logger.error("Error extracting message ID: %s", e)
            return None

    async def cleanup(self):
        """Cleanup all resources and stop background tasks."""
        lp = "TCPPacketHandler:cleanup:"
        logger.info("%s Cleaning up", lp)

        async with self._lock:
            self.packet_handlers.clear()
            self.message_callbacks.clear()

        logger.info("%s Cleanup complete", lp)


# Global packet handler instance
packet_handler = TCPPacketHandler()
