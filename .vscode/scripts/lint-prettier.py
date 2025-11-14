#!/usr/bin/env python3
"""Transform prettier output for VS Code problem matcher.

Reads prettier output from stdin, transforms it to the format expected by
the VS Code problem matcher: file:line:column: message
"""

import re
import subprocess

# ANSI escape sequence pattern
ANSI_PATTERN = re.compile(r'\x1b\[[0-9;]*m')

# Patterns to filter out
FILTER_PATTERNS = [
    re.compile(r'^panic:'),
    re.compile(r'^Checking formatting'),
    re.compile(r'^\[warn\] Code style'),
]

# Pattern to match [warn] file lines
WARN_PATTERN = re.compile(r'^\[warn\]\s+(.+)$')


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return ANSI_PATTERN.sub('', text)


def should_filter_line(line: str) -> bool:
    """Check if a line should be filtered out."""
    for pattern in FILTER_PATTERNS:
        if pattern.match(line):
            return True
    return False


def transform_prettier_line(line: str) -> str | None:
    """Transform a prettier output line to VS Code problem matcher format.

    Input format: [warn] file

    Output format: file:1:0: Code style issues found. Run npm run format to fix.
    """
    line = strip_ansi(line.strip())

    # Filter out unwanted lines
    if should_filter_line(line):
        return None

    # Match [warn] file pattern
    match = WARN_PATTERN.match(line)
    if not match:
        return None

    file_path = match.group(1)

    # Format: file:1:0: Code style issues found. Run npm run format to fix.
    return f"{file_path}:1:0: Code style issues found. Run npm run format to fix."


def main():
    """Main entry point."""
    # Run prettier
    try:
        result = subprocess.run(
            ['npm', 'run', 'format:check', '--silent'],
            capture_output=True,
            text=True,
            check=False  # Don't fail on formatting errors
        )
        output = result.stdout + result.stderr
    except Exception:
        # If npm fails, return empty output
        return

    # Process each line
    for line in output.splitlines():
        transformed = transform_prettier_line(line)
        if transformed:
            print(transformed)


if __name__ == '__main__':
    main()

