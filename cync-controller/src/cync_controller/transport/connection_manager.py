"""Connection management with state machine, handshake, and packet routing.

This module implements the ConnectionManager class which manages the connection
lifecycle, handshake flow, heartbeat monitoring, and packet routing for Phase 1b.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TypeVar

from cync_controller.metrics import registry
from cync_controller.protocol.cync_protocol import CyncProtocol
from cync_controller.protocol.exceptions import CyncProtocolError, PacketDecodeError
from cync_controller.protocol.packet_framer import PacketFramer
from cync_controller.protocol.packet_types import (
    PACKET_TYPE_DATA_ACK,
    PACKET_TYPE_DATA_CHANNEL,
    PACKET_TYPE_HEARTBEAT_CLOUD,
    PACKET_TYPE_HELLO_ACK,
    PACKET_TYPE_STATUS_ACK,
    PACKET_TYPE_STATUS_BROADCAST,
    CyncPacket,
)
from cync_controller.transport.exceptions import CyncConnectionError, HandshakeError
from cync_controller.transport.retry_policy import RetryPolicy, TimeoutConfig
from cync_controller.transport.socket_abstraction import TCPConnection
from cync_controller.transport.types import PendingMessage

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Lock hold time thresholds (seconds)
_LOCK_HOLD_CRITICAL_THRESHOLD = 0.1  # 100ms - deadlock risk
_LOCK_HOLD_WARNING_THRESHOLD = 0.01  # 10ms - investigate bottleneck

# Heartbeat configuration
_HEARTBEAT_INTERVAL_SECONDS = 60.0  # Send heartbeat every 60s
_PACKET_RECEIVE_TIMEOUT_SECONDS = 5.0  # Shorter timeout for responsive heartbeat sending


class ConnectionState(Enum):
    """Connection state enumeration."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


class ConnectionManager:
    """Manages connection lifecycle, handshake, heartbeat, and packet routing.

    **Architecture Note**: The handshake flow (connect()) uses raw TCPConnection methods
    (send/recv) to avoid a circular dependency with ReliableTransport. Since
    ReliableTransport.send_reliable() requires an established connection, the handshake
    must complete first using direct TCP operations. Handshake has its own retry logic
    separate from message retries.

    **Thread Safety**: Connection state is protected by `_state_lock` (asyncio.Lock) to
    prevent race conditions between retry loops in send_reliable() and reconnection logic.
    All state transitions (CONNECTING, CONNECTED, RECONNECTING, DISCONNECTED) must be
    performed while holding the lock. State checks in send_reliable() also acquire the
    lock to ensure consistent reads.

    **Performance Monitoring**: Lock hold time is instrumented and monitored with
    three-tier thresholds:
    - **Target**: < 1ms (typical state check + encoding operations)
    - **Warning**: > 10ms (logged as warning, investigate potential bottleneck)
    - **Critical**: > 100ms (indicates deadlock risk, escalate immediately)
    - Metric: `tcp_comm_state_lock_hold_seconds` (histogram records all durations)
    """

    def __init__(
        self,
        connection: TCPConnection,
        protocol: CyncProtocol,
        timeout_config: TimeoutConfig | None = None,
        ack_handler: Callable[[CyncPacket], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize connection manager.

        Args:
            connection: TCP connection abstraction
            protocol: Cync protocol encoder/decoder
            timeout_config: Timeout configuration (defaults to TimeoutConfig() if None)
            ack_handler: Optional callback for ACK packets (called by _packet_router)

        """
        self.conn: TCPConnection = connection
        self.protocol: CyncProtocol = protocol
        self.ack_handler: Callable[[CyncPacket], Awaitable[None]] | None = ack_handler
        self.state: ConnectionState = ConnectionState.DISCONNECTED
        self._state_lock: asyncio.Lock = asyncio.Lock()  # Protect state transitions
        self.packet_router_task: asyncio.Task[None] | None = None
        self.reconnect_task: asyncio.Task[bool | None] | None = None

        # Timeout configuration
        self.timeout_config: TimeoutConfig = timeout_config or TimeoutConfig()
        self.retry_policy: RetryPolicy = RetryPolicy()

        # Credentials for reconnection (set during connect())
        self.endpoint: bytes = b""
        self.auth_code: bytes = b""

        # FIFO queue for non-msg_id ACKs (0x28, 0x88, 0xD8)
        self.pending_requests: deque[tuple[int, PendingMessage]] = deque()

        # Packet router components
        self.framer: PacketFramer = PacketFramer()  # One per connection
        self._data_packet_queue: asyncio.Queue[CyncPacket] = asyncio.Queue()

        # Lock hold time monitoring
        self._lock_hold_warnings: int = 0  # Count of >10ms lock holds

    async def with_state_check(self, operation: str, action: Callable[[], Awaitable[T]]) -> T:
        """Execute action after state check, with automatic lock pattern enforcement.

        Enforces pattern: acquire lock → check state → release lock → execute action.
        Monitors lock hold time and logs warnings if held too long.

        Args:
            operation: Description of operation (for logging)
            action: Async action to execute after state check

        Returns:
            Result of action

        Raises:
            CyncConnectionError: If state is not CONNECTED

        """
        lock_start = time.perf_counter()
        async with self._state_lock:
            if self.state != ConnectionState.CONNECTED:
                error_msg = f"Operation '{operation}' requires CONNECTED state"
                raise CyncConnectionError(
                    error_msg,
                    state=self.state.value,
                )
            # State check complete, lock will be released before action
        lock_duration = time.perf_counter() - lock_start

        # Record lock hold time metric
        registry.record_state_lock_hold(lock_duration)

        # Monitor lock hold time
        if lock_duration > _LOCK_HOLD_CRITICAL_THRESHOLD:
            logger.critical(
                "State lock held for %.3fs during %s (deadlock risk)",
                lock_duration,
                operation,
            )
        elif lock_duration > _LOCK_HOLD_WARNING_THRESHOLD:
            self._lock_hold_warnings += 1
            logger.warning(
                "State lock held for %.3fs during %s (investigate bottleneck)",
                lock_duration,
                operation,
            )

        # Execute action with lock released (prevents deadlock on network I/O)
        return await action()

    async def _process_handshake_success(self, device_id: str) -> None:
        """Process successful handshake ACK.

        Matches ACK to pending request, updates state, and starts packet router.
        """
        logger.debug(
            "→ Processing handshake success",
            extra={"device_id": device_id},
        )
        # Match ACK to pending request (FIFO)
        correlation_id = "unknown"
        if self.pending_requests and self.pending_requests[0][0] == PACKET_TYPE_HELLO_ACK:
            _, matched_pending = self.pending_requests.popleft()
            correlation_id = matched_pending.correlation_id
            matched_pending.ack_event.set()

        async with self._state_lock:
            self.state = ConnectionState.CONNECTED
            registry.record_connection_state(device_id, self.state.value)

        # Start packet router task
        self.packet_router_task = asyncio.create_task(self._packet_router())

        registry.record_handshake(device_id, "success")
        logger.info(
            "Handshake successful",
            extra={"device_id": device_id, "correlation_id": correlation_id},
        )

    async def _attempt_handshake(self, attempt: int, max_retries: int) -> bool:
        """Attempt a single handshake (0x23 → 0x28).

        Returns:
            True if handshake successful, False otherwise

        """
        device_id = self.endpoint.hex()[:10] if self.endpoint else "unknown"
        logger.debug(
            "→ Attempting handshake",
            extra={"device_id": device_id, "attempt": attempt + 1, "max_retries": max_retries},
        )

        # 1. Encode handshake packet (0x23)
        handshake_packet = self.protocol.encode_handshake(self.endpoint, self.auth_code)

        # 2. Create pending request for FIFO matching
        pending = PendingMessage(
            msg_id=b"",  # No msg_id for handshake
            correlation_id=f"handshake-{attempt}",
            sent_at=time.time(),
            ack_event=asyncio.Event(),
            retry_count=attempt,
        )
        self.pending_requests.append((PACKET_TYPE_HELLO_ACK, pending))

        # 3. Send via raw TCP (lock released before network I/O)
        success = await self.conn.send(handshake_packet)
        if not success:
            logger.warning(
                "Handshake send failed",
                extra={"attempt": attempt + 1, "max_retries": max_retries},
            )
            if self.pending_requests:
                _ = self.pending_requests.popleft()  # Remove pending if send failed (FIFO)
            return False

        # 4. Wait for 0x28 ACK with timeout
        try:
            response = await asyncio.wait_for(
                self.conn.recv(),
                timeout=self.timeout_config.handshake_timeout_seconds,
            )

            # Check if response is valid handshake ACK
            is_valid_ack = response and response[0] == PACKET_TYPE_HELLO_ACK
            if not is_valid_ack:
                # Invalid handshake response
                logger.warning(
                    "Invalid handshake response: %s",
                    response[:1].hex() if response else "empty",
                )
                # Clean up pending request if exists
                if self.pending_requests:
                    _ = self.pending_requests.popleft()
                return False

            # Valid handshake ACK received - process success path
            await self._process_handshake_success(device_id)

        except TimeoutError:
            logger.warning(
                "Handshake timeout",
                extra={"attempt": attempt + 1, "max_retries": max_retries},
            )
            if self.pending_requests:
                _ = self.pending_requests.popleft()  # Remove pending on timeout
            return False
        else:
            return True

    def _handle_network_error(
        self,
        error: Exception,
        attempt: int,
        max_retries: int,
        _device_id: str,
    ) -> None:
        """Handle network errors during handshake (retryable).

        Args:
            error: The network error that occurred
            attempt: Current attempt number (0-indexed)
            max_retries: Maximum number of retries
            device_id: Device identifier for logging

        """
        logger.exception(
            "Handshake error on attempt %d/%d",
            attempt + 1,
            max_retries,
            extra={
                "attempt": attempt + 1,
                "max_retries": max_retries,
                "error": str(error),
                "error_type": type(error).__name__,
            },
        )
        if self.pending_requests:
            _ = self.pending_requests.popleft()  # Remove pending on error

    def _handle_handshake_error(
        self,
        error: HandshakeError,
        attempt: int,
        max_retries: int,
        _device_id: str,
    ) -> bool:
        """Handle handshake errors during connection (may be retryable).

        Args:
            error: The handshake error that occurred
            attempt: Current attempt number (0-indexed)
            max_retries: Maximum number of retries
            device_id: Device identifier for logging

        Returns:
            True if error should be re-raised (non-retryable), False otherwise

        """
        # Auth failures are not retryable
        if hasattr(error, "reason") and "auth" in error.reason.lower():
            logger.exception(
                "Handshake auth failure on attempt %d/%d",
                attempt + 1,
                max_retries,
                extra={
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "error": str(error),
                    "error_type": type(error).__name__,
                    "reason": error.reason,
                },
            )
            if self.pending_requests:
                _ = self.pending_requests.popleft()
            return True  # Re-raise auth failures

        # Other protocol errors - retryable
        logger.exception(
            "Handshake protocol error on attempt %d/%d",
            attempt + 1,
            max_retries,
            extra={
                "attempt": attempt + 1,
                "max_retries": max_retries,
                "error": str(error),
                "error_type": type(error).__name__,
                "reason": error.reason if hasattr(error, "reason") else None,
            },
        )
        if self.pending_requests:
            _ = self.pending_requests.popleft()  # Remove pending on error
        return False  # Don't re-raise, allow retry

    def _handle_protocol_error(
        self,
        error: CyncProtocolError,
        attempt: int,
        max_retries: int,
        _device_id: str,
    ) -> None:
        """Handle protocol errors during handshake (retryable).

        Args:
            error: The protocol error that occurred
            attempt: Current attempt number (0-indexed)
            max_retries: Maximum number of retries
            device_id: Device identifier for logging

        """
        logger.exception(
            "Handshake protocol error on attempt %d/%d",
            attempt + 1,
            max_retries,
            extra={
                "attempt": attempt + 1,
                "max_retries": max_retries,
                "error": str(error),
                "error_type": type(error).__name__,
            },
        )
        if self.pending_requests:
            _ = self.pending_requests.popleft()  # Remove pending on error

    def _handle_unexpected_error(
        self,
        error: Exception,
        attempt: int,
        max_retries: int,
        _device_id: str,
    ) -> None:
        """Handle unexpected errors during handshake (non-retryable).

        Args:
            error: The unexpected error that occurred
            attempt: Current attempt number (0-indexed)
            max_retries: Maximum number of retries
            device_id: Device identifier for logging

        """
        logger.exception(
            "Unexpected handshake error on attempt %d/%d",
            attempt + 1,
            max_retries,
            extra={
                "attempt": attempt + 1,
                "max_retries": max_retries,
                "error": str(error),
                "error_type": type(error).__name__,
            },
        )
        if self.pending_requests:
            _ = self.pending_requests.popleft()  # Remove pending on error

    async def _attempt_connection_with_retry(self, device_id: str, max_retries: int) -> bool:
        """Attempt connection with retry logic.

        Args:
            device_id: Device identifier for logging
            max_retries: Maximum number of retries

        Returns:
            True if connection successful, False otherwise

        """
        for attempt in range(max_retries):
            try:
                if await self._attempt_handshake(attempt, max_retries):
                    logger.info(
                        "✓ Connection handshake successful",
                        extra={"endpoint": device_id},
                    )
                    return True
            except (OSError, ConnectionError, TimeoutError) as e:
                # Network errors - always retryable
                self._handle_network_error(e, attempt, max_retries, device_id)
            except HandshakeError as e:
                # Protocol errors - check if retryable
                if self._handle_handshake_error(e, attempt, max_retries, device_id):
                    raise  # Don't retry auth failures
            except CyncProtocolError as e:
                # Other protocol errors - retryable
                self._handle_protocol_error(e, attempt, max_retries, device_id)
            except Exception as e:
                # Unexpected errors - re-raise
                self._handle_unexpected_error(e, attempt, max_retries, device_id)
                raise  # Re-raise unexpected errors to preserve exception context

            # Retry with exponential backoff
            if attempt < max_retries - 1:
                delay = self.retry_policy.get_delay(attempt)
                logger.debug(
                    "Retrying handshake",
                    extra={"delay": delay, "attempt": attempt + 1},
                )
                await asyncio.sleep(delay)

        return False

    async def connect(self, endpoint: bytes, auth_code: bytes) -> bool:
        """Perform handshake using raw TCP (bypass ReliableTransport).

        Uses raw TCPConnection.send() and recv() to avoid circular dependency with
        ReliableTransport. Implements handshake-specific retry logic with exponential backoff.

        Stores endpoint and auth_code for future reconnection attempts.

        Args:
            endpoint: 5-byte endpoint identifier from device authentication
            auth_code: Authentication code for handshake

        Returns:
            True if handshake successful, False otherwise

        """
        # Derive device_id from endpoint for metrics
        device_id = endpoint.hex()[:10] if endpoint else "unknown"
        logger.info(
            "→ Starting connection handshake",
            extra={"endpoint": device_id, "endpoint_hex": endpoint.hex() if endpoint else ""},
        )

        # Store credentials for reconnection
        self.endpoint = endpoint
        self.auth_code = auth_code

        async with self._state_lock:
            self.state = ConnectionState.CONNECTING
            registry.record_connection_state(device_id, self.state.value)

        max_retries = 3
        if await self._attempt_connection_with_retry(device_id, max_retries):
            return True

        async with self._state_lock:
            self.state = ConnectionState.DISCONNECTED
            registry.record_connection_state(device_id, self.state.value)
        registry.record_handshake(device_id, "failed")
        logger.error(
            "✗ Connection handshake failed",
            extra={"endpoint": device_id, "max_retries": max_retries, "attempts": max_retries},
        )
        return False

    def _get_device_id(self) -> str:
        """Derive device_id from endpoint for metrics."""
        return self.endpoint.hex()[:10] if self.endpoint else "unknown"

    async def _call_ack_handler_safe(self, packet: CyncPacket) -> None:
        """Call ack_handler with standardized exception handling.

        This method provides consistent exception handling for all ACK handler
        invocations. Protocol errors and cancellations are re-raised immediately,
        while unexpected errors are logged and re-raised for the caller to handle.

        Args:
            packet: ACK packet to pass to handler

        Raises:
            CyncProtocolError: Protocol-related errors from handler
            asyncio.CancelledError: Task cancellation
            Exception: Any other unexpected errors from handler

        """
        if not self.ack_handler:
            return

        try:
            await self.ack_handler(packet)
        except (CyncProtocolError, asyncio.CancelledError) as e:
            logger.exception(
                "ACK handler error",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            raise  # Re-raise protocol errors and cancellations
        except Exception as e:
            logger.exception(
                "Unexpected ACK handler error",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            raise  # Re-raise so caller can handle it

    async def _handle_heartbeat_ack(self, packet: CyncPacket) -> None:
        """Handle heartbeat ACK packet (0xD8)."""
        device_id = self._get_device_id()
        registry.record_heartbeat(device_id, "success")
        logger.debug("Heartbeat ACK received")
        await self._call_ack_handler_safe(packet)

    def _queue_packet_safe(self, packet: CyncPacket) -> bool:
        """Queue packet, return True if queued, False if dropped."""
        try:
            self._data_packet_queue.put_nowait(packet)
            logger.debug(
                "Queued packet type 0x%02x",
                packet.packet_type,
                extra={"packet_type": packet.packet_type},
            )
        except asyncio.QueueFull:
            device_id = self._get_device_id()
            logger.warning(
                "Data packet queue full, packet type 0x%02x dropped",
                packet.packet_type,
                extra={
                    "packet_type": packet.packet_type,
                    "device_id": device_id,
                    "queue_size": self._data_packet_queue.qsize(),
                },
            )
            return False
        else:
            return True

    def _handle_data_packet(self, packet: CyncPacket) -> None:
        """Handle data packet (0x73, 0x83) by queuing for application."""
        logger.debug(
            "→ Handling data packet",
            extra={"packet_type": f"0x{packet.packet_type:02x}"},
        )
        _ = self._queue_packet_safe(packet)
        logger.debug(
            "✓ Data packet handled",
            extra={"packet_type": f"0x{packet.packet_type:02x}"},
        )

    async def _handle_ack_packet(self, packet: CyncPacket) -> None:
        """Handle ACK packet (0x28, 0x7B, 0x88) by routing to handler."""
        logger.debug(
            "→ Handling ACK packet",
            extra={"packet_type": f"0x{packet.packet_type:02x}"},
        )
        await self._call_ack_handler_safe(packet)
        logger.debug(
            "✓ ACK packet handled",
            extra={"packet_type": f"0x{packet.packet_type:02x}"},
        )

    def _handle_unknown_packet(self, packet: CyncPacket) -> None:
        """Handle unknown packet type by queuing for application."""
        logger.debug(
            "→ Handling unknown packet type 0x%02x, queuing",
            packet.packet_type,
            extra={"packet_type": packet.packet_type},
        )
        _ = self._queue_packet_safe(packet)
        logger.debug(
            "✓ Unknown packet handled",
            extra={"packet_type": f"0x{packet.packet_type:02x}"},
        )

    async def _process_packets(self, complete_packets: list[bytes]) -> None:
        """Process complete packets from PacketFramer."""
        for packet_bytes in complete_packets:
            try:
                packet = self.protocol.decode_packet(packet_bytes)
            except (PacketDecodeError, CyncProtocolError) as e:
                logger.exception(
                    "Packet decode failed",
                    extra={"error": str(e), "error_type": type(e).__name__},
                )
                continue  # Skip malformed packets, continue processing others
            except Exception as e:
                # Unexpected decode errors should not happen (protocol.decode_packet
                # should only raise PacketDecodeError or CyncProtocolError). If we get
                # here, it's a bug in the protocol implementation. Log as critical but
                # continue processing other packets to avoid crashing the packet router.
                logger.critical(
                    "Unexpected packet decode error - this should not happen: %s",
                    e,
                    extra={"error": str(e), "error_type": type(e).__name__},
                )
                continue  # Skip malformed packets, continue processing others

            packet_type = packet.packet_type

            try:
                if packet_type == PACKET_TYPE_HEARTBEAT_CLOUD:
                    # Reset heartbeat ACK flag when ACK received
                    await self._handle_heartbeat_ack(packet)
                elif packet_type in {PACKET_TYPE_DATA_CHANNEL, PACKET_TYPE_STATUS_BROADCAST}:
                    self._handle_data_packet(packet)
                elif packet_type in {
                    PACKET_TYPE_HELLO_ACK,
                    PACKET_TYPE_DATA_ACK,
                    PACKET_TYPE_STATUS_ACK,
                }:
                    await self._handle_ack_packet(packet)
                else:
                    self._handle_unknown_packet(packet)
            except (CyncProtocolError, asyncio.CancelledError):
                # Re-raise protocol errors and cancellations
                raise
            except Exception as e:
                # Log unexpected errors from packet handlers but continue processing
                logger.exception(
                    "Unexpected error handling packet type 0x%02x",
                    packet_type,
                    extra={
                        "packet_type": packet_type,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                # Continue processing other packets
                continue

    async def _check_heartbeat_timeout(
        self,
        awaiting_heartbeat_ack: bool,
        last_heartbeat_sent: float,
        heartbeat_timeout: float,
    ) -> bool:
        """Check if heartbeat ACK is overdue and trigger reconnect if needed.

        Returns:
            True if reconnect was triggered (should break loop), False otherwise

        """
        if awaiting_heartbeat_ack and (time.time() - last_heartbeat_sent > heartbeat_timeout):
            async with self._state_lock:
                if self.state == ConnectionState.CONNECTED:
                    device_id = self._get_device_id()
                    logger.warning(
                        "Heartbeat ACK timeout (%.1fs)",
                        heartbeat_timeout,
                        extra={"device_id": device_id, "heartbeat_timeout": heartbeat_timeout},
                    )
                    registry.record_heartbeat(device_id, "timeout")
                    self._trigger_reconnect("heartbeat_timeout")
                    return True
        return False

    async def _packet_router(self) -> None:
        """Route incoming packets by type and monitor heartbeat health.

        **Primary Responsibilities**:

        1. Route incoming packets to appropriate handlers/queues by packet type
        2. Monitor connection health via periodic heartbeat (0xD3 → 0xD8)
        3. Trigger reconnection on heartbeat failures or errors

        **Packet Routing**:
        - 0xD8: Heartbeat ACK (monitors connection health, not queued)
        - 0x83, 0x73: Data packets (queued to _data_packet_queue for application processing)
        - Other types: Logged and queued for application

        **Task Lifecycle**:
        - **Start**: Created by connect() on successful handshake
        - **Stop**: Cancelled by disconnect() with proper cleanup
        - **Restart**: reconnect() calls disconnect() then connect() to get fresh task
        - **Crash Handling**: Any exception triggers reconnect()

        **Exception Handling**:
        - asyncio.CancelledError: Clean shutdown (re-raise after logging)
        - Other exceptions: Log error and trigger reconnect
        """
        last_heartbeat_sent = time.time()
        awaiting_heartbeat_ack = False
        heartbeat_interval = _HEARTBEAT_INTERVAL_SECONDS
        heartbeat_timeout = self.timeout_config.heartbeat_timeout_seconds

        try:
            while True:
                # 1. Check if heartbeat needs to be sent
                now = time.time()
                if now - last_heartbeat_sent >= heartbeat_interval:
                    # Send 0xD3 heartbeat
                    heartbeat_packet = self.protocol.encode_heartbeat()
                    if await self.conn.send(heartbeat_packet):
                        last_heartbeat_sent = now
                        awaiting_heartbeat_ack = True
                        logger.debug("Heartbeat sent")

                # 2. Receive and route packets (timeout allows heartbeat checking)
                try:
                    try:
                        tcp_data = await asyncio.wait_for(
                            self.conn.recv(),
                            timeout=_PACKET_RECEIVE_TIMEOUT_SECONDS,
                        )
                    except StopAsyncIteration:
                        # Connection closed (mock exhausted or real connection closed)
                        logger.debug("Connection closed (StopAsyncIteration)")
                        break

                    if not tcp_data:
                        continue

                    # Feed to PacketFramer (handles partial packets)
                    complete_packets = self.framer.feed(tcp_data)

                    # Process each complete packet
                    await self._process_packets(complete_packets)

                except TimeoutError:
                    # No packet received - check if heartbeat ACK overdue
                    if await self._check_heartbeat_timeout(
                        awaiting_heartbeat_ack,
                        last_heartbeat_sent,
                        heartbeat_timeout,
                    ):
                        break
                    # Continue loop (allows heartbeat send check)
                    continue

        except asyncio.CancelledError:
            # Clean cancellation from disconnect() - this is expected
            logger.debug("Packet router cancelled (clean shutdown)")
            raise
        except Exception as e:
            # Unexpected error - trigger reconnect and re-raise
            # Broad catch is intentional: packet router is the main event loop for connection.
            # Any unhandled exception here would crash the connection, so we catch all exceptions,
            # trigger reconnection, and re-raise to allow higher-level error handling.
            device_id = self._get_device_id()
            logger.exception(
                "Packet router crashed",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            registry.record_heartbeat(device_id, "crash")
            self._trigger_reconnect("packet_router_crash")
            raise  # Re-raise preserves exception context

    def _trigger_reconnect(self, reason: str) -> None:
        """Trigger reconnection if not already in progress.

        Prevents multiple concurrent reconnection attempts. If a reconnection
        is already running, logs and skips the new trigger.

        Args:
            reason: Reason for reconnection

        """
        if self.reconnect_task is None or self.reconnect_task.done():
            logger.info(
                "Triggering reconnection",
                extra={"reason": reason},
            )
            self.reconnect_task = asyncio.create_task(self.reconnect(reason))
        else:
            logger.debug(
                "Reconnection already in progress",
                extra={"reason": reason},
            )

    async def reconnect(self, reason: str = "unknown") -> bool:
        """Reconnect with exponential backoff.

        Uses state lock to prevent races with send_reliable() retry loops.
        Uses stored endpoint and auth_code from initial connect() call.

        Args:
            reason: Reason for reconnection

        Returns:
            True if reconnection successful, False otherwise

        Raises:
            CyncConnectionError: If credentials not available (connect() never called)

        """
        # Validate credentials exist (set during initial connect())
        if not self.endpoint or not self.auth_code:
            error_msg = "Cannot reconnect: no credentials stored (connect() never called)"
            raise CyncConnectionError(
                error_msg,
                state=self.state.value,
            )

        # Derive device_id from endpoint for metrics
        device_id = self.endpoint.hex()[:10] if self.endpoint else "unknown"

        logger.info(
            "→ Starting reconnection",
            extra={"endpoint": device_id, "reason": reason},
        )
        registry.record_reconnection(device_id, reason)

        async with self._state_lock:
            self.state = ConnectionState.RECONNECTING
            registry.record_connection_state(device_id, self.state.value)

        await self.disconnect()  # Clean up old connection and tasks

        # Retry connect with backoff
        max_retries = 3
        for attempt in range(max_retries):
            if await self.connect(self.endpoint, self.auth_code):  # Starts new packet router task
                logger.info(
                    "✓ Reconnection successful",
                    extra={"endpoint": device_id, "reason": reason},
                )
                return True
            if attempt < max_retries - 1:
                delay = self.retry_policy.get_delay(attempt)
                await asyncio.sleep(delay)

        async with self._state_lock:
            self.state = ConnectionState.DISCONNECTED
            registry.record_connection_state(device_id, self.state.value)
        logger.error(
            "✗ Reconnection failed",
            extra={
                "endpoint": device_id,
                "reason": reason,
                "max_retries": max_retries,
                "attempts": max_retries,
            },
        )
        return False

    async def disconnect(self) -> None:
        """Clean disconnect with task cleanup.

        Task cleanup order: packet_router first, then reconnect, then connection.
        This order prevents race conditions and ensures proper cleanup.
        """
        logger.info("Disconnecting...")

        # Derive device_id from endpoint for metrics
        device_id = self.endpoint.hex()[:10] if self.endpoint else "unknown"

        async with self._state_lock:
            self.state = ConnectionState.DISCONNECTED
            registry.record_connection_state(device_id, self.state.value)

        try:
            # 1. Cancel packet router task first (stops reading from TCP)
            if self.packet_router_task and not self.packet_router_task.done():
                _ = self.packet_router_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self.packet_router_task
            self.packet_router_task = None

            # 2. Cancel reconnect task (if in progress)
            if self.reconnect_task and not self.reconnect_task.done():
                _ = self.reconnect_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self.reconnect_task
            self.reconnect_task = None

            # 3. Close TCP connection
            await self.conn.close()
        finally:
            # Always clear queue, even if close() raises
            self.pending_requests.clear()
            logger.info("Disconnect complete")

    def is_connected(self) -> bool:
        """Check if connection is established (best effort, may be stale).

        ⚠️ WARNING: This check is NOT thread-safe. State may change between
        check and use. For critical operations, use `with_state_check()`.

        Use cases:
        - Non-critical status checks
        - Logging/debugging
        - Metrics collection

        Do NOT use for:
        - Conditional logic before sending packets
        - State-dependent operations

        Returns:
            True if state is CONNECTED, False otherwise

        """
        return self.state == ConnectionState.CONNECTED
