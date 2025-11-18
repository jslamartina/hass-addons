#!/usr/bin/env python3
"""Run pyright and normalize diagnostic paths for VS Code problem matchers."""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")
PYRIGHT_PATTERN = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+):(?P<column>\d+)\s+-\s+"
    r"(?P<severity>error|warning|information):\s+"
    r"(?P<message>.+?)(?:\s+\((?P<code>[^)]+)\))?$"
)
LOGGER = logging.getLogger("lint_pyright")


def configure_logger() -> None:
    """Configure module logger once."""
    if LOGGER.handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return ANSI_PATTERN.sub("", text)


def normalize_path(path_text: str, workspace_root: Path) -> str:
    """Normalize a path to be relative to the workspace root."""
    raw_path = Path(path_text)

    if not raw_path.is_absolute():
        raw_path = (workspace_root / raw_path).resolve()
    else:
        raw_path = raw_path.resolve()

    try:
        relative_path = raw_path.relative_to(workspace_root)
        return relative_path.as_posix()
    except ValueError:
        # Fallback to normalized absolute path if outside workspace
        LOGGER.debug(
            "⚠️ Unable to relativize path outside workspace",
            extra={"path": str(raw_path), "workspace_root": str(workspace_root)},
        )
        return raw_path.as_posix()


def transform_path_only_line(line: str, workspace_root: Path) -> str | None:
    """Normalize lines that consist solely of a file path."""
    clean_line = strip_ansi(line.strip())
    if not clean_line or " " in clean_line or ":" in clean_line:
        return None

    candidate = (workspace_root / clean_line).resolve()
    if not candidate.exists():
        LOGGER.debug(
            "⚠️ Skipping non-existent path from pyright output",
            extra={"path_hint": clean_line},
        )
        return None

    return normalize_path(clean_line, workspace_root)


def transform_line(line: str, workspace_root: Path) -> str | None:
    """Transform a pyright diagnostic line, normalizing the file path."""
    clean_line = strip_ansi(line.strip())
    match = PYRIGHT_PATTERN.match(clean_line)
    if not match:
        return transform_path_only_line(line, workspace_root)

    path = normalize_path(match.group("path"), workspace_root)
    message = match.group("message")

    transformed = f"{path}:{match.group('line')}:{match.group('column')} - "
    transformed += f"{match.group('severity')}: {message}"

    if code := match.group("code"):
        transformed += f" ({code})"

    return transformed


def run_pyright(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Execute pyright with the provided argument list."""
    LOGGER.info("→ Running pyright", extra={"pyright_args": args})
    result = subprocess.run(
        ["npx", "pyright", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    LOGGER.info(
        "✓ Pyright finished",
        extra={"exit_code": result.returncode, "diagnostic_bytes": len(result.stdout)},
    )
    return result


def main() -> int:
    configure_logger()
    workspace_root = Path(__file__).resolve().parents[2]
    LOGGER.info(
        "→ lint-pyright start",
        extra={"workspace_root": str(workspace_root)},
    )

    project_config = workspace_root / "python-rebuild-tcp-comm" / "pyrightconfig.json"
    default_targets = ["python-rebuild-tcp-comm/src", "python-rebuild-tcp-comm/tests"]

    if project_config.exists():
        LOGGER.info("→ Using project config", extra={"config": str(project_config)})
        pyright_args: list[str] = ["--project", str(project_config)]
    else:
        LOGGER.warning(
            "⚠️ Project config missing, falling back to direct targets",
            extra={"config": str(project_config)},
        )
        pyright_args = default_targets

    try:
        result = run_pyright(pyright_args)
    except FileNotFoundError:
        LOGGER.error(
            "✗ pyright executable not found",
            extra={"hint": "Install dev dependencies (npm install)."},
        )
        return 1

    combined_output = f"{result.stdout}\n{result.stderr}".strip("\n")
    lines = combined_output.splitlines()

    for line in lines:
        transformed = transform_line(line, workspace_root)
        print(transformed if transformed else strip_ansi(line))

    LOGGER.info(
        "✓ lint-pyright completed",
        extra={"exit_code": result.returncode, "line_count": len(lines)},
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())


