"""Typed stubs for the subset of aiomqtt APIs used in this repo."""

from __future__ import annotations

from typing import Any

class Will:
    """MQTT Last Will and Testament message."""
    def __init__(
        self,
        topic: str,
        payload: str | bytes | None = ...,
        qos: int = ...,
        retain: bool = ...,
    ) -> None: ...

class Client:
    """MQTT client."""

    messages: Any  # Async iterator of Message objects
    def __init__(
        self,
        hostname: str | None = ...,
        port: int = ...,
        username: str | None = ...,
        password: str | None = ...,
        identifier: str | None = ...,
        will: Will | None = ...,
        **kwargs: Any,
    ) -> None: ...
    async def __aenter__(self) -> Client: ...
    async def __aexit__(self, *args: Any) -> None: ...
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def publish(self, topic: str, payload: str | bytes | None = ..., **kwargs: Any) -> None: ...
    async def subscribe(self, topic: str, **kwargs: Any) -> None: ...

class MqttError(Exception):
    """Base MQTT error."""

class MqttCodeError(MqttError):
    """MQTT error with code."""

class message:  # noqa: N801
    class Message:
        """MQTT message."""

        topic: str
        payload: bytes | None
        qos: int
        retain: bool
