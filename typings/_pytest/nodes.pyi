"""Typed stubs for _pytest.nodes."""

class Node:
    """Pytest node."""

    @property
    def name(self) -> str: ...
