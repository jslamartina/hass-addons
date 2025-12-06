"""Typed stubs for _pytest.monkeypatch."""

from typing import Any, overload

class MonkeyPatch:
    """Monkey patch fixture."""

    @overload
    def setattr(
        self,
        target: str | object,
        name: str,
        value: Any,
        *,
        raising: bool = ...,
        **kwargs: Any,
    ) -> None: ...
    @overload
    def setattr(
        self, target: str, value: Any, *, raising: bool = ..., **kwargs: Any
    ) -> None: ...
    def setattr(
        self,
        target: str | object,
        name: str | None = None,
        value: Any = ...,
        *,
        raising: bool = ...,
        **kwargs: Any,
    ) -> None: ...
