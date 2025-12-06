from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any, Generic, NoReturn, TypeVar

from . import logging as logging

_T = TypeVar("_T")
_E = TypeVar("_E", bound=BaseException)

class _MarkDecorator:
    def __call__(self, obj: Callable[..., _T]) -> Callable[..., _T]: ...

class _Mark(Generic[_T]):
    asyncio: Callable[[Callable[..., Awaitable[_T]]], Callable[..., Awaitable[_T]]]

    def __getattr__(self, name: str) -> _MarkDecorator: ...

mark: _Mark[Any]

def fixture(*args: object, **kwargs: object) -> Callable[..., object]: ...
def skip(reason: str = "") -> NoReturn: ...
def fail(reason: str = "") -> NoReturn: ...

class _RaisesContextManager(AbstractContextManager[_E]):
    def __enter__(self) -> _E: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...

def raises(
    expected_exception: type[_E] | tuple[type[_E], ...],
    *args: object,
    **kwargs: object,
) -> _RaisesContextManager[_E]: ...

__all__ = ["fail", "fixture", "logging", "mark", "raises", "skip"]
