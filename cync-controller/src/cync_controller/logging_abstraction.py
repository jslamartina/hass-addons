"""Logging abstraction layer for Cync Controller.

Provides dual-format logging (JSON + human-readable) with correlation tracking,
structured context, and configurable output destinations.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast, override

__all__ = [
    "CyncLogger",
    "HumanReadableFormatter",
    "JSONFormatter",
    "get_logger",
]


class JSONFormatter(logging.Formatter):
    """Formatter that outputs structured JSON logs."""

    @override
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Import here to avoid circular dependency
        from cync_controller.correlation import get_correlation_id

        log_data: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }

        extra_data = getattr(record, "extra_data", None)
        if isinstance(extra_data, Mapping) and extra_data:
            context_map = cast("Mapping[str, object]", extra_data)
            log_data["context"] = dict(context_map)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add stack info if present
        if record.stack_info:
            log_data["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(log_data, default=str)


class HumanReadableFormatter(logging.Formatter):
    """Formatter that outputs human-readable logs with correlation IDs."""

    def __init__(self) -> None:
        # Format: timestamp level [module:line] correlation_id > message
        super().__init__(
            fmt="%(asctime)s.%(msecs)03d %(levelname)s [%(module)s:%(lineno)d] %(correlation_id)s > %(message)s",
            datefmt="%m/%d/%y %H:%M:%S",
        )

    @override
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as human-readable text."""
        # Import here to avoid circular dependency
        from cync_controller.correlation import get_correlation_id

        # Add correlation ID to record
        correlation_id = get_correlation_id()
        record.correlation_id = f"[{correlation_id[:8]}]" if correlation_id else "[--------]"

        # Add structured extra data to message if present
        formatted = super().format(record)

        extra_data = getattr(record, "extra_data", None)
        if isinstance(extra_data, Mapping) and extra_data:
            context_map = cast("Mapping[str, object]", extra_data)
            context_str = " | ".join(f"{k}={v}" for k, v in context_map.items())
            formatted = f"{formatted} | {context_str}"

        return formatted


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
        self.name: str = name
        self.logger: logging.Logger = logging.getLogger(name)
        self.log_format: str = log_format

        # Determine initial log level based on CYNC_DEBUG environment variable
        from cync_controller.const import CYNC_DEBUG

        initial_level = logging.DEBUG if CYNC_DEBUG else logging.INFO
        self.logger.setLevel(initial_level)

        # Don't add handlers if already configured (avoid duplicates)
        if not self.logger.handlers:
            self._configure_handlers(json_file, human_output)

    def _configure_handlers(
        self,
        json_file: str | Path | None,
        human_output: str | None,
    ) -> None:
        """Configure log handlers based on format settings."""
        # Use the same level as the logger for handlers
        handler_level = self.logger.level

        # JSON handler (file output)
        if self.log_format in ("json", "both") and json_file:
            try:
                json_path = Path(json_file)
                json_path.parent.mkdir(parents=True, exist_ok=True)
                json_handler = logging.FileHandler(json_path, mode="a")
                json_handler.setFormatter(JSONFormatter())
                json_handler.setLevel(handler_level)
                self.logger.addHandler(json_handler)
            except (OSError, PermissionError) as e:
                # Fallback: log to stderr if file creation fails
                print(f"Warning: Failed to create JSON log file {json_file}: {e}", file=sys.stderr)

        # Human-readable handler
        if self.log_format in ("human", "both"):
            normalized_output = human_output or "stdout"
            if normalized_output == "stdout":
                human_handler = logging.StreamHandler(sys.stdout)
            elif normalized_output == "stderr":
                human_handler = logging.StreamHandler(sys.stderr)
            else:
                # File path specified
                try:
                    human_path = Path(normalized_output)
                    human_path.parent.mkdir(parents=True, exist_ok=True)
                    human_handler = logging.FileHandler(human_path, mode="a")
                except (OSError, PermissionError) as e:
                    print(f"Warning: Failed to create human log file {human_output}: {e}", file=sys.stderr)
                    human_handler = logging.StreamHandler(sys.stdout)

            human_handler.setFormatter(HumanReadableFormatter())
            human_handler.setLevel(handler_level)
            self.logger.addHandler(human_handler)

    def _log(self, level: int, msg: str, *args: object, extra: Mapping[str, object] | None = None) -> None:
        """Internal logging method with structured context support."""
        extra_payload: Mapping[str, object] | None = None
        if extra:
            extra_payload = {"extra_data": dict(extra)}

        self.logger.log(level, msg, *args, extra=extra_payload)

    def debug(self, msg: str, *args: object, extra: Mapping[str, object] | None = None) -> None:
        """Log debug message with optional structured context."""
        self._log(logging.DEBUG, msg, *args, extra=extra)

    def info(self, msg: str, *args: object, extra: Mapping[str, object] | None = None) -> None:
        """Log info message with optional structured context."""
        self._log(logging.INFO, msg, *args, extra=extra)

    def warning(self, msg: str, *args: object, extra: Mapping[str, object] | None = None) -> None:
        """Log warning message with optional structured context."""
        self._log(logging.WARNING, msg, *args, extra=extra)

    def error(self, msg: str, *args: object, extra: Mapping[str, object] | None = None) -> None:
        """Log error message with optional structured context."""
        self._log(logging.ERROR, msg, *args, extra=extra)

    def critical(self, msg: str, *args: object, extra: Mapping[str, object] | None = None) -> None:
        """Log critical message with optional structured context."""
        self._log(logging.CRITICAL, msg, *args, extra=extra)

    def exception(self, msg: str, *args: object, extra: Mapping[str, object] | None = None) -> None:
        """Log exception with traceback and optional structured context."""
        log_extra = {"extra_data": dict(extra)} if extra else None
        self.logger.exception(msg, *args, extra=log_extra)

    def set_level(self, level: int) -> None:
        """Set logging level."""
        self.logger.setLevel(level)

    def add_handler(self, handler: logging.Handler) -> None:
        """Add a custom handler."""
        self.logger.addHandler(handler)

    def remove_handler(self, handler: logging.Handler) -> None:
        """Remove a handler."""
        self.logger.removeHandler(handler)

    @property
    def handlers(self) -> list[logging.Handler]:
        """Get list of handlers."""
        return self.logger.handlers


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
    # Import here to avoid circular dependency at module load time
    from cync_controller.const import (
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
