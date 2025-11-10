"""Unit tests for PacketFramer TCP stream framing."""

from protocol.packet_framer import PacketFramer


class TestPacketFramerBasic:
    """Basic PacketFramer functionality tests."""

    def test_empty_buffer_returns_empty_list(self) -> None:
        """Test that empty buffer returns no packets."""
        framer = PacketFramer()
        packets = framer.feed(b"")
        assert packets == []
        assert len(framer.buffer) == 0

    def test_partial_packet_header_only(self) -> None:
        """Test partial packet buffered (header only, then completion)."""
        framer = PacketFramer()

        # Send header only (5 bytes) - packet type 0x23, length 26
        header = bytes([0x23, 0x00, 0x00, 0x00, 0x1A])
        packets = framer.feed(header)

        # Should buffer but not return packet yet
        assert packets == []
        assert len(framer.buffer) == 5

        # Send remaining 26 bytes
        payload = b"\x03" + b"\x39\x87\xc8\x57\x00" + (b"\x00" * 20)
        packets = framer.feed(payload)

        # Should return complete packet now
        assert len(packets) == 1
        assert len(packets[0]) == 31  # 5 + 26
        assert packets[0][0] == 0x23
        assert len(framer.buffer) == 0

    def test_complete_packet_single_read(self) -> None:
        """Test complete packet in single read."""
        framer = PacketFramer()

        # Complete packet: type 0x23, length 10
        packet = bytes([0x23, 0x00, 0x00, 0x00, 0x0A]) + (b"\x00" * 10)
        packets = framer.feed(packet)

        assert len(packets) == 1
        assert packets[0] == packet
        assert len(framer.buffer) == 0

    def test_multiple_complete_packets_single_read(self) -> None:
        """Test multiple complete packets in single read."""
        framer = PacketFramer()

        # Two complete packets
        packet1 = bytes([0x23, 0x00, 0x00, 0x00, 0x05]) + (b"\x01" * 5)
        packet2 = bytes([0x73, 0x00, 0x00, 0x00, 0x08]) + (b"\x02" * 8)
        combined = packet1 + packet2

        packets = framer.feed(combined)

        assert len(packets) == 2
        assert packets[0] == packet1
        assert packets[1] == packet2
        assert len(framer.buffer) == 0

    def test_exact_boundary_read(self) -> None:
        """Test exact boundary reads (complete packet boundaries)."""
        framer = PacketFramer()

        # Send exactly one complete packet
        packet = bytes([0x73, 0x00, 0x00, 0x00, 0x0C]) + (b"\xaa" * 12)
        packets = framer.feed(packet)

        assert len(packets) == 1
        assert packets[0] == packet
        assert len(framer.buffer) == 0

    def test_large_packet_with_multiplier(self) -> None:
        """Test large packet requiring multiplier > 0."""
        framer = PacketFramer()

        # Packet with multiplier=1, base=0 → 256 bytes payload
        packet = bytes([0x73, 0x00, 0x00, 0x01, 0x00]) + (b"\xff" * 256)
        packets = framer.feed(packet)

        assert len(packets) == 1
        assert len(packets[0]) == 261  # 5 + 256
        assert packets[0][3] == 0x01  # multiplier
        assert packets[0][4] == 0x00  # base
        assert len(framer.buffer) == 0

    def test_zero_length_packet(self) -> None:
        """Test zero-length packet (header only)."""
        framer = PacketFramer()

        # Packet with length 0
        packet = bytes([0x23, 0x00, 0x00, 0x00, 0x00])
        packets = framer.feed(packet)

        assert len(packets) == 1
        assert packets[0] == packet
        assert len(packets[0]) == 5
        assert len(framer.buffer) == 0

    def test_partial_then_multiple_complete(self) -> None:
        """Test partial packet followed by multiple complete packets."""
        framer = PacketFramer()

        # Send header + partial payload
        partial = bytes([0x73, 0x00, 0x00, 0x00, 0x0A]) + (b"\x01" * 5)
        packets = framer.feed(partial)
        assert packets == []
        assert len(framer.buffer) == 10

        # Send rest of first + complete second packet
        rest_and_next = (b"\x02" * 5) + bytes([0x23, 0x00, 0x00, 0x00, 0x03]) + (b"\x03" * 3)
        packets = framer.feed(rest_and_next)

        assert len(packets) == 2
        assert len(packets[0]) == 15  # First packet
        assert len(packets[1]) == 8  # Second packet
        assert len(framer.buffer) == 0


class TestPacketFramerSecurity:
    """Security and edge case tests for PacketFramer."""

    def test_reject_packet_exceeding_max_size(self) -> None:
        """Test MAX_PACKET_SIZE validation (4096 byte limit)."""
        framer = PacketFramer()

        # Malicious packet: claims 5000 bytes (exceeds MAX_PACKET_SIZE=4096)
        # multiplier=19, base=136 → 19*256 + 136 = 5000
        malicious_header = bytes([0x73, 0x00, 0x00, 0x13, 0x88])

        packets = framer.feed(malicious_header)

        # Should discard invalid header and return empty list
        assert packets == []
        # Buffer should be cleared (advanced past bad header)
        assert len(framer.buffer) == 0

    def test_handle_integer_overflow(self) -> None:
        """Test integer overflow protection (multiplier=255, base=255)."""
        framer = PacketFramer()

        # Extreme values: 255*256 + 255 = 65535 bytes
        overflow_header = bytes([0x73, 0x00, 0x00, 0xFF, 0xFF])

        packets = framer.feed(overflow_header)

        # Should reject and clear buffer
        assert packets == []
        assert len(framer.buffer) == 0

    def test_buffer_cleared_on_invalid_length(self) -> None:
        """Test that buffer is cleared after invalid length."""
        framer = PacketFramer()

        # Invalid packet followed by valid packet
        invalid = bytes([0x73, 0x00, 0x00, 0xFF, 0xFF])
        valid = bytes([0x23, 0x00, 0x00, 0x00, 0x05]) + (b"\x00" * 5)

        # Feed invalid - should be discarded
        packets = framer.feed(invalid)
        assert packets == []
        assert len(framer.buffer) == 0

        # Feed valid - should work
        packets = framer.feed(valid)
        assert len(packets) == 1
        assert len(packets[0]) == 10

    def test_survive_malicious_packet_stream(self) -> None:
        """Test that framer doesn't exhaust memory under malicious input."""
        framer = PacketFramer()

        # Send 1000 malicious packets with invalid lengths
        # Some may accidentally form valid-looking headers from leftover bytes
        for i in range(1000):
            malicious = bytes([0x73, 0x00, 0x00, 0xFF, 0xFF, 0x00, 0x01, 0x02])
            _packets = framer.feed(malicious)
            # Don't assert _packets == [] because leftover bytes can form valid headers

        # Key check: Buffer should remain small (not accumulating unbounded data)
        # This proves memory exhaustion attack is prevented
        assert len(framer.buffer) < 1000  # Much smaller than 1000 * 8 = 8000 bytes fed

    def test_large_corrupt_stream_triggers_recovery_limit(self) -> None:
        """Test framer with >500 byte corrupt stream (exceeds recovery attempts)."""
        framer = PacketFramer()

        # Create 600-byte corrupt stream (no valid header)
        # Each byte claims to be start of packet with invalid length
        corrupt_stream = bytes([0xFF] * 600)

        packets = framer.feed(corrupt_stream)

        # After max recovery attempts exceeded, buffer should be cleared
        assert packets == []
        assert len(framer.buffer) == 0  # Buffer cleared after max attempts exceeded

    def test_buffer_state_after_error_recovery(self) -> None:
        """Test buffer state consistency after error recovery."""
        framer = PacketFramer()

        # Send invalid header + valid packet
        invalid = bytes([0x73, 0x00, 0x00, 0x20, 0x00])  # Claims 8192 bytes (too large)
        valid = bytes([0x23, 0x00, 0x00, 0x00, 0x03]) + (b"\xaa" * 3)

        combined = invalid + valid
        packets = framer.feed(combined)

        # Should skip invalid and extract valid
        assert len(packets) == 1
        assert packets[0][0] == 0x23
        assert len(framer.buffer) == 0

    def test_recovery_counter_reset_on_valid_packet(self) -> None:
        """Test that recovery counter resets when valid packet found."""
        framer = PacketFramer()

        # Send corrupt data followed by valid packets alternating
        for i in range(10):
            # Invalid header
            invalid = bytes([0x73, 0x00, 0x00, 0xFF, 0xFF])
            packets = framer.feed(invalid)
            assert packets == []

            # Valid packet - should reset recovery counter
            valid = bytes([0x23, 0x00, 0x00, 0x00, 0x02]) + (b"\x00" * 2)
            packets = framer.feed(valid)
            assert len(packets) == 1

        # Should successfully process all valid packets without hitting limit
        assert len(framer.buffer) == 0


class TestPacketFramerEdgeCases:
    """Edge case tests for PacketFramer."""

    def test_single_byte_feeds(self) -> None:
        """Test feeding one byte at a time."""
        framer = PacketFramer()

        # Complete packet: type 0x23, length 3
        packet = bytes([0x23, 0x00, 0x00, 0x00, 0x03]) + (b"\xaa" * 3)

        # Feed one byte at a time
        for byte in packet:
            packets = framer.feed(bytes([byte]))
            if byte != packet[-1]:  # Not last byte
                assert packets == []

        # After last byte, should return complete packet
        assert len(packets) == 1
        assert packets[0] == packet

    def test_max_valid_packet_size(self) -> None:
        """Test packet at exactly MAX_PACKET_SIZE boundary."""
        framer = PacketFramer()

        # Packet with exactly 4096 bytes payload (at limit)
        # multiplier=16, base=0 → 16*256 + 0 = 4096
        packet = bytes([0x73, 0x00, 0x00, 0x10, 0x00]) + (b"\xff" * 4096)
        packets = framer.feed(packet)

        assert len(packets) == 1
        assert len(packets[0]) == 4101  # 5 + 4096
        assert len(framer.buffer) == 0

    def test_packet_just_over_max_size(self) -> None:
        """Test packet one byte over MAX_PACKET_SIZE is rejected."""
        framer = PacketFramer()

        # Packet with 4097 bytes payload (over limit by 1)
        # multiplier=16, base=1 → 16*256 + 1 = 4097
        malicious_header = bytes([0x73, 0x00, 0x00, 0x10, 0x01])
        packets = framer.feed(malicious_header)

        assert packets == []
        assert len(framer.buffer) == 0  # Rejected and cleared
