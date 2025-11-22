"""Typed stubs for the subset of uvloop APIs used in this repo."""

from __future__ import annotations

import asyncio

class Loop(asyncio.AbstractEventLoop):
    """uvloop event loop type."""

class EventLoopPolicy(asyncio.AbstractEventLoopPolicy):
    """uvloop event loop policy."""
    def __init__(self) -> None: ...
