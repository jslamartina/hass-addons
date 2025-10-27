"""
Performance instrumentation and timing for network operations.

Provides decorators and utilities for automatic timing of operations with
configurable thresholds and on/off toggles.
"""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

__all__ = [
    "measure_time",
    "timed",
    "timed_async",
]

P = ParamSpec("P")
T = TypeVar("T")


def measure_time(start_time: float) -> float:
    """
    Calculate elapsed time in milliseconds.

    Args:
        start_time: Start time from time.perf_counter()

    Returns:
        Elapsed time in milliseconds
    """
    return (time.perf_counter() - start_time) * 1000


def timed(operation_name: str | None = None) -> Callable:
    """
    Decorator for timing synchronous functions with configurable threshold warnings.

    Logs execution time and warns if operation exceeds configured threshold.
    Can be disabled via CYNC_PERF_TRACKING environment variable.

    Args:
        operation_name: Name for the operation (defaults to function name)

    Example:
        @timed("mqtt_publish")
        def publish_message(topic, payload):
            # ... operation ...
            pass
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Import here to avoid circular dependency
            from cync_controller.const import (  # noqa: PLC0415
                CYNC_PERF_THRESHOLD_MS,
                CYNC_PERF_TRACKING,
            )
            from cync_controller.logging_abstraction import get_logger  # noqa: PLC0415

            # Skip timing if performance tracking is disabled
            if not CYNC_PERF_TRACKING:
                return func(*args, **kwargs)

            logger = get_logger(__name__)
            op_name = operation_name or func.__name__

            start_time = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed_ms = measure_time(start_time)
                _log_timing(logger, op_name, elapsed_ms, CYNC_PERF_THRESHOLD_MS)

        return wrapper

    return decorator


def timed_async(operation_name: str | None = None) -> Callable:
    """
    Decorator for timing async functions with configurable threshold warnings.

    Logs execution time and warns if operation exceeds configured threshold.
    Can be disabled via CYNC_PERF_TRACKING environment variable.

    Args:
        operation_name: Name for the operation (defaults to function name)

    Example:
        @timed_async("tcp_read")
        async def read_packet(reader):
            # ... async operation ...
            pass
    """

    def decorator(
        func: Callable[P, asyncio.coroutines.Coroutine[Any, Any, T]],
    ) -> Callable[P, asyncio.coroutines.Coroutine[Any, Any, T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Import here to avoid circular dependency
            from cync_controller.const import (  # noqa: PLC0415
                CYNC_PERF_THRESHOLD_MS,
                CYNC_PERF_TRACKING,
            )
            from cync_controller.logging_abstraction import get_logger  # noqa: PLC0415

            # Skip timing if performance tracking is disabled
            if not CYNC_PERF_TRACKING:
                return await func(*args, **kwargs)

            logger = get_logger(__name__)
            op_name = operation_name or func.__name__

            start_time = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                elapsed_ms = measure_time(start_time)
                _log_timing(logger, op_name, elapsed_ms, CYNC_PERF_THRESHOLD_MS)

        return wrapper

    return decorator


def _log_timing(logger: Any, operation_name: str, elapsed_ms: float, threshold_ms: int):
    """
    Log timing information with appropriate level based on threshold.

    Args:
        logger: Logger instance
        operation_name: Name of the operation
        elapsed_ms: Elapsed time in milliseconds
        threshold_ms: Warning threshold in milliseconds
    """
    if elapsed_ms > threshold_ms:
        logger.warning(
            "⏱️ [%s] completed in %.1fms (threshold: %dms)",
            operation_name,
            elapsed_ms,
            threshold_ms,
            extra={
                "operation": operation_name,
                "duration_ms": round(elapsed_ms, 2),
                "threshold_ms": threshold_ms,
                "exceeded_threshold": True,
            },
        )
    else:
        logger.debug(
            "⏱️ [%s] completed in %.1fms",
            operation_name,
            elapsed_ms,
            extra={
                "operation": operation_name,
                "duration_ms": round(elapsed_ms, 2),
                "threshold_ms": threshold_ms,
                "exceeded_threshold": False,
            },
        )
