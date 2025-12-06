"""Typed stubs for the subset of pydantic APIs used in this repo."""

from typing import Any

class BaseModel:
    """Base Pydantic model."""

    def __init__(self, **kwargs: Any) -> None: ...
    def model_dump(self, **kwargs: Any) -> dict[str, Any]: ...

def computed_field(*args: Any, **kwargs: Any) -> Any: ...
