import asyncio
from typing import Optional

from cync_controller.logging_abstraction import get_logger
from cync_controller.structs import GlobalObject

logger = get_logger(__name__)
g = GlobalObject()


class TCPConnectionManager:
    """
    Manages TCP connections to Cync bridge devices.
    Handles connection pooling, health checks, and failover.
    """

    def __init__(self):
        self.connections: dict[str, object] = {}
        self.health_check_interval: float = 30.0
        self.health_check_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def add_connection(self, address: str, port: int = 443, **kwargs) -> object:
        """
        Add a new TCP connection to the manager.

        Args:
            address: Bridge device IP address
            port: Bridge device port
            **kwargs: Additional arguments for CyncTCPDevice

        Returns:
            object: The created connection object
        """
        lp = "TCPConnectionManager:add_connection:"
        async with self._lock:
            if address in self.connections:
                logger.warning("%s Connection to %s already exists", lp, address)
                return self.connections[address]

            from cync_controller.devices.tcp_device import CyncTCPDevice

            connection = CyncTCPDevice(address, port, **kwargs)
            self.connections[address] = connection

            # Start health check if this is the first connection
            if len(self.connections) == 1 and not self.health_check_task:
                self.health_check_task = asyncio.create_task(self._health_check_loop())

            logger.info("%s Added connection to %s:%s", lp, address, port)
            return connection

    async def remove_connection(self, address: str):
        """
        Remove a TCP connection from the manager.

        Args:
            address: Bridge device IP address
        """
        lp = "TCPConnectionManager:remove_connection:"
        async with self._lock:
            if address not in self.connections:
                logger.warning("%s Connection to %s not found", lp, address)
                return

            connection = self.connections.pop(address)
            await connection.disconnect()

            # Stop health check if no connections remain
            if not self.connections and self.health_check_task:
                self.health_check_task.cancel()
                try:
                    await self.health_check_task
                except asyncio.CancelledError:
                    pass
                self.health_check_task = None

            logger.info("%s Removed connection to %s", lp, address)

    async def get_connection(self, address: str) -> object | None:
        """
        Get a TCP connection by address.

        Args:
            address: Bridge device IP address

        Returns:
            object or None if not found
        """
        return self.connections.get(address)

    async def get_any_connection(self) -> object | None:
        """
        Get any available TCP connection.

        Returns:
            object or None if no connections available
        """
        for connection in self.connections.values():
            if connection.connected and connection.ready_to_control:
                return connection
        return None

    async def connect_all(self) -> int:
        """
        Connect to all managed TCP devices.

        Returns:
            int: Number of successful connections
        """
        lp = "TCPConnectionManager:connect_all:"
        logger.info("%s Connecting to %s devices", lp, len(self.connections))

        connected_count = 0
        for address, connection in self.connections.items():
            try:
                if await connection.connect():
                    connected_count += 1
                    logger.info("%s Connected to %s", lp, address)
                else:
                    logger.error("%s Failed to connect to %s", lp, address)
            except Exception as e:
                logger.error("%s Error connecting to %s: %s", lp, address, e)

        logger.info("%s Connected to %s/%s devices", lp, connected_count, len(self.connections))
        return connected_count

    async def disconnect_all(self):
        """Disconnect from all managed TCP devices."""
        lp = "TCPConnectionManager:disconnect_all:"
        logger.info("%s Disconnecting from %s devices", lp, len(self.connections))

        for address, connection in self.connections.items():
            try:
                await connection.disconnect()
                logger.info("%s Disconnected from %s", lp, address)
            except Exception as e:
                logger.error("%s Error disconnecting from %s: %s", lp, address, e)

        # Stop health check
        if self.health_check_task:
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass
            self.health_check_task = None

    async def _health_check_loop(self):
        """Background task to periodically check connection health."""
        lp = "TCPConnectionManager:_health_check_loop:"
        logger.info("%s Starting health check loop", lp)

        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._check_connection_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("%s Health check error: %s", lp, e)

        logger.info("%s Health check loop ended", lp)

    async def _check_connection_health(self):
        """Check the health of all managed connections."""
        lp = "TCPConnectionManager:_check_connection_health:"
        logger.debug("%s Checking connection health", lp)

        for address, connection in self.connections.items():
            try:
                if not connection.connected:
                    logger.warning("%s Connection to %s is not connected", lp, address)
                    await connection.reconnect()
                elif not connection.ready_to_control:
                    logger.warning("%s Connection to %s is not ready to control", lp, address)
                else:
                    logger.debug("%s Connection to %s is healthy", lp, address)
            except Exception as e:
                logger.error("%s Error checking health of %s: %s", lp, address, e)

    def get_connection_stats(self) -> dict:
        """
        Get statistics about managed connections.

        Returns:
            dict: Connection statistics
        """
        total_connections = len(self.connections)
        connected_count = sum(1 for conn in self.connections.values() if conn.connected)
        ready_count = sum(1 for conn in self.connections.values() if conn.ready_to_control)

        return {
            "total": total_connections,
            "connected": connected_count,
            "ready": ready_count,
            "addresses": list(self.connections.keys()),
        }

    async def cleanup(self):
        """Cleanup all resources and stop background tasks."""
        lp = "TCPConnectionManager:cleanup:"
        logger.info("%s Cleaning up", lp)

        await self.disconnect_all()
        self.connections.clear()

        if self.health_check_task:
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass
            self.health_check_task = None

        logger.info("%s Cleanup complete", lp)


# Global connection manager instance
connection_manager = TCPConnectionManager()