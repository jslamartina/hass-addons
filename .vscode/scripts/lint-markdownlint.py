#!/usr/bin/env python3
"""Transform markdownlint output for VS Code problem matcher.

Reads markdownlint output from stdin, transforms it to the format expected by
the VS Code problem matcher: file:line:column:CODE:message
"""

import re
import os
import subprocess

# ANSI escape sequence pattern
ANSI_PATTERN = re.compile(r'\x1b\[[0-9;]*m')

# Pattern to match markdownlint output: file:line or file:line:column followed by CODE/rule message
MARKDOWNLINT_PATTERN = re.compile(r'^([^:]+):(\d+)(?::(\d+))?\s+([A-Z0-9]+)/([^\s]+)\s+(.+)$')

# Pattern to remove [Context:...] suffixes
CONTEXT_PATTERN = re.compile(r'\s+\[Context:.*\]$')


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return ANSI_PATTERN.sub('', text)


def transform_markdownlint_line(line: str, workspace_folder: str) -> str | None:
    """Transform a markdownlint output line to VS Code problem matcher format.

    Input format: file:line CODE/rule message
    or: file:line:column CODE/rule message

    Output format: workspace_folder/file:line:column:CODE:message
    """
    line = strip_ansi(line.strip())

    # Filter lines that match the markdownlint pattern
    if not re.match(r'^[^:]+:\d+(:\d+)?\s+', line):
        return None

    # Match the full pattern
    match = MARKDOWNLINT_PATTERN.match(line)
    if not match:
        return None

    file_path, line_num, column_num, code, rule, message = match.groups()

    # Default column to 0 if not present
    column = column_num if column_num else '0'

    # Remove [Context:...] suffix from message
    message = CONTEXT_PATTERN.sub('', message)

    # Format: file:line:column:CODE:message
    transformed = f"{file_path}:{line_num}:{column}:{code}:{message}"

    # Prepend workspace folder for absolute paths
    if workspace_folder:
        transformed = f"{workspace_folder}/{transformed}"

    return transformed


def main():
    """Main entry point."""
    workspace_folder = os.environ.get('WORKSPACE_FOLDER', '')

    # Run markdownlint
    try:
        result = subprocess.run(
            ['npm', 'run', 'lint:markdown', '--silent'],
            capture_output=True,
            text=True,
            check=False  # Don't fail on linting errors
        )
        output = result.stdout + result.stderr
    except Exception:
        # If npm fails, return empty output
        return

    # Process each line
    for line in output.splitlines():
        transformed = transform_markdownlint_line(line, workspace_folder)
        if transformed:
            print(transformed)


if __name__ == '__main__':
    main()

