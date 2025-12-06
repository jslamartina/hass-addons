"""Type stubs for cync_controller.logging_abstraction module."""

from pathlib import Path
from typing import Any

__all__ = [
    "CyncLogger",
    "HumanReadableFormatter",
    "JSONFormatter",
    "get_logger",
]

class JSONFormatter:
    """Formatter that outputs structured JSON logs."""

    def format(self, record: Any) -> str:
        """Format log record as JSON."""

class HumanReadableFormatter:
    """Formatter that outputs human-readable logs with correlation IDs."""

    def format(self, record: Any) -> str:
        """Format log record as human-readable string."""

class CyncLogger:
    """Logger abstraction providing dual-format output (JSON + human-readable).

    Similar to .NET's ILogger, provides structured logging with automatic
    correlation tracking and flexible output configuration.
    """

    def __init__(
        self,
        name: str,
        log_format: str = "both",
        json_file: str | Path | None = None,
        human_output: str | None = "stdout",
    ) -> None:
        """Initialize CyncLogger.

        Args:
            name: Logger name (typically module name)
            log_format: Output format - "json", "human", or "both"
            json_file: Path for JSON output file (None to disable file output)
            human_output: "stdout", "stderr", or file path for human-readable output

        """

    def debug(
        self, msg: str, *args: Any, extra: dict[str, Any] | None = None, **kwargs: Any
    ) -> None:
        """Log debug message with optional structured context."""

    def info(
        self, msg: str, *args: Any, extra: dict[str, Any] | None = None, **kwargs: Any
    ) -> None:
        """Log info message with optional structured context."""

    def warning(
        self, msg: str, *args: Any, extra: dict[str, Any] | None = None, **kwargs: Any
    ) -> None:
        """Log warning message with optional structured context."""

    def error(
        self, msg: str, *args: Any, extra: dict[str, Any] | None = None, **kwargs: Any
    ) -> None:
        """Log error message with optional structured context."""

    def critical(
        self, msg: str, *args: Any, extra: dict[str, Any] | None = None, **kwargs: Any
    ) -> None:
        """Log critical message with optional structured context."""

    def exception(
        self, msg: str, *args: Any, extra: dict[str, Any] | None = None, **kwargs: Any
    ) -> None:
        """Log exception with traceback and optional structured context."""

    def set_level(self, level: int) -> None:
        """Set logging level."""

    def add_handler(self, handler: Any) -> None:
        """Add a custom handler."""

    def remove_handler(self, handler: Any) -> None:
        """Remove a handler."""

    @property
    def handlers(self) -> list[Any]:
        """Get list of handlers."""

def get_logger(
    name: str,
    log_format: str | None = None,
    json_file: str | Path | None = None,
    human_output: str | None = None,
) -> CyncLogger:
    """Get or create a CyncLogger instance.

    Args:
        name: Logger name
        log_format: Override default format ("json", "human", or "both")
        json_file: Override default JSON output file
        human_output: Override default human-readable output

    Returns:
        CyncLogger instance

    """
