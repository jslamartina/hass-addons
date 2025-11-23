"""Shared helpers for asserting exceptions in tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

TException = TypeVar("TException", bound=BaseException)


async def expect_async_exception(
    func: Callable[..., Awaitable[Any]],
    exception_type: type[TException],
    *args: Any,
    **kwargs: Any,
) -> TException:
    """Await a coroutine and return the raised exception for inspection."""
    try:
        await func(*args, **kwargs)
    except exception_type as err:
        return err
    raise AssertionError(f"Expected {exception_type.__name__} to be raised")  # pragma: no cover


def expect_exception(
    func: Callable[..., Any],
    exception_type: type[TException],
    *args: Any,
    **kwargs: Any,
) -> TException:
    """Run a callable and return the raised exception for inspection."""
    try:
        func(*args, **kwargs)
    except exception_type as err:
        return err
    raise AssertionError(f"Expected {exception_type.__name__} to be raised")  # pragma: no cover
