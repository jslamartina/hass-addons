"""Unit tests for CodecValidatorPlugin."""

import logging

import pytest

from mitm.interfaces.packet_observer import PacketDirection
from mitm.validation.codec_validator import CodecValidatorPlugin
from tests.fixtures.real_packets import (
    HANDSHAKE_0x23_DEV_TO_CLOUD,
    STATUS_BROADCAST_0x83_DEV_TO_CLOUD,
    TOGGLE_ON_0x73_CLOUD_TO_DEV,
)


class TestCodecValidatorPluginInitialization:
    """Test plugin initialization."""

    def test_initialization(self) -> None:
        """Test that plugin initializes with protocol and empty framers."""
        plugin = CodecValidatorPlugin()

        assert plugin.protocol is not None
        assert plugin.framers == {}


class TestConnectionLifecycle:
    """Test connection establishment and closure."""

    def test_on_connection_established(self) -> None:
        """Test that framer is created when connection established."""
        plugin = CodecValidatorPlugin()
        connection_id = 1

        plugin.on_connection_established(connection_id)

        assert connection_id in plugin.framers
        assert plugin.framers[connection_id] is not None

    def test_on_connection_closed(self) -> None:
        """Test that framer is cleaned up when connection closed."""
        plugin = CodecValidatorPlugin()
        connection_id = 1

        # Establish connection
        plugin.on_connection_established(connection_id)
        assert connection_id in plugin.framers
        # Close connection
        plugin.on_connection_closed(connection_id)
        assert connection_id not in plugin.framers

    def test_on_connection_closed_nonexistent(self) -> None:
        """Test that closing nonexistent connection doesn't crash."""
        plugin = CodecValidatorPlugin()

        # Should not raise exception
        plugin.on_connection_closed(999)


class TestPacketValidation:
    """Test packet decoding and validation."""

    def test_decode_valid_handshake(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test decoding valid handshake packet logs success."""
        plugin = CodecValidatorPlugin()
        connection_id = 1

        with caplog.at_level(logging.INFO):
            plugin.on_packet_received(
                PacketDirection.DEVICE_TO_CLOUD,
                HANDSHAKE_0x23_DEV_TO_CLOUD,
                connection_id,
            )

        # Check that validation success was logged
        assert any("Phase 1a codec validated" in record.message for record in caplog.records)
        # Check that type is logged correctly
        success_record = next(r for r in caplog.records if "Phase 1a codec validated" in r.message)
        assert getattr(success_record, "type", None) == "0x23"

    def test_decode_valid_data_packet(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test decoding valid data packet logs success."""
        plugin = CodecValidatorPlugin()
        connection_id = 2

        with caplog.at_level(logging.INFO):
            plugin.on_packet_received(
                PacketDirection.CLOUD_TO_DEVICE,
                TOGGLE_ON_0x73_CLOUD_TO_DEV,
                connection_id,
            )

        # Check that validation success was logged
        assert any("Phase 1a codec validated" in record.message for record in caplog.records)
        success_record = next(r for r in caplog.records if "Phase 1a codec validated" in r.message)
        assert getattr(success_record, "type", None) == "0x73"

    def test_decode_valid_status_broadcast(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test decoding valid status broadcast packet logs success."""
        plugin = CodecValidatorPlugin()
        connection_id = 3

        with caplog.at_level(logging.INFO):
            plugin.on_packet_received(
                PacketDirection.DEVICE_TO_CLOUD,
                STATUS_BROADCAST_0x83_DEV_TO_CLOUD,
                connection_id,
            )

        # Check that validation success was logged
        assert any("Phase 1a codec validated" in record.message for record in caplog.records)
        success_record = next(r for r in caplog.records if "Phase 1a codec validated" in r.message)
        assert getattr(success_record, "type", None) == "0x83"

    def test_decode_invalid_packet(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test decoding invalid packet logs error without crashing."""
        plugin = CodecValidatorPlugin()
        connection_id = 4

        # Create a packet with valid header but invalid data (missing 0x7e markers for 0x73)
        # Header: type=0x73, length=10
        malformed_data = bytes([0x73, 0x00, 0x00, 0x00, 0x0A]) + bytes(
            10,
        )  # 10 random bytes without proper structure

        with caplog.at_level(logging.ERROR):
            plugin.on_packet_received(
                PacketDirection.CLOUD_TO_DEVICE,
                malformed_data,
                connection_id,
            )

        # Plugin should log error but not crash
        assert any("Phase 1a validation failed" in record.message for record in caplog.records)

    def test_partial_packet_buffering(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that partial packets are buffered until complete."""
        plugin = CodecValidatorPlugin()
        connection_id = 5

        # Split HANDSHAKE packet into two chunks
        packet = HANDSHAKE_0x23_DEV_TO_CLOUD
        chunk1 = packet[:10]  # Header + partial payload
        chunk2 = packet[10:]  # Remaining payload

        with caplog.at_level(logging.INFO):
            # Send first chunk - should buffer, not decode
            plugin.on_packet_received(PacketDirection.DEVICE_TO_CLOUD, chunk1, connection_id)
            assert not any("Phase 1a codec validated" in record.message for record in caplog.records)

            # Send second chunk - should complete and decode
            plugin.on_packet_received(PacketDirection.DEVICE_TO_CLOUD, chunk2, connection_id)
            assert any("Phase 1a codec validated" in record.message for record in caplog.records)


class TestMultiConnectionIsolation:
    """Test that multiple connections maintain separate state."""

    def test_multi_connection_isolation(self) -> None:
        """Test that multiple connections have separate framers."""
        plugin = CodecValidatorPlugin()
        conn1 = 1
        conn2 = 2

        # Establish two connections
        plugin.on_connection_established(conn1)
        plugin.on_connection_established(conn2)

        # Should have separate framers
        assert conn1 in plugin.framers
        assert conn2 in plugin.framers
        assert plugin.framers[conn1] is not plugin.framers[conn2]
        # Send partial packet to conn1
        packet = HANDSHAKE_0x23_DEV_TO_CLOUD
        plugin.on_packet_received(PacketDirection.DEVICE_TO_CLOUD, packet[:10], conn1)

        # conn2's framer should still be empty (not affected by conn1's data)
        assert len(plugin.framers[conn1].buffer) > 0
        assert len(plugin.framers[conn2].buffer) == 0
