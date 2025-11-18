"""Unit tests for MITM proxy observer pattern.

Tests observer registration and notification in MITMProxy.
"""

from unittest.mock import MagicMock, patch

import pytest

from mitm.interfaces.packet_observer import PacketDirection, PacketObserver
from mitm.mitm_proxy import MITMProxy

# Test constants
EXPECTED_OBSERVER_COUNT_MULTIPLE = 3  # Number of observers for multiple registration test


@pytest.fixture
def proxy() -> MITMProxy:
    """Create MITMProxy instance for testing."""
    return MITMProxy(
        listen_port=23779,
        upstream_host="localhost",
        upstream_port=23779,
        use_ssl=False,
    )


@pytest.fixture
def mock_observer() -> MagicMock:
    """Create mock observer for testing."""
    observer = MagicMock(spec=PacketObserver)
    observer.on_packet_received = MagicMock()
    observer.on_connection_established = MagicMock()
    observer.on_connection_closed = MagicMock()
    return observer


def test_proxy_initializes_empty_observers_list(proxy: MITMProxy) -> None:
    """Test proxy initializes with empty observers list."""
    assert hasattr(proxy, "observers")
    assert isinstance(proxy.observers, list)
    assert len(proxy.observers) == 0


def test_register_observer_adds_to_list(proxy: MITMProxy, mock_observer: MagicMock) -> None:
    """Test register_observer adds observer to list."""
    initial_count = len(proxy.observers)

    proxy.register_observer(mock_observer)

    assert len(proxy.observers) == initial_count + 1
    assert mock_observer in proxy.observers


def test_register_multiple_observers(proxy: MITMProxy) -> None:
    """Test multiple observers can be registered."""
    observer1 = MagicMock(spec=PacketObserver)
    observer2 = MagicMock(spec=PacketObserver)
    observer3 = MagicMock(spec=PacketObserver)

    proxy.register_observer(observer1)
    proxy.register_observer(observer2)
    proxy.register_observer(observer3)

    assert len(proxy.observers) == EXPECTED_OBSERVER_COUNT_MULTIPLE
    assert observer1 in proxy.observers
    assert observer2 in proxy.observers
    assert observer3 in proxy.observers


@patch("sys.stderr")
def test_register_observer_prints_confirmation(
    mock_stderr: MagicMock, proxy: MITMProxy, mock_observer: MagicMock
) -> None:
    """Test register_observer prints confirmation message."""
    mock_observer.__class__.__name__ = "TestObserver"

    proxy.register_observer(mock_observer)

    # Check that print was called with observer name
    # Note: print calls write and flush on stderr
    assert mock_stderr.write.called


def test_notify_observers_packet_calls_all_observers(
    proxy: MITMProxy, mock_observer: MagicMock
) -> None:
    """Test _notify_observers_packet calls all registered observers."""
    observer2 = MagicMock(spec=PacketObserver)
    proxy.register_observer(mock_observer)
    proxy.register_observer(observer2)

    data = b"\x73\x00\x00\x00\x1e"
    connection_id = 1

    proxy._notify_observers_packet(PacketDirection.DEVICE_TO_CLOUD, data, connection_id)  # pyright: ignore[reportPrivateUsage]

    # Both observers should be called
    mock_observer.on_packet_received.assert_called_once_with(
        PacketDirection.DEVICE_TO_CLOUD, data, connection_id
    )
    observer2.on_packet_received.assert_called_once_with(
        PacketDirection.DEVICE_TO_CLOUD, data, connection_id
    )


def test_notify_observers_packet_device_to_cloud(
    proxy: MITMProxy, mock_observer: MagicMock
) -> None:
    """Test packet notification with DEVICE_TO_CLOUD direction."""
    proxy.register_observer(mock_observer)
    data = b"\x73\x00\x00\x00\x1e"
    connection_id = 42

    proxy._notify_observers_packet(PacketDirection.DEVICE_TO_CLOUD, data, connection_id)  # pyright: ignore[reportPrivateUsage]

    mock_observer.on_packet_received.assert_called_once_with(
        PacketDirection.DEVICE_TO_CLOUD, data, connection_id
    )


def test_notify_observers_packet_cloud_to_device(
    proxy: MITMProxy, mock_observer: MagicMock
) -> None:
    """Test packet notification with CLOUD_TO_DEVICE direction."""
    proxy.register_observer(mock_observer)
    data = b"\x7b\x00\x00\x00\x0a"
    connection_id = 99

    proxy._notify_observers_packet(PacketDirection.CLOUD_TO_DEVICE, data, connection_id)  # pyright: ignore[reportPrivateUsage]

    mock_observer.on_packet_received.assert_called_once_with(
        PacketDirection.CLOUD_TO_DEVICE, data, connection_id
    )


def test_notify_observers_connection_established(
    proxy: MITMProxy, mock_observer: MagicMock
) -> None:
    """Test _notify_observers_connection_established calls all observers."""
    observer2 = MagicMock(spec=PacketObserver)
    proxy.register_observer(mock_observer)
    proxy.register_observer(observer2)

    connection_id = 1

    proxy._notify_observers_connection_established(connection_id)  # pyright: ignore[reportPrivateUsage]

    mock_observer.on_connection_established.assert_called_once_with(connection_id)
    observer2.on_connection_established.assert_called_once_with(connection_id)


def test_notify_observers_connection_closed(proxy: MITMProxy, mock_observer: MagicMock) -> None:
    """Test _notify_observers_connection_closed calls all observers."""
    observer2 = MagicMock(spec=PacketObserver)
    proxy.register_observer(mock_observer)
    proxy.register_observer(observer2)

    connection_id = 1

    proxy._notify_observers_connection_closed(connection_id)  # pyright: ignore[reportPrivateUsage]

    mock_observer.on_connection_closed.assert_called_once_with(connection_id)
    observer2.on_connection_closed.assert_called_once_with(connection_id)


@patch("sys.stderr")
def test_observer_exception_doesnt_break_proxy(
    _mock_stderr: MagicMock,  # noqa: PT019
    proxy: MITMProxy,
    mock_observer: MagicMock,
) -> None:
    """Test that observer failures don't break proxy operation."""
    # Make first observer raise exception
    mock_observer.on_packet_received.side_effect = Exception("Observer error")

    # Register failing observer and a good one
    observer2 = MagicMock(spec=PacketObserver)
    proxy.register_observer(mock_observer)
    proxy.register_observer(observer2)

    data = b"\x73\x00\x00\x00\x1e"
    connection_id = 1

    # Should not raise - proxy catches exceptions
    proxy._notify_observers_packet(PacketDirection.DEVICE_TO_CLOUD, data, connection_id)  # pyright: ignore[reportPrivateUsage]

    # First observer was called (and failed)
    mock_observer.on_packet_received.assert_called_once()

    # Second observer should still be called despite first one failing
    observer2.on_packet_received.assert_called_once_with(
        PacketDirection.DEVICE_TO_CLOUD, data, connection_id
    )


@patch("sys.stderr")
def test_observer_exception_is_logged(
    mock_stderr: MagicMock, proxy: MITMProxy, mock_observer: MagicMock
) -> None:
    """Test that observer exceptions are logged."""
    error_message = "Test observer error"
    mock_observer.on_packet_received.side_effect = Exception(error_message)
    proxy.register_observer(mock_observer)

    data = b"\x73\x00\x00\x00\x1e"
    connection_id = 1

    proxy._notify_observers_packet(PacketDirection.DEVICE_TO_CLOUD, data, connection_id)  # pyright: ignore[reportPrivateUsage]

    # Error should be printed to stderr
    assert mock_stderr.write.called


def test_no_observers_registered(proxy: MITMProxy) -> None:
    """Test notification methods work with no observers registered."""
    # Should not raise errors
    proxy._notify_observers_packet(PacketDirection.DEVICE_TO_CLOUD, b"\x73", 1)  # pyright: ignore[reportPrivateUsage]
    proxy._notify_observers_connection_established(1)  # pyright: ignore[reportPrivateUsage]
    proxy._notify_observers_connection_closed(1)  # pyright: ignore[reportPrivateUsage]


def test_observer_receives_correct_data(proxy: MITMProxy, mock_observer: MagicMock) -> None:
    """Test observer receives exact data passed to notification."""
    proxy.register_observer(mock_observer)

    # Test with various packet data
    test_cases = [
        (b"\x73\x00\x00\x00\x1e", 1),
        (b"\x7b\x00\x00\x00\x0a", 2),
        (b"\x23\x00\x00\x00\x1a", 3),
        (b"", 4),  # Empty data
        (b"\x00" * 100, 5),  # Larger packet
    ]

    for data, conn_id in test_cases:
        proxy._notify_observers_packet(PacketDirection.DEVICE_TO_CLOUD, data, conn_id)  # pyright: ignore[reportPrivateUsage]

    # Verify all calls received correct data
    assert mock_observer.on_packet_received.call_count == len(test_cases)
    for idx, (data, conn_id) in enumerate(test_cases):
        call_args = mock_observer.on_packet_received.call_args_list[idx]
        assert call_args[0][0] == PacketDirection.DEVICE_TO_CLOUD
        assert call_args[0][1] == data
        assert call_args[0][2] == conn_id


def test_observer_list_order_preserved(proxy: MITMProxy) -> None:
    """Test observers are called in registration order."""
    call_order: list[int] = []

    def create_ordered_observer(order_id: int) -> MagicMock:
        observer = MagicMock(spec=PacketObserver)

        def track_call(*_args: object, **_kwargs: object) -> None:
            call_order.append(order_id)

        observer.on_packet_received = track_call
        return observer

    # Register observers in specific order
    observer1 = create_ordered_observer(1)
    observer2 = create_ordered_observer(2)
    observer3 = create_ordered_observer(3)

    proxy.register_observer(observer1)
    proxy.register_observer(observer2)
    proxy.register_observer(observer3)

    # Notify all observers
    proxy._notify_observers_packet(PacketDirection.DEVICE_TO_CLOUD, b"\x73", 1)  # pyright: ignore[reportPrivateUsage]

    # Verify they were called in registration order
    assert call_order == [1, 2, 3]
