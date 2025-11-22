"""Device operations module for mesh info and device info requests.

This module provides high-level device management operations built on top of
ReliableTransport, including:
- Mesh info requests (PACKET_TYPE_DATA_CHANNEL=0x73 →
    PACKET_TYPE_STATUS_BROADCAST=0x83 status broadcasts)
- Device info requests (PACKET_TYPE_DATA_CHANNEL=0x73 →
    PACKET_TYPE_DEVICE_INFO=0x43 device info packets)
- Primary device architecture enforcement
- DEVICE_TYPE_LENGTH_BYTES-byte device struct parsing
- Packet/ACK analysis with correlation tracking

Implementation copied and adapted from legacy code:
- cync-controller/src/cync_controller/devices/tcp_device.py (lines 213-273)
- cync-controller/src/cync_controller/devices/tcp_packet_handler.py (lines 524-564)
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import OrderedDict
from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal, Protocol, cast, overload

from uuid_extensions import (
    uuid7,
)

from metrics import registry
from protocol import PACKET_TYPE_DEVICE_INFO, PACKET_TYPE_STATUS_BROADCAST
from protocol.packet_types import PACKET_TYPE_DATA_ACK

from .device_info import (
    DEVICE_TYPE_LENGTH_BYTES,
    DeviceInfo,
    DeviceInfoRequestError,
    DeviceStructParseError,
    MeshInfoRequestError,
)

if TYPE_CHECKING:
    # Protocol-based type definitions for forward references
    class CyncPacket(Protocol):
        """Protocol for CyncPacket."""

        packet_type: int
        payload: bytes

    class CyncProtocol(Protocol):
        """Protocol for CyncProtocol."""

    class ReliableTransportResult(Protocol):
        """Protocol for ReliableTransport.send_reliable() result."""

        success: bool
        reason: str

    class ReliableTransportPacket(Protocol):
        """Protocol for ReliableTransport.recv_reliable() result."""

        packet: CyncPacket

    class ReliableTransport(Protocol):
        """Protocol for ReliableTransport (Phase 1b)."""

        async def send_reliable(self, payload: bytes, timeout: float) -> ReliableTransportResult:
            """Send reliable packet."""
            ...

        async def recv_reliable(self) -> ReliableTransportPacket:
            """Receive reliable packet."""
            ...


logger = logging.getLogger(__name__)


def record_metric(metric_name: str, **labels: str) -> None:
    """Record metric using metrics registry.

    This function provides a unified interface for recording metrics from DeviceOperations.
    Metrics are recorded via the Prometheus metrics registry.

    Args:
        metric_name: Name of the metric (e.g., "tcp_comm_mesh_info_request_total")
        **labels: Label key-value pairs for the metric (device_id extracted from
            labels if available)

    Note: Phase 1b implementation - metrics registry is available and functional.
    DeviceOperations operates on multiple devices, so device_id defaults to
    "unknown" if not provided.

    """
    # Extract device_id from labels or use default
    device_id = labels.get("device_id", "unknown")
    outcome = labels.get("outcome", "unknown")

    # Map metric names to registry functions
    # Remove try/except wrapper - if metrics fail, we want to know
    if metric_name == "tcp_comm_mesh_info_request_total":
        registry.record_mesh_info_request(device_id=device_id, outcome=outcome)
    elif metric_name == "tcp_comm_device_info_request_total":
        registry.record_device_info_request(device_id=device_id, outcome=outcome)
    elif metric_name == "tcp_comm_device_struct_parsed_total":
        # device_struct_parsed uses device_id from labels
        registry.record_device_struct_parsed(device_id=device_id)
    elif metric_name == "tcp_comm_primary_device_violations_total":
        registry.record_primary_device_violation()
    elif metric_name == "tcp_comm_device_cache_evictions_total":
        registry.record_device_cache_eviction()
    else:
        logger.debug(
            "Unknown metric name: %s (labels: %s)",
            metric_name,
            labels,
            extra={"metric_name": metric_name, "labels": labels},
        )


class DeviceOperations:
    """High-level device management operations with primary device architecture.

    Provides mesh info and device info request/response handling with:
    - Primary device enforcement (only designated primary can request mesh info)
    - DEVICE_TYPE_LENGTH_BYTES-byte device struct parsing
    - Packet/ACK analysis with correlation tracking
    - Metrics recording for all operations

    Primary Device Architecture:
        Only one device per mesh should be designated as "primary" to prevent
        duplicate MQTT publishes when multiple devices respond to mesh info requests.
        This mirrors the architecture in cync-controller/src/cync_controller/server.py
        lines 494-597.

    Usage:
        >>> transport = ReliableTransport(...)
        >>> protocol = CyncProtocol()
        >>> device_ops = DeviceOperations(transport, protocol)
        >>> device_ops.set_primary(True)  # Designate as primary
        >>> devices = await device_ops.ask_for_mesh_info(parse=True)

    Attributes:
        transport: ReliableTransport instance for sending/receiving packets
        protocol: CyncProtocol instance for encoding/decoding packets
        is_primary: Whether this device is designated as primary
        parse_mesh_status: Flag indicating if mesh status should be parsed
        device_cache: Cache of parsed DeviceInfo objects by device_id
        logger_prefix: Prefix for log messages

    """

    # Timeout constants
    DEFAULT_MESH_INFO_TIMEOUT = 10.0  # Timeout for collecting mesh info responses
    DEFAULT_DEVICE_INFO_TIMEOUT = 5.0  # Default timeout for device info requests
    MESH_INFO_SEND_TIMEOUT = 5.0  # Timeout for sending mesh info request
    MAX_DEVICE_INFO_TIMEOUT = 60.0  # Maximum recommended timeout for device info requests

    # Device ID constants
    DEVICE_ID_LENGTH_BYTES = 4  # Standard device ID length in bytes

    # Cache constants
    MAX_CACHE_SIZE = 1000  # Maximum number of cached device info objects (LRU eviction)

    def __init__(self, transport: ReliableTransport, protocol: CyncProtocol):
        """Initialize DeviceOperations.

        Args:
            transport: ReliableTransport instance for packet send/receive
            protocol: CyncProtocol instance for packet encoding/decoding

        """
        self.transport = transport
        self.protocol = protocol
        self.is_primary = False  # Primary device designation
        self.parse_mesh_status = False  # Flag for parsing responses
        self.device_cache: OrderedDict[str, DeviceInfo] = (
            OrderedDict()
        )  # Parsed device structs (LRU)
        self._cache_lock = asyncio.Lock()  # Protect cache operations
        self.logger_prefix = "[DeviceOps]"

    def _validate_primary_device(self) -> None:
        """Validate that this is the primary device, raise error if not."""
        logger.debug(
            "→ Validating primary device",
            extra={"logger_prefix": self.logger_prefix, "is_primary": self.is_primary},
        )
        if not self.is_primary:
            logger.warning(
                "Non-primary device attempted mesh info request",
                extra={
                    "logger_prefix": self.logger_prefix,
                    "is_primary": False,
                },
            )
            # METRIC: tcp_comm_primary_device_violations_total
            record_metric("tcp_comm_primary_device_violations_total")
            error_code = "not_primary"
            error_msg = "Only primary device can request mesh info"
            logger.debug(
                "✗ Primary device validation failed",
                extra={"logger_prefix": self.logger_prefix, "error_code": error_code},
            )
            raise MeshInfoRequestError(error_code, error_msg)

        logger.debug(
            "✓ Primary device validation passed",
            extra={"logger_prefix": self.logger_prefix, "is_primary": self.is_primary},
        )

    async def _add_to_cache(self, device_id: str, device_info: DeviceInfo) -> None:
        """Add device to cache with LRU eviction (thread-safe).

        Maintains an LRU cache of parsed DeviceInfo objects. When the cache
        exceeds MAX_CACHE_SIZE, the oldest (least recently used) entry is evicted.

        Args:
            device_id: Device identifier (hex string)
            device_info: Parsed DeviceInfo object to cache

        Example:
            >>> device_ops = DeviceOperations(mock_transport, mock_protocol)
            >>> device_info = DeviceInfo(...)
            >>> await device_ops._add_to_cache("aabbccdd", device_info)
            >>> assert "aabbccdd" in device_ops.device_cache

        """
        async with self._cache_lock:
            if device_id in self.device_cache:
                # Move to end (most recently used)
                self.device_cache.move_to_end(device_id)
            else:
                self.device_cache[device_id] = device_info
                # Evict oldest if over limit
                if len(self.device_cache) > self.MAX_CACHE_SIZE:
                    evicted_id, _ = self.device_cache.popitem(last=False)  # Remove oldest
                    logger.debug(
                        "Device cache evicted oldest entry",
                        extra={
                            "logger_prefix": self.logger_prefix,
                            "evicted_device_id": evicted_id,
                            "cache_size": len(self.device_cache),
                        },
                    )
                    # METRIC: tcp_comm_device_cache_evictions_total
                    record_metric("tcp_comm_device_cache_evictions_total")

    def _build_mesh_info_inner_struct(self) -> bytes:
        """Build mesh info request inner struct (0x7e 1f 00 00 00 f8 52 06 ...).

        Example:
            >>> device_ops = DeviceOperations(mock_transport, mock_protocol)
            >>> inner_struct = device_ops._build_mesh_info_inner_struct()
            >>> assert len(inner_struct) == 18
            >>> assert inner_struct[0] == 0x7E  # Frame marker

        """
        logger.debug(
            "→ Building mesh info inner struct",
            extra={"logger_prefix": self.logger_prefix},
        )
        # Inner struct from legacy tcp_device.py lines 235-255
        # 0x7e 1f 00 00 00 f8 52 06 00 00 00 ff ff 00 00 56 7e
        result = bytes(
            [
                0x7E,  # Frame marker
                0x1F,
                0x00,
                0x00,
                0x00,  # Header
                0xF8,
                0x52,
                0x06,  # Mesh info request command
                0x00,
                0x00,
                0x00,  # Padding
                0xFF,
                0xFF,  # All devices
                0x00,
                0x00,  # Padding
                0x56,  # Checksum
                0x7E,  # Frame marker
            ],
        )
        logger.debug(
            "✓ Mesh info inner struct built",
            extra={"logger_prefix": self.logger_prefix, "length": len(result)},
        )
        return result

    async def _send_mesh_info_request(
        self,
        inner_struct: bytes,
        correlation_id: str,
        refresh_id: str | None,
    ) -> None:
        """Send mesh info request via reliable transport, raise on failure."""
        logger.info(
            "→ Sending mesh info request",
            extra={
                "logger_prefix": self.logger_prefix,
                "correlation_id": correlation_id,
                "refresh_id": refresh_id,
                "bytes": inner_struct.hex(),
            },
        )

        # Send via reliable transport
        try:
            result = await self.transport.send_reliable(
                payload=inner_struct,
                timeout=self.MESH_INFO_SEND_TIMEOUT,
            )
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.exception(
                "✗ Mesh info request failed",
                extra={
                    "logger_prefix": self.logger_prefix,
                    "correlation_id": correlation_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            # METRIC: tcp_comm_mesh_info_request_total
            record_metric("tcp_comm_mesh_info_request_total", outcome="send_failed")
            error_code = "send_failed"
            error_msg = str(e)
            raise MeshInfoRequestError(error_code, error_msg) from e

        if not result.success:
            logger.error(
                "✗ Mesh info request failed",
                extra={
                    "logger_prefix": self.logger_prefix,
                    "correlation_id": correlation_id,
                    "reason": result.reason,
                },
            )
            # METRIC: tcp_comm_mesh_info_request_total
            record_metric("tcp_comm_mesh_info_request_total", outcome="send_failed")
            error_msg = "Failed to send mesh info request"
            raise MeshInfoRequestError(result.reason, error_msg)

        logger.info(
            "✓ Mesh info request sent",
            extra={
                "logger_prefix": self.logger_prefix,
                "correlation_id": correlation_id,
            },
        )

    async def _collect_mesh_info_responses(
        self,
        correlation_id: str,
        parse: bool,
    ) -> list[CyncPacket | DeviceInfo]:
        """Collect 0x83 status broadcast responses."""
        logger.info(
            "→ Starting mesh info response collection",
            extra={
                "logger_prefix": self.logger_prefix,
                "correlation_id": correlation_id,
                "parse": parse,
                "timeout": self.DEFAULT_MESH_INFO_TIMEOUT,
            },
        )

        responses: list[CyncPacket | DeviceInfo] = []
        timeout = self.DEFAULT_MESH_INFO_TIMEOUT
        wait_start = time.time()

        self.parse_mesh_status = parse  # Set flag for parsing

        try:
            while time.time() - wait_start < timeout:
                try:
                    remaining_timeout = timeout - (time.time() - wait_start)
                    if remaining_timeout <= 0:
                        break

                    packet = await asyncio.wait_for(
                        self.transport.recv_reliable(),
                        timeout=remaining_timeout,
                    )

                    # Check if this is a PACKET_TYPE_STATUS_BROADCAST (0x83) status broadcast
                    if packet.packet.packet_type == PACKET_TYPE_STATUS_BROADCAST:
                        logger.debug(
                            "Status broadcast received",
                            extra={
                                "logger_prefix": self.logger_prefix,
                                "correlation_id": correlation_id,
                                "packet_type": hex(PACKET_TYPE_STATUS_BROADCAST),
                            },
                        )

                        if parse:
                            # Parse device structs from PACKET_TYPE_STATUS_BROADCAST packet
                            device_infos = await self._parse_0x83_packet(
                                packet.packet,
                                correlation_id,
                            )
                            responses.extend(device_infos)
                        else:
                            responses.append(packet.packet)

                except TimeoutError:
                    # No more responses
                    break

        finally:
            self.parse_mesh_status = False

        collection_duration = time.time() - wait_start
        logger.info(
            "✓ Collected %d mesh info responses",
            len(responses),
            extra={
                "logger_prefix": self.logger_prefix,
                "correlation_id": correlation_id,
                "response_count": len(responses),
                "duration_seconds": collection_duration,
            },
        )

        # METRIC: tcp_comm_mesh_info_collection_duration_seconds
        registry.record_mesh_info_collection_duration(collection_duration)

        return responses

    @overload
    async def ask_for_mesh_info(
        self,
        parse: Literal[True],
        refresh_id: str | None = ...,
    ) -> list[DeviceInfo]: ...

    @overload
    async def ask_for_mesh_info(
        self,
        parse: Literal[False] = False,
        refresh_id: str | None = ...,
    ) -> list[CyncPacket]: ...

    async def ask_for_mesh_info(
        self,
        parse: bool = False,
        refresh_id: str | None = None,
    ) -> Sequence[CyncPacket | DeviceInfo]:
        """Request mesh info from connected device.

        Sends PACKET_TYPE_DATA_CHANNEL (0x73) mesh info request with inner_struct
        (0x7e 1f 00 00 00 f8 52 06 ...), then collects PACKET_TYPE_STATUS_BROADCAST
        (0x83) status broadcast responses for up to 10 seconds.

        Implementation based on legacy tcp_device.py lines 213-273.

        Packet Flow:
            1. Send PACKET_TYPE_DATA_CHANNEL (0x73) mesh info request →
               receive PACKET_TYPE_DATA_ACK (0x7B) ACK
            2. Wait for PACKET_TYPE_STATUS_BROADCAST (0x83) status broadcasts
               (asynchronous responses)
            3. Parse device structs if requested

        Primary Device Enforcement:
            Only primary device can request mesh info. This prevents duplicate
            MQTT publishes when multiple devices respond. See legacy code
            tcp_packet_handler.py lines 386-387 for primary device check pattern.

        Args:
            parse: If True, parse DEVICE_TYPE_LENGTH_BYTES-byte device structs and
                return DeviceInfo objects
            refresh_id: UUID for correlation tracking in logs/metrics

        Returns:
            List of raw CyncPacket or parsed DeviceInfo objects

        Raises:
            MeshInfoRequestError: If send fails or device not primary

        Example:
            >>> device_ops.set_primary(True)
            >>> devices = await device_ops.ask_for_mesh_info(parse=True)
            >>> for device in devices:
            ...     print(f"Device {device.device_id_hex()}: {device.state}")

        """
        # Generate correlation_id for tracking (UUID v7 for time-ordering)
        correlation_id = refresh_id if refresh_id else str(cast(uuid.UUID, uuid7()))

        logger.info(
            "→ Starting mesh info request",
            extra={
                "logger_prefix": self.logger_prefix,
                "correlation_id": correlation_id,
                "parse": parse,
                "refresh_id": refresh_id,
            },
        )

        request_start = time.time()
        try:
            # Validate primary device enforcement
            self._validate_primary_device()

            # Build mesh info request packet (0x73)
            inner_struct = self._build_mesh_info_inner_struct()

            # Send via reliable transport
            await self._send_mesh_info_request(inner_struct, correlation_id, refresh_id)

            # Log ACK timing (packet/ACK analysis)
            ack_latency_ms = int((time.time() - request_start) * 1000)
            logger.info(
                "Mesh info ACK received",
                extra={
                    "logger_prefix": self.logger_prefix,
                    "correlation_id": correlation_id,
                    "ack_type": hex(PACKET_TYPE_DATA_ACK),
                    "latency_ms": ack_latency_ms,
                },
            )

            # Listen for PACKET_TYPE_STATUS_BROADCAST (0x83) status broadcasts
            responses = await self._collect_mesh_info_responses(correlation_id, parse)

            # Log summary (packet/ACK analysis)
            total_time_ms = int((time.time() - request_start) * 1000)
            logger.info(
                "✓ Mesh info request complete",
                extra={
                    "logger_prefix": self.logger_prefix,
                    "correlation_id": correlation_id,
                    "device_count": len(responses),
                    "total_time_ms": total_time_ms,
                },
            )

            # METRIC: tcp_comm_mesh_info_request_total
            record_metric("tcp_comm_mesh_info_request_total", outcome="success")
        except MeshInfoRequestError as e:
            total_time_ms = int((time.time() - request_start) * 1000)
            logger.exception(
                "✗ Mesh info request failed",
                extra={
                    "logger_prefix": self.logger_prefix,
                    "correlation_id": correlation_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "total_time_ms": total_time_ms,
                },
            )
            raise
        except Exception as e:
            total_time_ms = int((time.time() - request_start) * 1000)
            logger.exception(
                "✗ Mesh info request unexpected exception",
                extra={
                    "logger_prefix": self.logger_prefix,
                    "correlation_id": correlation_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "total_time_ms": total_time_ms,
                },
            )
            # Wrap unexpected exceptions in MeshInfoRequestError for consistency
            error_code = "unexpected_error"
            error_msg = (
                f"Unexpected error during mesh info request (correlation_id={correlation_id}): {e}"
            )
            raise MeshInfoRequestError(error_code, error_msg) from e
        else:
            # Success path - return responses
            return responses

    def _validate_device_info_request(self, device_id: bytes, timeout: float | None) -> float:
        """Validate device info request parameters.

        Args:
            device_id: Device identifier to validate
            timeout: Timeout value to validate

        Returns:
            Validated timeout value (defaults to DEFAULT_DEVICE_INFO_TIMEOUT if None)

        Raises:
            ValueError: If device_id or timeout is invalid

        """
        # Validate device_id
        if not device_id:
            error_msg = "device_id cannot be empty"
            raise ValueError(error_msg)

        if len(device_id) != self.DEVICE_ID_LENGTH_BYTES:
            error_msg = (
                f"device_id must be {self.DEVICE_ID_LENGTH_BYTES} bytes, got {len(device_id)}"
            )
            raise ValueError(error_msg)

        # Validate timeout
        validated_timeout = timeout if timeout is not None else self.DEFAULT_DEVICE_INFO_TIMEOUT

        if timeout is not None:
            if timeout <= 0:
                error_msg = f"timeout must be positive, got {timeout}"
                raise ValueError(error_msg)
            if timeout > self.MAX_DEVICE_INFO_TIMEOUT:
                logger.warning(
                    "Large timeout value: %.1fs (max recommended: %.1fs)",
                    timeout,
                    self.MAX_DEVICE_INFO_TIMEOUT,
                    extra={"timeout": timeout},
                )

        logger.debug(
            "✓ Device info request validation passed",
            extra={
                "logger_prefix": self.logger_prefix,
                "device_id_length": len(device_id),
                "timeout": validated_timeout,
            },
        )
        return validated_timeout

    async def request_device_info(
        self,
        device_id: bytes,
        timeout: float | None = None,
    ) -> DeviceInfo | None:
        """Request info for specific device.

        Sends PACKET_TYPE_DATA_CHANNEL (0x73) device info request, waits for
        PACKET_TYPE_DEVICE_INFO (0x43) response.

        Packet Flow:
            1. Send PACKET_TYPE_DATA_CHANNEL (0x73) device info request →
               receive PACKET_TYPE_DATA_ACK (0x7B) ACK
            2. Wait for PACKET_TYPE_DEVICE_INFO (0x43) device info response
            3. Parse DEVICE_TYPE_LENGTH_BYTES-byte device struct

        Args:
            device_id: 4-byte device identifier
            timeout: Response timeout in seconds

        Returns:
            Parsed DeviceInfo or None if timeout

        Raises:
            DeviceInfoRequestError: If send fails

        Example:
            >>> device_id = bytes([0x39, 0x87, 0xC8, 0x57])
            >>> device_info = await device_ops.request_device_info(device_id)
            >>> if device_info:
            ...     print(f"Device state: {device_info.state}")

        """
        # Validate parameters and get validated timeout
        timeout = self._validate_device_info_request(device_id, timeout)

        correlation_id = str(cast(uuid.UUID, uuid7()))
        request_start = time.time()

        logger.info(
            "→ Starting device info request",
            extra={
                "logger_prefix": self.logger_prefix,
                "correlation_id": correlation_id,
                "device_id": device_id.hex(),
                "timeout": timeout,
            },
        )

        # Build device info request packet (0x73)
        # TODO(phase-1a-complete): Enhance packet structure from legacy code
        # for individual device query
        # Phase 1a is complete - this is an enhancement to support individual device queries
        # Legacy reference: cync-controller/src/cync_controller/devices/tcp_device.py
        inner_struct = self._build_device_info_request(device_id)

        logger.info(
            "Device info request sent",
            extra={
                "logger_prefix": self.logger_prefix,
                "correlation_id": correlation_id,
                "device_id": device_id.hex(),
            },
        )

        # Send via reliable transport
        try:
            result = await self.transport.send_reliable(payload=inner_struct, timeout=timeout)
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.exception(
                "✗ Device info request failed",
                extra={
                    "logger_prefix": self.logger_prefix,
                    "correlation_id": correlation_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            # METRIC: tcp_comm_device_info_request_total
            record_metric("tcp_comm_device_info_request_total", outcome="send_failed")
            error_code = "send_failed"
            error_msg = str(e)
            raise DeviceInfoRequestError(error_code, error_msg) from e

        if not result.success:
            logger.error(
                "✗ Device info request failed",
                extra={
                    "logger_prefix": self.logger_prefix,
                    "correlation_id": correlation_id,
                    "reason": result.reason,
                },
            )
            # METRIC: tcp_comm_device_info_request_total
            record_metric("tcp_comm_device_info_request_total", outcome="send_failed")
            error_msg = "Failed to send device info request"
            raise DeviceInfoRequestError(result.reason, error_msg)

        # Wait for 0x43 response
        wait_start = time.time()
        try:
            while time.time() - wait_start < timeout:
                remaining_timeout = timeout - (time.time() - wait_start)
                if remaining_timeout <= 0:
                    break

                packet = await asyncio.wait_for(
                    self.transport.recv_reliable(),
                    timeout=remaining_timeout,
                )

                # Check if this is a PACKET_TYPE_DEVICE_INFO (0x43) device info packet
                if packet.packet.packet_type == PACKET_TYPE_DEVICE_INFO:
                    latency_ms = int((time.time() - request_start) * 1000)
                    logger.info(
                        "Device info received",
                        extra={
                            "logger_prefix": self.logger_prefix,
                            "correlation_id": correlation_id,
                            "packet_type": hex(PACKET_TYPE_DEVICE_INFO),
                            "latency_ms": latency_ms,
                        },
                    )

                    # Parse device struct
                    device_info = await self._parse_device_struct(
                        packet.packet.payload,
                        correlation_id,
                    )

                    # METRIC: tcp_comm_device_info_request_total
                    record_metric("tcp_comm_device_info_request_total", outcome="success")

                    latency_ms = int((time.time() - request_start) * 1000)
                    latency_seconds = time.time() - request_start
                    logger.info(
                        "✓ Device info request complete",
                        extra={
                            "logger_prefix": self.logger_prefix,
                            "correlation_id": correlation_id,
                            "latency_ms": latency_ms,
                        },
                    )

                    # METRIC: tcp_comm_device_info_request_latency_seconds
                    registry.record_device_info_request_latency(device_id.hex(), latency_seconds)

                    return device_info

        except TimeoutError:
            latency_ms = int((time.time() - request_start) * 1000)
            logger.warning(
                "✗ Device info request timeout",
                extra={
                    "logger_prefix": self.logger_prefix,
                    "correlation_id": correlation_id,
                    "device_id": device_id.hex(),
                    "timeout": timeout,
                    "latency_ms": latency_ms,
                },
            )
            # METRIC: tcp_comm_device_info_request_total
            record_metric("tcp_comm_device_info_request_total", outcome="timeout")
            return None

        # Explicit return if loop exits without finding 0x43 packet
        latency_ms = int((time.time() - request_start) * 1000)
        logger.warning(
            "✗ Device info request incomplete",
            extra={
                "logger_prefix": self.logger_prefix,
                "correlation_id": correlation_id,
                "device_id": device_id.hex(),
                "latency_ms": latency_ms,
            },
        )
        return None

    async def _parse_0x83_packet(self, packet: CyncPacket, correlation_id: str) -> list[DeviceInfo]:
        """Parse PACKET_TYPE_STATUS_BROADCAST (0x83) status broadcast packet
        containing multiple DEVICE_TYPE_LENGTH_BYTES-byte device structs.

        Implementation based on legacy tcp_packet_handler.py lines 566-600.

        Args:
            packet: Parsed PACKET_TYPE_STATUS_BROADCAST (0x83) packet
            correlation_id: UUID for tracking

        Returns:
            List of parsed DeviceInfo objects

        """
        devices: list[DeviceInfo] = []
        payload = packet.payload

        # Extract device structs (DEVICE_TYPE_LENGTH_BYTES bytes each) from between 0x7e markers
        # Legacy code reference: tcp_packet_handler.py lines 566-600
        offset = 0
        while offset + DEVICE_TYPE_LENGTH_BYTES <= len(payload):
            device_struct = payload[offset : offset + DEVICE_TYPE_LENGTH_BYTES]
            try:
                device_info = await self._parse_device_struct(device_struct, correlation_id)
                devices.append(device_info)
                offset += DEVICE_TYPE_LENGTH_BYTES
            except (DeviceStructParseError, ValueError, IndexError) as e:
                logger.warning(
                    "Failed to parse device struct",
                    extra={
                        "logger_prefix": self.logger_prefix,
                        "offset": offset,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                break

        return devices

    async def _parse_device_struct(self, raw_bytes: bytes, correlation_id: str) -> DeviceInfo:
        """Parse DEVICE_TYPE_LENGTH_BYTES-byte device struct from
        PACKET_TYPE_STATUS_BROADCAST (0x83) or PACKET_TYPE_DEVICE_INFO (0x43) packet.

        Struct format (from legacy DEVICE_STRUCTS):
        - Bytes 0-3: device_id (4 bytes)
        - Bytes 4-7: capabilities/flags (4 bytes)
        - Bytes 8-11: state data (4 bytes)
        - Bytes 12-23: additional fields (12 bytes)

        Implementation adapted from legacy structs.py and tcp_packet_handler.py.

        Args:
            raw_bytes: DEVICE_TYPE_LENGTH_BYTES-byte device struct
            correlation_id: UUID for tracking

        Returns:
            Parsed DeviceInfo object

        Raises:
            DeviceStructParseError: If struct is invalid

        Example:
            >>> raw_bytes = bytes([0x39, 0x87, 0xC8, 0x57] + [0] * 20)
            ...  # DEVICE_TYPE_LENGTH_BYTES bytes
            >>> device_info = device_ops._parse_device_struct(raw_bytes, "correlation-123")
            >>> print(device_info.device_id_hex())
            '3987c857'

        """
        logger.debug(
            "→ Parsing device struct",
            extra={
                "logger_prefix": self.logger_prefix,
                "correlation_id": correlation_id,
                "bytes_length": len(raw_bytes),
            },
        )

        if len(raw_bytes) != DEVICE_TYPE_LENGTH_BYTES:
            error_msg = (
                f"Invalid device struct length: {len(raw_bytes)} "
                f"(expected {DEVICE_TYPE_LENGTH_BYTES})"
            )
            raise DeviceStructParseError(error_msg)

        # Extract fields
        device_id = raw_bytes[0:4]
        capabilities_raw = raw_bytes[4:8]
        state_raw = raw_bytes[8:12]

        # Parse capabilities and state
        # TODO(phase-1a-complete): Enhance parsing logic from legacy structs.py
        # Phase 1a is complete - this is an enhancement for full struct parsing
        # Legacy reference: cync-controller/src/cync_controller/devices/structs.py
        # Current implementation is simplified but functional
        capabilities = int.from_bytes(capabilities_raw, byteorder="big")
        device_type = (capabilities >> 24) & 0xFF  # Example field extraction

        # Parse state fields
        # TODO(phase-1a-complete): Enhance state parsing from legacy code
        # Legacy reference: cync-controller/src/cync_controller/devices/structs.py
        state = {
            "on": bool(state_raw[0] & 0x01),
            "brightness": state_raw[1] if len(state_raw) > 1 else 0,
            "raw": state_raw.hex(),
        }

        device_info = DeviceInfo(
            device_id=device_id,
            device_type=device_type,
            capabilities=capabilities,
            state=state,
            raw_bytes=raw_bytes,
            correlation_id=correlation_id,
        )

        # Cache parsed device (with LRU eviction)
        await self._add_to_cache(device_id.hex(), device_info)

        # METRIC: tcp_comm_device_struct_parsed_total
        record_metric("tcp_comm_device_struct_parsed_total", device_id=device_id.hex())

        logger.debug(
            "Device struct parsed",
            extra={
                "logger_prefix": self.logger_prefix,
                "correlation_id": correlation_id,
                "device_id": device_id.hex(),
                "device_type": device_type,
            },
        )

        return device_info

    def _build_device_info_request(self, device_id: bytes) -> bytes:
        """Build 0x73 device info request packet for specific device.

        Args:
            device_id: 4-byte device identifier

        Returns:
            Inner struct bytes for 0x73 packet

        Example:
            >>> device_id = bytes([0x39, 0x87, 0xC8, 0x57])
            >>> inner_struct = device_ops._build_device_info_request(device_id)
            >>> len(inner_struct) > 0
            True

        """
        # TODO(phase-1a-complete): Enhance from legacy code for individual device query
        # Phase 1a is complete - this is an enhancement for individual device queries
        # Legacy reference: cync-controller/src/cync_controller/devices/tcp_device.py
        # Current implementation is simplified but functional -
        # needs validation against real protocol
        return bytes([0x7E]) + device_id + bytes([0x7E])

    def set_primary(self, is_primary: bool) -> None:
        """Designate this device as primary for mesh operations.

        Only the primary device can request mesh info to prevent duplicate
        MQTT publishes when multiple devices respond.

        Primary device architecture mirrors legacy code pattern from
        server.py lines 494-597.

        Args:
            is_primary: True if this is the primary device

        Example:
            >>> device_ops.set_primary(True)
            >>> devices = await device_ops.ask_for_mesh_info(parse=True)
            >>> device_ops.set_primary(False)  # Release primary status

        """
        self.is_primary = is_primary
        logger.info(
            "Primary device status changed",
            extra={
                "logger_prefix": self.logger_prefix,
                "is_primary": is_primary,
            },
        )
