from builtins import BaseException
from collections.abc import Callable
from typing import Awaitable, ContextManager, TypeVar

_T = TypeVar("_T")
_E = TypeVar("_E", bound=BaseException)

class _MarkDecorator:
    def __call__(self, obj: Callable[..., _T]) -> Callable[..., _T]: ...

class _Mark:
    asyncio: Callable[[Callable[..., Awaitable[_T]]], Callable[..., Awaitable[_T]]]

    def __getattr__(self, name: str) -> _MarkDecorator: ...

mark: _Mark

def fixture(*args: object, **kwargs: object) -> Callable[..., object]: ...

class _RaisesContextManager(ContextManager[_E]):
    def __enter__(self) -> _E: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> bool: ...

def raises(
    expected_exception: type[_E] | tuple[type[_E], ...],
    *args: object,
    **kwargs: object,
) -> _RaisesContextManager[_E]: ...

__all__ = ["fixture", "mark", "raises"]
