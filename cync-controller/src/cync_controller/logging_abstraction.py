"""
Logging abstraction layer for Cync Controller.

Provides dual-format logging (JSON + human-readable) with correlation tracking,
structured context, and configurable output destinations.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "CyncLogger",
    "HumanReadableFormatter",
    "JSONFormatter",
    "get_logger",
]


class JSONFormatter(logging.Formatter):
    """Formatter that outputs structured JSON logs."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Import here to avoid circular dependency
        from cync_controller.correlation import get_correlation_id  # noqa: PLC0415

        log_data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }

        # Add structured extra data if present
        if hasattr(record, "extra_data") and record.extra_data:
            log_data["context"] = record.extra_data

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add stack info if present
        if record.stack_info:
            log_data["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(log_data, default=str)


class HumanReadableFormatter(logging.Formatter):
    """Formatter that outputs human-readable logs with correlation IDs."""

    def __init__(self):
        # Format: timestamp level [module:line] correlation_id > message
        super().__init__(
            fmt="%(asctime)s.%(msecs)03d %(levelname)s [%(module)s:%(lineno)d] %(correlation_id)s > %(message)s",
            datefmt="%m/%d/%y %H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as human-readable text."""
        # Import here to avoid circular dependency
        from cync_controller.correlation import get_correlation_id  # noqa: PLC0415

        # Add correlation ID to record
        correlation_id = get_correlation_id()
        record.correlation_id = f"[{correlation_id[:8]}]" if correlation_id else "[--------]"

        # Add structured extra data to message if present
        formatted = super().format(record)

        if hasattr(record, "extra_data") and record.extra_data:
            context_str = " | ".join(f"{k}={v}" for k, v in record.extra_data.items())
            formatted = f"{formatted} | {context_str}"

        return formatted


class CyncLogger:
    """
    Logger abstraction providing dual-format output (JSON + human-readable).

    Similar to .NET's ILogger, provides structured logging with automatic
    correlation tracking and flexible output configuration.
    """

    def __init__(
        self,
        name: str,
        log_format: str = "both",
        json_file: str | Path | None = None,
        human_output: str | None = "stdout",
    ):
        """
        Initialize CyncLogger.

        Args:
            name: Logger name (typically module name)
            log_format: Output format - "json", "human", or "both"
            json_file: Path for JSON output file (None to disable file output)
            human_output: "stdout", "stderr", or file path for human-readable output
        """
        self.name = name
        self.logger = logging.getLogger(name)
        self.log_format = log_format

        # Don't add handlers if already configured (avoid duplicates)
        if not self.logger.handlers:
            self._configure_handlers(json_file, human_output)

    def _configure_handlers(
        self,
        json_file: str | Path | None,
        human_output: str | None,
    ):
        """Configure log handlers based on format settings."""
        # JSON handler (file output)
        if self.log_format in ("json", "both") and json_file:
            try:
                json_path = Path(json_file)
                json_path.parent.mkdir(parents=True, exist_ok=True)
                json_handler = logging.FileHandler(json_path, mode="a")
                json_handler.setFormatter(JSONFormatter())
                self.logger.addHandler(json_handler)
            except (OSError, PermissionError) as e:
                # Fallback: log to stderr if file creation fails
                print(f"Warning: Failed to create JSON log file {json_file}: {e}", file=sys.stderr)

        # Human-readable handler
        if self.log_format in ("human", "both"):
            if human_output == "stdout":
                human_handler = logging.StreamHandler(sys.stdout)
            elif human_output == "stderr":
                human_handler = logging.StreamHandler(sys.stderr)
            else:
                # File path specified
                try:
                    human_path = Path(human_output)
                    human_path.parent.mkdir(parents=True, exist_ok=True)
                    human_handler = logging.FileHandler(human_path, mode="a")
                except (OSError, PermissionError) as e:
                    print(f"Warning: Failed to create human log file {human_output}: {e}", file=sys.stderr)
                    human_handler = logging.StreamHandler(sys.stdout)

            human_handler.setFormatter(HumanReadableFormatter())
            self.logger.addHandler(human_handler)

    def _log(self, level: int, msg: str, *args, extra: dict[str, Any] | None = None, **kwargs):
        """Internal logging method with structured context support."""
        # Create a LogRecord with extra data attached
        if extra:
            # Use extra parameter properly by creating a custom LogRecord
            kwargs["extra"] = {"extra_data": extra}

        self.logger.log(level, msg, *args, **kwargs)

    def debug(self, msg: str, *args, extra: dict[str, Any] | None = None, **kwargs):
        """Log debug message with optional structured context."""
        self._log(logging.DEBUG, msg, *args, extra=extra, **kwargs)

    def info(self, msg: str, *args, extra: dict[str, Any] | None = None, **kwargs):
        """Log info message with optional structured context."""
        self._log(logging.INFO, msg, *args, extra=extra, **kwargs)

    def warning(self, msg: str, *args, extra: dict[str, Any] | None = None, **kwargs):
        """Log warning message with optional structured context."""
        self._log(logging.WARNING, msg, *args, extra=extra, **kwargs)

    def error(self, msg: str, *args, extra: dict[str, Any] | None = None, **kwargs):
        """Log error message with optional structured context."""
        self._log(logging.ERROR, msg, *args, extra=extra, **kwargs)

    def critical(self, msg: str, *args, extra: dict[str, Any] | None = None, **kwargs):
        """Log critical message with optional structured context."""
        self._log(logging.CRITICAL, msg, *args, extra=extra, **kwargs)

    def exception(self, msg: str, *args, extra: dict[str, Any] | None = None, **kwargs):
        """Log exception with traceback and optional structured context."""
        kwargs["exc_info"] = True
        self._log(logging.ERROR, msg, *args, extra=extra, **kwargs)

    def set_level(self, level: int):
        """Set logging level."""
        self.logger.setLevel(level)

    def add_handler(self, handler: logging.Handler):
        """Add a custom handler."""
        self.logger.addHandler(handler)

    def remove_handler(self, handler: logging.Handler):
        """Remove a handler."""
        self.logger.removeHandler(handler)

    @property
    def handlers(self):
        """Get list of handlers."""
        return self.logger.handlers


def get_logger(
    name: str,
    log_format: str | None = None,
    json_file: str | Path | None = None,
    human_output: str | None = None,
) -> CyncLogger:
    """
    Get or create a CyncLogger instance.

    Args:
        name: Logger name
        log_format: Override default format ("json", "human", or "both")
        json_file: Override default JSON output file
        human_output: Override default human-readable output

    Returns:
        CyncLogger instance
    """
    # Import here to avoid circular dependency at module load time
    from cync_controller.const import (  # noqa: PLC0415
        CYNC_LOG_FORMAT,
        CYNC_LOG_HUMAN_OUTPUT,
        CYNC_LOG_JSON_FILE,
    )

    log_format = log_format or CYNC_LOG_FORMAT
    json_file = json_file or CYNC_LOG_JSON_FILE
    human_output = human_output or CYNC_LOG_HUMAN_OUTPUT

    return CyncLogger(
        name=name,
        log_format=log_format,
        json_file=json_file,
        human_output=human_output,
    )
