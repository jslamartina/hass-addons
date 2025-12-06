"""Typed stubs for _pytest.terminal."""

from typing import Any

class TerminalReporter:
    """Terminal reporter."""

    def write_line(self, msg: str, **kwargs: Any) -> None: ...
