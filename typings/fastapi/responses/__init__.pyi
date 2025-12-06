"""Typed stubs for fastapi responses."""

from pathlib import Path
from typing import Any

class FileResponse:
    """File response."""

    def __init__(
        self, path: str | Path, filename: str | None = ..., **kwargs: Any
    ) -> None: ...

class HTMLResponse:
    """HTML response."""

    def __init__(self, content: str = ..., **kwargs: Any) -> None: ...

__all__ = ["FileResponse", "HTMLResponse"]
