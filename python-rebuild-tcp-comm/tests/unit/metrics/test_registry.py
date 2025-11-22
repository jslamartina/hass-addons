"""Unit tests for metrics registry."""

from __future__ import annotations

from metrics import registry

# Test constants
EXPECTED_DEDUP_CACHE_SIZE = 100  # Cache size value for testing


class TestACKMetrics:
    """Tests for ACK/Response metrics."""

    def test_record_ack_received(self) -> None:
        """Test record_ack_received helper."""
        registry.record_ack_received("device1", "0x7B", "matched")
        # Verify metric was incremented (check sample count)
        samples = list(registry.tcp_comm_ack_received_total.collect()[0].samples)
        assert any(
            s.labels == {"device_id": "device1", "ack_type": "0x7B", "outcome": "matched"}
            for s in samples
        )

    def test_record_ack_timeout(self) -> None:
        """Test record_ack_timeout helper."""
        registry.record_ack_timeout("device1")
        samples = list(registry.tcp_comm_ack_timeout_total.collect()[0].samples)
        assert any(s.labels == {"device_id": "device1"} for s in samples)

    def test_record_idempotent_drop(self) -> None:
        """Test record_idempotent_drop helper."""
        registry.record_idempotent_drop("device1")
        samples = list(registry.tcp_comm_idempotent_drop_total.collect()[0].samples)
        assert any(s.labels == {"device_id": "device1"} for s in samples)

    def test_record_retry_attempt(self) -> None:
        """Test record_retry_attempt helper."""
        registry.record_retry_attempt("device1", 1)
        samples = list(registry.tcp_comm_retry_attempts_total.collect()[0].samples)
        assert any(s.labels == {"device_id": "device1", "attempt_number": "1"} for s in samples)

    def test_record_message_abandoned(self) -> None:
        """Test record_message_abandoned helper."""
        registry.record_message_abandoned("device1", "max_retries")
        samples = list(registry.tcp_comm_message_abandoned_total.collect()[0].samples)
        assert any(s.labels == {"device_id": "device1", "reason": "max_retries"} for s in samples)


class TestConnectionMetrics:
    """Tests for connection metrics."""

    def test_record_connection_state(self) -> None:
        """Test record_connection_state helper."""
        registry.record_connection_state("device1", "connected")
        samples = list(registry.tcp_comm_connection_state.collect()[0].samples)
        # Should have 4 states, only "connected" should be 1
        connected_sample = next(
            (s for s in samples if s.labels == {"device_id": "device1", "state": "connected"}),
            None,
        )
        assert connected_sample is not None
        assert connected_sample.value == 1.0
        # Other states should be 0
        disconnected_sample = next(
            (s for s in samples if s.labels == {"device_id": "device1", "state": "disconnected"}),
            None,
        )
        assert disconnected_sample is not None
        assert disconnected_sample.value == 0.0

    def test_record_handshake(self) -> None:
        """Test record_handshake helper."""
        registry.record_handshake("device1", "success")
        samples = list(registry.tcp_comm_handshake_total.collect()[0].samples)
        assert any(s.labels == {"device_id": "device1", "outcome": "success"} for s in samples)

    def test_record_reconnection(self) -> None:
        """Test record_reconnection helper."""
        registry.record_reconnection("device1", "heartbeat_timeout")
        samples = list(registry.tcp_comm_reconnection_total.collect()[0].samples)
        assert any(
            s.labels == {"device_id": "device1", "reason": "heartbeat_timeout"} for s in samples
        )

    def test_record_heartbeat(self) -> None:
        """Test record_heartbeat helper."""
        registry.record_heartbeat("device1", "success")
        samples = list(registry.tcp_comm_heartbeat_total.collect()[0].samples)
        assert any(s.labels == {"device_id": "device1", "outcome": "success"} for s in samples)


class TestDedupCacheMetrics:
    """Tests for deduplication cache metrics."""

    def test_record_dedup_cache_size(self) -> None:
        """Test record_dedup_cache_size helper."""
        registry.record_dedup_cache_size(EXPECTED_DEDUP_CACHE_SIZE)
        samples = list(registry.tcp_comm_dedup_cache_size.collect()[0].samples)
        assert any(s.value == float(EXPECTED_DEDUP_CACHE_SIZE) for s in samples)

    def test_record_dedup_cache_hit(self) -> None:
        """Test record_dedup_cache_hit helper."""
        registry.record_dedup_cache_hit()
        samples = list(registry.tcp_comm_dedup_cache_hits_total.collect()[0].samples)
        assert len(samples) > 0

    def test_record_dedup_cache_eviction(self) -> None:
        """Test record_dedup_cache_eviction helper."""
        registry.record_dedup_cache_eviction()
        samples = list(registry.tcp_comm_dedup_cache_evictions_total.collect()[0].samples)
        assert len(samples) > 0


class TestPerformanceMetrics:
    """Tests for performance metrics."""

    def test_record_state_lock_hold(self) -> None:
        """Test record_state_lock_hold helper."""
        registry.record_state_lock_hold(0.005)
        samples = list(registry.tcp_comm_state_lock_hold_seconds.collect()[0].samples)
        assert len(samples) > 0


class TestDeviceOperationMetrics:
    """Tests for device operation metrics."""

    def test_record_mesh_info_request(self) -> None:
        """Test record_mesh_info_request helper."""
        registry.record_mesh_info_request("device1", "success")
        samples = list(registry.tcp_comm_mesh_info_request_total.collect()[0].samples)
        assert any(s.labels == {"device_id": "device1", "outcome": "success"} for s in samples)

    def test_record_device_info_request(self) -> None:
        """Test record_device_info_request helper."""
        registry.record_device_info_request("device1", "success")
        samples = list(registry.tcp_comm_device_info_request_total.collect()[0].samples)
        assert any(s.labels == {"device_id": "device1", "outcome": "success"} for s in samples)

    def test_record_device_struct_parsed(self) -> None:
        """Test record_device_struct_parsed helper."""
        registry.record_device_struct_parsed("device1")
        samples = list(registry.tcp_comm_device_struct_parsed_total.collect()[0].samples)
        assert any(s.labels == {"device_id": "device1"} for s in samples)

    def test_record_primary_device_violation(self) -> None:
        """Test record_primary_device_violation helper."""
        registry.record_primary_device_violation()
        samples = list(registry.tcp_comm_primary_device_violations_total.collect()[0].samples)
        assert len(samples) > 0
