"""Typed stubs for the subset of uvicorn APIs used in this repo."""

from typing import Any

class Config:
    """Uvicorn configuration."""

    def __init__(self, app: Any, **kwargs: Any) -> None: ...

class Server:
    """Uvicorn server."""

    def __init__(self, config: Config) -> None: ...
    async def serve(self) -> None: ...
    async def shutdown(self) -> None: ...

__all__ = ["Config", "Server"]
