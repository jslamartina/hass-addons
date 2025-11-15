"""Cync protocol encoder/decoder implementation.

This module implements header parsing, packet encoding, and packet decoding
for the Cync device protocol. Based on Phase 0.5 protocol validation.
"""

from __future__ import annotations

import logging

from protocol.checksum import calculate_checksum_between_markers, insert_checksum_in_place
from protocol.exceptions import PacketDecodeError
from protocol.packet_types import (
    PACKET_TYPE_DATA_CHANNEL,
    PACKET_TYPE_STATUS_BROADCAST,
    CyncDataPacket,
    CyncPacket,
)

# Protocol constants
ENDPOINT_LENGTH_BYTES = 5
AUTH_CODE_LENGTH_BYTES = 16
MSG_ID_LENGTH_BYTES = 2
PACKET_HEADER_LENGTH = 5  # Magic (2) + Reserved (2) + Type (1)
MIN_PAYLOAD_LENGTH = 7  # Minimum payload length for data packets

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

        Example:
            >>> from protocol.packet_types import PACKET_TYPE_DATA_CHANNEL
            >>> # type=PACKET_TYPE_DATA_CHANNEL (0x73), length=16
            >>> header = bytes([PACKET_TYPE_DATA_CHANNEL, 0x00, 0x00, 0x00, 0x10])
            >>> packet_type, length, reserved = CyncProtocol.parse_header(header)
            >>> packet_type == PACKET_TYPE_DATA_CHANNEL
            True
            >>> length == 16
            True

        """
        if len(data) < PACKET_HEADER_LENGTH:
            error_reason = "too_short"
            raise PacketDecodeError(error_reason, data)

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
            packet_type: Packet type byte (PACKET_TYPE_HANDSHAKE=0x23,
                PACKET_TYPE_DATA_CHANNEL=0x73, etc.)
            length: Payload length in bytes

        Returns:
            5-byte header

        Example:
            >>> from protocol.packet_types import PACKET_TYPE_DATA_CHANNEL
            >>> header = CyncProtocol.encode_header(PACKET_TYPE_DATA_CHANNEL, 16)
            >>> len(header) == 5
            True
            >>> header[0] == PACKET_TYPE_DATA_CHANNEL
            True

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
        """Extract endpoint (bytes[0:5]) and msg_id (bytes[5:7]) from payload.

        Used for 0x73 (data channel) and 0x83 (status broadcast) packets.

        Note: msg_id is 2 bytes. Byte 7 (byte 12 of full packet) is padding (0x00).
        Byte 8 (byte 13 of full packet) is the 0x7e start marker.

        Args:
            payload: Packet payload (header stripped)

        Returns:
            Tuple of (endpoint, msg_id)

        Raises:
            PacketDecodeError: If payload too short to extract endpoint and msg_id

        Example:
            >>> payload = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x13, 0x00])
            >>> endpoint, msg_id = CyncProtocol.extract_endpoint_and_msg_id(payload)
            >>> len(endpoint) == ENDPOINT_LENGTH_BYTES
            True
            >>> len(msg_id) == MSG_ID_LENGTH_BYTES
            True

        """
        if len(payload) < MIN_PAYLOAD_LENGTH:
            error_reason = "too_short"
            raise PacketDecodeError(error_reason, payload)

        endpoint = payload[0:5]  # 5 bytes
        msg_id = payload[5:7]  # 2 bytes (NOT 3 - byte 7 is padding)

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

        Example:
            >>> packet_bytes = bytes([0x73, 0x00, 0x00, 0x00, 0x10] + [0] * 16)
            >>> packet = CyncProtocol.decode_packet(packet_bytes)
            >>> packet.packet_type == 0x73
            True

        """
        logger.debug("Decoding packet", extra={"bytes": len(data)})

        # Parse header
        packet_type, length, _ = CyncProtocol.parse_header(data)

        # Validate packet length matches header
        expected_total = 5 + length
        if len(data) < expected_total:
            error_reason = "invalid_length"
            raise PacketDecodeError(error_reason, data)

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
        packet_type: int,
        length: int,
        payload: bytes,
        raw: bytes,
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

        # Find 0x7e markers within current packet
        # NOTE: Protocol allows msg_id to end with 0x7e, which serves dual purpose
        # as both msg_id's last byte AND the start marker (no separate marker byte)
        # Example: msg_id "09 00 7e" in STATUS_BROADCAST_0x83 packet
        try:
            start_marker_idx = packet_bytes.index(0x7E)
            end_marker_idx = len(packet_bytes) - 1 - packet_bytes[::-1].index(0x7E)
        except ValueError as e:
            error_reason = "missing_0x7e_markers"
            raise PacketDecodeError(error_reason, raw) from e

        # Extract framed data (between markers)
        if end_marker_idx <= start_marker_idx:
            error_reason = "missing_0x7e_markers"
            raise PacketDecodeError(error_reason, packet_bytes)

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
        if len(endpoint) != ENDPOINT_LENGTH_BYTES:
            error_msg = f"Endpoint must be {ENDPOINT_LENGTH_BYTES} bytes, got {len(endpoint)}"
            raise ValueError(error_msg)
        if len(auth_code) != AUTH_CODE_LENGTH_BYTES:
            error_msg = f"Auth code must be {AUTH_CODE_LENGTH_BYTES} bytes, got {len(auth_code)}"
            raise ValueError(error_msg)

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
          - Bytes 5-6: msg_id (2 bytes)
          - Byte 7: padding (0x00)
          - Byte 8: 0x7e (start marker)
          - Bytes 9+: inner payload
          - Byte N-1: checksum (calculated)
          - Byte N: 0x7e (end marker)

        Args:
            endpoint: 5-byte device endpoint
            msg_id: 2-byte message ID
            payload: Inner payload bytes (between markers)

        Returns:
            Complete 0x73 data packet with framing and checksum

        Raises:
            ValueError: If endpoint not 5 bytes or msg_id not 2 bytes

        """
        # Validate inputs
        if len(endpoint) != ENDPOINT_LENGTH_BYTES:
            error_msg = f"Endpoint must be {ENDPOINT_LENGTH_BYTES} bytes, got {len(endpoint)}"
            raise ValueError(error_msg)
        if len(msg_id) != MSG_ID_LENGTH_BYTES:
            error_msg = f"msg_id must be {MSG_ID_LENGTH_BYTES} bytes, got {len(msg_id)}"
            raise ValueError(error_msg)

        # Build outer payload: endpoint + msg_id + padding
        packet_payload = bytearray()
        packet_payload.extend(endpoint)
        packet_payload.extend(msg_id)
        packet_payload.append(0x00)  # Padding byte (always 0x00)

        # Start framing (after padding byte)
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
        insert_checksum_in_place(full_packet, 5 + checksum_idx)

        logger.debug(
            "Encoded data packet: endpoint=%s, msg_id=%s, payload_len=%d",
            endpoint.hex(" "),
            msg_id.hex(" "),
            len(payload),
        )

        return bytes(full_packet)

    @staticmethod
    def encode_heartbeat() -> bytes:
        """Encode 0xD3 heartbeat packet (device to cloud).

        Heartbeat packets are simple keepalive messages with no payload.
        Structure: [0xD3, 0x00, 0x00, 0x00, 0x00] (5 bytes total)

        Returns:
            Complete 0xD3 heartbeat packet (5 bytes)

        """
        return bytes([0xD3, 0x00, 0x00, 0x00, 0x00])

    @staticmethod
    def encode_status_broadcast(endpoint: bytes, msg_id: bytes, payload: bytes) -> bytes:
        """Encode 0x83 status broadcast packet with 0x7e framing.

        Status broadcast packets have similar structure to 0x73 data packets
        but use packet type 0x83 and do NOT include the padding byte.
        Typically sent by devices to report status.

        Packet structure:
        - Header: [0x83, 0x00, 0x00, multiplier, base] (5 bytes)
        - Payload:
          - Bytes 0-4: endpoint (5 bytes)
          - Bytes 5-6: msg_id (2 bytes)
          - Byte 7: 0x7e (start marker, NO padding byte for 0x83)
          - Bytes 8+: inner payload
          - Byte N-1: checksum (calculated)
          - Byte N: 0x7e (end marker)

        Args:
            endpoint: 5-byte device endpoint
            msg_id: 2-byte message ID
            payload: Inner payload bytes (between markers)

        Returns:
            Complete 0x83 status broadcast packet with framing and checksum

        Raises:
            ValueError: If endpoint not 5 bytes or msg_id not 2 bytes

        """
        # Validate inputs
        if len(endpoint) != ENDPOINT_LENGTH_BYTES:
            error_msg = f"Endpoint must be {ENDPOINT_LENGTH_BYTES} bytes, got {len(endpoint)}"
            raise ValueError(error_msg)
        if len(msg_id) != MSG_ID_LENGTH_BYTES:
            error_msg = f"msg_id must be {MSG_ID_LENGTH_BYTES} bytes, got {len(msg_id)}"
            raise ValueError(error_msg)

        # Build outer payload: endpoint + msg_id (NO padding for 0x83)
        packet_payload = bytearray()
        packet_payload.extend(endpoint)
        packet_payload.extend(msg_id)

        # Start framing (immediately after msg_id, no padding byte)
        packet_payload.append(0x7E)  # Start marker
        packet_payload.extend(payload)  # Inner payload

        # Placeholder for checksum (will calculate after full packet built)
        checksum_idx = len(packet_payload)
        packet_payload.append(0x00)  # Placeholder
        packet_payload.append(0x7E)  # End marker

        # Build full packet with header
        header = CyncProtocol.encode_header(0x83, len(packet_payload))
        full_packet = bytearray(header)
        full_packet.extend(packet_payload)

        # Calculate and insert checksum
        insert_checksum_in_place(full_packet, 5 + checksum_idx)

        logger.debug(
            "Encoded status broadcast: endpoint=%s, msg_id=%s, payload_len=%d",
            endpoint.hex(" "),
            msg_id.hex(" "),
            len(payload),
        )

        return bytes(full_packet)
