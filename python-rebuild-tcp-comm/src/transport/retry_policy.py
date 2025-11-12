"""Retry policy and timeout configuration for Phase 1b reliable transport.

This module provides adaptive timeout configuration and exponential backoff
retry logic based on measured ACK latency from Phase 0.5.
"""

from __future__ import annotations

import random


class TimeoutConfig:
    """Adaptive timeout configuration based on measured ACK latency.

    All timeout values are calculated from measured p99 ACK latency using
    formulas, eliminating need for manual updates if Phase 0.5 findings differ.

    Default uses Phase 0.5 measured p99=51ms (0x7B DATA_ACK from 9 samples).
    Note: Small sample size, may need adjustment after Phase 1d testing.
    """

    def __init__(self, measured_p99_ms: float = 51.0):
        """Initialize timeout configuration.

        Args:
            measured_p99_ms: Measured p99 ACK latency from Phase 0.5 (milliseconds)
                           Default: 51ms (Phase 0.5 measured for 0x7B DATA_ACK)
                           Note: Based on small sample (9 pairs), monitor in Phase 1d
        """
        self.measured_p99_ms = measured_p99_ms

        # Calculate all timeouts from measured p99
        self.ack_timeout_seconds = (measured_p99_ms * 2.5) / 1000.0  # 2.5x p99
        self.handshake_timeout_seconds = self.ack_timeout_seconds * 2.5  # 2.5x ACK
        self.heartbeat_timeout_seconds = max(self.ack_timeout_seconds * 3, 10.0)  # max(3x ACK, 10s)
        # Cleanup interval: max(10, min(60, ack_timeout / 3)) seconds
        # This is the interval between cleanup runs, NOT a timeout value
        self.cleanup_interval_seconds = max(10.0, min(60.0, self.ack_timeout_seconds / 3))
        self.send_timeout_seconds = self.ack_timeout_seconds  # Match ACK timeout

    def __repr__(self) -> str:
        """String representation showing all calculated timeouts."""
        return (
            f"TimeoutConfig(measured_p99={self.measured_p99_ms}ms, "
            f"ack={self.ack_timeout_seconds:.3f}s, "
            f"handshake={self.handshake_timeout_seconds:.3f}s, "
            f"heartbeat={self.heartbeat_timeout_seconds:.1f}s, "
            f"cleanup_interval={self.cleanup_interval_seconds:.1f}s)"
        )


class RetryPolicy:
    """Exponential backoff retry policy with jitter.

    Provides retry delay calculation using exponential backoff with random
    jitter to prevent thundering herd problems.
    """

    def __init__(
        self,
        base_delay_seconds: float = 0.1,
        max_delay_seconds: float = 5.0,
        jitter_factor: float = 0.1,
    ):
        """Initialize retry policy.

        Args:
            base_delay_seconds: Base delay for first retry (default: 0.1s)
            max_delay_seconds: Maximum delay cap (default: 5.0s)
            jitter_factor: Jitter as fraction of delay (default: 0.1 = 10%)
        """
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.jitter_factor = jitter_factor

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt.

        Formula: base_delay * (2 ** attempt) + jitter
        Jitter: random value between 0 and delay * jitter_factor

        Args:
            attempt: Retry attempt number (0-indexed, so attempt=0 is first retry)

        Returns:
            Delay in seconds (capped at max_delay_seconds)
        """
        # Exponential backoff: base * 2^attempt
        delay = self.base_delay_seconds * (2**attempt)

        # Cap at maximum delay
        delay = min(delay, self.max_delay_seconds)

        # Add jitter: random value between 0 and delay * jitter_factor
        jitter = random.uniform(0, delay * self.jitter_factor)
        return delay + jitter

    def __repr__(self) -> str:
        """String representation of retry policy."""
        return (
            f"RetryPolicy(base_delay={self.base_delay_seconds}s, "
            f"max_delay={self.max_delay_seconds}s, "
            f"jitter_factor={self.jitter_factor})"
        )
