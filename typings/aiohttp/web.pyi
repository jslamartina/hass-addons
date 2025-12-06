from collections.abc import Awaitable, Callable
from typing import Any

class Request:
    def json(self) -> Awaitable[dict[str, Any]]: ...

class Response:
    def __init__(self, **kwargs: Any) -> None: ...

class RouteTableDef:
    def add_post(
        self, path: str, handler: Callable[..., Awaitable[Response]]
    ) -> None: ...
    def add_get(
        self, path: str, handler: Callable[..., Awaitable[Response]]
    ) -> None: ...

class Application:
    router: RouteTableDef

    def __init__(self, **kwargs: Any) -> None: ...

def json_response(data: Any, **kwargs: Any) -> Response: ...

class AppRunner:
    def __init__(self, app: Application, **kwargs: Any) -> None: ...
    async def setup(self) -> None: ...

class TCPSite:
    def __init__(
        self, runner: AppRunner, host: str, port: int, **kwargs: Any
    ) -> None: ...
    async def start(self) -> None: ...

__all__ = [
    "AppRunner",
    "Application",
    "Request",
    "Response",
    "RouteTableDef",
    "TCPSite",
    "json_response",
]
