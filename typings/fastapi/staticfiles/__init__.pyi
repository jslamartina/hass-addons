"""Typed stubs for fastapi staticfiles."""

from pathlib import Path
from typing import Any

class StaticFiles:
    """Static files handler."""

    def __init__(self, directory: str | Path, **kwargs: Any) -> None: ...

__all__ = ["StaticFiles"]
