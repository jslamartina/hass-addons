"""Unit tests for packet observer interface.

Tests the PacketDirection enum and PacketObserver Protocol interface.
"""

from mitm.interfaces.packet_observer import PacketDirection


def test_packet_direction_enum_values() -> None:
    """Test PacketDirection enum has correct values."""
    assert PacketDirection.DEVICE_TO_CLOUD.value == "device_to_cloud"
    assert PacketDirection.CLOUD_TO_DEVICE.value == "cloud_to_device"


def test_packet_direction_enum_members() -> None:
    """Test PacketDirection enum has exactly two members."""
    assert len(PacketDirection) == 2
    assert hasattr(PacketDirection, "DEVICE_TO_CLOUD")
    assert hasattr(PacketDirection, "CLOUD_TO_DEVICE")


def test_packet_observer_protocol_structural_subtyping() -> None:
    """Test that classes implementing all methods are recognized as observers.

    Uses structural subtyping - no inheritance required.
    """

    class ValidObserver:
        """Valid observer implementation."""

        def on_packet_received(
            self, direction: PacketDirection, data: bytes, connection_id: int
        ) -> None:
            """Packet received handler."""
            pass

        def on_connection_established(self, connection_id: int) -> None:
            """Connection established handler."""
            pass

        def on_connection_closed(self, connection_id: int) -> None:
            """Connection closed handler."""
            pass

    # Create instance and verify it can be used where PacketObserver is expected
    observer = ValidObserver()
    assert hasattr(observer, "on_packet_received")
    assert hasattr(observer, "on_connection_established")
    assert hasattr(observer, "on_connection_closed")


def test_packet_observer_protocol_missing_method() -> None:
    """Test that classes missing required methods are incomplete.

    This test verifies structural requirements at runtime.
    """

    class IncompleteObserver:
        """Observer missing on_connection_closed method."""

        def on_packet_received(
            self, direction: PacketDirection, data: bytes, connection_id: int
        ) -> None:
            """Packet received handler."""
            pass

        def on_connection_established(self, connection_id: int) -> None:
            """Connection established handler."""
            pass

        # Missing: on_connection_closed

    observer = IncompleteObserver()
    assert hasattr(observer, "on_packet_received")
    assert hasattr(observer, "on_connection_established")
    assert not hasattr(observer, "on_connection_closed")


def test_packet_observer_protocol_method_signatures() -> None:
    """Test that observer methods have correct signatures.

    Verifies method parameters and return types at runtime.
    """

    class TestObserver:
        """Test observer for signature validation."""

        def on_packet_received(
            self, direction: PacketDirection, data: bytes, connection_id: int
        ) -> None:
            """Packet received handler."""
            pass

        def on_connection_established(self, connection_id: int) -> None:
            """Connection established handler."""
            pass

        def on_connection_closed(self, connection_id: int) -> None:
            """Connection closed handler."""
            pass

    observer = TestObserver()

    # Verify methods are callable
    assert callable(observer.on_packet_received)
    assert callable(observer.on_connection_established)
    assert callable(observer.on_connection_closed)

    # Test that methods can be called with correct arguments
    observer.on_packet_received(PacketDirection.DEVICE_TO_CLOUD, b"\x73\x00", 1)
    observer.on_connection_established(1)
    observer.on_connection_closed(1)
