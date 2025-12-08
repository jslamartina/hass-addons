from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
TException = TypeVar("TException", bound=BaseException)

async def expect_async_exception(
    func: Callable[P, Awaitable[object]],
    exception_type: type[TException],
    *args: P.args,
    **kwargs: P.kwargs,
) -> TException: ...
def expect_exception(
    func: Callable[P, object],
    exception_type: type[TException],
    *args: P.args,
    **kwargs: P.kwargs,
) -> TException: ...
