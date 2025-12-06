"""Typed stubs for the subset of fastapi APIs used in this repo."""

from collections.abc import Callable
from typing import Any

class FastAPI:
    """FastAPI application."""

    def __init__(self, **kwargs: Any) -> None: ...
    def get(self, path: str, **kwargs: Any) -> Callable[[Any], Any]: ...
    def post(self, path: str, **kwargs: Any) -> Callable[[Any], Any]: ...
    def add_middleware(self, middleware: Any, **kwargs: Any) -> None: ...
    def mount(
        self, path: str, app: Any, name: str | None = ..., **kwargs: Any
    ) -> None: ...

class HTTPException(Exception):
    """HTTP exception."""

    status_code: int
    detail: Any

    def __init__(self, status_code: int, detail: Any = ..., **kwargs: Any) -> None: ...

__all__ = ["FastAPI", "HTTPException"]
