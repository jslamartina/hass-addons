#!/usr/bin/env python3
"""
Mock Cync Device for Integration Testing

This script simulates a Cync smart device for testing purposes.
It connects to the Cync Controller add-on via TCP and responds to commands.
"""

import asyncio
import logging
import os
import signal
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mock_cync_device")


class MockCyncDevice:
    """
    Mock Cync device that simulates TCP protocol interactions.

    This device:
    - Connects to the Cync Controller server
    - Responds to control commands (0x73 packets)
    - Sends ACK responses
    - Simulates device state changes
    """

    def __init__(
        self,
        device_id: int,
        server_host: str,
        server_port: int,
        device_name: str = "Mock Device",
        device_room: str = "Test Room",
    ):
        self.device_id = device_id
        self.server_host = server_host
        self.server_port = server_port
        self.device_name = device_name
        self.device_room = device_room
        self.connected = False
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.running = True

        # Device state
        self.power_on = False
        self.brightness = 0
        self.color_temp = 0

    async def connect(self) -> bool:
        """Connect to the Cync Controller server."""
        try:
            logger.info(
                f"Connecting to {self.server_host}:{self.server_port} as device {self.device_id:04x} ({self.device_name})"
            )
            self.reader, self.writer = await asyncio.open_connection(self.server_host, self.server_port)
            self.connected = True
            logger.info(f"✅ Connected as device {self.device_id:04x}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False

    async def disconnect(self):
        """Disconnect from server."""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")
        self.connected = False
        logger.info(f"Disconnected device {self.device_id:04x}")

    async def send_packet(self, packet: bytes):
        """Send packet to server."""
        if not self.connected:
            raise RuntimeError("Not connected")
        try:
            self.writer.write(packet)
            await self.writer.drain()
            logger.debug(f"Sent packet: {' '.join(f'{b:02x}' for b in packet)}")
        except Exception as e:
            logger.error(f"Failed to send packet: {e}")
            raise

    async def receive_packet(self, timeout: float = 10.0) -> bytes | None:
        """Receive packet from server with timeout."""
        if not self.connected:
            raise RuntimeError("Not connected")

        try:
            data = await asyncio.wait_for(self.reader.read(4096), timeout=timeout)
            if data:
                logger.debug(f"Received packet: {' '.join(f'{b:02x}' for b in data)}")
            return data
        except TimeoutError:
            logger.debug(f"No packet received within {timeout}s")
            return None
        except Exception as e:
            logger.error(f"Error receiving packet: {e}")
            return None

    def create_ack_packet(self, msg_id: int = 0) -> bytes:
        """
        Create an ACK packet (0x73 response).

        Basic structure:
        - Header: 0x73
        - Padding: 00 00 00
        - Length: calculated based on payload
        - Device ID: 2 bytes (little endian)
        - Payload data
        - Checksum: 2 bytes (simplified for testing)
        """
        # Simplified ACK packet structure
        packet = bytearray()
        packet.append(0x73)  # Control packet header
        packet.extend([0x00, 0x00, 0x00])  # Padding
        packet.extend([0x00, 0x1E])  # Length (30 bytes) - simplified
        packet.extend(self.device_id.to_bytes(2, "little"))  # Device ID

        # ACK payload (simplified)
        packet.extend([0x01])  # ACK flag
        packet.extend([msg_id & 0xFF])  # Message ID
        packet.extend([0x00] * 18)  # Padding

        # Checksum (simplified - just use 0xABCD for testing)
        packet.extend([0xAB, 0xCD])

        return bytes(packet)

    def create_state_broadcast(self) -> bytes:
        """
        Create a state broadcast packet (0x43).

        This simulates the device broadcasting its current state.
        """
        packet = bytearray()
        packet.append(0x43)  # Broadcast packet header
        packet.extend([0x00, 0x00, 0x00])  # Padding
        packet.extend([0x00, 0x1A])  # Length (26 bytes)
        packet.extend(self.device_id.to_bytes(2, "little"))  # Device ID

        # State data
        packet.append(0x01 if self.power_on else 0x00)  # Power state
        packet.append(self.brightness)  # Brightness (0-100)
        packet.extend([0x00, 0x00])  # Color temp
        packet.extend([0xFF, 0xFF])  # Padding
        packet.extend([0x00] * 10)  # More padding

        # Checksum
        packet.extend([0xAB, 0xCD])

        return bytes(packet)

    def parse_control_command(self, packet: bytes) -> dict | None:
        """
        Parse a control command packet (0x73).

        Returns dict with command info or None if not a control packet.
        """
        if not packet or len(packet) < 10:
            return None

        if packet[0] != 0x73:
            return None

        # Extract basic info
        result = {
            "packet_type": "0x73",
            "length": packet[4] if len(packet) > 4 else 0,
            "command": "UNKNOWN",
        }

        # Try to parse command type
        # In real Cync protocol, commands have specific byte patterns
        # For testing, we'll use simplified detection
        if len(packet) > 15:
            # Check for power command
            if packet[12] == 0x01:
                result["command"] = "POWER_ON"
                self.power_on = True
            elif packet[12] == 0x00:
                result["command"] = "POWER_OFF"
                self.power_on = False

            # Check for brightness command
            if len(packet) > 16 and packet[16] > 0:
                result["command"] = "SET_BRIGHTNESS"
                self.brightness = packet[16]

        return result

    async def handle_incoming_commands(self):
        """Continuously listen for and respond to commands."""
        logger.info(f"Listening for commands on device {self.device_id:04x}...")

        while self.running and self.connected:
            try:
                packet = await self.receive_packet(timeout=5.0)
                if not packet:
                    continue

                # Parse command
                cmd = self.parse_control_command(packet)
                if cmd:
                    logger.info(f"📥 Received command: {cmd['command']}")

                    # Send ACK response
                    ack_packet = self.create_ack_packet()
                    await self.send_packet(ack_packet)
                    logger.info(f"📤 Sent ACK for command: {cmd['command']}")

                    # Send state broadcast
                    await asyncio.sleep(0.1)  # Small delay
                    state_packet = self.create_state_broadcast()
                    await self.send_packet(state_packet)
                    logger.info(f"📡 Broadcast state: power={self.power_on}, brightness={self.brightness}")

            except Exception as e:
                logger.error(f"Error handling commands: {e}")
                break

    async def run(self):
        """Main run loop."""
        logger.info(f"🚀 Starting mock device {self.device_id:04x}")

        # Connect to server with retries
        max_retries = 10
        retry_delay = 2

        for attempt in range(max_retries):
            if await self.connect():
                break
            logger.info(f"Connection attempt {attempt + 1}/{max_retries} failed, retrying in {retry_delay}s...")
            await asyncio.sleep(retry_delay)
        else:
            logger.error(f"Failed to connect after {max_retries} attempts")
            return

        try:
            # Send initial state broadcast
            await asyncio.sleep(1)
            initial_state = self.create_state_broadcast()
            await self.send_packet(initial_state)
            logger.info("📡 Sent initial state broadcast")

            # Handle incoming commands
            await self.handle_incoming_commands()

        finally:
            await self.disconnect()

    def stop(self):
        """Signal the device to stop."""
        logger.info("🛑 Stopping mock device...")
        self.running = False


async def main():
    """Main entry point."""
    # Get configuration from environment variables
    server_host = os.environ.get("CYNC_SERVER_HOST", "cync-controller")
    server_port = int(os.environ.get("CYNC_SERVER_PORT", "23779"))
    device_id = int(os.environ.get("DEVICE_ID", "0x1234"), 16)
    device_name = os.environ.get("DEVICE_NAME", "Test Light 1")
    device_room = os.environ.get("DEVICE_ROOM", "Living Room")

    # Create mock device
    device = MockCyncDevice(
        device_id=device_id,
        server_host=server_host,
        server_port=server_port,
        device_name=device_name,
        device_room=device_room,
    )

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("Received shutdown signal")
        device.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    # Run device
    try:
        await device.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Mock device shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
