"""Cync protocol encoder/decoder implementation.

This module implements header parsing, packet encoding, and packet decoding
for the Cync device protocol. Based on Phase 0.5 protocol validation.
"""

from __future__ import annotations

import logging

from protocol.checksum import calculate_checksum_between_markers
from protocol.exceptions import PacketDecodeError
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
            PacketDecodeError: If data is too short to parse header
        """
        if len(data) < 5:
            raise PacketDecodeError("too_short", data)

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
            PacketDecodeError: If payload too short to extract endpoint and msg_id
        """
        if len(payload) < 8:
            raise PacketDecodeError("too_short", payload)

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
            PacketDecodeError: If packet too short or malformed
        """
        logger.debug("Decoding packet: %d bytes", len(data))

        # Parse header
        packet_type, length, _ = CyncProtocol.parse_header(data)

        # Validate packet length matches header
        expected_total = 5 + length
        if len(data) < expected_total:
            raise PacketDecodeError("invalid_length", data)

        # Extract payload
        payload = data[5 : 5 + length]

        # Handle data packets with framing (0x73, 0x83)
        if packet_type in (PACKET_TYPE_DATA_CHANNEL, PACKET_TYPE_STATUS_BROADCAST):
            return CyncProtocol._decode_data_packet(packet_type, length, payload, data)

        # Base packet type for all others
        logger.debug("Decoded base packet: type=0x%02x", packet_type)
        return CyncPacket(packet_type=packet_type, length=length, payload=payload, raw=data)

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
            PacketDecodeError: If 0x7e markers not found or checksum invalid
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
            raise PacketDecodeError("missing_0x7e_markers", raw) from e

        # Extract framed data (between markers)
        if end_marker_idx <= start_marker_idx:
            raise PacketDecodeError("missing_0x7e_markers", packet_bytes)

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

        Packet structure (from Phase 0.5 captures):
        - Header: [0x23, 0x00, 0x00, multiplier, base] (5 bytes)
        - Payload:
          - Byte 0: 0x03 (constant prefix)
          - Bytes 1-5: endpoint (5 bytes)
          - Bytes 6-21: auth_code (16 bytes)
          - Bytes 22-24: suffix (0x00 0x00 0x3c)

        Args:
            endpoint: 5-byte device endpoint
            auth_code: 16-byte authentication code

        Returns:
            Complete 0x23 handshake packet

        Raises:
            ValueError: If endpoint not 5 bytes or auth_code not 16 bytes
        """
        # Validate inputs
        if len(endpoint) != 5:
            raise ValueError(f"Endpoint must be 5 bytes, got {len(endpoint)}")
        if len(auth_code) != 16:
            raise ValueError(f"Auth code must be 16 bytes, got {len(auth_code)}")

        # Build payload: prefix + endpoint + length_indicator + auth_code + suffix
        payload = bytearray([0x03])  # Constant prefix from captures
        payload.extend(endpoint)
        payload.append(0x10)  # Auth code length indicator (16 bytes)
        payload.extend(auth_code)
        payload.extend([0x00, 0x00, 0x3C])  # Suffix from captures

        # Encode header
        header = CyncProtocol.encode_header(0x23, len(payload))

        logger.debug(
            "Encoded handshake: endpoint=%s, auth_code_len=%d",
            endpoint.hex(" "),
            len(auth_code),
        )

        # Combine header + payload
        return header + bytes(payload)

    @staticmethod
    def encode_data_packet(endpoint: bytes, msg_id: bytes, payload: bytes) -> bytes:
        """Encode 0x73 data channel packet with 0x7e framing.

        Packet structure:
        - Header: [0x73, 0x00, 0x00, multiplier, base] (5 bytes)
        - Payload:
          - Bytes 0-4: endpoint (5 bytes)
          - Bytes 5-7: msg_id (3 bytes)
          - Byte 8: 0x7e (start marker)
          - Bytes 9+: inner payload
          - Byte N-1: checksum (calculated)
          - Byte N: 0x7e (end marker)

        Args:
            endpoint: 5-byte device endpoint
            msg_id: 3-byte message ID
            payload: Inner payload bytes (between markers)

        Returns:
            Complete 0x73 data packet with framing and checksum

        Raises:
            ValueError: If endpoint not 5 bytes or msg_id not 3 bytes
        """
        # Validate inputs
        if len(endpoint) != 5:
            raise ValueError(f"Endpoint must be 5 bytes, got {len(endpoint)}")
        if len(msg_id) != 3:
            raise ValueError(f"msg_id must be 3 bytes, got {len(msg_id)}")

        # Build outer payload: endpoint + msg_id
        packet_payload = bytearray()
        packet_payload.extend(endpoint)
        packet_payload.extend(msg_id)

        # Start framing (immediately after msg_id, no separator)
        packet_payload.append(0x7E)  # Start marker
        packet_payload.extend(payload)  # Inner payload

        # Placeholder for checksum (will calculate after full packet built)
        checksum_idx = len(packet_payload)
        packet_payload.append(0x00)  # Placeholder
        packet_payload.append(0x7E)  # End marker

        # Build full packet with header
        header = CyncProtocol.encode_header(0x73, len(packet_payload))
        full_packet = bytearray(header)
        full_packet.extend(packet_payload)

        # Calculate and insert checksum
        from protocol.checksum import insert_checksum_in_place

        insert_checksum_in_place(full_packet, 5 + checksum_idx)

        logger.debug(
            "Encoded data packet: endpoint=%s, msg_id=%s, payload_len=%d",
            endpoint.hex(" "),
            msg_id.hex(" "),
            len(payload),
        )

        return bytes(full_packet)
