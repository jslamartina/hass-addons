"""Typed stubs for _pytest.fixtures."""

from typing import Any

class FixtureRequest:
    """Fixture request."""

    config: Any
    @property
    def node(self) -> Any: ...
