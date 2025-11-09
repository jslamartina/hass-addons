"""Cync protocol encoder/decoder implementation.

This module implements header parsing, packet encoding, and packet decoding
for the Cync device protocol. Based on Phase 0.5 protocol validation.
"""

from __future__ import annotations

import logging

from protocol.checksum import calculate_checksum_between_markers
from protocol.packet_types import (
    PACKET_TYPE_DATA_CHANNEL,
    PACKET_TYPE_STATUS_BROADCAST,
    CyncDataPacket,
    CyncPacket,
)

logger = logging.getLogger(__name__)


class CyncProtocol:
    """Cync protocol encoder/decoder.

    Provides static methods for encoding and decoding Cync protocol packets.
    All methods are stateless - no instance state maintained.
    """

    @staticmethod
    def parse_header(data: bytes) -> tuple[int, int, int]:
        """Parse 5-byte header and return (packet_type, length, reserved).

        Header structure:
        - Byte 0: packet_type (0x23, 0x73, etc.)
        - Bytes 1-2: reserved (usually 0x00)
        - Byte 3: multiplier
        - Byte 4: base_len
        Length = (multiplier * 256) + base_len

        Args:
            data: Packet bytes (must be at least 5 bytes)

        Returns:
            Tuple of (packet_type, length, reserved)

        Raises:
            ValueError: If data is too short to parse header
        """
        if len(data) < 5:
            raise ValueError(f"Packet too short for header: {len(data)} bytes (need 5)")

        packet_type = data[0]
        reserved = (data[1] << 8) | data[2]  # Bytes 1-2 combined
        multiplier = data[3]
        base_len = data[4]
        length = (multiplier * 256) + base_len

        logger.debug(
            "Parsed header: type=0x%02x, length=%d, reserved=0x%04x",
            packet_type,
            length,
            reserved,
        )

        return (packet_type, length, reserved)

    @staticmethod
    def encode_header(packet_type: int, length: int) -> bytes:
        """Encode 5-byte header.

        Calculates multiplier and base from length:
        - multiplier = length // 256
        - base = length % 256
        Returns bytes: [packet_type, 0x00, 0x00, multiplier, base]

        Args:
            packet_type: Packet type byte (0x23, 0x73, etc.)
            length: Payload length in bytes

        Returns:
            5-byte header
        """
        multiplier = length // 256
        base = length % 256

        header = bytes([packet_type, 0x00, 0x00, multiplier, base])

        logger.debug(
            "Encoded header: type=0x%02x, length=%d (mult=%d, base=%d)",
            packet_type,
            length,
            multiplier,
            base,
        )

        return header

    @staticmethod
    def extract_endpoint_and_msg_id(payload: bytes) -> tuple[bytes, bytes]:
        """Extract endpoint (bytes[0:5]) and msg_id (bytes[5:8]) from payload.

        Used for 0x73 (data channel) and 0x83 (status broadcast) packets.

        Args:
            payload: Packet payload (header stripped)

        Returns:
            Tuple of (endpoint, msg_id)

        Raises:
            ValueError: If payload too short to extract endpoint and msg_id
        """
        if len(payload) < 8:
            raise ValueError(
                f"Payload too short for endpoint/msg_id: {len(payload)} bytes (need 8)"
            )

        endpoint = payload[0:5]  # 5 bytes
        msg_id = payload[5:8]  # 3 bytes

        logger.debug(
            "Extracted endpoint=%s, msg_id=%s",
            endpoint.hex(" "),
            msg_id.hex(" "),
        )

        return (endpoint, msg_id)

    @staticmethod
    def decode_packet(data: bytes) -> CyncPacket | CyncDataPacket:
        """Decode any Cync packet type.

        Steps:
        1. Validate minimum length (5 bytes)
        2. Parse header to get type and length
        3. Extract payload (bytes 5+)
        4. For data packets (0x73, 0x83): extract endpoint, msg_id, parse framing
        5. Return appropriate packet dataclass

        Known types (0x23, 0x28, 0x73, 0x83, etc.): Returns specific subclass
        Unknown types: Returns base CyncPacket

        Args:
            data: Complete packet bytes

        Returns:
            CyncPacket or CyncDataPacket instance

        Raises:
            ValueError: If packet too short or malformed
        """
        logger.debug("Decoding packet: %d bytes", len(data))

        # Parse header
        packet_type, length, _ = CyncProtocol.parse_header(data)

        # Validate packet length matches header
        expected_total = 5 + length
        if len(data) < expected_total:
            raise ValueError(
                f"Packet length mismatch: expected {expected_total}, got {len(data)}"
            )

        # Extract payload
        payload = data[5 : 5 + length]

        # Handle data packets with framing (0x73, 0x83)
        if packet_type in (PACKET_TYPE_DATA_CHANNEL, PACKET_TYPE_STATUS_BROADCAST):
            return CyncProtocol._decode_data_packet(packet_type, length, payload, data)

        # Base packet type for all others
        logger.debug("Decoded base packet: type=0x%02x", packet_type)
        return CyncPacket(
            packet_type=packet_type, length=length, payload=payload, raw=data
        )

    @staticmethod
    def _decode_data_packet(
        packet_type: int, length: int, payload: bytes, raw: bytes
    ) -> CyncDataPacket:
        """Decode data packet with 0x7e framing (0x73, 0x83).

        Args:
            packet_type: Packet type (0x73 or 0x83)
            length: Payload length from header
            payload: Packet payload (header stripped)
            raw: Complete packet bytes (may contain trailing data)

        Returns:
            CyncDataPacket instance

        Raises:
            ValueError: If 0x7e markers not found or checksum invalid
        """
        # Extract endpoint and msg_id
        endpoint, msg_id = CyncProtocol.extract_endpoint_and_msg_id(payload)

        # Restrict marker search to declared packet boundaries only
        # This prevents finding markers in trailing data when buffer contains multiple packets
        packet_bytes = raw[: 5 + length]

        # Find 0x7e markers within current packet only
        try:
            start_marker_idx = packet_bytes.index(0x7E)
            end_marker_idx = len(packet_bytes) - 1 - packet_bytes[::-1].index(0x7E)
        except ValueError as e:
            raise ValueError(f"Missing 0x7e frame markers in data packet: {e}") from e

        # Extract framed data (between markers)
        if end_marker_idx <= start_marker_idx:
            raise ValueError("Invalid 0x7e marker positions")

        # Data is between markers, excluding markers and checksum
        data_start = start_marker_idx + 1
        data_end = end_marker_idx - 1  # Exclude checksum byte
        framed_data = packet_bytes[data_start:data_end]

        # Get checksum byte (before trailing 0x7e)
        checksum_byte = packet_bytes[end_marker_idx - 1]

        # Validate checksum
        try:
            calculated = calculate_checksum_between_markers(packet_bytes)
            checksum_valid = calculated == checksum_byte
        except ValueError:
            checksum_valid = False
            calculated = 0

        logger.debug(
            "Decoded data packet: type=0x%02x, checksum=%02x (valid=%s)",
            packet_type,
            checksum_byte,
            checksum_valid,
        )

        return CyncDataPacket(
            packet_type=packet_type,
            length=length,
            payload=payload,
            raw=raw,
            endpoint=endpoint,
            msg_id=msg_id,
            data=framed_data,
            checksum=checksum_byte,
            checksum_valid=checksum_valid,
        )

    @staticmethod
    def encode_handshake(endpoint: bytes, auth_code: bytes) -> bytes:
        """Encode 0x23 handshake packet.

        To be implemented in Step 4.

        Args:
            endpoint: 5-byte device endpoint
            auth_code: Authentication code

        Returns:
            Encoded handshake packet

        Raises:
            NotImplementedError: Step 4 not yet implemented
        """
        raise NotImplementedError("Step 4: Packet encoding not yet implemented")

    @staticmethod
    def encode_data_packet(endpoint: bytes, msg_id: bytes, payload: bytes) -> bytes:
        """Encode 0x73 data channel packet.

        To be implemented in Step 4.

        Args:
            endpoint: 5-byte device endpoint
            msg_id: 3-byte message ID
            payload: Packet payload

        Returns:
            Encoded data packet with 0x7e framing

        Raises:
            NotImplementedError: Step 4 not yet implemented
        """
        raise NotImplementedError("Step 4: Packet encoding not yet implemented")

