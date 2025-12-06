"""Typed stubs for starlette.responses."""

from pathlib import Path
from typing import Any

class FileResponse:
    """File response."""

    path: str | Path

    def __init__(self, path: str | Path, **kwargs: Any) -> None: ...
