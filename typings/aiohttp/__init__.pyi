"""Typed stubs for the subset of aiohttp APIs used in this repo."""

from typing import Any

class ClientTimeout:
    """HTTP client timeout configuration."""

    def __init__(self, *, total: float | None = ..., **kwargs: Any) -> None: ...

class ClientResponse:
    """HTTP client response."""

    status: int

    async def __aenter__(self) -> ClientResponse: ...
    async def __aexit__(self, *args: object) -> None: ...
    async def json(self) -> Any: ...
    async def text(self) -> str: ...
    def raise_for_status(self) -> None: ...

class ClientSession:
    """HTTP client session."""

    closed: bool

    def __init__(self, **kwargs: Any) -> None: ...
    async def __aenter__(self) -> ClientSession: ...
    async def __aexit__(self, *args: object) -> None: ...
    async def close(self) -> None: ...
    def post(
        self,
        url: str,
        *,
        json: Any = ...,
        timeout: ClientTimeout | None = ...,
        headers: dict[str, str] | None = ...,
        **kwargs: Any,
    ) -> ClientResponse: ...
    def get(
        self,
        url: str,
        *,
        timeout: ClientTimeout | None = ...,
        headers: dict[str, str] | None = ...,
        **kwargs: Any,
    ) -> ClientResponse: ...

class ClientError(Exception):
    """Base HTTP client error."""

    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class RequestInfo:
    """Request information."""

class ClientResponseError(ClientError):
    """HTTP client response error."""

    status: int
    request_info: RequestInfo

    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

__all__ = [
    "ClientError",
    "ClientResponse",
    "ClientResponseError",
    "ClientSession",
    "ClientTimeout",
    "RequestInfo",
]
