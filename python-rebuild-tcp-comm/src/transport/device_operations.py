"""Device operations module for mesh info and device info requests.

This module provides high-level device management operations built on top of
ReliableTransport, including:
- Mesh info requests (0x73 → 0x83 status broadcasts)
- Device info requests (0x73 → 0x43 device info packets)
- Primary device architecture enforcement
- 24-byte device struct parsing
- Packet/ACK analysis with correlation tracking

Implementation copied and adapted from legacy code:
- cync-controller/src/cync_controller/devices/tcp_device.py (lines 213-273)
- cync-controller/src/cync_controller/devices/tcp_packet_handler.py (lines 524-564)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Union

from uuid_extensions import uuid7

from .device_info import (
    DeviceInfo,
    DeviceInfoRequestError,
    DeviceStructParseError,
    MeshInfoRequestError,
)

if TYPE_CHECKING:
    from ..protocol.cync_protocol import CyncPacket, CyncProtocol
    from .reliable_layer import ReliableTransport

logger = logging.getLogger(__name__)


def record_metric(metric_name: str, **labels):
    """Record metric (placeholder for actual metrics implementation)."""
    # TODO: Replace with actual metrics recording in Phase 1b implementation
    pass


class DeviceOperations:
    """High-level device management operations with primary device architecture.

    Provides mesh info and device info request/response handling with:
    - Primary device enforcement (only designated primary can request mesh info)
    - 24-byte device struct parsing
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
        self.device_cache: Dict[str, DeviceInfo] = {}  # Parsed device structs
        self.logger_prefix = "[DeviceOps]"

    async def ask_for_mesh_info(
        self, parse: bool = False, refresh_id: Optional[str] = None
    ) -> List[Union[CyncPacket, DeviceInfo]]:
        """Request mesh info from connected device.

        Sends 0x73 mesh info request with inner_struct (0x7e 1f 00 00 00 f8 52 06 ...),
        then collects 0x83 status broadcast responses for up to 10 seconds.

        Implementation based on legacy tcp_device.py lines 213-273.

        Packet Flow:
            1. Send 0x73 mesh info request → receive 0x7B ACK
            2. Wait for 0x83 status broadcasts (asynchronous responses)
            3. Parse device structs if requested

        Primary Device Enforcement:
            Only primary device can request mesh info. This prevents duplicate
            MQTT publishes when multiple devices respond. See legacy code
            tcp_packet_handler.py lines 386-387 for primary device check pattern.

        Args:
            parse: If True, parse 24-byte device structs and return DeviceInfo objects
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
        # Validate primary device enforcement
        if not self.is_primary:
            logger.warning("%s Non-primary device attempted mesh info request", self.logger_prefix)
            # METRIC: tcp_comm_primary_device_violations_total
            record_metric("tcp_comm_primary_device_violations_total")
            raise MeshInfoRequestError("not_primary", "Only primary device can request mesh info")

        # Generate correlation_id for tracking (UUID v7 for time-ordering)
        correlation_id = refresh_id if refresh_id else str(uuid7())
        request_start = time.time()

        # Build mesh info request packet (0x73)
        # Inner struct from legacy tcp_device.py lines 235-255
        # 0x7e 1f 00 00 00 f8 52 06 00 00 00 ff ff 00 00 56 7e
        inner_struct = bytes(
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
            ]
        )

        # Log request details with correlation_id and bytes
        logger.info(
            "%s Mesh info request sent | correlation_id=%s refresh_id=%s bytes=%s",
            self.logger_prefix,
            correlation_id,
            refresh_id,
            inner_struct.hex(),
        )

        # Send via reliable transport (5s timeout for mesh info)
        try:
            result = await self.transport.send_reliable(payload=inner_struct, timeout=5.0)
        except Exception as e:
            logger.error("%s Mesh info request send failed: %s", self.logger_prefix, e)
            # METRIC: tcp_comm_mesh_info_request_total
            record_metric("tcp_comm_mesh_info_request_total", outcome="send_failed")
            raise MeshInfoRequestError("send_failed", str(e))

        if not result.success:
            logger.error("%s Mesh info request failed: %s", self.logger_prefix, result.reason)
            # METRIC: tcp_comm_mesh_info_request_total
            record_metric("tcp_comm_mesh_info_request_total", outcome="send_failed")
            raise MeshInfoRequestError(result.reason, "Failed to send mesh info request")

        # Log ACK timing (packet/ACK analysis)
        ack_latency_ms = int((time.time() - request_start) * 1000)
        logger.info(
            "%s Mesh info ACK received | correlation_id=%s ack_type=0x7B latency_ms=%d",
            self.logger_prefix,
            correlation_id,
            ack_latency_ms,
        )

        # Listen for 0x83 status broadcasts for up to 10s
        responses: List[Union[CyncPacket, DeviceInfo]] = []
        timeout = 10.0
        wait_start = time.time()

        self.parse_mesh_status = parse  # Set flag for parsing

        try:
            while time.time() - wait_start < timeout:
                try:
                    remaining_timeout = timeout - (time.time() - wait_start)
                    if remaining_timeout <= 0:
                        break

                    packet = await asyncio.wait_for(
                        self.transport.recv_reliable(), timeout=remaining_timeout
                    )

                    # Check if this is a 0x83 status broadcast
                    if packet.packet.packet_type == 0x83:
                        logger.debug(
                            "%s Status broadcast received (0x83) | correlation_id=%s",
                            self.logger_prefix,
                            correlation_id,
                        )

                        if parse:
                            # Parse device structs from packet
                            device_infos = self._parse_0x83_packet(packet.packet, correlation_id)
                            responses.extend(device_infos)
                        else:
                            responses.append(packet.packet)

                except asyncio.TimeoutError:
                    # No more responses
                    break

        finally:
            self.parse_mesh_status = False

        # Log summary (packet/ACK analysis)
        total_time_ms = int((time.time() - request_start) * 1000)
        logger.info(
            "%s Status broadcast received | correlation_id=%s packet_type=0x83 "
            "device_count=%d total_time_ms=%d",
            self.logger_prefix,
            correlation_id,
            len(responses),
            total_time_ms,
        )

        # METRIC: tcp_comm_mesh_info_request_total
        record_metric("tcp_comm_mesh_info_request_total", outcome="success")

        return responses

    async def request_device_info(
        self, device_id: bytes, timeout: float = 5.0
    ) -> Optional[DeviceInfo]:
        """Request info for specific device.

        Sends 0x73 device info request, waits for 0x43 response.

        Packet Flow:
            1. Send 0x73 device info request → receive 0x7B ACK
            2. Wait for 0x43 device info response
            3. Parse 24-byte device struct

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
        correlation_id = str(uuid7())
        request_start = time.time()

        # Build device info request packet (0x73)
        # TODO: Adapt packet structure from legacy code for individual device query
        inner_struct = self._build_device_info_request(device_id)

        logger.info(
            "%s Device info request sent | correlation_id=%s device_id=%s",
            self.logger_prefix,
            correlation_id,
            device_id.hex(),
        )

        # Send via reliable transport
        try:
            result = await self.transport.send_reliable(payload=inner_struct, timeout=timeout)
        except Exception as e:
            logger.error("%s Device info request send failed: %s", self.logger_prefix, e)
            # METRIC: tcp_comm_device_info_request_total
            record_metric("tcp_comm_device_info_request_total", outcome="send_failed")
            raise DeviceInfoRequestError("send_failed", str(e))

        if not result.success:
            logger.error("%s Device info request failed: %s", self.logger_prefix, result.reason)
            # METRIC: tcp_comm_device_info_request_total
            record_metric("tcp_comm_device_info_request_total", outcome="send_failed")
            raise DeviceInfoRequestError(result.reason, "Failed to send device info request")

        # Wait for 0x43 response
        wait_start = time.time()
        try:
            while time.time() - wait_start < timeout:
                remaining_timeout = timeout - (time.time() - wait_start)
                if remaining_timeout <= 0:
                    break

                packet = await asyncio.wait_for(
                    self.transport.recv_reliable(), timeout=remaining_timeout
                )

                # Check if this is a 0x43 device info packet
                if packet.packet.packet_type == 0x43:
                    latency_ms = int((time.time() - request_start) * 1000)
                    logger.info(
                        "%s Device info received (0x43) | correlation_id=%s latency_ms=%d",
                        self.logger_prefix,
                        correlation_id,
                        latency_ms,
                    )

                    # Parse device struct
                    device_info = self._parse_device_struct(packet.packet.payload, correlation_id)

                    # METRIC: tcp_comm_device_info_request_total
                    record_metric("tcp_comm_device_info_request_total", outcome="success")

                    return device_info

        except asyncio.TimeoutError:
            logger.warning(
                "%s Device info timeout | correlation_id=%s device_id=%s timeout=%ds",
                self.logger_prefix,
                correlation_id,
                device_id.hex(),
                timeout,
            )
            # METRIC: tcp_comm_device_info_request_total
            record_metric("tcp_comm_device_info_request_total", outcome="timeout")
            return None

    def _parse_0x83_packet(self, packet: CyncPacket, correlation_id: str) -> List[DeviceInfo]:
        """Parse 0x83 status broadcast packet containing multiple 24-byte device structs.

        Implementation based on legacy tcp_packet_handler.py lines 566-600.

        Args:
            packet: Parsed 0x83 packet
            correlation_id: UUID for tracking

        Returns:
            List of parsed DeviceInfo objects
        """
        devices = []
        payload = packet.payload

        # Extract device structs (24 bytes each) from between 0x7e markers
        # Legacy code reference: tcp_packet_handler.py lines 566-600
        offset = 0
        while offset + 24 <= len(payload):
            device_struct = payload[offset : offset + 24]
            try:
                device_info = self._parse_device_struct(device_struct, correlation_id)
                devices.append(device_info)
                offset += 24
            except Exception as e:
                logger.warning(
                    "%s Failed to parse device struct at offset %d: %s",
                    self.logger_prefix,
                    offset,
                    e,
                )
                break

        return devices

    def _parse_device_struct(self, raw_bytes: bytes, correlation_id: str) -> DeviceInfo:
        """Parse 24-byte device struct from 0x83 or 0x43 packet.

        Struct format (from legacy DEVICE_STRUCTS):
        - Bytes 0-3: device_id (4 bytes)
        - Bytes 4-7: capabilities/flags (4 bytes)
        - Bytes 8-11: state data (4 bytes)
        - Bytes 12-23: additional fields (12 bytes)

        Implementation adapted from legacy structs.py and tcp_packet_handler.py.

        Args:
            raw_bytes: 24-byte device struct
            correlation_id: UUID for tracking

        Returns:
            Parsed DeviceInfo object

        Raises:
            DeviceStructParseError: If struct is invalid
        """
        if len(raw_bytes) != 24:
            raise DeviceStructParseError(
                f"Invalid device struct length: {len(raw_bytes)} (expected 24)"
            )

        # Extract fields
        device_id = raw_bytes[0:4]
        capabilities_raw = raw_bytes[4:8]
        state_raw = raw_bytes[8:12]

        # Parse capabilities and state
        # TODO: Adapt detailed parsing logic from legacy structs.py
        # This is a simplified version - full parsing requires legacy struct definitions
        capabilities = int.from_bytes(capabilities_raw, byteorder="big")
        device_type = (capabilities >> 24) & 0xFF  # Example field extraction

        # Parse state fields
        # TODO: Adapt detailed state parsing from legacy code
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

        # Cache parsed device
        self.device_cache[device_id.hex()] = device_info

        # METRIC: tcp_comm_device_struct_parsed_total
        record_metric("tcp_comm_device_struct_parsed_total")

        logger.debug(
            "%s Device struct parsed | correlation_id=%s device_id=%s type=%d",
            self.logger_prefix,
            correlation_id,
            device_id.hex(),
            device_type,
        )

        return device_info

    def _build_device_info_request(self, device_id: bytes) -> bytes:
        """Build 0x73 device info request packet for specific device.

        Args:
            device_id: 4-byte device identifier

        Returns:
            Inner struct bytes for 0x73 packet
        """
        # TODO: Adapt from legacy code for individual device query
        # Placeholder structure - needs validation against real protocol
        # This is a simplified version - full structure requires protocol analysis
        inner_struct = bytes([0x7E]) + device_id + bytes([0x7E])
        return inner_struct

    def set_primary(self, is_primary: bool):
        """Designate this device as primary for mesh operations.

        Only the primary device can request mesh info to prevent duplicate
        MQTT publishes when multiple devices respond.

        Primary device architecture mirrors legacy code pattern from
        server.py lines 494-597.

        Args:
            is_primary: True if this is the primary device
        """
        self.is_primary = is_primary
        logger.info("%s Primary device status: %s", self.logger_prefix, is_primary)
