"""Summarize lint output counts by linter and rule."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

LINT_FILE = Path("lint_output.txt")
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
RUFF_PATTERN = re.compile(r"^([A-Z]+[0-9]+)\s+(.*)")
PYRIGHT_PATTERN = re.compile(r" - (error|warning): .* \((.*)\)$")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from a line."""
    return ANSI_ESCAPE.sub("", text)


def detect_linter(line: str, current: str) -> str:
    """Determine which linter is currently emitting output."""
    markers = {
        "=== Running Ruff": "Ruff",
        "=== Running type checker": "Pyright",
        "=== Running ShellCheck": "ShellCheck",
        "=== Running ESLint": "ESLint",
        "=== Running markdownlint": "Markdownlint",
        "=== Running Prettier": "Prettier",
    }
    for marker, name in markers.items():
        if marker in line:
            return name
    return current


def parse_lint_lines(
    lines: Iterable[str],
) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """Parse lint lines into counts per linter and rule."""
    counts: defaultdict[str, int] = defaultdict(int)
    categories: defaultdict[str, defaultdict[str, int]] = defaultdict(
        lambda: defaultdict(int),
    )
    current_linter = "Unknown"

    for raw_line in lines:
        line = raw_line.strip()
        current_linter = detect_linter(line, current_linter)
        clean_line = strip_ansi(line)

        if current_linter == "Ruff":
            match = RUFF_PATTERN.search(clean_line)
            if match:
                code = match.group(1)
                categories["Ruff"][code] += 1
                counts["Ruff"] += 1
        elif current_linter == "Pyright":
            match = PYRIGHT_PATTERN.search(clean_line)
            if match:
                rule = match.group(2)
                categories["Pyright"][rule] += 1
                counts["Pyright"] += 1

    return dict(counts), {linter: dict(rules) for linter, rules in categories.items()}


def build_summary(counts: dict[str, int], categories: dict[str, dict[str, int]]) -> str:
    """Create a human-readable summary."""
    lines = ["Error Analysis Summary", "======================"]
    total_errors = 0

    for linter, count in counts.items():
        lines.append(f"\n{linter}: {count} issues")
        total_errors += count
        sorted_rules = sorted(
            categories[linter].items(),
            key=lambda item: item[1],
            reverse=True,
        )
        for rule, rule_count in sorted_rules:
            lines.append(f"  - {rule}: {rule_count}")

    lines.append(f"\nTotal Issues: {total_errors}")
    return "\n".join(lines)


def read_lint_file(path: Path) -> list[str]:
    """Read lint output file, logging if it is missing."""
    if not path.exists():
        logger.error("File %s not found.", path)
        return []
    return path.read_text(encoding="utf-8").splitlines()


def main() -> None:
    """Entry point for CLI usage."""
    lines = read_lint_file(LINT_FILE)
    if not lines:
        return

    counts, categories = parse_lint_lines(lines)
    summary = build_summary(counts, categories)
    logger.info("%s", summary)


if __name__ == "__main__":
    main()
