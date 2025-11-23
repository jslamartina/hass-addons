"""Unit tests for retry policy and timeout configuration."""

# pyright: reportUnknownMemberType=false

from __future__ import annotations

import math


def assert_close(actual: float, expected: float, rel_tol: float = 1e-6) -> None:
    """Assert that two floats are approximately equal."""
    assert math.isclose(actual, expected, rel_tol=rel_tol)


from transport.retry_policy import RetryPolicy, TimeoutConfig

# Test constants
LARGE_TIMEOUT_MS = 100.0
BASE_DELAY = 0.1
MAX_DELAY = 0.2
DEFAULT_P99_MS = 51.0  # Default measured p99 value
HIGH_P99_MS = 500.0  # High p99 value for testing
DEFAULT_MAX_DELAY_SECONDS = 5.0  # Default max delay
CUSTOM_MAX_DELAY_SECONDS = 10.0  # Custom max delay for testing


class TestTimeoutConfig:
    """Tests for TimeoutConfig class."""

    def test_default_timeout_config(self):
        """Test TimeoutConfig with default p99 value."""
        config = TimeoutConfig()
        assert config.measured_p99_ms == DEFAULT_P99_MS
        # Verify calculated timeouts
        assert_close(config.ack_timeout_seconds, 0.1275)  # 51 * 2.5 / 1000
        assert_close(config.handshake_timeout_seconds, 0.31875)  # 0.1275 * 2.5
        assert_close(config.heartbeat_timeout_seconds, 10.0)  # max(0.1275 * 3, 10)
        assert_close(config.cleanup_interval_seconds, 10.0)  # max(10, min(60, 0.1275/3))

    def test_custom_p99_timeout_config(self):
        """Test TimeoutConfig with custom p99 value."""
        config = TimeoutConfig(measured_p99_ms=LARGE_TIMEOUT_MS)
        assert config.measured_p99_ms == LARGE_TIMEOUT_MS
        # Verify calculated timeouts
        assert_close(config.ack_timeout_seconds, 0.25)  # 100 * 2.5 / 1000
        assert_close(config.handshake_timeout_seconds, 0.625)  # 0.25 * 2.5
        assert_close(config.heartbeat_timeout_seconds, 10.0)  # max(0.25 * 3, 10)
        assert_close(config.cleanup_interval_seconds, 10.0)  # max(10, min(60, 0.25/3))

    def test_high_p99_timeout_config(self):
        """Test TimeoutConfig with high p99 value (heartbeat timeout calculation)."""
        config = TimeoutConfig(measured_p99_ms=HIGH_P99_MS)
        assert config.measured_p99_ms == HIGH_P99_MS
        # Verify heartbeat timeout uses max(3x ACK, 10s)
        # ack_timeout = 500.0 * 2.5 / 1000.0 = 1.25s, so max(1.25 * 3, 10) = 10.0
        assert_close(config.heartbeat_timeout_seconds, 10.0)

    def test_cleanup_interval_calculation(self):
        """Test cleanup interval calculation with various p99 values."""
        # Small p99: cleanup interval should be 10s (minimum)
        config_small = TimeoutConfig(measured_p99_ms=10.0)
        assert_close(config_small.cleanup_interval_seconds, 10.0)
        # Medium p99: cleanup interval should be ack_timeout / 3
        config_medium = TimeoutConfig(measured_p99_ms=200.0)
        expected_interval = max(10.0, min(60.0, (200.0 * 2.5 / 1000.0) / 3))
        assert_close(config_medium.cleanup_interval_seconds, expected_interval)
        # Large p99: cleanup interval should be capped at 60s
        # Need p99 such that ack_timeout / 3 >= 60
        # ack_timeout = p99 * 2.5 / 1000, so p99 * 2.5 / 1000 / 3 >= 60
        # p99 >= 60 * 3 * 1000 / 2.5 = 72000ms
        config_large = TimeoutConfig(measured_p99_ms=72000.0)
        assert_close(config_large.cleanup_interval_seconds, 60.0)

    def test_timeout_config_repr(self):
        """Test TimeoutConfig string representation."""
        config = TimeoutConfig(measured_p99_ms=51.0)
        repr_str = repr(config)
        assert "TimeoutConfig" in repr_str
        assert "51.0" in repr_str
        assert "ack=" in repr_str
        assert "handshake=" in repr_str
        assert "heartbeat=" in repr_str
        assert "cleanup_interval=" in repr_str


class TestRetryPolicy:
    """Tests for RetryPolicy class."""

    def test_default_retry_policy(self):
        """Test RetryPolicy with default values."""
        policy = RetryPolicy()
        assert policy.base_delay_seconds == BASE_DELAY
        assert policy.max_delay_seconds == DEFAULT_MAX_DELAY_SECONDS
        assert policy.jitter_factor == BASE_DELAY

    def test_custom_retry_policy(self):
        """Test RetryPolicy with custom values."""
        policy = RetryPolicy(
            base_delay_seconds=0.2,
            max_delay_seconds=CUSTOM_MAX_DELAY_SECONDS,
            jitter_factor=0.2,
        )
        assert policy.base_delay_seconds == MAX_DELAY
        assert policy.max_delay_seconds == CUSTOM_MAX_DELAY_SECONDS
        assert policy.jitter_factor == MAX_DELAY

    def test_get_delay_exponential_backoff(self):
        """Test exponential backoff delay calculation."""
        policy = RetryPolicy(base_delay_seconds=0.1, max_delay_seconds=5.0, jitter_factor=0.0)
        # Without jitter, delays should be: 0.1, 0.2, 0.4, 0.8, 1.6, 3.2, 5.0 (capped)
        assert_close(policy.get_delay(0), BASE_DELAY)  # BASE_DELAY * 2^0
        assert_close(policy.get_delay(1), MAX_DELAY)  # BASE_DELAY * 2^1
        assert_close(policy.get_delay(2), 0.4)  # BASE_DELAY * 2^2
        assert_close(policy.get_delay(3), 0.8)  # BASE_DELAY * 2^3
        assert_close(policy.get_delay(4), 1.6)  # BASE_DELAY * 2^4
        assert_close(policy.get_delay(5), 3.2)  # BASE_DELAY * 2^5
        assert_close(policy.get_delay(6), 5.0)  # Capped at max_delay

    def test_get_delay_with_jitter(self):
        """Test delay calculation includes jitter."""
        policy = RetryPolicy(
            base_delay_seconds=0.1, max_delay_seconds=5.0, jitter_factor=BASE_DELAY
        )
        delay = policy.get_delay(0)
        # Delay should be between base_delay and base_delay * (1 + jitter_factor)
        assert delay >= BASE_DELAY
        assert delay <= BASE_DELAY * 1.1  # BASE_DELAY + (BASE_DELAY * BASE_DELAY)

    def test_get_delay_max_cap(self):
        """Test that delay is capped at max_delay_seconds."""
        policy = RetryPolicy(base_delay_seconds=1.0, max_delay_seconds=2.0, jitter_factor=0.0)
        # Attempt 5 would be 1.0 * 2^5 = 32.0, but should be capped at 2.0
        delay = policy.get_delay(5)
        assert_close(delay, 2.0)

    def test_retry_policy_repr(self):
        """Test RetryPolicy string representation."""
        policy = RetryPolicy()
        repr_str = repr(policy)
        assert "RetryPolicy" in repr_str
        assert "base_delay=" in repr_str
        assert "max_delay=" in repr_str
        assert "jitter_factor=" in repr_str
