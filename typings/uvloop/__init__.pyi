"""Typed stubs for the subset of uvloop APIs used in this repo."""

import asyncio

class Loop(asyncio.AbstractEventLoop):
    """uvloop event loop type."""

class EventLoopPolicy(asyncio.AbstractEventLoopPolicy):
    """uvloop event loop policy."""

    def __init__(self) -> None: ...

def install() -> None: ...
def new_event_loop() -> Loop: ...
