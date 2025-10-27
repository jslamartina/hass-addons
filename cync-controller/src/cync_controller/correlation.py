"""
Correlation ID tracking for distributed tracing across async operations.

Provides automatic correlation ID generation and propagation using contextvars
for async-safe operation tracking across TCP → Server → MQTT → HA chains.
"""

from __future__ import annotations

import contextvars
import uuid
from collections.abc import Generator
from contextlib import contextmanager

__all__ = [
    "correlation_context",
    "generate_correlation_id",
    "get_correlation_id",
    "set_correlation_id",
]

# Context variable for storing correlation ID (async-safe)
_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id",
    default=None,
)


def generate_correlation_id() -> str:
    """
    Generate a new correlation ID.

    Returns:
        New UUID-based correlation ID (format: UUID4 hex without dashes)
    """
    return uuid.uuid4().hex


def get_correlation_id() -> str | None:
    """
    Get current correlation ID from context.

    Returns:
        Current correlation ID or None if not set
    """
    return _correlation_id.get()


def set_correlation_id(correlation_id: str | None) -> None:
    """
    Set correlation ID in current context.

    Args:
        correlation_id: Correlation ID to set (or None to clear)
    """
    _correlation_id.set(correlation_id)


@contextmanager
def correlation_context(
    correlation_id: str | None = None,
    auto_generate: bool = True,
) -> Generator[str]:
    """
    Context manager for correlation ID scope.

    Automatically generates correlation ID if not provided and auto_generate=True.
    Restores previous correlation ID on exit.

    Args:
        correlation_id: Specific correlation ID to use (None to auto-generate)
        auto_generate: Generate new ID if correlation_id is None

    Yields:
        The correlation ID used in this context

    Example:
        # Auto-generate correlation ID
        with correlation_context() as corr_id:
            logger.info("Processing request")  # Includes auto-generated corr_id

        # Use custom correlation ID (for testing)
        with correlation_context("TEST-123") as corr_id:
            logger.info("Testing critical path")  # Includes "TEST-123"
    """
    # Save previous correlation ID
    previous_id = get_correlation_id()

    # Use provided ID, or generate new one if auto_generate is enabled
    if correlation_id is None and auto_generate:
        correlation_id = generate_correlation_id()

    # Set new correlation ID
    set_correlation_id(correlation_id)

    try:
        yield correlation_id
    finally:
        # Restore previous correlation ID
        set_correlation_id(previous_id)


def ensure_correlation_id() -> str:
    """
    Ensure a correlation ID exists in current context.

    If no correlation ID is set, generates and sets a new one.
    Useful for async task entry points.

    Returns:
        Current or newly generated correlation ID
    """
    current_id = get_correlation_id()
    if current_id is None:
        current_id = generate_correlation_id()
        set_correlation_id(current_id)
    return current_id
