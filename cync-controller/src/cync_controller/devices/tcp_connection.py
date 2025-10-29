"""
TCP connection management utilities for CyncTCPDevice.
"""

import asyncio
import time

from cync_controller.logging_abstraction import get_logger

logger = get_logger(__name__)


class TCPConnectionManager:
    """Manages TCP connection lifecycle and health monitoring."""

    def __init__(self, tcp_device):
        self.tcp_device = tcp_device
        self.connection_start_time = time.time()
        self.last_heartbeat = time.time()
        self.heartbeat_interval = 30.0  # seconds
        self.connection_timeout = 300.0  # 5 minutes

    async def monitor_connection_health(self):
        """Monitor connection health and handle timeouts."""
        while not self.tcp_device.closing:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                current_time = time.time()

                # Check if connection has been idle too long
                if current_time - self.last_heartbeat > self.connection_timeout:
                    logger.warning(
                        f"Connection timeout for {self.tcp_device.address} - "
                        f"no activity for {self.connection_timeout}s"
                    )
                    await self.tcp_device.close()
                    break

                # Update heartbeat if we've received data recently
                if hasattr(self.tcp_device, "last_data_received"):
                    if current_time - self.tcp_device.last_data_received < self.heartbeat_interval:
                        self.last_heartbeat = current_time

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in connection health monitoring: {e}")

    def update_heartbeat(self):
        """Update the last heartbeat timestamp."""
        self.last_heartbeat = time.time()

    def get_connection_stats(self):
        """Get connection statistics."""
        uptime = time.time() - self.connection_start_time
        return {
            "uptime_seconds": uptime,
            "last_heartbeat": self.last_heartbeat,
            "is_healthy": time.time() - self.last_heartbeat < self.connection_timeout
        }
