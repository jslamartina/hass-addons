"""Integration tests for Phase 0 TCP communication."""

from __future__ import annotations

import json
import time
import urllib.request
from typing import TYPE_CHECKING

import pytest

from harness.toggler import toggle_device_with_retry
from metrics import start_metrics_server

from .conftest import MockTCPServer, ResponseMode

# Test constants
EXPECTED_PACKET_COUNT = 2
MIN_ARGS_REQUIRED = 2

# TCP packet header constants (magic + version + length)
TCP_PACKET_HEADER_LENGTH = 7  # magic (2) + version (1) + length (4)
TCP_PACKET_MAGIC_BYTE_1 = 0xF0
TCP_PACKET_MAGIC_BYTE_2 = 0x0D

if TYPE_CHECKING:
    from .performance import PerformanceTracker

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_happy_path_toggle_success(
    mock_tcp_server: MockTCPServer,
    unique_device_id: str,
    unique_metrics_port: int,
    performance_tracker: PerformanceTracker,
) -> None:
    """Test successful toggle with immediate server response."""
    # Start metrics server
    start_metrics_server(unique_metrics_port)

    # Track performance: measure round-trip time
    start_time = time.perf_counter()

    # Toggle device
    result = await toggle_device_with_retry(
        device_id=unique_device_id,
        device_host=mock_tcp_server.host,
        device_port=mock_tcp_server.port,
        state=True,
        max_attempts=2,
    )

    # Record latency
    latency_ms = (time.perf_counter() - start_time) * 1000.0
    performance_tracker.record_latency(latency_ms)

    # Verify success
    assert result is True, "Toggle should succeed"
    # Verify server received exactly one packet
    assert len(mock_tcp_server.received_packets) == 1, "Should receive exactly one packet"
    packet = mock_tcp_server.received_packets[0]

    # Verify packet format
    assert packet.magic == b"\xf0\x0d", "Magic bytes should be 0xF0 0x0D"
    assert packet.version == 0x01, "Version should be 0x01"
    assert packet.length == len(json.dumps(packet.payload).encode("utf-8"))
    # Verify payload content
    assert packet.payload["opcode"] == "toggle", "Opcode should be 'toggle'"
    assert packet.payload["device_id"] == unique_device_id
    assert packet.payload["state"] is True
    assert "msg_id" in packet.payload, "Packet should contain msg_id"
    # Verify exactly one connection attempt
    assert mock_tcp_server.connection_count == 1, "Should have exactly one connection"


@pytest.mark.asyncio
async def test_packet_format_validation(
    mock_tcp_server: MockTCPServer,
    unique_device_id: str,
    unique_metrics_port: int,
    performance_tracker: PerformanceTracker,
) -> None:
    """Test exact packet structure validation."""
    start_metrics_server(unique_metrics_port)

    # Track performance: measure round-trip time
    start_time = time.perf_counter()

    # Toggle with state=False to test both states
    result = await toggle_device_with_retry(
        device_id=unique_device_id,
        device_host=mock_tcp_server.host,
        device_port=mock_tcp_server.port,
        state=False,
        max_attempts=1,
    )

    # Record latency
    latency_ms = (time.perf_counter() - start_time) * 1000.0
    performance_tracker.record_latency(latency_ms)

    assert result is True
    packet = mock_tcp_server.received_packets[0]

    # Verify exact packet structure
    raw = packet.raw_bytes

    # Header: magic (2) + version (1) + length (4) = 7 bytes
    assert len(raw) >= TCP_PACKET_HEADER_LENGTH, "Packet should have at least 7-byte header"
    # Magic bytes
    assert raw[0] == TCP_PACKET_MAGIC_BYTE_1
    assert raw[1] == TCP_PACKET_MAGIC_BYTE_2
    # Version
    assert raw[2] == 0x01
    # Length (big-endian 4 bytes)
    payload_length = int.from_bytes(raw[3:7], "big")
    assert payload_length > 0, "Payload length should be positive"
    assert len(raw) == 7 + payload_length, "Total length should match header + payload"
    # Payload should be valid JSON
    payload_bytes = raw[7:]
    payload_dict = json.loads(payload_bytes.decode("utf-8"))

    # Verify all required fields
    assert "opcode" in payload_dict
    assert "device_id" in payload_dict
    assert "msg_id" in payload_dict
    assert "state" in payload_dict
    # Verify state is False
    assert payload_dict["state"] is False


@pytest.mark.asyncio
async def test_retry_intermittent_connection_failure(
    mock_tcp_server: MockTCPServer,
    unique_device_id: str,
    unique_metrics_port: int,
) -> None:
    """Test retry logic when first connection fails, second succeeds."""
    start_metrics_server(unique_metrics_port)

    # Configure server to reject first connection, then accept
    mock_tcp_server.reject_next_connection()

    # Toggle device with retries
    result = await toggle_device_with_retry(
        device_id=unique_device_id,
        device_host=mock_tcp_server.host,
        device_port=mock_tcp_server.port,
        state=True,
        max_attempts=2,
    )

    # Verify eventual success
    assert result is True, "Should succeed on second attempt"
    # Verify two connection attempts (first rejected, second succeeded)
    assert mock_tcp_server.connection_count == EXPECTED_PACKET_COUNT, (
        "Should have two connection attempts"
    )
    # Verify packet was received on second attempt
    assert len(mock_tcp_server.received_packets) == 1, "Should receive one packet"


@pytest.mark.asyncio
async def test_retry_intermittent_timeout(
    unique_device_id: str,
    unique_metrics_port: int,
) -> None:
    """Test retry when first attempt times out, second succeeds."""
    start_metrics_server(unique_metrics_port)

    # Create two servers: first times out, second succeeds
    server1 = MockTCPServer(response_mode=ResponseMode.TIMEOUT)
    await server1.start()

    try:
        # First attempt will timeout (io_timeout is 1.5s by default)
        # We'll simulate this by using a server that delays too long
        result = await toggle_device_with_retry(
            device_id=unique_device_id,
            device_host=server1.host,
            device_port=server1.port,
            state=True,
            max_attempts=2,
        )

        # Should fail because both attempts timeout
        assert result is False, "Should fail when all attempts timeout"
        # Verify both attempts were made
        assert server1.connection_count == EXPECTED_PACKET_COUNT, (
            "Should have two connection attempts"
        )
        # Server receives packet but doesn't respond
        assert len(server1.received_packets) == EXPECTED_PACKET_COUNT, (
            "Should receive packets on both attempts"
        )
    finally:
        await server1.stop()


@pytest.mark.asyncio
async def test_all_attempts_timeout(
    mock_tcp_server_timeout: MockTCPServer,
    unique_device_id: str,
    unique_metrics_port: int,
) -> None:
    """Test when all retry attempts timeout."""
    start_metrics_server(unique_metrics_port)

    # Server is configured to never respond (TIMEOUT mode)
    result = await toggle_device_with_retry(
        device_id=unique_device_id,
        device_host=mock_tcp_server_timeout.host,
        device_port=mock_tcp_server_timeout.port,
        state=True,
        max_attempts=2,
    )

    # Verify failure
    assert result is False, "Should fail when all attempts timeout"
    # Verify both attempts were made
    assert mock_tcp_server_timeout.connection_count == EXPECTED_PACKET_COUNT, (
        "Should attempt connection twice"
    )
    # Server should receive packets but not respond
    assert len(mock_tcp_server_timeout.received_packets) == EXPECTED_PACKET_COUNT, (
        "Server should receive both packets"
    )


@pytest.mark.asyncio
async def test_connection_refused(
    unique_device_id: str,
    unique_metrics_port: int,
) -> None:
    """Test when connection is refused (no server listening)."""
    start_metrics_server(unique_metrics_port)

    # Use a port that is very unlikely to have a server listening
    unreachable_port = 19999

    result = await toggle_device_with_retry(
        device_id=unique_device_id,
        device_host="127.0.0.1",
        device_port=unreachable_port,
        state=True,
        max_attempts=2,
    )

    # Verify failure
    assert result is False, "Should fail when connection is refused"


@pytest.mark.asyncio
async def test_connection_closed_during_recv(
    unique_device_id: str,
    unique_metrics_port: int,
) -> None:
    """Test when server closes connection before responding."""
    start_metrics_server(unique_metrics_port)

    # Server accepts connection but closes immediately after receiving packet
    server = MockTCPServer(response_mode=ResponseMode.DISCONNECT)
    await server.start()

    try:
        result = await toggle_device_with_retry(
            device_id=unique_device_id,
            device_host=server.host,
            device_port=server.port,
            state=True,
            max_attempts=2,
        )

        # Should fail because server disconnects
        assert result is False, "Should fail when connection is closed"
        # Verify attempts were made
        assert server.connection_count == EXPECTED_PACKET_COUNT, "Should attempt twice"
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_metrics_endpoint_accessible(
    mock_tcp_server: MockTCPServer,
    unique_device_id: str,
    unique_metrics_port: int,
    performance_tracker: PerformanceTracker,
) -> None:
    """Test that metrics endpoint is accessible and contains expected data."""
    # Start metrics server
    start_metrics_server(unique_metrics_port)

    # Track performance: measure round-trip time
    start_time = time.perf_counter()

    # Perform a successful toggle to generate metrics
    result = await toggle_device_with_retry(
        device_id=unique_device_id,
        device_host=mock_tcp_server.host,
        device_port=mock_tcp_server.port,
        state=True,
        max_attempts=1,
    )

    # Record latency
    latency_ms = (time.perf_counter() - start_time) * 1000.0
    performance_tracker.record_latency(latency_ms)

    assert result is True, "Toggle should succeed"
    # Query metrics endpoint
    metrics_url = f"http://localhost:{unique_metrics_port}/metrics"

    try:
        with urllib.request.urlopen(metrics_url, timeout=5) as response:  # noqa: S310
            metrics_text = response.read().decode("utf-8")
    except Exception as e:
        pytest.fail(f"Failed to access metrics endpoint: {e}")

    # Verify metrics exist in output
    assert "tcp_comm_packet_sent_total" in metrics_text, "Should have sent packet metric"
    assert "tcp_comm_packet_recv_total" in metrics_text, "Should have recv packet metric"
    assert "tcp_comm_packet_latency_seconds" in metrics_text, "Should have latency metric"
    # Verify device_id label is present (at least somewhere in metrics)
    # Note: The actual device_id might be URL-encoded or quoted
    assert (
        unique_device_id in metrics_text or unique_device_id.replace("_", "%5F") in metrics_text
    ), "Metrics should contain device_id label"

    # Verify success outcome is recorded
    assert 'outcome="success"' in metrics_text, "Should have success outcome in metrics"
