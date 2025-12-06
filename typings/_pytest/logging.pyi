"""Typed stubs for _pytest.logging."""

from contextlib import AbstractContextManager
from typing import Any

class LogRecord:
    """Log record."""

    message: str
    levelname: str
    levelno: int
    name: str
    type: str | None

class LogCaptureFixture:
    """Log capture fixture."""

    def at_level(
        self, level: int | str, **kwargs: Any
    ) -> AbstractContextManager[Any]: ...
    @property
    def records(self) -> list[LogRecord]: ...
    @property
    def text(self) -> str: ...
