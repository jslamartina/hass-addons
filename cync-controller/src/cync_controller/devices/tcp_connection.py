"""TCP connection management utilities for CyncTCPDevice."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from cync_controller.logging_abstraction import get_logger

if TYPE_CHECKING:
    from cync_controller.devices.tcp_device import CyncTCPDevice

logger = get_logger(__name__)


class TCPConnectionManager:
    """Manages TCP connection lifecycle and health monitoring."""

    def __init__(self, tcp_device: CyncTCPDevice) -> None:
        """Initialize the manager for a specific TCP device instance."""
        self.tcp_device: CyncTCPDevice = tcp_device
        self.connection_start_time: float = time.time()
        self.last_heartbeat: float = time.time()
        self.heartbeat_interval: float = 30.0  # seconds
        self.connection_timeout: float = 300.0  # 5 minutes

    async def monitor_connection_health(self):
        """Monitor connection health and handle timeouts."""
        while not self.tcp_device.closing:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                current_time = time.time()

                # Check if connection has been idle too long
                if current_time - self.last_heartbeat > self.connection_timeout:
                    logger.warning(
                        "Connection timeout for %s - no activity for %ss",
                        self.tcp_device.address,
                        self.connection_timeout,
                    )
                    await self.tcp_device.close()
                    break

                # Update heartbeat if we've received data recently
                last_data: float = getattr(self.tcp_device, "last_data_received", 0.0)
                if last_data and current_time - last_data < self.heartbeat_interval:
                    self.last_heartbeat = current_time

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in connection health monitoring")

    def update_heartbeat(self):
        """Update the last heartbeat timestamp."""
        self.last_heartbeat = time.time()

    def get_connection_stats(self) -> dict[str, float | bool]:
        """Get connection statistics."""
        uptime = time.time() - self.connection_start_time
        result: dict[str, float | bool] = {
            "uptime_seconds": uptime,
            "last_heartbeat": self.last_heartbeat,
            "is_healthy": time.time() - self.last_heartbeat < self.connection_timeout,
        }
        return result
