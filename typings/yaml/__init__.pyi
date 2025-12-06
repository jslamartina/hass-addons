"""Typed stubs for the subset of yaml (PyYAML) APIs used in this repo."""

from typing import Any

def dump(data: Any, **kwargs: Any) -> str: ...
def safe_load(stream: Any, **kwargs: Any) -> Any: ...

class YAMLError(Exception):
    """Base YAML error."""

    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
