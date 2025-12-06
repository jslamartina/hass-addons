"""Typed stubs for _pytest.config."""

from typing import Any

class Config:
    """Pytest configuration."""

    def getoption(self, name: str, default: Any = ..., **kwargs: Any) -> Any: ...
