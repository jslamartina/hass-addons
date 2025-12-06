"""Typed stubs for python-dotenv."""

from pathlib import Path
from typing import Any

def load_dotenv(dotenv_path: str | Path | None = ..., **kwargs: Any) -> bool: ...
