"""Shared helpers for asserting exceptions in tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
TException = TypeVar("TException", bound=BaseException)


async def expect_async_exception(
    func: Callable[P, Awaitable[Any]],
    exception_type: type[TException],
    *args: P.args,
    **kwargs: P.kwargs,
) -> TException:
    """Await a coroutine and return the raised exception for inspection."""
    try:
        await func(*args, **kwargs)
    except exception_type as err:
        return err
    message = f"Expected {exception_type.__name__} to be raised"
    raise AssertionError(message)  # pragma: no cover


def expect_exception(
    func: Callable[P, Any],
    exception_type: type[TException],
    *args: P.args,
    **kwargs: P.kwargs,
) -> TException:
    """Run a callable and return the raised exception for inspection."""
    try:
        func(*args, **kwargs)
    except exception_type as err:
        return err
    message = f"Expected {exception_type.__name__} to be raised"
    raise AssertionError(message)  # pragma: no cover
